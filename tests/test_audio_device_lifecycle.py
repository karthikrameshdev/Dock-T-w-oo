"""Audio shutdown and repeated interruptions must leave bounded resident work."""
import threading
import weakref
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtCore import QObject

from dock_twoo.brain.audio import SpeechClip
from dock_twoo.brain.audio_devices import DefaultAudioDevices, MicrophoneConverter, PlaybackRequest
from dock_twoo.brain.speech import SpeechPlayback


def test_repeated_input_close_releases_capture_buffers_and_idle_timer(qapp, monkeypatch):
    route = DefaultAudioDevices()
    stopped = []

    def open_input():
        route.source = SimpleNamespace(stop=lambda: stopped.append(True), deleteLater=lambda: None)
        route.input_io = object()
        route._converter = MicrophoneConverter(48000)
        route._input_tail = b'partial frame'

    monkeypatch.setattr(route, '_open_input', open_input)
    for _ in range(200):
        route.start_input()
        converter = weakref.ref(route._converter)
        assert route.timer.isActive()
        route.stop_input()
        assert not route.timer.isActive()
        assert route.source is None and route.input_io is None
        assert route._converter is None and not route._input_tail
        assert converter() is None
    assert len(stopped) == 200
    route.close()


def test_output_keeps_timer_only_until_last_audio_lane_closes(qapp, monkeypatch):
    route = DefaultAudioDevices()
    monkeypatch.setattr(route, '_open_output', lambda: None)
    request = PlaybackRequest(SpeechClip.from_pcm(bytes(3200), 16000), threading.Event(), lambda _: None, lambda _: None)
    route._start_playback(request)
    route.stop_input()
    assert route.timer.isActive()  # An answer must continue with the mic disabled.
    route._finish_output()
    assert request.done.is_set() and not route.timer.isActive()

    route._want_input = True
    route.timer.start()
    route._finish_output()
    assert route.timer.isActive()  # Capture/reconnection is still requested.
    route.close()
    assert not route.timer.isActive()


def test_rapid_speech_replacements_keep_one_worker_and_only_latest_pending(qtbot, monkeypatch):
    playback = SpeechPlayback()
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def worker(token, text, cancel, *_):
        calls.append((text, cancel))
        if len(calls) == 1:
            entered.set()
            release.wait(5)

    monkeypatch.setattr(playback, '_play_worker', worker)
    try:
        playback.start('First statement')
        assert entered.wait(1)
        first_worker = playback.worker
        for index in range(200):
            playback.start(f'Statement {index}')
        assert playback.worker is first_worker
        assert len(calls) == 1 and calls[0][1].is_set()
        assert playback._pending_speech[1] == 'Statement 199'
        release.set()
        qtbot.waitUntil(lambda: len(calls) == 2)
        assert calls[1][0] == 'Statement 199'
        assert playback._pending_speech is None
        assert not playback._speech_start_timer.isActive()
    finally:
        release.set()
        playback.stop()
        if playback.worker:
            playback.worker.join(1)
        playback.audio_devices.close()


def test_stop_discards_pending_speech_while_cancelled_inference_finishes(qtbot, monkeypatch):
    playback = SpeechPlayback()
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def worker(token, text, cancel, *_):
        calls.append(text)
        entered.set()
        release.wait(5)

    monkeypatch.setattr(playback, '_play_worker', worker)
    try:
        playback.start('Old statement')
        assert entered.wait(1)
        playback.start('Pending statement')
        playback.stop()
        assert playback._pending_speech is None
        assert not playback._speech_start_timer.isActive()
        release.set()
        playback.worker.join(1)
        qtbot.wait(50)
        assert calls == ['Old statement']
        assert not playback.playing
    finally:
        release.set()
        playback.stop()
        playback.worker.join(1)
        playback.audio_devices.close()


def test_closed_assistant_rejects_late_speech_and_pending_restarts(qapp, monkeypatch):
    parent = QObject()
    parent.assistant_available = False
    playback = SpeechPlayback(parent)
    monkeypatch.setattr(playback, '_play_worker', lambda *_: pytest.fail('Closed assistant started speech'))
    playback.start('Late response')
    playback.sing('Late song')
    playback.sound('default')
    assert playback.worker is None and playback._pending_speech is None
    playback._pending_speech = (playback.generation, 'Late pending response', threading.Event(), False, None, None)
    playback._speech_start_timer.start()
    playback._start_pending_speech()
    assert playback._pending_speech is None and not playback._speech_start_timer.isActive()
    playback.audio_devices.close()


def test_speech_model_release_never_waits_for_load_or_synthesis():
    from dock_twoo.brain.local_tts import LocalTts
    engine = LocalTts()
    loaded = object()
    engine.engine = loaded
    engine.speakers = {'af_heart': 0}
    for lock in (engine._load_lock, engine._synth_lock):
        with lock:
            assert not engine.release_if_idle()
            assert engine.engine is loaded
    engine._thread = SimpleNamespace(is_alive=lambda: True)
    assert not engine.release_if_idle()
    engine._thread = None
    assert engine.release_if_idle()
    assert engine.engine is None and engine.speakers == {} and engine.state == 'released'
    with pytest.raises(RuntimeError, match='preparing'):
        engine.clip('A new request', threading.Event())


def test_active_synthesis_finishes_before_model_release():
    from dock_twoo.brain.local_tts import LocalTts
    engine = LocalTts()
    entered = threading.Event()
    release = threading.Event()
    results = []

    def create(*_, **__):
        entered.set()
        release.wait(5)
        return np.zeros(2400, dtype=np.float32), 24000

    engine.engine = SimpleNamespace(create=create)
    worker = threading.Thread(target=lambda: results.append(engine.clip('In progress', threading.Event())))
    worker.start()
    try:
        assert entered.wait(1)
        assert not engine.release_if_idle()
        assert engine.engine is not None
    finally:
        release.set()
        worker.join(1)
    assert len(results) == 1
    assert engine.release_if_idle()
    assert engine.engine is None
