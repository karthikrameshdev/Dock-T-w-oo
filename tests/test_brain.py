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
    assert "climb_dock" in ACTIONS
    assert "inspect_window" in ACTIONS
    assert "replace_text" in ACTIONS
    assert "fold_arms" in ACTIONS
    assert "sensor_scan" in ACTIONS
    # Stool sitting must not exist
    assert "sit" not in ACTIONS
    assert len(PLAYLIST) >= 20

    # New robotic actions return valid Pose
    pose_climb = pose_at("climb_dock", 0.5)
    assert isinstance(pose_climb, Pose)

    pose_scan = pose_at("inspect_window", 0.5)
    assert isinstance(pose_scan, Pose)
    assert pose_scan.scan_beam > 0

    pose_text = pose_at("replace_text", 0.5)
    assert isinstance(pose_text, Pose)
    assert pose_text.text_sparkle > 0

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

    # Default active profile is local
    active = profile_mgr.get_active_profile()
    assert active["id"] == "local"
    assert active["name"] == "Local"
    assert active["status"] == "active"

    # Status before key
    gemini_prof = [p for p in profiles if p["id"] == "gemini"][0]
    assert gemini_prof["status"] == "not configured"

    openrouter_prof = [p for p in profiles if p["id"] == "openrouter"][0]
    assert openrouter_prof["status"] == "not configured"

    # Set key for gemini
    profile_mgr.set_key("gemini", "ai-test-key-12345")
    assert profile_mgr.get_key("gemini") == "ai-test-key-12345"
    updated_profiles = profile_mgr.get_profiles()
    gemini_updated = [p for p in updated_profiles if p["id"] == "gemini"][0]
    assert gemini_updated["status"] == "active"

    # Switch active profile
    assert profile_mgr.activate_profile("gemini") is True
    assert profile_mgr.get_active_profile()["id"] == "gemini"


def test_companion_mascot_window(qtbot, qapp, tmp_path, monkeypatch):
    """Verify Companion mascot window creation, transparent layout, native pinning, and absence of bottom toolbars or captions."""
    from dock_twoo.brain import manager
    from dock_twoo.brain.mascot import pin_native
    test_store = BrainStore(data_dir=tmp_path)
    
    # Create test manager instance
    mgr = BrainManager()
    mgr.store = test_store
    mgr.profile_mgr = ProfileManager(test_store)

    companion = mgr.companion
    qtbot.addWidget(companion)

    # 1. Window geometry and flags
    assert companion.width() == 264
    assert companion.height() == 268
    flags = companion.windowFlags()
    assert bool(flags & Qt.WindowType.FramelessWindowHint) is True
    assert bool(flags & Qt.WindowType.WindowStaysOnTopHint) is True
    assert bool(flags & Qt.WindowType.WindowDoesNotAcceptFocus) is True

    # 2. Window attributes for desktop permanence (never auto-hide on click outside)
    assert companion.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) is True
    assert companion.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating) is True
    assert companion.testAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow) is True

    # Pin native execution
    pin_native(companion)

    # 3. Strict check: Companion has NO text captions and NO bottom controls/toolbar buttons
    assert not hasattr(companion, "caption")
    child_buttons = companion.findChildren(QPushButton)
    assert len(child_buttons) == 0

    # 4. Test all headlight activity states
    for state in ("listening", "thinking", "processing", "speaking", "offline", "idle"):
        companion.set_activity(state)
        assert companion.activity == state

    # 5. Turn to user animation
    companion.turn_to_user()
    assert companion.action == "turn_around"

    # 6. Travel to corner
    companion.travel_to_corner("bottom_left", style="jump")
    assert companion.destination is not None
    assert companion.action == "jump"

    companion.travel_to_corner("top_right", style="walk")
    assert companion.action == "walk"

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


def test_local_first_conversational_engine():
    """Verify local-first spoken answers without API key prompt."""
    from dock_twoo.brain.providers import query_llm, answer_locally, get_system_summary

    # 1. System summary pulls machine status
    summary = get_system_summary()
    assert isinstance(summary, str)
    assert len(summary) > 10

    # 2. Querying without any API key or profile returns natural voice response
    reply_system = query_llm("How is my system?", profile=None, api_key="")
    assert "API key" not in reply_system
    assert "Error" not in reply_system

    reply_time = query_llm("What time is it?", profile=None, api_key="")
    assert "currently" in reply_time.lower() or "pm" in reply_time.lower() or "am" in reply_time.lower()
    assert "API key" not in reply_time

    reply_hello = query_llm("Hello!", profile=None, api_key="")
    assert len(reply_hello) > 5
    assert "API key" not in reply_hello

    reply_dock = query_llm("What can you do?", profile=None, api_key="")
    assert "Brain" in reply_dock or "desktop" in reply_dock
    assert "API key" not in reply_dock


def test_voice_commands_router(tmp_path):
    """Verify voice commands for mascot movement, actions, memory inspection, and computer automation."""
    from dock_twoo.brain.commands import handle_voice_command, get_process_memory_usage
    mgr = BrainManager.get_instance()
    mgr.store = BrainStore(data_dir=tmp_path)

    # 1. Mascot movement voice commands
    r_jump = handle_voice_command("Brain, jump from the right corner to the left corner", mgr)
    assert r_jump is not None
    assert "Jumping" in r_jump
    assert mgr.companion.action == "jump"

    r_walk = handle_voice_command("Walk towards the top right", mgr)
    assert r_walk is not None
    assert "Walking" in r_walk
    assert mgr.companion.action == "walk"

    r_fly = handle_voice_command("Fly to the right", mgr)
    assert r_fly is not None
    assert "Flying" in r_fly
    assert mgr.companion.action == "fly"

    # 2. Gesture actions
    r_wave = handle_voice_command("Brain, wave", mgr)
    assert r_wave is not None
    assert "Waving" in r_wave

    r_climb = handle_voice_command("Brain, climb onto the dock", mgr)
    assert r_climb is not None
    assert "Climbing" in r_climb
    assert mgr.companion.action == "climb_dock"

    r_inspect = handle_voice_command("Brain, inspect window", mgr)
    assert r_inspect is not None
    assert "Inspecting" in r_inspect
    assert mgr.companion.action == "inspect_window"

    r_replace = handle_voice_command("Brain, replace text", mgr)
    assert r_replace is not None
    assert "replacing text" in r_replace.lower()
    assert mgr.companion.action == "replace_text"

    r_fold = handle_voice_command("Brain, fold your arms", mgr)
    assert r_fold is not None
    assert "standby" in r_fold.lower()
    assert mgr.companion.action == "fold_arms"

    # 3. Process Memory
    count, mb = get_process_memory_usage("python")
    assert count > 0
    assert mb > 0.0

    r_mem = handle_voice_command("What is my current memory usage in Python?", mgr)
    assert r_mem is not None
    assert "Python" in r_mem
    assert "megabytes" in r_mem or "gigabytes" in r_mem


def test_audio_listener_and_shortcuts():
    """Verify AudioListener and GlobalShortcutListener initialization and signal routing."""
    from dock_twoo.brain.listener import AudioListener, GlobalShortcutListener

    woken = []
    listener = AudioListener(wake_word="brain", on_wake=lambda: woken.append(True))
    assert listener.wake_word == "brain"
    assert listener.is_recording is False

    # Simulate wake detection
    listener.wake_detected.emit()
    assert len(woken) == 1

    # Shortcut listener initialization
    pressed = []
    shortcut = GlobalShortcutListener(shortcut_key="cmd_r", on_press=lambda: pressed.append(True))
    assert shortcut.shortcut_key == "cmd_r"


