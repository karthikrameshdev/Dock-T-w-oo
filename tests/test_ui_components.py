"""Unit tests for UI components: DockIconButton, DockTooltip, AttachedWindow, and DockWindow."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
import pytest

from dock_twoo.config import ConfigManager, DockAppItem, DockConfig
from dock_twoo.os_integration.screen_manager import ScreenManager
from dock_twoo.ui import AttachedWindow, DockIconButton, DockTooltip, DockWindow, DockTrayIcon
from dock_twoo.ui.apps import NotesAppWidget, VaultAppWidget, BrainAppWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_dock_icon_button(qtbot, qapp):
    cfg = DockConfig(dock_width=60, dock_padding_x=8, icon_size=20)
    item = DockAppItem(id="notes", name="Notes", icon="notes", tooltip="Open Notes")
    btn = DockIconButton(item, cfg)
    qtbot.addWidget(btn)

    # Standardized bounding box
    expected_dim = 60 - (8 * 2)  # 44
    assert btn.width() == expected_dim
    assert btn.height() == expected_dim

    # Test click signal
    clicked_data = []
    btn.clicked.connect(lambda app_id, pt: clicked_data.append((app_id, pt)))

    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
    assert len(clicked_data) == 1
    assert clicked_data[0][0] == "notes"

    # Test active state
    btn.set_active(True)
    assert btn._is_active is True
    btn.set_active(False)
    assert btn._is_active is False


def test_dock_tooltip(qtbot, qapp):
    cfg = DockConfig(edge="right")
    item = DockAppItem(id="vault", name="Vault", icon="vault", tooltip="Vault")
    btn = DockIconButton(item, cfg)
    qtbot.addWidget(btn)
    btn.show()

    tooltip = DockTooltip.get_instance(cfg)

    tooltip.show_for_widget(btn, "Vault", edge="right")
    assert tooltip.isVisible()
    assert tooltip._text == "Vault"
    assert tooltip._pointer_edge == "right"

    tooltip.hide_tooltip()
    assert tooltip.isHidden()
    btn.close()


def test_attached_window_switching_apps(qtbot, qapp):
    cfg = DockConfig(edge="right", attached_width=380, attached_height=500)
    window = AttachedWindow(cfg)
    qtbot.addWidget(window)

    from PySide6.QtCore import QRect
    dock_geom = QRect(1800, 200, 60, 700)

    # Show Notes app
    window.show_app("notes", dock_geom, icon_center_y=300)
    assert window.isVisible()
    assert window.is_showing_app("notes")
    assert isinstance(window.stack.currentWidget(), NotesAppWidget)

    # Attached window matches exact dock height
    assert window.height() == dock_geom.height()

    # Switch to Brain app
    window.show_app("brain", dock_geom, icon_center_y=800)
    assert window.is_showing_app("brain")
    assert isinstance(window.stack.currentWidget(), BrainAppWidget)
    assert window.height() == dock_geom.height()

    # Hide window
    window.hide_window()
    assert not window.isVisible()
    window.close()


def test_dock_window_toggle_and_active_state(qtbot, qapp, tmp_path):
    config_file = tmp_path / "config.json"
    mgr = ConfigManager(config_path=config_file)

    dock = DockWindow(mgr)
    qtbot.addWidget(dock)
    dock.show()

    assert dock.isVisible()
    assert "notes" in dock._icon_buttons
    assert "vault" in dock._icon_buttons
    assert "settings" in dock._icon_buttons
    assert "brain" in dock._icon_buttons
    assert len(dock._icon_buttons) == 6
    assert "tasks" in dock._icon_buttons and "keep_awake" in dock._icon_buttons

    # Simulate clicking notes icon
    notes_btn = dock._icon_buttons["notes"]
    dock._handle_icon_click("notes", notes_btn.mapToGlobal(QPoint(10, 10)))

    assert dock.attached_window.isVisible()
    assert dock.attached_window.is_showing_app("notes")
    assert notes_btn._is_active is True
    assert dock.attached_window.height() == dock.height()

    # Clicking notes again toggles it off
    dock._handle_icon_click("notes", notes_btn.mapToGlobal(QPoint(10, 10)))
    assert not dock.attached_window.isVisible()
    assert notes_btn._is_active is False

    dock.close()


def test_dock_hover_inspector_cursor_behavior(qtbot, qapp, tmp_path):
    from PySide6.QtGui import QGuiApplication
    config_file = tmp_path / "config.json"
    mgr = ConfigManager(config_path=config_file)

    dock = DockWindow(mgr)
    qtbot.addWidget(dock)
    dock.show()

    # STRICT REQUIREMENT: Logo widget must strictly use ArrowCursor (never pointing hand)
    assert dock.logo_widget.cursor().shape() == Qt.CursorShape.ArrowCursor

    # Icon buttons must use PointingHandCursor
    assert dock._icon_buttons["notes"].cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert dock._icon_buttons["settings"].cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert dock._icon_buttons["brain"].cursor().shape() == Qt.CursorShape.PointingHandCursor

    # Inactive hover override cursor mechanism
    dock._set_pointing_hand_cursor()
    assert dock._has_hand_cursor_override is True
    assert QGuiApplication.overrideCursor() is not None

    dock._restore_default_cursor()
    assert dock._has_hand_cursor_override is False
    assert QGuiApplication.overrideCursor() is None

    # Hovering an app icon shows the callout tooltip
    notes_btn = dock._icon_buttons["notes"]
    notes_btn.set_hover(True)
    tooltip = DockTooltip.get_instance()
    assert tooltip.isVisible()

    notes_btn.set_hover(False)
    assert not tooltip.isVisible()

    dock.close()


def test_dock_auto_hide_slide_mechanics(qtbot, qapp, tmp_path):
    config_file = tmp_path / "config.json"
    mgr = ConfigManager(config_path=config_file)
    mgr.update({"auto_hide": True})

    dock = DockWindow(mgr)
    qtbot.addWidget(dock)
    dock.show()

    # Verify collapsed geometry computation
    collapsed = dock._get_collapsed_geometry()
    avail = ScreenManager.get_available_geometry(0)
    assert collapsed.left() == avail.right() - 2

    # Verify slide out
    dock._slide_out()
    assert dock._is_collapsed is True

    # Verify slide in
    dock._slide_in()
    assert dock._is_collapsed is False

    dock.close()


def test_dock_tray_icon_non_modal_menu(qtbot, qapp, tmp_path):
    config_file = tmp_path / "config.json"
    mgr = ConfigManager(config_path=config_file)

    dock = DockWindow(mgr)
    qtbot.addWidget(dock)
    dock.show()

    tray = DockTrayIcon(dock, mgr)

    # 1. Ensure tray does NOT set a native blocking NSMenu (contextMenu is None)
    assert tray.contextMenu() is None

    # 2. Trigger menu presentation
    from PySide6.QtWidgets import QSystemTrayIcon
    tray._on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)

    # 3. Dock must remain fully enabled and active while tray menu options are displayed
    assert dock.isEnabled() is True
    assert dock.isVisible() is True

    # 4. Icon buttons remain clickable and interactive
    notes_btn = dock._icon_buttons["notes"]
    assert notes_btn.isEnabled() is True

    # 5. Menu actions work as expected
    assert tray.auto_hide_action.isChecked() is False
    tray.auto_hide_action.setChecked(True)
    assert mgr.config.auto_hide is True

    tray.auto_hide_action.setChecked(False)
    assert mgr.config.auto_hide is False

    # Close menu and clean up
    tray.menu.hide()
    dock.close()


def test_notes_app_two_page_design_and_state_persistence(qtbot, qapp, tmp_path, monkeypatch):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)

    # Monkeypatch get_default_config_dir to use isolated test tmp_path
    from dock_twoo.ui.apps import notes_app
    monkeypatch.setattr(notes_app, "get_default_config_dir", lambda: tmp_path)

    cfg = DockConfig()
    notes_widget = NotesAppWidget(cfg)
    qtbot.addWidget(notes_widget)
    notes_widget.show()

    # 1. Initial State: Page 0 (List View), back button hidden
    assert notes_widget.stack.currentIndex() == 0
    assert notes_widget.back_btn.isHidden() is True
    assert notes_widget.title_label.text() == "Notes"

    # 2. Create a new note -> switches to Page 1 (Editor View)
    notes_widget._create_new_note()
    assert notes_widget.stack.currentIndex() == 1
    assert notes_widget.back_btn.isVisible() is True
    assert notes_widget.title_label.text() == "Note"

    note_id = notes_widget._current_note_id
    assert note_id is not None

    # Edit note content
    notes_widget.title_input.setText("Secret Roadmap")
    notes_widget.body_edit.setText("This contains quantum computing blueprints.")

    # 3. Back button returns to Page 0 (List View)
    qtbot.mouseClick(notes_widget.back_btn, Qt.MouseButton.LeftButton)
    assert notes_widget.stack.currentIndex() == 0
    assert notes_widget.back_btn.isHidden() is True
    assert notes_widget.title_label.text() == "Notes"

    # Card updated in list view
    assert note_id in notes_widget._note_cards
    card = notes_widget._note_cards[note_id]
    assert card.title_lbl.text() == "Secret Roadmap"
    assert "quantum computing blueprints" in card.snippet_lbl.text()

    # 4. Search by title
    notes_widget.search_input.setText("Secret")
    assert card.isVisible() is True

    # 5. Search by body content
    notes_widget.search_input.setText("blueprints")
    assert card.isVisible() is True

    # Search non-matching query
    notes_widget.search_input.setText("non_existent_text_xyz")
    assert card.isVisible() is False
    assert notes_widget.empty_label.isVisible() is True

    notes_widget.search_input.clear()
    assert card.isVisible() is True

    # 6. Click card to open Editor View (Page 1)
    card.clicked.emit(note_id)
    assert notes_widget.stack.currentIndex() == 1
    assert notes_widget.back_btn.isVisible() is True
    assert notes_widget.title_input.text() == "Secret Roadmap"

    # 7. State persistence: reopen widget preserves opened note
    reopened_widget = NotesAppWidget(cfg)
    qtbot.addWidget(reopened_widget)
    reopened_widget.show()

    # Preserves previous state: opened directly into the note!
    assert reopened_widget.stack.currentIndex() == 1
    assert reopened_widget.back_btn.isVisible() is True
    assert reopened_widget._current_note_id == note_id
    assert reopened_widget.title_input.text() == "Secret Roadmap"

    # 8. Delete note from editor view (monkeypatch QMessageBox to return Yes)
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    notes_widget._on_editor_delete_clicked()
    # After deleting currently opened note, navigates back to list view
    assert notes_widget.stack.currentIndex() == 0
    assert notes_widget.back_btn.isHidden() is True
    assert (notes_dir / f"{note_id}.json").exists() is False

    notes_widget.close()
    reopened_widget.close()


def test_dock_edge_orientation_and_no_overlap(qtbot, qapp, tmp_path):
    """Verify automatic orientation switching (horizontal/vertical) and attached window overlap prevention."""
    cfg_path = tmp_path / "config.json"
    cfg_mgr = ConfigManager(config_path=cfg_path)
    cfg_mgr.update({"edge": "right", "attached_gap": 12, "attached_width": 390})

    dock = DockWindow(cfg_mgr)
    qtbot.addWidget(dock)
    qtbot.addWidget(dock.attached_window)

    # 1. Right edge: vertical layout
    assert dock.layout().__class__.__name__ == "QVBoxLayout"
    assert dock.scroll_area.is_horizontal is False
    right_width = dock.width()

    dock_geom = dock.geometry()
    avail = ScreenManager.get_available_geometry(cfg_mgr.config.screen_index)
    # Strict boundary guarantee: dock right edge never goes beyond the screen or window boundary
    assert dock_geom.right() <= avail.right() - cfg_mgr.config.edge_offset_x

    dock.attached_window.show_app("vault", dock_geom, 300)
    att_geom = dock.attached_window.geometry()
    # Pinned to the left of the dock with gap
    assert dock_geom.left() - att_geom.right() >= 12

    # 2. Switch edge to 'top': automatic horizontal layout & scrolling
    cfg_mgr.update({"edge": "top"})
    assert dock.layout().__class__.__name__ == "QHBoxLayout"
    assert dock.scroll_area.is_horizontal is True
    # Strict cross-axis symmetry: horizontal dock height must match vertical dock width exactly
    assert dock.height() == right_width

    dock_geom = dock.geometry()
    # Strict boundary guarantee: dock top edge within available screen geometry
    assert dock_geom.top() >= avail.top() + cfg_mgr.config.edge_offset_x

    dock.attached_window.show_app("vault", dock_geom, 500)
    att_geom = dock.attached_window.geometry()
    # Pinned below the dock with gap
    assert att_geom.top() - dock_geom.bottom() >= 12

    # 3. Switch edge to 'bottom': horizontal layout & exact same height
    cfg_mgr.update({"edge": "bottom"})
    assert dock.height() == right_width

    # 4. Switch edge to 'left': vertical layout & exact same width
    cfg_mgr.update({"edge": "left"})
    assert dock.width() == right_width

    # 5. When dock_height is customized independently on top, returning to right restores original dock_width
    cfg_mgr.update({"edge": "top", "dock_height": 52})
    assert dock.height() == 52 + 16
    cfg_mgr.update({"edge": "right"})
    assert dock.width() == right_width

    dock.close()




def test_tasks_drawer_uses_the_persistent_voice_work_log(tmp_path,qtbot):
    from PySide6.QtCore import QDate
    from dock_twoo.ui.apps.tasks_app import TasksAppWidget
    from dock_twoo.tasks import TaskStore
    cfg=DockConfig(storage_path=str(tmp_path))
    widget=TasksAppWidget(cfg);qtbot.addWidget(widget);widget.show()
    widget.date.setDate(QDate(2026,1,5));widget.entry.setText('Reviewed voice agent');widget.add()
    assert widget.list.count()==1
    item=widget.list.item(0);widget.toggle(item)
    assert TaskStore(tmp_path/'tasks').list(date='2026-01-05')['tasks'][0]['status']=='todo'
    TaskStore(tmp_path/'tasks').add('Recorded through voice',date='2026-01-05')
    widget.refresh();assert widget.list.count()==2
    widget.date.setDate(QDate(2026,1,6));assert widget.list.count()==0
    widget.close()


def test_repeated_voice_open_keeps_tasks_visible(qtbot,tmp_path):
    mgr=ConfigManager(config_path=tmp_path/'config.json');mgr.update({'storage_path':str(tmp_path/'storage')})
    dock=DockWindow(mgr);qtbot.addWidget(dock);dock.show()
    dock._open_voice_app('tasks')
    assert dock.attached_window.is_showing_app('tasks')
    dock._open_voice_app('tasks')
    assert dock.attached_window.is_showing_app('tasks') and dock.attached_window.isVisible()
    dock.attached_window.close();dock.close()
