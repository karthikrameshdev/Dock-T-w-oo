"""Complete-statement voice capture, silent wake, and honest retry behavior."""

import threading
from types import SimpleNamespace

import pytest

from dock_twoo.brain.endpoint import TurnEndpoint
from dock_twoo.brain.listener import AudioListener, command_after_keyword
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.providers import answer_locally
from dock_twoo.brain.recognition import LocalRecognizer
from dock_twoo.brain.storage import BrainStore


SPEECH = b'\x64\x00' * 1600
SILENCE = bytes(3200)


def listener_for_test(tmp_path):
    listener = AudioListener(store=BrainStore(tmp_path))
    calls = [0]

    def keyword(_pcm):
        calls[0] += 1
        return 'BRAIN' if calls[0] == 1 else ''

    listener.wake_detector = SimpleNamespace(ready=True, feed=keyword, reset=lambda: None)
    listener._is_speech_frame = lambda pcm, *_args: pcm != SILENCE
    return listener


def feed(listener, pcm, count):
    for _ in range(count):
        listener._handle_pcm_frame(pcm)


def test_inline_command_waits_through_a_pause_and_more_than_four_seconds(tmp_path, qtbot):
    listener = listener_for_test(tmp_path)
    listener._transcribe_pcm = lambda _pcm: 'Brain, go to the top right.'
    commands, wakes = [], []
    listener.turn_completed.connect(commands.append)
    listener.wake_detected.connect(lambda: wakes.append(True))
    feed(listener, SPEECH, 20)
    feed(listener, SILENCE, 8)
    feed(listener, SPEECH, 40)
    feed(listener, SILENCE, 14)
    assert commands == [] and wakes == []
    assert listener.is_recording
    feed(listener, SILENCE, 1)
    qtbot.waitUntil(lambda: bool(commands))
    assert commands == ['go to the top right']
    assert wakes == []


def test_speech_resuming_during_asr_discards_the_partial_result(tmp_path, qtbot):
    listener = listener_for_test(tmp_path)
    entered, release = threading.Event(), threading.Event()
    decodes = []

    def transcribe(pcm):
        decodes.append(len(pcm))
        if len(decodes) == 1:
            entered.set()
            release.wait(2)
            return 'Brain, go to the top'
        return 'Brain, go to the top right'

    listener._transcribe_pcm = transcribe
    commands = []
    listener.turn_completed.connect(commands.append)
    feed(listener, SPEECH, 10)
    feed(listener, SILENCE, 15)
    assert entered.wait(1)
    feed(listener, SPEECH, 10)
    release.set()
    qtbot.waitUntil(lambda: listener._decode_token is None)
    assert commands == [] and listener.is_recording
    feed(listener, SILENCE, 15)
    qtbot.waitUntil(lambda: bool(commands))
    assert commands == ['go to the top right']
    assert decodes[1] > decodes[0]


def test_backup_window_activates_capture_without_executing_its_partial_text(tmp_path, qtbot):
    listener = listener_for_test(tmp_path)
    transcripts = iter(['Hey Brain, go to', 'Hey Brain, go to the top left'])
    listener._transcribe_pcm = lambda _pcm: next(transcripts)
    commands, wakes = [], []
    listener.turn_completed.connect(commands.append)
    listener.wake_detected.connect(lambda: wakes.append(True))
    listener._check_wake_word([SPEECH] * 20)
    assert listener.is_recording
    assert commands == [] and wakes == []
    feed(listener, SPEECH, 20)
    feed(listener, SILENCE, 15)
    qtbot.waitUntil(lambda: bool(commands))
    assert commands == ['go to the top left']
    assert wakes == []


def test_backup_replays_the_silence_buffered_while_asr_was_running(tmp_path, qtbot):
    listener = listener_for_test(tmp_path)
    transcripts = iter(['Hey grain open the cursor app', 'Hey Brain open Cursor and type hello world'])
    listener._transcribe_pcm = lambda _pcm: next(transcripts)
    commands = []
    listener.turn_completed.connect(commands.append)
    listener._audio_timeline.extend([(index, SILENCE, False) for index in range(21, 41)])
    listener._check_wake_word([SPEECH] * 20, frame_end=20)
    qtbot.waitUntil(lambda: bool(commands))
    assert commands == ['open Cursor and type hello world']


def test_followup_capture_does_not_cut_off_at_twenty_seconds(tmp_path, qtbot):
    listener = listener_for_test(tmp_path)
    sizes = []
    listener._transcribe_pcm = lambda pcm: sizes.append(len(pcm)) or 'Research this entire topic'
    commands = []
    listener.turn_completed.connect(commands.append)
    listener.start_recording()
    feed(listener, SPEECH, 350)
    assert listener.is_recording and commands == []
    feed(listener, SILENCE, 15)
    qtbot.waitUntil(lambda: bool(commands))
    assert sizes[0] > 35 * 32000
    assert commands == ['Research this entire topic']


def test_completed_bare_wake_speaks_a_greeting_then_resumes_listening(tmp_path, qapp, monkeypatch):
    manager = BrainManager(store=BrainStore(tmp_path), start_services=False)
    spoken = []
    monkeypatch.setattr(manager.speech, 'start', spoken.append)
    manager._do_wake_detected()
    assert len(spoken) == 1 and 'Model is not configured' in spoken[0]
    assert not manager.session_timer.isActive()
    assert not manager.session_timer.isActive()
    manager._on_speech_finished()
    assert manager.listener.is_recording
    assert not manager.session_timer.isActive()
    manager.stop_talking()
    manager.companion.close()


def test_unintelligible_speech_asks_for_a_repeat_and_then_listens_again(tmp_path, qapp, monkeypatch):
    manager = BrainManager(store=BrainStore(tmp_path), start_services=False)
    spoken = []
    monkeypatch.setattr(manager.speech, 'start', spoken.append)
    manager.in_conversation_session = True
    manager._do_turn_complete('')
    assert len(spoken) == 1
    assert 'Hey Buddy' in spoken[0] and 'repeat' in spoken[0]
    manager._on_speech_finished()
    assert manager.listener.is_recording
    manager.stop_talking()
    manager.companion.close()


def test_unhandled_request_gets_a_clarification_instead_of_a_fake_success():
    reply = answer_locally('frobnicate the thingamabob')
    assert 'Model is not configured' in reply
    assert 'running smoothly' not in reply and 'Understood' not in reply


def test_short_direct_command_after_a_verified_keyword_is_not_a_bare_wake():
    assert command_after_keyword('Go top left') == (True, 'Go top left')


def test_silent_idle_times_out_but_long_speech_waits_for_the_end():
    endpoint = TurnEndpoint()
    endpoint.feed(10, False)
    assert endpoint.idle_expired and not endpoint.complete
    endpoint = TurnEndpoint()
    endpoint.feed(121, True)
    assert endpoint.overlong and not endpoint.complete and not endpoint.idle_expired
    endpoint.feed(1.5, False)
    assert endpoint.complete


def test_long_whisper_input_is_decoded_in_overlapping_windows(tmp_path):
    recognizer = LocalRecognizer(tmp_path)
    lengths, streams = [], []
    texts = iter(['start of statement shared words', 'shared words middle of statement final section',
                  'final section end of statement'])

    def stream():
        result = SimpleNamespace(text='')
        instance = SimpleNamespace(accept_waveform=lambda _rate, samples: lengths.append(len(samples)), result=result)
        streams.append(instance)
        return instance

    recognizer._recognizer = SimpleNamespace(create_stream=stream, decode_stream=lambda s: setattr(s.result, 'text', next(texts)))
    text = recognizer.transcribe(bytes(65 * 32000))
    assert lengths == [26 * 16000, 26 * 16000, 17 * 16000]
    assert text == 'start of statement shared words middle of statement final section end of statement'


def test_bare_address_in_followup_acknowledges_without_starting_a_query(tmp_path, qapp, monkeypatch):
    manager = BrainManager(store=BrainStore(tmp_path), start_services=False)
    spoken = []
    monkeypatch.setattr(manager.speech, 'start', spoken.append)
    manager.in_conversation_session = True
    manager._do_turn_complete('Hey Brain')
    assert len(spoken) == 1 and not manager.conversation_history
    manager._on_speech_finished()
    assert manager.listener.is_recording
    manager.stop_talking()
    manager.companion.close()
