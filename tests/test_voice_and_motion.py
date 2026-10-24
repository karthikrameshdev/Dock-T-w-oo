"""Regressions for wake gating, playback echo, articulated gait, and desktop placement."""

import math
import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from dock_twoo.brain.animation import gait_at, two_bone_joint
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
    listener.wake_detected.connect(lambda: woken.append(True))
    for _ in range(5):
        listener._handle_pcm_frame(b'\x64\x00' * 1600)
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


def test_support_foot_is_planted_and_swing_foot_lifts():
    first = gait_at(7)[0]
    second = gait_at(15)[0]
    assert first.stance and second.stance
    assert 7 + first.x == pytest.approx(15 + second.x)
    left, right = gait_at(51)
    assert not left.stance and left.lift > 5
    assert right.stance and right.lift == 0


def test_elbows_and_knees_preserve_bone_lengths():
    start, end = (0, 0), (12, 30)
    joint = two_bone_joint(start, end, 20, 22)
    assert math.dist(start, joint) == pytest.approx(20)
    assert math.dist(joint, end) == pytest.approx(22)


def test_side_profile_articulates_legs_between_steps(companion):
    companion.action = 'walk'
    companion.turn_progress = 1
    companion.gait_blend = 1
    frames = []
    for distance in (0, 17):
        companion.gait_distance = distance
        image = QImage(companion.size(), QImage.Format.Format_ARGB32)
        image.fill(0)
        companion.render(image)
        frames.append(image.copy(65, 180, 145, 62))
    assert frames[0] != frames[1]


def test_turn_blend_preserves_opacity_on_overlapping_body_pixels(companion):
    import numpy as np
    masks = []
    for turn in (0, .5, .25):
        companion.turn_progress = turn
        image = QImage(companion.size(), QImage.Format.Format_ARGB32)
        image.fill(0)
        companion.render(image)
        masks.append(np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.bytesPerLine())[:, 3::4].copy())
    # Keep the original texture's alpha instead of darkening it during turns.
    assert (masks[2][90:120, 120:145] == masks[0][90:120, 120:145]).all()


@pytest.mark.parametrize('action', ['walk', 'climb', 'climb_dock', 'walk_window', 'chase_ball'])
@pytest.mark.parametrize('facing', [-1, 1])
def test_motion_turns_head_with_the_same_live_face(companion, action, facing, monkeypatch):
    from dock_twoo.brain.animation import Pose
    from PySide6.QtGui import QPainter
    companion.pose = Pose(wink=.3)
    companion.gait_blend = 0
    companion._render_facing = facing
    original = companion._paint_face
    faces, scales = [], []

    def capture(painter, visible_eyes=(0, 1)):
        assert visible_eyes == (0, 1)
        canonical = QImage(168, 202, QImage.Format.Format_ARGB32)
        canonical.fill(0)
        target = QPainter(canonical)
        target.scale(168, 202)
        original(target, visible_eyes)
        target.end()
        faces.append(canonical)
        scales.append(painter.transform().m11())
        original(painter, visible_eyes)

    monkeypatch.setattr(companion, '_paint_face', capture)
    image = QImage(companion.size(), QImage.Format.Format_ARGB32)
    companion.render(image)
    companion.action = action
    for turn in (0, .25, .5, .75, 1):
        companion.turn_progress = turn
        image.fill(0)
        companion.render(image)
        assert faces[-1] == faces[0]
    # The face keeps its design, but its projection actually rotates with the head.
    assert abs(scales[-1]) == pytest.approx(abs(scales[0]) * .5)
    assert scales[-1] * facing > 0


def test_roaming_never_pushes_or_resizes_external_windows(companion, monkeypatch):
    import dock_twoo.brain.mascot as module
    companion.store.set_setting('roaming', True)
    companion.show()
    companion.last_dragged = 0
    companion.last_user_interaction = time.monotonic()
    monkeypatch.setattr(module.random, 'random', lambda: .4)
    monkeypatch.setattr(companion, 'push_window', lambda: pytest.fail('Roaming must not resize windows'))
    companion._roam()
    assert companion.action == 'inspect_window'


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
    assert companion.destination.x() >= companion.screen().availableGeometry().left()
    assert companion.destination.y() >= companion.screen().availableGeometry().top()


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
    assert companion.destination.x() == companion.screen().availableGeometry().left()
    assert companion.testAttribute(__import__('PySide6.QtCore', fromlist=['Qt']).Qt.WidgetAttribute.WA_TransparentForMouseEvents)
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
