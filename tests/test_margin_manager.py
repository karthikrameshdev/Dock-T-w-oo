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


@pytest.fixture
def macos_backend(monkeypatch):
    """Run the mocked Finder backend on every CI host without OS automation."""
    from types import SimpleNamespace
    from dock_twoo.os_integration import margin_manager
    monkeypatch.setattr(margin_manager, "platform", SimpleNamespace(system=lambda: "Darwin"))


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


def test_margin_manager_window_restoration_on_edge_change(qapp, monkeypatch, macos_backend):
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


def test_margin_manager_desktop_icon_clamping_and_collision_avoidance(qapp, monkeypatch, macos_backend):
    cfg = DockConfig(reserve_screen_space=True, edge="right", screen_margin_gap=8)
    mgr = DesktopMarginManager(cfg)

    # Mock subprocess.run to simulate Finder desktop query and batch move execution
    mock_calls = []

    def mock_subprocess_run(cmd, capture_output=True, text=True, timeout=1.5, **kwargs):
        import re
        script = cmd[2]
        mock_calls.append(script)
        class MockResult:
            returncode = 0
            stdout = "Screenshot 1.png|1446.0|73.0\nScreenshot 2.png|1446.0|73.0\n"
            stderr = ""
        if 'set desktop position of item' in script:
            MockResult.stdout = ''.join(f'{name}|{x}|{y}\n' for name, x, y in re.findall(r'set desktop position of item "([^"]+)" of desktop to \{(-?\d+), (-?\d+)\}', script))
        return MockResult()

    import subprocess
    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    dock_rect = QRect(1440, 50, 60, 800)
    adjusted_events = []
    mgr.icon_adjusted.connect(lambda name, x, y: adjusted_events.append((name, x, y)))

    mgr._check_and_clamp_desktop_icons(dock_rect, edge="right", gap=8)

    # Both screenshots must have been clamped outside the dock zone (x < 1400)
    assert len(adjusted_events) == 2
    name1, x1, y1 = adjusted_events[0]
    name2, x2, y2 = adjusted_events[1]

    assert name1 == "Screenshot 1.png"
    assert x1 < 1400
    assert y1 == 73

    assert name2 == "Screenshot 2.png"
    assert x2 < 1400
    # Collision avoidance stepped to the next free column
    assert x2 != x1
    assert "Screenshot 1.png" in mgr._adjusted_icons
    assert "Screenshot 2.png" in mgr._adjusted_icons


def test_margin_manager_desktop_icon_restoration_on_edge_vacated(qapp, monkeypatch, macos_backend):
    cfg = DockConfig(reserve_screen_space=True, edge="right")
    mgr = DesktopMarginManager(cfg)

    mgr._adjusted_icons["Screenshot.png"] = {
        "edge": "right",
        "orig_x": 1446,
        "orig_y": 73,
        "clamped_x": 1362,
        "clamped_y": 73,
    }

    mock_executed_scripts = []
    def mock_run(cmd, capture_output=True, timeout=1.5, **kwargs):
        mock_executed_scripts.append(cmd[2])
        class MockResult:
            returncode = 0
        return MockResult()

    import subprocess
    monkeypatch.setattr(subprocess, "run", mock_run)

    # When config edge moves to "top" (vacating "right"):
    new_cfg = DockConfig(reserve_screen_space=True, edge="top")
    mgr.update_config(new_cfg)

    # Icon was restored and cleared from adjusted icons
    assert "Screenshot.png" not in mgr._adjusted_icons
    assert any("set desktop position of item \"Screenshot.png\" of desktop to {1446, 73}" in s for s in mock_executed_scripts)


def test_margin_manager_native_clamping_and_restoration(qapp, monkeypatch):
    from types import SimpleNamespace
    from dock_twoo.os_integration import margin_manager

    set_attributes = []
    window_obj = "mock_window_ptr"

    class MockPoint:
        x = 100
        y = 50

    class MockSize:
        width = 1400
        height = 900

    mock_ax = SimpleNamespace(
        AXIsProcessTrusted=lambda: True,
        kAXValueCGPointType=1,
        kAXValueCGSizeType=2,
        AXUIElementCreateApplication=lambda pid: "mock_app",
        AXUIElementCopyAttributeValue=lambda obj, attr, val: (
            0,
            window_obj if attr == "AXFocusedWindow" else ("pos_token" if attr == "AXPosition" else "size_token"),
        ),
        AXValueGetValue=lambda token, val_type, ptr: (
            True,
            MockPoint() if val_type == 1 else MockSize(),
        ),
        AXValueCreate=lambda val_type, val: ("created_val", val),
        AXUIElementSetAttributeValue=lambda win, attr, val: (set_attributes.append((win, attr, val)) or 0),
    )

    class MockApp:
        def bundleIdentifier(self):
            return "com.google.Chrome"

        def localizedName(self):
            return "Google Chrome"

        def processIdentifier(self):
            return 12345

    mock_workspace = SimpleNamespace(
        frontmostApplication=lambda: MockApp(),
        runningApplications=lambda: [MockApp()],
    )
    mock_appkit = SimpleNamespace(
        NSWorkspace=SimpleNamespace(sharedWorkspace=lambda: mock_workspace)
    )

    monkeypatch.setattr(margin_manager, "_HAS_NATIVE_AX", True)
    monkeypatch.setattr(margin_manager, "AX", mock_ax)
    monkeypatch.setattr(margin_manager, "AppKit", mock_appkit)

    cfg = DockConfig(reserve_screen_space=True, edge="right", screen_margin_gap=8)
    mgr = DesktopMarginManager(cfg)
    screen = QRect(0, 0, 1512, 982)
    # Dock on right edge: max_right = 1360
    handled = mgr._check_and_clamp_frontmost_native(
        max_right=1360,
        min_left=0,
        min_top=0,
        max_bottom=0,
        edge="right",
        screen=screen,
    )

    assert handled is True
    assert "Google Chrome" in mgr._adjusted_windows
    assert mgr._adjusted_windows["Google Chrome"]["orig_w"] == 1400
    # Clamped width: max_right - wx = 1360 - 100 = 1260
    assert len(set_attributes) == 1
    win, attr, (tag, sz) = set_attributes[0]
    assert attr == "AXSize"
    assert sz == (1260, 900)

    # Now test restore_adjusted_window
    mgr.restore_adjusted_window("Google Chrome")
    assert "Google Chrome" not in mgr._adjusted_windows
    # Restoration sets AXSize and AXPosition back
    restored_sizes = [val for win, attr, (tag, val) in set_attributes if attr == "AXSize"]
    assert (1400, 900) in restored_sizes


