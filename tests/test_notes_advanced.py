"""Unit tests for Notes app: permanent welcome note deletion, created/modified dates, and drag & drop reordering."""

import json
from pathlib import Path
import time
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from dock_twoo.config import DockConfig
from dock_twoo.ui.apps.notes_app import NoteCard, NotesAppWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_welcome_note_can_be_deleted_permanently(qtbot, qapp, tmp_path, monkeypatch):
    """Verify that deleting the welcome note leaves it deleted and doesn't resurrect it."""
    from dock_twoo.ui.apps import notes_app
    monkeypatch.setattr(notes_app, "get_default_config_dir", lambda: tmp_path)

    cfg = DockConfig()
    widget = NotesAppWidget(cfg)
    qtbot.addWidget(widget)
    widget.show()

    # Initial launch creates welcome note once
    assert "welcome" in widget._note_cards
    welcome_card = widget._note_cards["welcome"]
    assert (tmp_path / "notes" / "welcome.json").exists() is True

    # Delete the welcome note (monkeypatch confirmation)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    widget._delete_note("welcome", "Welcome to Notes")

    # Welcome file must be deleted from disk
    assert (tmp_path / "notes" / "welcome.json").exists() is False
    assert len(widget._note_cards) == 0
    assert widget.empty_label.isVisible() is True

    # Reopening the widget MUST NOT resurrect the welcome note
    reopened = NotesAppWidget(cfg)
    qtbot.addWidget(reopened)
    reopened.show()

    assert len(reopened._note_cards) == 0
    assert (tmp_path / "notes" / "welcome.json").exists() is False
    assert reopened.empty_label.isVisible() is True

    widget.close()
    reopened.close()


def test_created_and_modified_dates_displayed_on_notes(qtbot, qapp, tmp_path, monkeypatch):
    """Verify that every note displays both Created and Modified dates below the preview."""
    from dock_twoo.ui.apps import notes_app
    monkeypatch.setattr(notes_app, "get_default_config_dir", lambda: tmp_path)

    cfg = DockConfig()
    widget = NotesAppWidget(cfg)
    qtbot.addWidget(widget)
    widget.show()

    # Create a new note
    widget._create_new_note()
    note_id = widget._current_note_id
    assert note_id is not None

    widget.title_input.setText("Project Mercury")
    widget.body_edit.setText("Orbital mechanics calculation notes.")

    # Return to list view
    widget._go_back_to_list()
    assert note_id in widget._note_cards
    card = widget._note_cards[note_id]

    # Verify both dates exist on card
    assert hasattr(card, "created_lbl")
    assert hasattr(card, "modified_lbl")
    assert "Created:" in card.created_lbl.text()
    assert "Modified:" in card.modified_lbl.text()

    # Open note and check editor metadata
    widget._open_note(note_id)
    editor_meta = widget.editor_meta_lbl.text()
    assert "Created" in editor_meta
    assert "Modified" in editor_meta

    widget.close()


def test_notes_reordering_and_latest_to_top(qtbot, qapp, tmp_path, monkeypatch):
    """Verify manual drag & drop reordering and that newest/latest note goes to the top."""
    from dock_twoo.ui.apps import notes_app
    monkeypatch.setattr(notes_app, "get_default_config_dir", lambda: tmp_path)

    cfg = DockConfig()
    widget = NotesAppWidget(cfg)
    qtbot.addWidget(widget)
    widget.show()

    # Remove welcome note to start clean
    notes_dir = tmp_path / "notes"
    if (notes_dir / "welcome.json").exists():
        (notes_dir / "welcome.json").unlink()

    # Create Note A, Note B, Note C
    now = time.time()
    for letter, t_offset in [("A", 10), ("B", 20), ("C", 30)]:
        fpath = notes_dir / f"note_{letter}.json"
        data = {
            "title": f"Note {letter}",
            "body": f"Content {letter}",
            "created_at": now + t_offset,
            "updated_at": now + t_offset,
        }
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f)

    widget._load_notes()
    # Initially sorted newest first: C, B, A
    cards = [widget.cards_layout.itemAt(i).widget() for i in range(widget.cards_layout.count()) if isinstance(widget.cards_layout.itemAt(i).widget(), NoteCard)]
    assert [c.title for c in cards] == ["Note C", "Note B", "Note A"]

    # Manually reorder: A, C, B via order_changed signal
    widget.cards_container.order_changed.emit(["note_A", "note_C", "note_B"])

    # Verify manual order saved in state file
    with open(widget.state_file, "r") as f:
        state = json.load(f)
    assert state.get("manual_order") == ["note_A", "note_C", "note_B"]

    # Reopening preserves manual order
    reopened = NotesAppWidget(cfg)
    qtbot.addWidget(reopened)
    reopened.show()
    reopened_cards = [reopened.cards_layout.itemAt(i).widget() for i in range(reopened.cards_layout.count()) if isinstance(reopened.cards_layout.itemAt(i).widget(), NoteCard)]
    assert [c.title for c in reopened_cards] == ["Note A", "Note C", "Note B"]

    # Editing Note B promotes it to the top!
    reopened._open_note("note_B")
    reopened.body_edit.setPlainText("Updated Note B content")
    reopened._on_content_changed()
    reopened._go_back_to_list()

    updated_cards = [reopened.cards_layout.itemAt(i).widget() for i in range(reopened.cards_layout.count()) if isinstance(reopened.cards_layout.itemAt(i).widget(), NoteCard)]
    # Note B is now at the top
    assert updated_cards[0].title == "Note B"

    widget.close()
    reopened.close()
