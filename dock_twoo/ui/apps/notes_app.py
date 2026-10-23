"""Notes application attached drawer with two-page design, search, state persistence, and delete."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
import time
from typing import Dict, List, Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
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
    """Clean card representing a note in the list view with title, preview, date, and delete action."""

    clicked = Signal(str)  # note_id
    delete_requested = Signal(str, str)  # note_id, title

    def __init__(
        self,
        note_id: str,
        title: str,
        body: str,
        updated_at: float,
        config: DockConfig,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.note_id = note_id
        self.title = title
        self.body = body
        self.updated_at = updated_at
        self.config = config

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_ui()

    def _setup_ui(self) -> None:
        tokens = get_theme_tokens(self.config)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Header row: Title + Delete button
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

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

        # Timestamp footer
        date_str = self._format_date(self.updated_at)
        self.date_lbl = QLabel(date_str, self)
        self.date_lbl.setFont(create_app_font(self.config, size=10, weight=QFont.Weight.Normal))
        self.date_lbl.setStyleSheet("color: rgba(142, 142, 159, 0.7); background: transparent; border: none;")
        layout.addWidget(self.date_lbl)

        self._apply_frame_style(False)

    def _format_date(self, ts: float) -> str:
        if not ts:
            return ""
        try:
            dt = datetime.datetime.fromtimestamp(ts)
            now = datetime.datetime.now()
            if dt.date() == now.date():
                return f"Today, {dt.strftime('%I:%M %p')}"
            elif (now.date() - dt.date()).days == 1:
                return f"Yesterday, {dt.strftime('%I:%M %p')}"
            else:
                return dt.strftime("%b %d, %Y")
        except Exception:
            return ""

    def _apply_frame_style(self, hover: bool) -> None:
        tokens = get_theme_tokens(self.config)
        is_dark = self.config.get_effective_theme() == "dark"
        if hover:
            bg = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.06)"
            border = tokens.accent_color
        else:
            bg = "rgba(255, 255, 255, 0.04)" if is_dark else "rgba(0, 0, 0, 0.03)"
            border = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.08)"

        self.setStyleSheet(f"""
            NoteCard {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 9px;
            }}
        """)

    def enterEvent(self, event) -> None:
        self._apply_frame_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._apply_frame_style(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.note_id)
        super().mousePressEvent(event)

    def _on_delete_clicked(self) -> None:
        self.delete_requested.emit(self.note_id, self.title)


class NotesAppWidget(BaseAttachedApp):
    """Notes attached drawer with a dedicated two-page design (List & Editor), state persistence, and full search."""

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

        self.cards_container = QWidget()
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

    def _load_notes(self) -> None:
        """Load all notes from disk and populate the list cards."""
        # Clear existing cards
        for card in list(self._note_cards.values()):
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self._note_cards.clear()

        # Gather note JSON files
        json_files = [f for f in self.notes_dir.glob("*.json") if not f.name.startswith(".")]

        if not json_files:
            self._create_welcome_note()
            json_files = [f for f in self.notes_dir.glob("*.json") if not f.name.startswith(".")]

        notes_data: List[dict] = []
        for file in json_files:
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data["id"] = file.stem
                    data["updated_at"] = data.get("updated_at", file.stat().st_mtime)
                    notes_data.append(data)
            except Exception:
                pass

        # Sort by updated_at descending (newest first)
        notes_data.sort(key=lambda x: x.get("updated_at", 0), reverse=True)

        for n in notes_data:
            card = NoteCard(
                note_id=n["id"],
                title=n.get("title", "Untitled Note"),
                body=n.get("body", ""),
                updated_at=n.get("updated_at", 0),
                config=self.config,
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
        data = {
            "title": "Welcome to Notes",
            "body": "Welcome to your persistent secondary dock companion!\n\n- Write fast thoughts and meeting notes\n- Auto-saves instantly as you type\n- Clean dark & light mode styling\n- Attached drawer stays beside your dock.",
            "updated_at": time.time(),
        }
        with open(welcome_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _save_state(self, page_index: int, note_id: Optional[str]) -> None:
        """Persist current view state so reopen preserves exact position."""
        state = {
            "last_page": page_index,
            "last_note_id": note_id,
        }
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def _restore_state(self) -> None:
        """Restore user's previous state (Page 0 List vs Page 1 Editor) on launch."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                last_page = state.get("last_page", 0)
                last_note_id = state.get("last_note_id")
                if last_page == 1 and last_note_id:
                    note_file = self.notes_dir / f"{last_note_id}.json"
                    if note_file.exists():
                        self._open_note(last_note_id, save_state=False)
                        return
            except Exception:
                pass
        self._go_back_to_list(save_state=False)

    def _create_new_note(self) -> None:
        """Create a new note and immediately open it in the editor."""
        note_id = f"note_{int(time.time())}"
        data = {"title": "Untitled Note", "body": "", "updated_at": time.time()}
        file_path = self.notes_dir / f"{note_id}.json"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
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
            self._update_editor_meta(data.get("updated_at", 0), data.get("body", ""))
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

        # Reload list cards so latest updates and previews are fresh
        self._load_notes()

        if save_state:
            self._save_state(page_index=0, note_id=None)

    def _update_editor_meta(self, updated_at: float, body: str) -> None:
        words = len((body or "").split())
        dt_str = ""
        if updated_at:
            try:
                dt = datetime.datetime.fromtimestamp(updated_at)
                dt_str = f"Last edited {dt.strftime('%b %d, %I:%M %p')} • "
            except Exception:
                pass
        self.editor_meta_lbl.setText(f"{dt_str}{words} {'word' if words == 1 else 'words'}")

    def _on_content_changed(self) -> None:
        """Auto-save note content as user types."""
        if not self._current_note_id:
            return
        file_path = self.notes_dir / f"{self._current_note_id}.json"
        title = self.title_input.text().strip()
        body = self.body_edit.toPlainText()
        now = time.time()
        data = {
            "title": title or "Untitled Note",
            "body": body,
            "updated_at": now,
        }
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._update_editor_meta(now, body)
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
