"""Notes T(w)oo application attached drawer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dock_twoo.config import DockConfig, get_default_config_dir
from dock_twoo.ui.apps.base_app import BaseAttachedApp
from dock_twoo.ui.theme import get_theme_tokens


class NotesAppWidget(BaseAttachedApp):
    """Notes attached drawer with fast search, creation, and markdown note editing."""

    def __init__(self, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__("notes", "Notes T(w)oo", config, parent)
        self.notes_dir = get_default_config_dir() / "notes"
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self._current_note_id: Optional[str] = None
        self._init_notes_ui()
        self._load_notes()

    def _init_notes_ui(self) -> None:
        tokens = get_theme_tokens(self.config)

        # Top toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search notes...")
        self.search_input.setStyleSheet(
            f"""
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
            """
        )
        self.search_input.textChanged.connect(self._filter_notes)
        toolbar.addWidget(self.search_input)

        self.new_btn = QPushButton("+ New", self)
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {tokens.accent_color};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            """
        )
        self.new_btn.clicked.connect(self._create_new_note)
        toolbar.addWidget(self.new_btn)

        self.content_layout.addLayout(toolbar)

        # Note Title
        self.title_input = QLineEdit(self)
        self.title_input.setPlaceholderText("Note Title...")
        self.title_input.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent;
                color: {tokens.text_primary};
                border: none;
                font-size: 15px;
                font-weight: 600;
                padding: 4px 0;
            }}
            """
        )
        self.title_input.textChanged.connect(self._on_content_changed)
        self.content_layout.addWidget(self.title_input)

        # Note Body
        self.body_edit = QTextEdit(self)
        self.body_edit.setPlaceholderText("Write your note here in markdown or plain text...")
        self.body_edit.setStyleSheet(
            f"""
            QTextEdit {{
                background: rgba(0, 0, 0, 0.2);
                color: {tokens.text_primary};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 10px;
                font-size: 13px;
                line-height: 1.4;
            }}
            """
        )
        self.body_edit.textChanged.connect(self._on_content_changed)
        self.content_layout.addWidget(self.body_edit, 1)

        # List of notes at bottom or quick selector
        self.notes_list = QListWidget(self)
        self.notes_list.setFixedHeight(110)
        self.notes_list.setStyleSheet(
            f"""
            QListWidget {{
                background: rgba(0, 0, 0, 0.15);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 8px;
                color: {tokens.text_primary};
                padding: 4px;
                font-size: 12px;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-radius: 6px;
            }}
            QListWidget::item:selected {{
                background: rgba(59, 130, 246, 0.25);
                color: #ffffff;
            }}
            """
        )
        self.notes_list.itemClicked.connect(self._on_note_selected)
        self.content_layout.addWidget(self.notes_list)

    def _load_notes(self) -> None:
        self.notes_list.clear()
        files = sorted(self.notes_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            # Create a welcome note
            self._create_welcome_note()
            files = list(self.notes_dir.glob("*.json"))

        for file in files:
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    item = QListWidgetItem(data.get("title", "Untitled Note"))
                    item.setData(Qt.ItemDataRole.UserRole, file.stem)
                    self.notes_list.addItem(item)
            except Exception:
                pass

        if self.notes_list.count() > 0:
            self.notes_list.setCurrentRow(0)
            self._on_note_selected(self.notes_list.item(0))

    def _create_welcome_note(self) -> None:
        welcome_file = self.notes_dir / "welcome.json"
        data = {
            "title": "Welcome to Notes T(w)oo",
            "body": "Welcome to your persistent secondary dock companion!\n\n- Write fast thoughts and meeting notes\n- Auto-saves instantly as you type\n- Clean dark & light mode styling\n- Dock T(w)oo attached drawer stays beside your dock.",
        }
        with open(welcome_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _create_new_note(self) -> None:
        import time
        note_id = f"note_{int(time.time())}"
        data = {"title": "Untitled Note", "body": ""}
        file_path = self.notes_dir / f"{note_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        item = QListWidgetItem("Untitled Note")
        item.setData(Qt.ItemDataRole.UserRole, note_id)
        self.notes_list.insertItem(0, item)
        self.notes_list.setCurrentRow(0)
        self._on_note_selected(item)
        self.title_input.setFocus()
        self.title_input.selectAll()

    def _on_note_selected(self, item: QListWidgetItem) -> None:
        note_id = item.data(Qt.ItemDataRole.UserRole)
        self._current_note_id = note_id
        file_path = self.notes_dir / f"{note_id}.json"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.title_input.blockSignals(True)
                    self.body_edit.blockSignals(True)
                    self.title_input.setText(data.get("title", ""))
                    self.body_edit.setText(data.get("body", ""))
                    self.title_input.blockSignals(False)
                    self.body_edit.blockSignals(False)
            except Exception:
                pass

    def _on_content_changed(self) -> None:
        if not self._current_note_id:
            return
        file_path = self.notes_dir / f"{self._current_note_id}.json"
        title = self.title_input.text() or "Untitled Note"
        body = self.body_edit.toPlainText()
        data = {"title": title, "body": body}
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            # Update list item text
            current_item = self.notes_list.currentItem()
            if current_item:
                current_item.setText(title)
        except Exception:
            pass

    def _filter_notes(self, query: str) -> None:
        query = query.lower()
        for i in range(self.notes_list.count()):
            item = self.notes_list.item(i)
            item.setHidden(query not in item.text().lower())
