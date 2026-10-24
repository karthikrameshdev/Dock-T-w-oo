"""Regressions for actual microphone boundaries, bounded TTS and cursor ownership."""
import time
import threading
from types import SimpleNamespace

from dock_twoo.brain.voice_models import LocalVoiceModels
from dock_twoo.ui.dock_window import DockWindow
from dock_twoo.os_integration.screen_manager import MacOSCursorHelper


def test_slow_optional_tts_cannot_block_the_voice_response(tmp_path, monkeypatch):
    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    models = LocalVoiceModels(tmp_path)
    release = threading.Event()
    class SlowVoice:
        def generate_custom_voice(self, **kwargs):
            release.wait(2)
            return iter([])
    models._tts = SlowVoice()
    start = time.monotonic()
    assert not models.synthesize_wav('Hello', tmp_path/'speech.wav', budget=.05)
    assert time.monotonic()-start < .4
    assert not (tmp_path/'speech.wav').exists()
    # A still-running optional model must not spawn another blocked request.
    start = time.monotonic()
    assert not models.synthesize_wav('Hello again', tmp_path/'second.wav')
    assert time.monotonic()-start < .05
    release.set()


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
