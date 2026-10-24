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
    assert pose_turn.surprise == 0
    assert pose_turn.squash == 1

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
    assert status["voice_input"]["enabled"] is True
    assert status["voice_input"]["error"] == ""
    assert "active_profile" in status
    assert len(status["profiles"]) > 0

    mgr._on_audio_listener_error("Microphone stream error: permission denied")
    assert mgr.get_status()["voice_input"]["error"] == "Microphone stream error: permission denied"
    mgr.audio_listener_error = ""

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


def test_listener_vad_does_not_override_noise_rejection_with_energy():
    from dock_twoo.brain.listener import AudioListener
    listener = AudioListener()
    listener._vad = type("NoiseVAD", (), {"is_speech": lambda self, _frame, _rate: False})()
    assert listener._is_speech_frame(bytes(3200), rms=900, threshold=12.0) is False


def test_ambient_wake_checks_continue_when_background_never_gets_silent():
    from dock_twoo.brain.listener import AudioListener

    listener = AudioListener()
    listener.models.recognizer._recognizer = object()
    listener._vad = type("SpeechVAD", (), {"is_speech": lambda self, _frame, _rate: True})()
    checked = []
    listener._dispatch_wake_check = lambda frames: checked.append(frames)

    for _ in range(55):
        listener._handle_pcm_frame(b"\x64\x00" * 1600)

    assert len(checked) == 2
    assert [len(frames) for frames in checked] == [20, 40]


@pytest.mark.parametrize(
    ("transcript", "expected_wakes", "expected_commands"),
    [
        ("Brain.", 1, []),
        ("Hey Brain!", 1, []),
        ("Hello Brain.", 1, []),
        ("Hey Buddy!", 1, []),
        ("Hi there, Assistant.", 0, []),
        ("Brain, what time is it?", 0, ["what time is it"]),
        ("Hey Buddy, what time is it?", 0, ["what time is it"]),
        ("I saw rain earlier.", 0, []),
        ("The human brain has many functions.", 0, []),
        ("Background speech. Hey Brain!", 1, []),
    ],
)
def test_wake_word_transcription_variants(transcript, expected_wakes, expected_commands, qtbot):
    """Natural greetings and approved aliases wake; mentions and commands route correctly."""
    from dock_twoo.brain.listener import AudioListener

    listener = AudioListener(wake_word="Brain")
    # Keep unit tests offline; model-specific denoising has separate adapter coverage.
    listener.models.enhance_pcm = lambda audio, sample_rate=16000: audio
    listener._transcribe_pcm = lambda _pcm: transcript
    woken = []
    commands = []
    listener.wake_detected.connect(lambda: woken.append(True))
    listener.turn_completed.connect(commands.append)

    listener._check_wake_word([bytes(6400)])

    # Backup ASR activates capture only. It must not greet or execute a partial
    # four-second window before the user has completed their whole statement.
    assert woken == [] and commands == []
    listener._is_speech_frame = lambda *_args: False
    for _ in range(16):
        listener._handle_pcm_frame(bytes(3200))
    if expected_wakes or expected_commands:
        qtbot.waitUntil(lambda: bool(woken or commands), timeout=2000)

    assert len(woken) == expected_wakes
    assert commands == expected_commands


def test_missing_transformer_checkpoints_never_block_live_wake_audio(tmp_path, monkeypatch):
    """A missing HF download must fall through instead of hanging the microphone thread."""
    import platform
    from dock_twoo.brain.voice_models import LocalVoiceModels

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("HUGGINGFACE_HUB_CACHE", str(tmp_path / "hub"))
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    models = LocalVoiceModels(tmp_path / "models")
    pcm = bytes(16000)
    models._get_enhancer = lambda: (_ for _ in ()).throw(AssertionError("must not download in live listener"))
    models._get_asr = lambda: (_ for _ in ()).throw(AssertionError("must not download in live listener"))

    assert models.enhance_pcm(pcm) == pcm
    assert models.transcribe_pcm(pcm) == ""
    assert models.errors["recognizer"] == "unavailable (speech checkpoint is not downloaded)"


def test_missing_wake_models_download_in_background(tmp_path, monkeypatch):
    """First-run weights download outside the microphone worker and are retryable."""
    import platform
    from dock_twoo.brain.voice_models import LocalVoiceModels

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    models = LocalVoiceModels(tmp_path / "models")
    downloads = []
    models.model_weights_cached = lambda _model_id: False
    models._download_model = lambda component, model_id: downloads.append((component, model_id))

    models.start_model_downloads()
    for thread in models._download_threads.values():
        thread.join(timeout=2)

    assert set(downloads) == {
        ("recognizer", models.ASR_MODEL),
        ("denoiser", models.ENHANCER_MODEL),
        ("tts", models.TTS_MODEL),
    }


def test_continuous_multiturn_conversation_session(tmp_path):
    """Verify hands-free multi-turn session persistence and farewell exits."""
    mgr = BrainManager.get_instance()
    mgr.store = BrainStore(data_dir=tmp_path)

    # 1. Start session on wake
    mgr._on_wake_detected()
    assert mgr.in_conversation_session is True

    # 2. Complete a statement: Brain responds and speech finishes
    mgr._on_turn_complete("How is my system?")
    assert mgr.in_conversation_session is True
    assert len(mgr.conversation_history) >= 1

    # When speech finishes, it automatically resumes listening for follow-ups hands-free!
    mgr._on_speech_finished()
    assert mgr.in_conversation_session is True
    assert mgr.companion.activity == "listening"
    assert mgr.listener.is_recording is True

    # 3. Follow-up statement
    mgr._on_turn_complete("What time is it?")
    assert mgr.in_conversation_session is True
    assert len(mgr.conversation_history) >= 2

    # 4. User says goodbye / farewell phrase -> terminates session
    mgr._on_turn_complete("Goodbye, that's all for now")
    assert mgr.in_conversation_session is False


def test_grounded_factual_research(tmp_path):
    """Verify research answers factual questions accurately without echoing or repeating prompt."""
    from dock_twoo.brain.commands import handle_voice_command, execute_web_research
    mgr = BrainManager.get_instance()
    mgr.store = BrainStore(data_dir=tmp_path)

    reply = handle_voice_command("What is superposition in quantum computing?", mgr)
    assert reply is not None
    # Must NOT echo the question
    assert not reply.lower().startswith("you are asking about")
    assert not reply.lower().startswith("what is superposition")
    # Must contain factual physics explanation
    assert "qubit" in reply.lower() or "quantum" in reply.lower() or "superposition" in reply.lower()


def test_profile_walking_and_window_surface(tmp_path):
    """Verify side profile walking orientation and window top edge walking."""
    from dock_twoo.brain.vision import get_desktop_surfaces
    mgr = BrainManager.get_instance()
    mgr.store = BrainStore(data_dir=tmp_path)
    companion = mgr.companion

    # Directional profile facing
    companion.move(200, 200)
    companion.play_action("walk", destination=QPoint(600, 200))
    assert companion.facing == 1.0

    companion.play_action("walk", destination=QPoint(50, 200))
    assert companion.facing == -1.0

    # Window surface detection
    surfaces = get_desktop_surfaces()
    assert len(surfaces) >= 1
    assert surfaces[0].surface_y >= 0
    assert surfaces[0].right_x > surfaces[0].left_x

    # Walk on window surface
    companion.walk_window_surface()
    assert companion.action in ("jump", "walk_window")


def test_interactive_energy_ball(tmp_path):
    """Verify DesktopBall creation, physics kick, and companion play."""
    mgr = BrainManager.get_instance()
    mgr.store = BrainStore(data_dir=tmp_path)
    companion = mgr.companion

    companion.play_ball()
    assert companion.desktop_ball is not None
    assert companion.desktop_ball.active is True

    # Test kick physics
    initial_vx = companion.desktop_ball.vel_x
    companion.desktop_ball.kick(450.0, -350.0)
    assert companion.desktop_ball.vel_x == 450.0
    assert companion.desktop_ball.vel_y == -350.0

    ball = companion.desktop_ball
    companion.stop_ball()
    assert ball.active is False
    assert companion.desktop_ball is None


def test_dynamic_wake_greeting(tmp_path):
    """Verify first vs subsequent realistic greetings when activating Brain."""
    from dock_twoo.brain.commands import handle_voice_command
    mgr = BrainManager.get_instance()
    mgr.store = BrainStore(data_dir=tmp_path)
    mgr.wake_count = 0
    mgr.last_wake_time = 0.0
    mgr._last_wake_reply = ""

    # First activation: welcoming greeting
    first_reply = mgr.get_wake_greeting()
    assert any(w in first_reply for w in ("like to do", "help you today", "working on"))
    assert mgr.wake_count == 1

    # Second activation: natural active short response
    second_reply = mgr.get_wake_greeting()
    assert any(w in second_reply.lower() for w in ("here", "tell me", "listening", "mind", "what's up", "all ears", "go ahead"))
    assert mgr.wake_count == 2
    assert second_reply != first_reply

    # Third activation via handle_voice_command("Brain", mgr)
    third_reply = handle_voice_command("Brain", mgr)
    assert any(w in third_reply.lower() for w in ("here", "tell me", "listening", "mind", "what's up", "all ears", "go ahead"))
    assert third_reply != second_reply


def test_wake_greeting_is_owner_aware(tmp_path, qapp):
    mgr = BrainManager.get_instance()
    mgr.store = BrainStore(data_dir=tmp_path)
    mgr.store.set_setting("owner_first_name", "Karthik")
    mgr.wake_count = 0
    mgr.last_wake_time = 0.0

    assert "Karthik" in mgr.get_wake_greeting(owner_verified=True)
    assert mgr.get_wake_greeting(owner_verified=False) == "Hey Buddy, what can I do for you?"
    assert mgr.get_wake_greeting(owner_verified=None) == "Hey Buddy, what can I do for you?"


def test_speaker_match_is_fail_closed_and_uses_cosine_threshold(tmp_path, monkeypatch):
    from dock_twoo.brain.voice_models import LocalVoiceModels

    models = LocalVoiceModels(tmp_path / "models")
    monkeypatch.setattr(models, "speaker_embedding", lambda _pcm, _rate: [1.0, 0.0])
    assert models.verify_owner(b"sample", [1.0, 0.0]) is True
    assert models.verify_owner(b"sample", [0.0, 1.0]) is False
    monkeypatch.setattr(models, "speaker_embedding", lambda _pcm, _rate: None)
    assert models.verify_owner(b"sample", [1.0, 0.0]) is None


def test_props_voice_commands_lifecycle(tmp_path):
    """Verify voice commands for keeping toys inside, playing with props, and stopping."""
    from dock_twoo.brain.commands import handle_voice_command
    mgr = BrainManager.get_instance()
    mgr.store = BrainStore(data_dir=tmp_path)
    companion = mgr.companion

    # 1. Play with hammer
    rep_hammer = handle_voice_command("Brain, play with hammer", mgr)
    assert rep_hammer is not None
    assert "hammer" in rep_hammer.lower()
    assert companion.active_prop is not None
    assert companion.active_prop.prop_type == "hammer"

    # 2. Keep the ball/prop inside
    rep_stow = handle_voice_command("keep the ball inside", mgr)
    assert rep_stow is not None
    assert "storage" in rep_stow.lower() or "away" in rep_stow.lower()

    # 3. Play with parachute
    rep_parachute = handle_voice_command("Brain, deploy parachute", mgr)
    assert rep_parachute is not None
    assert "parachute" in rep_parachute.lower()
    assert companion.active_prop.prop_type == "parachute"

    # 4. Stop playing
    rep_stop = handle_voice_command("stop playing", mgr)
    assert rep_stop is not None

    # 5. Play with balloon
    rep_balloon = handle_voice_command("play with balloon", mgr)
    assert rep_balloon is not None
    assert "balloon" in rep_balloon.lower()
    assert companion.active_prop.prop_type == "balloon"


def test_carry_prop_and_window_push(tmp_path):
    """Verify carry-and-play, naughty window push, and walking on text box commands."""
    from dock_twoo.brain.commands import handle_voice_command
    mgr = BrainManager.get_instance()
    mgr.store = BrainStore(data_dir=tmp_path)
    companion = mgr.companion

    # 1. Carry prop to top right
    rep_carry = handle_voice_command("go to the top right and then play", mgr)
    assert rep_carry is not None
    assert "top right" in rep_carry.lower()
    assert companion.action == "walk"

    # 2. Window push
    rep_push = handle_voice_command("push the window", mgr)
    assert rep_push is not None
    assert "push" in rep_push.lower()

    # 3. Walk on text box
    rep_text_box = handle_voice_command("walk on top of text box", mgr)
    assert rep_text_box is not None
    assert "text box" in rep_text_box.lower()


def test_tightened_resource_gating():
    """Verify that generic words do NOT dump hardware/resources, but explicit requests do."""
    from dock_twoo.brain.providers import answer_locally

    # Generic statements should not trigger system resource dump
    general_reply = answer_locally("How is the system today?")
    assert "cpu" not in general_reply.lower()
    assert "battery" not in general_reply.lower()

    general_reply2 = answer_locally("Give me a status update")
    assert "cpu" not in general_reply2.lower()
    assert "battery" not in general_reply2.lower()

    # Explicit resource request SHOULD trigger resource summary
    explicit_reply = answer_locally("what are my resources?")
    assert "cpu" in explicit_reply.lower() or "battery" in explicit_reply.lower() or "memory" in explicit_reply.lower()


def test_top_left_corner_voice_command(tmp_path):
    """Verify voice commands for top-left corner with hyphens, with/without corner, etc."""
    from dock_twoo.brain.commands import handle_voice_command
    mgr = BrainManager.get_instance()
    mgr.store = BrainStore(data_dir=tmp_path)
    companion = mgr.companion

    # "go to the top-left corner"
    rep1 = handle_voice_command("Brain, go to the top-left corner", mgr)
    assert rep1 is not None
    assert "top left" in rep1.lower()
    assert companion.action == "walk"

    # "go to top-left"
    rep2 = handle_voice_command("go to top-left", mgr)
    assert rep2 is not None
    assert "top left" in rep2.lower()

    # "move to top left corner"
    rep3 = handle_voice_command("move to top left corner", mgr)
    assert rep3 is not None
    assert "top left" in rep3.lower()


def test_afconvert_flac_encoding(tmp_path):
    """Verify afconvert FLAC conversion produces valid FLAC audio data."""
    import speech_recognition as sr
    import wave

    test_wav = tmp_path / "test.wav"
    with wave.open(str(test_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 3200)

    with sr.AudioFile(str(test_wav)) as src:
        r = sr.Recognizer()
        aud = r.record(src)
    flac_bytes = aud.get_flac_data()
    assert len(flac_bytes) > 0
    assert flac_bytes[:4] == b"fLaC"






