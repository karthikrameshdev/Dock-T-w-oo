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
    qtbot.addWidget(tooltip)

    tooltip.show_for_widget(btn, "Vault", edge="right")
    assert tooltip.isVisible()
    assert tooltip._text == "Vault"
    assert tooltip._pointer_edge == "right"

    tooltip.hide_tooltip()
    assert tooltip.isHidden()


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
    assert len(dock._icon_buttons) == 4

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

