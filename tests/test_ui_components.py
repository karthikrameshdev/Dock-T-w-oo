"""Unit tests for UI components: DockIconButton, DockTooltip, AttachedWindow, and DockWindow."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
import pytest

from dock_twoo.config import ConfigManager, DockAppItem, DockConfig
from dock_twoo.ui import AttachedWindow, DockIconButton, DockTooltip, DockWindow
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
    item = DockAppItem(id="vault", name="Vault", icon="vault", tooltip="Vault T(w)oo")
    btn = DockIconButton(item, cfg)
    qtbot.addWidget(btn)
    btn.show()

    tooltip = DockTooltip.get_instance(cfg)
    qtbot.addWidget(tooltip)

    tooltip.show_for_widget(btn, "Vault T(w)oo - Password Manager", edge="right")
    assert tooltip.isVisible()
    assert tooltip._text == "Vault T(w)oo - Password Manager"
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

    # Switch to Vault app
    window.show_app("vault", dock_geom, icon_center_y=350)
    assert window.is_showing_app("vault")
    assert isinstance(window.stack.currentWidget(), VaultAppWidget)

    # Switch to Brain app
    window.show_app("brain", dock_geom, icon_center_y=800)
    assert window.is_showing_app("brain")
    assert isinstance(window.stack.currentWidget(), BrainAppWidget)

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
    assert "brain" in dock._icon_buttons

    # Simulate clicking notes icon
    notes_btn = dock._icon_buttons["notes"]
    dock._handle_icon_click("notes", notes_btn.mapToGlobal(QPoint(10, 10)))

    assert dock.attached_window.isVisible()
    assert dock.attached_window.is_showing_app("notes")
    assert notes_btn._is_active is True

    # Clicking notes again toggles it off
    dock._handle_icon_click("notes", notes_btn.mapToGlobal(QPoint(10, 10)))
    assert not dock.attached_window.isVisible()
    assert notes_btn._is_active is False

    dock.close()
