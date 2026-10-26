"""The speaker may mention any character without waking or switching it."""
import threading
from types import SimpleNamespace

import pytest
from tests.test_multi_brain import manager_at, inventory
from tests.test_voice_turns import SPEECH, feed, listener_for_test


@pytest.mark.parametrize('mode', ['speaking', 'thinking', 'reading_gap'])
def test_all_named_wake_paths_are_silent_during_output(qapp, tmp_path, mode):
    manager = manager_at(tmp_path, inventory()[:1]); listener = manager.listener
    listener.start = lambda: None
    listener.wake_detector.feed = lambda _: pytest.fail('Playback reached name KWS')
    listener._transcribe_pcm = lambda _: pytest.fail('Playback reached backup ASR')
    listener.stop_detector = SimpleNamespace(ready=True, reset=lambda: None, feed=lambda _: '')
    # Even unfiltered/echo-free audio must not be allowed to wake another name.
    listener.echo_guard.filter = lambda pcm, at=None: pcm
    try:
        if mode == 'reading_gap':listener.suspend()
        else:manager.speech.activity.emit(mode)
        generation = listener._capture_generation
        feed(listener, SPEECH, 60)
        listener._check_wake_word([SPEECH] * 5, generation)
        assert not listener._begin_wake_capture([SPEECH], 'parrot')
        listener._emit_statement('Hey Rio, read this')
        # A signal queued before playback started is rejected by the GUI too.
        manager._on_named_keyword_started('parrot')
        manager._on_named_turn_completed('parrot', 'read this', 'Hey Rio, read this', False)
        assert manager.companion.character_id == 'default'
        assert not listener.is_recording and not manager._turn_queue
        assert not manager._processing_turns
    finally:manager.shutdown()


@pytest.mark.parametrize('reading', [False, True])
def test_stop_remains_available_with_named_characters(qapp, tmp_path, reading):
    listener = listener_for_test(tmp_path); listener.named_characters = True
    if reading:listener.suspend()
    else:listener.set_output_active(True)
    listener.wake_detector.feed = lambda _: pytest.fail('Stop must not reach named wake')
    listener.stop_detector = SimpleNamespace(ready=True, reset=lambda: None, feed=lambda _: 'BRAIN_STOP')
    stops = []; listener.stop_requested.connect(stops.append)
    feed(listener, SPEECH, 3)
    assert stops == ['Brain Stop'] and not listener.is_recording


def test_audio_tail_and_queued_playback_frames_are_discarded_before_rearming(qapp, tmp_path, monkeypatch):
    from dock_twoo.brain import listener as module
    clock = [10.]; monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    listener = listener_for_test(tmp_path); listener.named_characters = True
    names = []; listener.named_wake_started.connect(names.append)
    listener.wake_detector.feed = lambda _: 'RIO'
    listener.set_output_active(True); listener.set_output_active(False); listener.arm_wake()
    clock[0] = 10.2; feed(listener, SPEECH, 1)
    assert names == []
    clock[0] = 10.5
    listener._handle_pcm_frame(SPEECH, captured_at=10.1)
    assert names == []  # Delayed input cannot replay the speaker after the guard.
    listener._handle_pcm_frame(SPEECH, captured_at=10.5)
    assert names == ['parrot'] and listener.is_recording


def test_asr_started_before_playback_cannot_summon_after_playback(qtbot, tmp_path, monkeypatch):
    from dock_twoo.brain import listener as module
    clock = [10.]; monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    listener = listener_for_test(tmp_path); listener.named_characters = True
    entered, release = threading.Event(), threading.Event(); names = []
    listener.named_wake_started.connect(names.append)
    def transcribe(_):
        entered.set(); release.wait(2); return 'Hey Rio, read this'
    listener._transcribe_pcm = transcribe
    worker = threading.Thread(target=listener._check_wake_word, args=([SPEECH] * 5, listener._capture_generation))
    worker.start()
    try:
        assert entered.wait(1)
        listener.set_output_active(True); listener.set_output_active(False); listener.arm_wake()
        clock[0] = 11.
        release.set(); worker.join(2); qtbot.wait(10)
        assert not worker.is_alive() and not names and not listener.is_recording
    finally:release.set(); worker.join(2)


def test_named_requests_still_work_during_silent_background_processing(qapp, tmp_path):
    listener = listener_for_test(tmp_path); listener.named_characters = True
    listener._passive_stop = True; listener._wake_armed = False
    listener.wake_detector.feed = lambda _: 'RIO'
    names = []; listener.named_wake_started.connect(names.append)
    feed(listener, SPEECH, 1)
    assert names == ['parrot']


def test_reading_lock_survives_phrase_completion_and_releases_at_end(qapp, tmp_path, monkeypatch):
    from dock_twoo.brain import listener as module
    clock = [10.]; monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    listener = listener_for_test(tmp_path); listener.named_characters = True
    listener.suspend(); listener.set_output_active(True); listener.set_output_active(False)
    clock[0] = 11.
    assert not listener._begin_wake_capture([SPEECH], 'parrot')
    listener.arm_wake()
    assert listener._begin_wake_capture([SPEECH], 'parrot')
