"""Unit tests for DesktopMarginManager."""

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication
import pytest

from dock_twoo.config import DockConfig
from dock_twoo.os_integration.margin_manager import DesktopMarginManager


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_margin_manager_lifecycle(qapp):
    cfg = DockConfig(reserve_screen_space=True, edge="right", screen_margin_gap=8)
    mgr = DesktopMarginManager(cfg)

    # Geometry update
    rect = QRect(1440, 50, 60, 800)
    mgr.update_dock_geometry(rect)
    assert mgr._dock_rect == rect

    # Config update
    new_cfg = DockConfig(reserve_screen_space=False, edge="left", screen_margin_gap=12)
    mgr.update_config(new_cfg)
    assert mgr.config.reserve_screen_space is False
    assert mgr.config.edge == "left"
    assert mgr.config.screen_margin_gap == 12

    # Start and stop safely
    mgr.start()
    assert mgr._running is True
    mgr.stop()
    assert mgr._running is False


def test_margin_manager_signals(qapp):
    cfg = DockConfig(reserve_screen_space=True, edge="right")
    mgr = DesktopMarginManager(cfg)

    received = []
    mgr.margin_adjusted.connect(lambda app, w, h: received.append((app, w, h)))

    mgr.margin_adjusted.emit("Safari", 1370, 900)
    assert len(received) == 1
    assert received[0] == ("Safari", 1370, 900)


def test_margin_manager_window_restoration_on_edge_change(qapp, monkeypatch):
    cfg = DockConfig(reserve_screen_space=True, edge="top")
    mgr = DesktopMarginManager(cfg)

    # Simulate Safari having been clamped on top edge
    mgr._adjusted_windows["Safari"] = {
        "edge": "top",
        "orig_x": 50,
        "orig_y": 25,
        "orig_w": 1200,
        "orig_h": 900,
    }

    restored_apps = []
    def mock_restore(app_name):
        restored_apps.append(app_name)
        mgr._adjusted_windows.pop(app_name, None)

    monkeypatch.setattr(mgr, "restore_adjusted_window", mock_restore)

    # When config changes to "right" (vacating "top"):
    new_cfg = DockConfig(reserve_screen_space=True, edge="right")
    mgr.update_config(new_cfg)

    # Safari must have been restored!
    assert "Safari" in restored_apps
    assert "Safari" not in mgr._adjusted_windows
