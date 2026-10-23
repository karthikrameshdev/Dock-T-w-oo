"""Notes application attached drawer with two-page design, search, state persistence, created/modified dates, and drag-and-drop reordering."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
import time
from typing import Dict, List, Optional

from PySide6.QtCore import QMimeData, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dock_twoo.config import DockConfig, get_default_config_dir
from dock_twoo.ui.apps.base_app import BaseAttachedApp
from dock_twoo.ui.theme import create_app_font, get_scrollbar_style, get_theme_tokens


def format_note_date(ts: float) -> str:
    """Format timestamp into a clean, human-readable date string."""
    if not ts:
        return "Unknown"
    try:
        dt = datetime.datetime.fromtimestamp(ts)
        now = datetime.datetime.now()
        time_part = dt.strftime("%I:%M %p").lstrip("0")
        if dt.date() == now.date():
            return f"Today, {time_part}"
        elif (now.date() - dt.date()).days == 1:
            return f"Yesterday, {time_part}"
        elif dt.year == now.year:
            return f"{dt.strftime('%b %d')}, {time_part}"
        else:
            return f"{dt.strftime('%b %d, %Y')}, {time_part}"
    except Exception:
        return ""


class NotesToast(QWidget):
    """Subtle floating notification inside the drawer."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._message = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, message: str, duration_ms: int = 2000) -> None:
        self._message = message
        self.adjustSize()
        if self.parentWidget():
            parent_w = self.parentWidget().width()
            parent_h = self.parentWidget().height()
            self.move((parent_w - self.width()) // 2, parent_h - 55)
        self.show()
        self.raise_()
        self._timer.start(duration_ms)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        rect = self.rect().adjusted(1, 1, -1, -1)
        path.addRoundedRect(rect, 8, 8)

        painter.fillPath(path, QColor(24, 24, 27, 230))
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.drawPath(path)

        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._message)
        painter.end()

    def sizeHint(self) -> QSize:
        return QSize(max(170, len(self._message) * 9 + 28), 32)


class NoteCard(QFrame):
    """Clean card representing a note in the list view with title, preview, created & modified dates, and drag-and-drop."""

    clicked = Signal(str)  # note_id
    delete_requested = Signal(str, str)  # note_id, title

    def __init__(
        self,
        note_id: str,
        title: str,
        body: str,
        updated_at: float,
        config: DockConfig,
        created_at: Optional[float] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.note_id = note_id
        self.title = title
        self.body = body
        self.updated_at = updated_at
        self.created_at = created_at if created_at else updated_at
        self.config = config
        self._drag_start_pos: Optional[QPoint] = None

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_ui()

    def _setup_ui(self) -> None:
        tokens = get_theme_tokens(self.config)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Header row: Drag Grip + Title + Delete button
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)

        self.grip_lbl = QLabel("⋮⋮", self)
        self.grip_lbl.setFont(create_app_font(self.config, size=11, weight=QFont.Weight.Bold))
        self.grip_lbl.setStyleSheet("color: rgba(142, 142, 159, 0.4); background: transparent; border: none;")
        self.grip_lbl.setToolTip("Drag to reorder notes")
        self.grip_lbl.setFixedWidth(14)
        header_row.addWidget(self.grip_lbl)

        self.title_lbl = QLabel(self.title or "Untitled Note", self)
        self.title_lbl.setFont(create_app_font(self.config, size=13, weight=QFont.Weight.DemiBold))
        self.title_lbl.setStyleSheet(f"color: {tokens.text_primary}; background: transparent; border: none;")
        header_row.addWidget(self.title_lbl, 1)

        # Delete button on the card
        self.delete_btn = QPushButton("✕", self)
        self.delete_btn.setFixedSize(22, 22)
        self.delete_btn.setToolTip("Delete note")
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.06);
                color: {tokens.text_secondary};
                border: none;
                border-radius: 11px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: rgba(239, 68, 68, 0.85);
                color: #ffffff;
            }}
        """)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        header_row.addWidget(self.delete_btn)
        layout.addLayout(header_row)

        # Content Snippet / Preview
        first_line = (self.body or "").strip().replace("\n", " ")
        snippet = first_line[:110] + ("..." if len(first_line) > 110 else "")
        if not snippet:
            snippet = "No additional text"
        self.snippet_lbl = QLabel(snippet, self)
        self.snippet_lbl.setFont(create_app_font(self.config, size=11, weight=QFont.Weight.Normal))
        self.snippet_lbl.setStyleSheet(f"color: {tokens.text_secondary}; background: transparent; border: none;")
        self.snippet_lbl.setWordWrap(True)
        layout.addWidget(self.snippet_lbl)

        # Timestamps footer: Both Created Date and Modified Date
        dates_layout = QVBoxLayout()
        dates_layout.setContentsMargins(0, 3, 0, 0)
        dates_layout.setSpacing(2)

        self.created_lbl = QLabel(f"Created: {format_note_date(self.created_at)}", self)
        self.created_lbl.setFont(create_app_font(self.config, size=10, weight=QFont.Weight.Normal))
        self.created_lbl.setStyleSheet("color: rgba(142, 142, 159, 0.65); background: transparent; border: none;")
        dates_layout.addWidget(self.created_lbl)

        self.modified_lbl = QLabel(f"Modified: {format_note_date(self.updated_at)}", self)
        self.modified_lbl.setFont(create_app_font(self.config, size=10, weight=QFont.Weight.Normal))
        self.modified_lbl.setStyleSheet("color: rgba(142, 142, 159, 0.65); background: transparent; border: none;")
        dates_layout.addWidget(self.modified_lbl)

        layout.addLayout(dates_layout)

        self._apply_frame_style(False)

    def _apply_frame_style(self, hover: bool) -> None:
        tokens = get_theme_tokens(self.config)
        is_dark = self.config.get_effective_theme() == "dark"
        if hover:
            bg = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.06)"
            border = tokens.accent_color
            grip_color = tokens.accent_color
        else:
            bg = "rgba(255, 255, 255, 0.04)" if is_dark else "rgba(0, 0, 0, 0.03)"
            border = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.08)"
            grip_color = "rgba(142, 142, 159, 0.4)"

        self.setStyleSheet(f"""
            NoteCard {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 9px;
            }}
        """)
        if hasattr(self, "grip_lbl"):
            self.grip_lbl.setStyleSheet(f"color: {grip_color}; background: transparent; border: none;")

    def enterEvent(self, event) -> None:
        self._apply_frame_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._apply_frame_style(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            if (event.pos() - self._drag_start_pos).manhattanLength() >= 8:
                self._start_drag(event)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            if (event.pos() - self._drag_start_pos).manhattanLength() < 8:
                self.clicked.emit(self.note_id)
            self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _start_drag(self, event) -> None:
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self.note_id)
        mime.setData("application/x-note-id", self.note_id.encode("utf-8"))
        drag.setMimeData(mime)

        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())
        self.setStyleSheet("""
            NoteCard {
                opacity: 0.35;
                border: 1px dashed #3b82f6;
                border-radius: 9px;
            }
        """)
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start_pos = None
        self._apply_frame_style(False)

    def _on_delete_clicked(self) -> None:
        self.delete_requested.emit(self.note_id, self.title)


class CardsContainerWidget(QWidget):
    """Container holding note cards with drag-and-drop reordering and drop indicator."""

    order_changed = Signal(list)  # list of note_ids

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._drop_indicator_index: Optional[int] = None

        self._indicator_line = QFrame(self)
        self._indicator_line.setFrameShape(QFrame.Shape.HLine)
        self._indicator_line.setFixedHeight(3)
        self._indicator_line.setStyleSheet("background-color: #3b82f6; border-radius: 1px; border: none;")
        self._indicator_line.hide()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat("application/x-note-id"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat("application/x-note-id"):
            pos = event.position().toPoint()
            target_idx = self._get_drop_index(pos.y())
            self._drop_indicator_index = target_idx
            self._update_indicator_line(target_idx)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._indicator_line.hide()
        self._drop_indicator_index = None
        event.accept()

    def dropEvent(self, event) -> None:
        self._indicator_line.hide()
        if event.mimeData().hasFormat("application/x-note-id"):
            dragged_id = event.mimeData().text()
            target_idx = self._drop_indicator_index if self._drop_indicator_index is not None else -1
            layout = self.layout()
            if layout is None:
                event.ignore()
                return

            cards: List[NoteCard] = []
            for i in range(layout.count()):
                w = layout.itemAt(i).widget()
                if isinstance(w, NoteCard):
                    cards.append(w)

            dragged_card = next((c for c in cards if c.note_id == dragged_id), None)
            if dragged_card:
                cards.remove(dragged_card)
                if target_idx < 0 or target_idx >= len(cards):
                    cards.append(dragged_card)
                else:
                    cards.insert(target_idx, dragged_card)

                for c in cards:
                    layout.removeWidget(c)
                for i, c in enumerate(cards):
                    layout.insertWidget(i, c)

                new_order = [c.note_id for c in cards]
                self.order_changed.emit(new_order)

            event.acceptProposedAction()
        else:
            event.ignore()

    def _get_drop_index(self, y: int) -> int:
        layout = self.layout()
        if layout is None:
            return 0
        idx = 0
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if isinstance(w, NoteCard):
                mid_y = w.y() + w.height() // 2
                if y > mid_y:
                    idx = idx + 1
        return idx

    def _update_indicator_line(self, index: int) -> None:
        layout = self.layout()
        if layout is None:
            self._indicator_line.hide()
            return
        cards = [layout.itemAt(i).widget() for i in range(layout.count()) if isinstance(layout.itemAt(i).widget(), NoteCard)]
        if not cards:
            self._indicator_line.hide()
            return
        if index <= 0:
            top_y = cards[0].y() - 4
        elif index >= len(cards):
            top_y = cards[-1].y() + cards[-1].height() + 2
        else:
            top_y = cards[index].y() - 4
        self._indicator_line.setGeometry(8, max(0, top_y), max(10, self.width() - 16), 3)
        self._indicator_line.show()
        self._indicator_line.raise_()


class NotesAppWidget(BaseAttachedApp):
    """Notes attached drawer with a dedicated two-page design, drag-and-drop reordering, dates, and state persistence."""

    def __init__(self, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__("notes", "Notes", config, parent)
        self.notes_dir = get_default_config_dir() / "notes"
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.notes_dir / ".state.json"

        self._current_note_id: Optional[str] = None
        self._note_cards: Dict[str, NoteCard] = {}

        self._init_notes_ui()
        self._load_notes()
        self._restore_state()

    def _read_state_dict(self) -> dict:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _write_state_dict(self, state: dict) -> None:
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def _has_welcome_been_created(self) -> bool:
        state = self._read_state_dict()
        return bool(state.get("welcome_created", False))

    def _mark_welcome_created(self) -> None:
        state = self._read_state_dict()
        state["welcome_created"] = True
        self._write_state_dict(state)

    def _get_manual_order(self) -> List[str]:
        state = self._read_state_dict()
        return list(state.get("manual_order", []))

    def _save_manual_order(self, order: List[str]) -> None:
        state = self._read_state_dict()
        state["manual_order"] = order
        self._write_state_dict(state)

    def _promote_note_to_top(self, note_id: str) -> None:
        manual_order = self._get_manual_order()
        if note_id in manual_order:
            manual_order.remove(note_id)
        manual_order.insert(0, note_id)
        self._save_manual_order(manual_order)

    def _init_notes_ui(self) -> None:
        tokens = get_theme_tokens(self.config)

        # Connect base header back button
        self.back_btn.clicked.connect(self._go_back_to_list)

        # Main Stacked Widget: Page 0 = List View, Page 1 = Editor View
        self.stack = QStackedWidget(self)
        self.content_layout.addWidget(self.stack)

        # ----------------------------------------------------
        # Page 0: List View
        # ----------------------------------------------------
        self.list_page = QWidget(self)
        list_layout = QVBoxLayout(self.list_page)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(10)

        # Top Toolbar: Search + "+ New"
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.search_input = QLineEdit(self.list_page)
        self.search_input.setPlaceholderText("Search notes by title or content...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(0, 0, 0, 0.25);
                color: {tokens.text_primary};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {tokens.accent_color};
            }}
        """)
        self.search_input.textChanged.connect(self._filter_notes)
        toolbar.addWidget(self.search_input, 1)

        self.new_btn = QPushButton("+ New", self.list_page)
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {tokens.accent_color};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """)
        self.new_btn.clicked.connect(self._create_new_note)
        toolbar.addWidget(self.new_btn)
        list_layout.addLayout(toolbar)

        # Scrollable Cards Area
        self.scroll_area = QScrollArea(self.list_page)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            {get_scrollbar_style(tokens)}
        """)

        self.cards_container = CardsContainerWidget()
        self.cards_container.order_changed.connect(self._on_cards_reordered)
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Empty state label
        self.empty_label = QLabel("No notes yet.\nClick + New to create your first note.", self.cards_container)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setFont(create_app_font(self.config, size=12, weight=QFont.Weight.Normal))
        self.empty_label.setStyleSheet(f"color: {tokens.text_secondary}; padding: 40px 20px; background: transparent;")
        self.empty_label.setVisible(False)
        self.cards_layout.addWidget(self.empty_label)

        self.scroll_area.setWidget(self.cards_container)
        list_layout.addWidget(self.scroll_area, 1)

        self.stack.addWidget(self.list_page)

        # ----------------------------------------------------
        # Page 1: Editor View
        # ----------------------------------------------------
        self.editor_page = QWidget(self)
        editor_layout = QVBoxLayout(self.editor_page)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)

        # Editor Meta Header: Last saved info & Delete button
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(8)

        self.editor_meta_lbl = QLabel("", self.editor_page)
        self.editor_meta_lbl.setFont(create_app_font(self.config, size=10, weight=QFont.Weight.Normal))
        self.editor_meta_lbl.setStyleSheet("color: rgba(142, 142, 159, 0.7); background: transparent;")
        meta_row.addWidget(self.editor_meta_lbl, 1)

        self.editor_delete_btn = QPushButton("🗑 Delete Note", self.editor_page)
        self.editor_delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.editor_delete_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(239, 68, 68, 0.12);
                color: #ef4444;
                border: 1px solid rgba(239, 68, 68, 0.25);
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(239, 68, 68, 0.25);
                color: #f87171;
            }}
        """)
        self.editor_delete_btn.clicked.connect(self._on_editor_delete_clicked)
        meta_row.addWidget(self.editor_delete_btn)
        editor_layout.addLayout(meta_row)

        # Title Input
        self.title_input = QLineEdit(self.editor_page)
        self.title_input.setPlaceholderText("Note Title...")
        self.title_input.setFont(create_app_font(self.config, size=17, weight=QFont.Weight.DemiBold))
        self.title_input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {tokens.text_primary};
                border: none;
                padding: 2px 0;
            }}
        """)
        self.title_input.textChanged.connect(self._on_content_changed)
        editor_layout.addWidget(self.title_input)

        # Subtle divider below title
        divider = QFrame(self.editor_page)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); border: none;")
        editor_layout.addWidget(divider)

        # Body Editor
        self.body_edit = QTextEdit(self.editor_page)
        self.body_edit.setPlaceholderText("Write your note here in markdown or plain text...")
        self.body_edit.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(0, 0, 0, 0.2);
                color: {tokens.text_primary};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 10px;
                font-size: 13px;
                line-height: 1.45;
            }}
        """)
        self.body_edit.textChanged.connect(self._on_content_changed)
        editor_layout.addWidget(self.body_edit, 1)

        self.stack.addWidget(self.editor_page)

        # Floating Toast notification
        self.toast = NotesToast(self)

    def _on_cards_reordered(self, new_order: List[str]) -> None:
        """Handle user manually reordering notes via drag and drop."""
        self._save_manual_order(new_order)
        self.toast.show_message("Notes reordered")

    def _load_notes(self) -> None:
        """Load all notes from disk, apply ordering, and populate list cards."""
        # Clear existing cards
        for card in list(self._note_cards.values()):
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self._note_cards.clear()

        # Gather note JSON files
        json_files = [f for f in self.notes_dir.glob("*.json") if not f.name.startswith(".")]

        # Only create initial welcome note once on first launch if not yet created
        if not json_files and not self._has_welcome_been_created():
            self._create_welcome_note()
            json_files = [f for f in self.notes_dir.glob("*.json") if not f.name.startswith(".")]

        notes_data: List[dict] = []
        for file in json_files:
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data["id"] = file.stem
                    updated_at = data.get("updated_at", file.stat().st_mtime)
                    created_at = data.get("created_at")
                    if not created_at:
                        try:
                            created_at = file.stat().st_birthtime
                        except AttributeError:
                            created_at = file.stat().st_ctime
                    data["created_at"] = created_at
                    data["updated_at"] = updated_at
                    notes_data.append(data)
            except Exception:
                pass

        # Sort:
        # If manual order exists, follow it. Notes not in manual order (newly created/edited) go to top by updated_at descending.
        manual_order = self._get_manual_order()
        if manual_order:
            order_map = {nid: idx for idx, nid in enumerate(manual_order)}
            notes_data.sort(
                key=lambda x: (
                    0 if x["id"] in order_map else -1,
                    order_map.get(x["id"], -x.get("updated_at", 0)),
                )
            )
        else:
            notes_data.sort(key=lambda x: x.get("updated_at", 0), reverse=True)

        for n in notes_data:
            card = NoteCard(
                note_id=n["id"],
                title=n.get("title", "Untitled Note"),
                body=n.get("body", ""),
                updated_at=n.get("updated_at", 0),
                config=self.config,
                created_at=n.get("created_at"),
                parent=self.cards_container,
            )
            card.clicked.connect(self._open_note)
            card.delete_requested.connect(self._delete_note)
            self._note_cards[n["id"]] = card
            self.cards_layout.addWidget(card)

        # Re-apply search filter if user already typed in search bar
        self._filter_notes(self.search_input.text())

    def _create_welcome_note(self) -> None:
        welcome_file = self.notes_dir / "welcome.json"
        now = time.time()
        data = {
            "title": "Welcome to Notes",
            "body": "Welcome to your persistent secondary dock companion!\n\n- Write fast thoughts and meeting notes\n- Drag and drop notes to reorder anytime\n- View create & modified dates on every card\n- Auto-saves instantly as you type\n- Attached drawer stays beside your dock.",
            "created_at": now,
            "updated_at": now,
        }
        with open(welcome_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self._mark_welcome_created()

    def _save_state(self, page_index: int, note_id: Optional[str]) -> None:
        """Persist current view state so reopen preserves exact position."""
        state = self._read_state_dict()
        state["last_page"] = page_index
        state["last_note_id"] = note_id
        self._write_state_dict(state)

    def _restore_state(self) -> None:
        """Restore user's previous state (Page 0 List vs Page 1 Editor) on launch."""
        state = self._read_state_dict()
        last_page = state.get("last_page", 0)
        last_note_id = state.get("last_note_id")
        if last_page == 1 and last_note_id:
            note_file = self.notes_dir / f"{last_note_id}.json"
            if note_file.exists():
                self._open_note(last_note_id, save_state=False)
                return
        self._go_back_to_list(save_state=False)

    def _create_new_note(self) -> None:
        """Create a new note, place it at top, and immediately open it in the editor."""
        note_id = f"note_{int(time.time())}"
        now = time.time()
        data = {
            "title": "Untitled Note",
            "body": "",
            "created_at": now,
            "updated_at": now,
        }
        file_path = self.notes_dir / f"{note_id}.json"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._promote_note_to_top(note_id)
        except Exception:
            pass

        self._open_note(note_id)
        self.title_input.setFocus()
        self.title_input.selectAll()
        self.toast.show_message("New note created")

    def _open_note(self, note_id: str, save_state: bool = True) -> None:
        """Open the selected note in Page 1 (Editor View)."""
        file_path = self.notes_dir / f"{note_id}.json"
        if not file_path.exists():
            self._go_back_to_list()
            return

        self._current_note_id = note_id
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.title_input.blockSignals(True)
            self.body_edit.blockSignals(True)
            self.title_input.setText(data.get("title", ""))
            self.body_edit.setText(data.get("body", ""))
            self.title_input.blockSignals(False)
            self.body_edit.blockSignals(False)
            self._update_editor_meta(
                data.get("created_at", data.get("updated_at", 0)),
                data.get("updated_at", 0),
                data.get("body", ""),
            )
        except Exception:
            pass

        # Switch to Editor View and show Header Back Button
        self.stack.setCurrentIndex(1)
        self.back_btn.setVisible(True)
        self.title_label.setText("Note")

        if save_state:
            self._save_state(page_index=1, note_id=note_id)

    def _go_back_to_list(self, save_state: bool = True) -> None:
        """Return to Page 0 (List View) and hide Header Back Button."""
        self._current_note_id = None
        self.stack.setCurrentIndex(0)
        self.back_btn.setVisible(False)
        self.title_label.setText("Notes")

        # Reload list cards so latest updates, dates, and order are fresh
        self._load_notes()

        if save_state:
            self._save_state(page_index=0, note_id=None)

    def _update_editor_meta(self, created_at: float, updated_at: float, body: str) -> None:
        words = len((body or "").split())
        created_str = format_note_date(created_at) if created_at else ""
        updated_str = format_note_date(updated_at) if updated_at else ""
        meta_parts = []
        if created_str:
            meta_parts.append(f"Created {created_str}")
        if updated_str:
            meta_parts.append(f"Modified {updated_str}")
        meta_parts.append(f"{words} {'word' if words == 1 else 'words'}")
        self.editor_meta_lbl.setText(" • ".join(meta_parts))

    def _on_content_changed(self) -> None:
        """Auto-save note content as user types and promote note to top."""
        if not self._current_note_id:
            return
        file_path = self.notes_dir / f"{self._current_note_id}.json"
        title = self.title_input.text().strip()
        body = self.body_edit.toPlainText()
        now = time.time()

        created_at = now
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    prev = json.load(f)
                    created_at = prev.get("created_at", now)
            except Exception:
                pass

        data = {
            "title": title or "Untitled Note",
            "body": body,
            "created_at": created_at,
            "updated_at": now,
        }
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._update_editor_meta(created_at, now, body)
            self._promote_note_to_top(self._current_note_id)
        except Exception:
            pass

    def _on_editor_delete_clicked(self) -> None:
        """Handle user clicking the delete button inside the editor."""
        if self._current_note_id:
            self._delete_note(self._current_note_id, self.title_input.text())

    def _delete_note(self, note_id: str, title: str = "") -> None:
        """Delete a note with user confirmation."""
        display_title = title or "this note"
        reply = QMessageBox.question(
            self,
            "Delete Note",
            f"Are you sure you want to delete '{display_title}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Mark welcome created so deleting welcome note never resurrects it
        self._mark_welcome_created()

        # Remove from manual order
        manual_order = self._get_manual_order()
        if note_id in manual_order:
            manual_order.remove(note_id)
            self._save_manual_order(manual_order)

        file_path = self.notes_dir / f"{note_id}.json"
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass

        # If currently open in editor, navigate back to list view
        if self._current_note_id == note_id:
            self._go_back_to_list()
        else:
            self._load_notes()

        self.toast.show_message("Note deleted")

    def _filter_notes(self, query: str) -> None:
        """Filter notes list in real-time matching both title and note content."""
        q = query.strip().lower()
        visible_count = 0
        for card in self._note_cards.values():
            if not q:
                card.setVisible(True)
                visible_count += 1
            else:
                matches_title = q in card.title.lower()
                matches_body = q in card.body.lower()
                is_match = matches_title or matches_body
                card.setVisible(is_match)
                if is_match:
                    visible_count += 1

        if visible_count == 0:
            if q:
                self.empty_label.setText(f"No notes matching \"{query}\"")
            else:
                self.empty_label.setText("No notes yet.\nClick + New to create your first note.")
            self.empty_label.setVisible(True)
        else:
            self.empty_label.setVisible(False)

    def update_config(self, config: DockConfig) -> None:
        """Handle dynamic theme/config updates."""
        self.config = config
        tokens = get_theme_tokens(config)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            {get_scrollbar_style(tokens)}
        """)
        for card in self._note_cards.values():
            card.config = config
            card._apply_frame_style(False)
