"""Regressions for actual microphone boundaries, bounded TTS and cursor ownership."""
import time
import threading
from types import SimpleNamespace

from dock_twoo.brain.voice_models import LocalVoiceModels
from dock_twoo.ui.dock_window import DockWindow
from dock_twoo.os_integration.screen_manager import MacOSCursorHelper


def test_unprepared_onnx_voice_never_blocks_the_audio_caller(tmp_path, monkeypatch):
    models = LocalVoiceModels(tmp_path)
    monkeypatch.setattr(models.local_tts,'engine',None)
    start = time.monotonic()
    assert not models.synthesize_wav('Hello',tmp_path/'speech.wav')
    assert time.monotonic()-start < .05
    assert not (tmp_path/'speech.wav').exists()


def test_dock_does_not_force_an_arrow_when_it_does_not_own_the_cursor(monkeypatch):
    arrows = []
    monkeypatch.setattr(MacOSCursorHelper, 'set_arrow', lambda: arrows.append(True))
    dock = SimpleNamespace(_has_hand_cursor_override=False)
    for _ in range(50):
        DockWindow._restore_default_cursor(dock)
    assert arrows == []


def test_indicator_states_and_effects_use_the_user_requested_colors():
    import shutil, subprocess
    from pathlib import Path
    import pytest
    node=shutil.which('node')
    if not node: pytest.skip('Node is required for the actual Three.js indicator check')
    script=Path(__file__).resolve().parents[1]/'scripts/verify_brain_indicator.mjs'
    result=subprocess.run([node,str(script)],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr


def test_speech_output_failure_is_not_reported_as_healthy(qapp):
    from dock_twoo.brain.speech import SpeechPlayback
    speech=SpeechPlayback()
    speech._finish(speech.generation,'Output device unavailable')
    assert speech.last_error=='Output device unavailable'


def test_companion_hit_region_and_drag_resilience(qapp, tmp_path):
    from types import SimpleNamespace
    from PySide6.QtCore import Qt, QPoint, QPointF
    from PySide6.QtGui import QMouseEvent, QRegion
    from dock_twoo.brain.mascot import Companion
    from dock_twoo.brain.storage import BrainStore
    from dock_twoo.brain.profiles import ProfileManager

    store = BrainStore(tmp_path)
    companion = Companion(SimpleNamespace(store=store, profile_mgr=ProfileManager(store), active_screen_id='default', companions={'default': None}))
    companion.show()

    # 1. Hit region falls back to provisional body even when input_region is empty
    hit = companion.input_hit_region()
    assert not hit.isEmpty()
    assert hit.contains(QPoint(100, 100))

    # 2. Simulate resource release on sleep/hide
    companion.input_region = QRegion()
    companion.has_input_shape = False
    companion.apply_input_mask()
    hit_after_release = companion.input_hit_region()
    assert not hit_after_release.isEmpty()
    assert hit_after_release.contains(QPoint(100, 100))

    # 3. Simulate mouse drag and drop
    press = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(100, 100), QPointF(companion.x() + 100, companion.y() + 100), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    companion.mousePressEvent(press)
    assert companion.origin is not None

    move = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(150, 150), QPointF(companion.x() + 150, companion.y() + 150), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    companion.mouseMoveEvent(move)
    assert companion.moved is True

    release = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPointF(150, 150), QPointF(companion.x() + 150, companion.y() + 150), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    companion.mouseReleaseEvent(release)
    assert companion.origin is None

    companion.close()
    companion.deleteLater()


def test_pin_native_orders_front_and_sets_status_level(qapp, monkeypatch):
    from dock_twoo.brain.mascot import pin_native
    from PySide6.QtWidgets import QWidget
    w = QWidget()
    messages = []
    monkeypatch.setattr('dock_twoo.brain.mascot.mac_window', lambda widget: (123, lambda res, target, sel, *args: messages.append((sel, args))))
    pin_native(w, level=8)
    selectors = [m[0] for m in messages]
    assert 'setLevel:' in selectors
    assert any(m[0] == 'setLevel:' and m[1][0][1] == 8 for m in messages)
    assert 'orderFrontRegardless' in selectors
    w.deleteLater()
