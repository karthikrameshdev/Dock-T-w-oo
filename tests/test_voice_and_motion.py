"""Regressions for wake gating, playback echo, articulated gait, and desktop placement."""

import math
import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from dock_twoo.brain.listener import AudioListener, command_after_keyword
from dock_twoo.brain.mascot import Companion
from dock_twoo.brain.profiles import ProfileManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.recognition import LocalRecognizer
from dock_twoo.os_integration.margin_manager import DesktopMarginManager, desktop_icon_targets
from dock_twoo.config import DockConfig


@pytest.fixture
def companion(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = BrainStore(tmp_path)
    widget = Companion(SimpleNamespace(store=store, profile_mgr=ProfileManager(store)))
    for timer in (widget.activity_timer, widget.motion_timer, widget.blink_timer, widget.roam_timer):
        timer.stop()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


@pytest.mark.parametrize(('text', 'accepted', 'command'), [
    ('Brain. Brain. Brain. Brain.', True, ''),
    ('plane', True, ''),
    ('Hey Bobby', True, ''),
    ('A brain what time is it?', True, 'what time is it'),
    ('May grain what time is it?', True, 'what time is it'),
    ('Bring me a cup of tea.', False, ''),
    ('The weather is beautiful today.', False, ''),
])
def test_keyword_confirmation_handles_observed_dictation_errors(text, accepted, command):
    assert command_after_keyword(text) == (accepted, command)


def test_streaming_keyword_bypasses_the_voice_gate():
    app = QApplication.instance() or QApplication([])
    listener = AudioListener()
    detector = SimpleNamespace(ready=True, feed=lambda _pcm: 'BRAIN', reset=lambda: None)
    listener.wake_detector = detector
    listener._vad = SimpleNamespace(is_speech=lambda _pcm, _rate: False)
    listener._transcribe_pcm = lambda _pcm: 'Brain.'
    woken = []
    started = []
    listener.wake_detected.connect(lambda: woken.append(True))
    listener.wake_started.connect(lambda: started.append(True))
    for _ in range(5):
        listener._handle_pcm_frame(b'\x64\x00' * 1600)
    assert started == [True]
    assert woken == []
    for _ in range(15):
        listener._handle_pcm_frame(bytes(3200))
    deadline = time.monotonic() + 1
    while not woken and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert woken == [True]


def test_dictation_backup_runs_when_ready_keyword_model_misses():
    listener = AudioListener()
    listener.wake_detector = SimpleNamespace(ready=True, feed=lambda _pcm: '', reset=lambda: None)
    listener._vad = SimpleNamespace(is_speech=lambda _pcm, _rate: False)
    windows = []
    listener._dispatch_wake_check = lambda frames: windows.append(frames)
    for _ in range(60):
        listener._handle_pcm_frame(b'\x64\x00' * 1600)
    assert [len(frames) for frames in windows] == [20, 40, 40]


def test_playback_echo_and_its_tail_cannot_wake_the_agent(monkeypatch):
    import dock_twoo.brain.listener as module
    clock = [10.0]
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    listener = AudioListener()
    frames = []
    listener.wake_detector = SimpleNamespace(ready=True, feed=lambda pcm: frames.append(pcm) or '', reset=lambda: None)
    pcm = b'\x64\x00' * 1600
    listener.set_output_active(True)
    listener._handle_pcm_frame(pcm)
    listener.set_output_active(False)
    clock[0] = 10.2
    listener._handle_pcm_frame(pcm)
    assert frames == []
    clock[0] = 10.4
    listener._handle_pcm_frame(pcm)
    assert frames == []  # Busy playback remains stop-only until explicitly armed.
    listener.arm_wake()
    listener._handle_pcm_frame(pcm)
    assert frames == [pcm]


def test_cancelled_transcription_cannot_restart_a_conversation():
    import threading
    app = QApplication.instance() or QApplication([])
    listener = AudioListener()
    entered, release = threading.Event(), threading.Event()
    turns = []
    listener.turn_completed.connect(turns.append)

    def transcribe(_pcm):
        entered.set()
        release.wait(1)
        return 'What time is it?'

    listener._transcribe_pcm = transcribe
    worker = threading.Thread(target=listener._process_utterance, args=([bytes(16000)], listener._capture_generation))
    worker.start()
    assert entered.wait(1)
    listener.arm_wake()
    release.set()
    worker.join(1)
    app.processEvents()
    assert turns == []


def test_cached_command_model_starts_without_contacting_hugging_face(tmp_path, monkeypatch):
    import huggingface_hub
    import sherpa_onnx
    recognizer = LocalRecognizer(tmp_path)
    folder = recognizer.cache_dir / f"models--{recognizer.MODEL_ID.replace('/', '--')}" / 'snapshots' / recognizer.REVISION
    folder.mkdir(parents=True)
    for filename in recognizer.FILES:
        (folder / filename).write_bytes(b'cached model fixture')
    monkeypatch.setattr(huggingface_hub, 'snapshot_download', lambda *_args, **_kwargs: pytest.fail('Cached startup must remain offline'))
    monkeypatch.setattr(sherpa_onnx.OfflineRecognizer, 'from_whisper', lambda **_kwargs: object())
    assert recognizer.load(allow_download=True)
    assert recognizer.ready


















def test_turn_callback_runs_once_and_cancelled_turns_cannot_resume(companion, monkeypatch):
    import dock_twoo.brain.mascot as module
    clock = [100.0]
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    companion.show()
    calls = []
    companion._yaw = companion.turn_progress = 1
    companion.turn_to_user(on_turned=lambda: calls.append('finished'))
    for _ in range(75):
        clock[0] += 1 / 60
        companion._advance_motion()
    assert calls == ['finished']
    assert companion._yaw == 0
    assert companion.action is None
    companion.turn_to_side(-1, on_turned=lambda: calls.append('cancelled'))
    companion.play_action('wave')
    for _ in range(120):
        clock[0] += 1 / 60
        companion._advance_motion()
    assert calls == ['finished']


def test_turn_walk_inspect_return_keeps_a_continuous_orientation(companion, monkeypatch):
    import dock_twoo.brain.mascot as module
    clock = [100.0]
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    companion.show()
    companion.move(100, 200)
    started = []

    def inspect():
        started.append('inspect')
        companion.play_action('inspect_window', duration=1.2, keep_orientation=True)
        companion.arrival = companion.turn_to_user

    def walk():
        started.append('walk')
        companion.play_action('walk_window', QPoint(180, 200), duration=1.2)
        companion.arrival = lambda: companion.turn_to_side(-1, on_turned=inspect)

    companion.turn_to_side(1, on_turned=walk)
    previous = companion._yaw
    for _ in range(420):
        clock[0] += 1 / 60
        companion._advance_motion()
        assert abs(companion._yaw - previous) <= 2.8 / 60 + .011
        previous = companion._yaw
        if companion.action == 'walk_window':
            assert companion._yaw == 1
        elif companion.action == 'inspect_window':
            assert companion._yaw == -1
    assert started == ['walk', 'inspect']
    assert companion.action is None
    assert companion._yaw == 0


def test_roaming_never_pushes_or_resizes_external_windows(companion, monkeypatch):
    import dock_twoo.brain.mascot as module
    companion.store.set_setting('roaming', True)
    companion.show()
    companion.last_dragged = 0
    companion.last_user_interaction = time.monotonic()
    monkeypatch.setattr(module.random, 'random', lambda: .4)
    monkeypatch.setattr(companion, 'push_window', lambda: pytest.fail('Roaming must not resize windows'))
    companion._roam()
    assert companion.action in companion.actions


def test_eyes_recenter_after_a_glance(companion):
    companion.gaze = QPoint(5000, 5000)
    cursor = QPoint(300, 300)
    for tick in range(15):
        companion._update_gaze(10 + tick * .03, cursor)
    assert companion._gaze_offset.manhattanLength() > .005
    for tick in range(40):
        companion._update_gaze(13 + tick * .03, cursor)
    assert companion._gaze_offset.manhattanLength() < .0001


def test_climb_has_vertical_travel_and_stays_on_screen(companion):
    companion.move(200, 200)
    companion.play_action('climb_dock')
    assert companion.destination.y() < 200
    companion.play_action('walk', QPoint(-10000, -10000))
    visible = companion.body_region().boundingRect().translated(companion.destination)
    assert companion.screen().availableGeometry().contains(visible)


def test_parachute_reaches_altitude_descends_then_lands_before_stowing(companion):
    companion.show();companion.move(250,450)
    companion.play_action('parachute')
    assert companion.action=='fly' and companion.destination.y()<companion.y()
    companion.motion_started=time.monotonic()-companion.motion_duration-.01
    companion._advance_motion()
    assert companion.action=='parachute'
    launch=QPoint(companion.motion_start);landing=QPoint(companion.destination)
    assert landing.y()>launch.y()+100
    def phase(p):
        companion.motion_started=time.monotonic()-p*companion.motion_duration
        companion._advance_motion()
    phase(.05);assert abs(companion.y()-launch.y())<=1
    phase(.5);assert launch.y()<companion.y()<landing.y()
    phase(.87);assert companion.pos()==landing
    phase(.96);assert companion.pos()==landing and companion.action=='parachute'
    phase(1.01);assert companion.pos()==landing and companion.action=='land'


def test_parachute_curve_only_descends_after_canopy_opens():
    from dock_twoo.brain.animation import travel_point
    start,end=(100,30),(140,600)
    points=[travel_point(start,end,p/100,'parachute') for p in range(101)]
    assert all(point==start for point in points[:13])
    assert all(point==end for point in points[86:])
    assert all(a[1]<=b[1] for a,b in zip(points,points[1:]))


def test_follow_cursor_retargets_immediately_at_a_calm_speed(companion):
    assert not companion.isVisible()
    companion.move(200, 200)
    companion.set_follow_cursor(True)
    assert companion.isVisible()
    companion.follow_timer.stop()
    companion._follow_cursor_step(QPoint(700, 424), elapsed=.1)
    first = companion.pos()
    assert 200 < first.x() <= 209
    phase = companion.gait_distance
    companion._follow_cursor_step(QPoint(132, 424), elapsed=.1)
    assert companion.x() < first.x()
    assert companion.gait_distance > phase
    assert companion.destination.x() + companion.body_region().boundingRect().left() >= companion.screen().availableGeometry().left()
    assert not companion.testAttribute(__import__('PySide6.QtCore', fromlist=['Qt']).Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    companion.set_follow_cursor(False)
    assert companion.action is None


def test_follow_cursor_pauses_for_voice_interaction(companion):
    companion.show()
    companion.move(200, 200)
    companion.set_follow_cursor(True)
    companion.follow_timer.stop()
    companion.activity = 'listening'
    companion._follow_cursor_step(QPoint(700, 424), elapsed=.1)
    assert companion.pos() == QPoint(200, 200)


@pytest.mark.parametrize('edge,dock', [
    ('right', QRect(1440, 30, 60, 900)), ('left', QRect(0, 30, 60, 900)),
    ('top', QRect(0, 30, 1500, 60)), ('bottom', QRect(0, 900, 1500, 60)),
])
def test_desktop_icons_clear_each_dock_edge_without_leaving_screen(edge, dock):
    screen = QRect(0, 30, 1500, 930)
    point = (dock.center().x(), dock.center().y())
    items = {f'Screenshot {i}.png': point for i in range(12)}
    targets = desktop_icon_targets(items, dock, edge, 8, screen, 96)
    assert len(targets) == len(items)
    for x, y in targets.values():
        assert screen.contains(QPoint(x, y))
        if edge == 'right': assert x + 72 <= dock.left() - 8
        elif edge == 'left': assert x - 72 >= dock.right() + 1 + 8
        elif edge == 'top': assert y - 56 >= dock.bottom() + 1 + 8
        else: assert y + 76 <= dock.top() - 8
    assert len(set(targets.values())) == len(targets)


def test_mutated_config_restores_the_actual_previous_dock_edge(monkeypatch):
    config = DockConfig(edge='right')
    manager = DesktopMarginManager(config)
    restored = []
    monkeypatch.setattr(manager, 'restore_all_adjusted_windows', lambda vacated_edge=None: restored.append(vacated_edge))
    monkeypatch.setattr(manager, 'restore_all_adjusted_desktop_icons', lambda vacated_edge=None: restored.append(vacated_edge))
    manager._dock_rect = QRect(1440, 30, 60, 900)
    config.edge = 'top'  # ConfigManager updates this same object in place.
    manager.update_config(config)
    assert restored == ['right', 'right']
    assert manager._dock_rect is None


def test_screenshot_protection_is_active_when_window_reservation_is_off(monkeypatch):
    import threading
    app = QApplication.instance() or QApplication([])
    manager = DesktopMarginManager(DockConfig(edge='right', reserve_screen_space=False))
    manager._dock_rect = QRect(1440, 30, 60, 900)
    manager._running = True
    scanned = threading.Event()
    monkeypatch.setattr(manager, '_check_and_clamp_desktop_icons', lambda *_args: scanned.set())
    manager._schedule_icon_scan()
    assert scanned.wait(1)
    manager._running = False


def test_running_uses_the_run_clip_and_turns_toward_the_destination(companion):
    companion.travel_to_corner('top_left', style='run')
    assert companion.action == 'run'
    assert companion.turn_target == 1.0
    assert companion.destination is not None
    companion.stop_motion()
