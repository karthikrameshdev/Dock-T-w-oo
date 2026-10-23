"""Unit tests for the Brain subsystem, Mini Agent companion mascot, and Dock integration."""

import os
from pathlib import Path
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QPushButton

from dock_twoo.brain.animation import ACTIONS, PLAYLIST, Pose, pose_at, travel_point
from dock_twoo.brain.audio import SpeechClip, whistle_clip
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.mascot import Companion
from dock_twoo.brain.profiles import ProfileManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.config import ConfigManager, DockConfig
from dock_twoo.os_integration.screen_manager import ScreenManager
from dock_twoo.ui import DockWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_animation_poses_and_interpolation():
    """Verify procedural poses, pose_at interpolation, and travel curves."""
    assert "wave" in ACTIONS
    assert "nod" in ACTIONS
    assert "jump" in ACTIONS
    assert "turn_around" in ACTIONS
    assert "scan_screen" in ACTIONS
    assert "inspect_icon" in ACTIONS
    assert "explore" in ACTIONS
    # Stool sitting must not exist
    assert "sit" not in ACTIONS
    assert len(PLAYLIST) >= 20

    pose_wave = pose_at("wave", 0.5)
    assert isinstance(pose_wave, Pose)
    assert isinstance(pose_wave.right_arm, (int, float))
    assert 0.0 <= pose_wave.squash <= 2.0

    pose_turn = pose_at("turn_around", 0.4)
    assert isinstance(pose_turn, Pose)
    assert pose_turn.surprise > 0

    pose_nod = pose_at("nod", 0.2)
    assert isinstance(pose_nod, Pose)

    # Travel curve smoothing
    start = (100, 100)
    end = (300, 400)
    pt_half = travel_point(start, end, 0.5, "walk")
    assert isinstance(pt_half, tuple)
    assert len(pt_half) == 2
    assert 100 <= pt_half[0] <= 300
    assert 100 <= pt_half[1] <= 400


def test_speech_clip_generation():
    """Verify audio waveform SpeechClip parsing and whistle generator."""
    clip = whistle_clip()
    assert isinstance(clip, SpeechClip)
    assert clip.rate > 0
    assert clip.channels in (1, 2)
    assert clip.duration > 0
    assert clip.frames > 0
    # Level at frame 0 and mid frame
    assert 0.0 <= clip.level_at(0) <= 1.0
    assert 0.0 <= clip.level_at(clip.frames // 2) <= 1.0


def test_brain_storage_and_profiles(tmp_path):
    """Verify BrainStore settings persistence and ProfileManager profile routing."""
    store = BrainStore(data_dir=tmp_path)
    assert store.setting("roaming", False) is False

    # Update settings
    store.set_setting("roaming", True)
    assert store.setting("roaming") is True

    # Check persistence on reload
    reloaded_store = BrainStore(data_dir=tmp_path)
    assert reloaded_store.setting("roaming") is True

    # Profile manager
    profile_mgr = ProfileManager(store)
    profiles = profile_mgr.get_profiles()
    assert len(profiles) >= 3

    # Check default active profile
    active = profile_mgr.get_active_profile()
    assert "id" in active
    assert "model" in active

    # Switch active profile
    assert profile_mgr.activate_profile("local_ollama") is True
    assert profile_mgr.get_active_profile()["id"] == "local_ollama"

    # API key encryption and lookup
    profile_mgr.set_key("gemini", "ai-test-key-12345")
    assert profile_mgr.get_key("gemini") == "ai-test-key-12345"


def test_companion_mascot_window(qtbot, qapp, tmp_path, monkeypatch):
    """Verify Companion mascot window creation, transparent layout, and absence of bottom toolbars."""
    from dock_twoo.brain import manager
    test_store = BrainStore(data_dir=tmp_path)
    
    # Create test manager instance
    mgr = BrainManager()
    mgr.store = test_store
    mgr.profile_mgr = ProfileManager(test_store)

    companion = mgr.companion
    qtbot.addWidget(companion)
    qtbot.addWidget(companion.caption)

    # 1. Window geometry and flags
    assert companion.width() == 264
    assert companion.height() == 268
    flags = companion.windowFlags()
    assert bool(flags & Qt.WindowType.FramelessWindowHint) is True
    assert bool(flags & Qt.WindowType.WindowStaysOnTopHint) is True

    # 2. Strict check: Mascot has NO bottom controls/toolbar buttons (mic, chat, console, settings)
    child_buttons = companion.findChildren(QPushButton)
    # The Companion window itself has 0 QPushButton child controls (only transparent canvas)
    assert len(child_buttons) == 0

    # 3. Test activity states
    companion.set_activity("listening")
    assert companion.activity == "listening"

    companion.set_activity("thinking")
    assert companion.activity == "thinking"

    companion.set_activity("speaking")
    assert companion.activity == "speaking"

    companion.set_activity("idle")
    assert companion.activity == "idle"

    # 4. Speech caption bubble
    companion.caption.present("Hello from Brain Mini Agent!", duration_sec=5)
    assert companion.caption.isVisible() is True
    assert companion.caption.text_lbl.text() == "Hello from Brain Mini Agent!"

    companion.caption.hide()
    assert companion.caption.isVisible() is False

    # 5. Turn to user animation
    companion.turn_to_user()
    assert companion.action == "turn_around"

    companion.close()


def test_mini_agent_right_click_disabled(qtbot, qapp, tmp_path, monkeypatch):
    """Verify right-clicking on the Mini Agent directly is disabled and never triggers context menu."""
    mgr = BrainManager.get_instance()
    mgr.store = BrainStore(data_dir=tmp_path)
    companion = mgr.companion
    qtbot.addWidget(companion)
    companion.show()

    menu_calls = []
    monkeypatch.setattr(mgr, "show_context_menu", lambda pt: menu_calls.append(pt))

    # Right click on companion
    qtbot.mouseClick(companion, Qt.MouseButton.RightButton)
    assert len(menu_calls) == 0

    companion.close()


def test_brain_manager_lifecycle(qtbot, qapp, tmp_path):
    """Verify BrainManager summon, hide, toggle (on/off switch behavior), and status report."""
    mgr = BrainManager.get_instance()
    mgr.store = BrainStore(data_dir=tmp_path)
    qtbot.addWidget(mgr.companion)
    qtbot.addWidget(mgr.companion.caption)

    # Initially hide
    mgr.hide_mini_agent()
    assert mgr.is_mini_agent_visible() is False

    # 1. First click: Turn on (Mini Agent appears)
    mgr.toggle_mini_agent()
    assert mgr.is_mini_agent_visible() is True

    # 2. Second click: Turn off (Mini Agent disappears like an on/off button)
    mgr.toggle_mini_agent()
    assert mgr.is_mini_agent_visible() is False

    # 3. Third click: Turn back on without reinitializing
    mgr.toggle_mini_agent()
    assert mgr.is_mini_agent_visible() is True

    # Status dictionary for console
    status = mgr.get_status()
    assert status["name"] == "Brain"
    assert status["is_mini_agent_visible"] is True
    assert "active_profile" in status
    assert len(status["profiles"]) > 0

    # Hide mini agent
    mgr.hide_mini_agent()
    assert mgr.is_mini_agent_visible() is False


def test_dock_window_brain_click_and_context_menu(qtbot, qapp, tmp_path, monkeypatch):
    """Verify clicking Brain on the dock toggles mini agent (no chat drawer) and right-click opens menu."""
    config_file = tmp_path / "config.json"
    mgr = ConfigManager(config_path=config_file)
    mgr.config.auto_hide = False

    dock = DockWindow(mgr)
    qtbot.addWidget(dock)
    dock.show()

    brain_mgr = dock.brain_manager
    qtbot.addWidget(brain_mgr.companion)
    qtbot.addWidget(brain_mgr.companion.caption)

    # Ensure mini agent is initially hidden and drawer is closed
    brain_mgr.hide_mini_agent()
    assert dock.attached_window.isVisible() is False
    assert brain_mgr.is_mini_agent_visible() is False

    # 1. Left-click Brain icon on dock -> Mini Agent appears
    brain_btn = dock._icon_buttons["brain"]
    qtbot.mouseClick(brain_btn, Qt.MouseButton.LeftButton)

    # CRITICAL: Attached drawer MUST NOT open!
    assert dock.attached_window.isVisible() is False
    # The Mini Agent robot companion MUST open!
    assert brain_mgr.is_mini_agent_visible() is True

    # 2. Left-click Brain icon again -> Mini Agent disappears (on/off toggle)
    qtbot.mouseClick(brain_btn, Qt.MouseButton.LeftButton)
    assert brain_mgr.is_mini_agent_visible() is False

    # 3. Left-click again -> Mini Agent appears again
    qtbot.mouseClick(brain_btn, Qt.MouseButton.LeftButton)
    assert brain_mgr.is_mini_agent_visible() is True

    # 4. Right-click Brain icon on dock emits signal and invokes context menu
    right_clicks = []
    brain_btn.right_clicked.connect(lambda app_id, pt: right_clicks.append((app_id, pt)))

    menu_shown = []
    monkeypatch.setattr(brain_mgr, "show_context_menu", lambda pt: menu_shown.append(pt))

    qtbot.mouseClick(brain_btn, Qt.MouseButton.RightButton)
    assert len(right_clicks) == 1
    assert right_clicks[0][0] == "brain"
    assert len(menu_shown) == 1

    # Clean up
    brain_mgr.hide_mini_agent()
    dock.close()
