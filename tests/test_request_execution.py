"""Request routing must reach a real capability and preserve literal dictation."""
from types import SimpleNamespace

import pytest

from dock_twoo.brain import commands
from dock_twoo.brain.computer_actions import ActionResult, parse_desktop_request


@pytest.mark.parametrize('phrase', [
    'Sing a song for me.',
    'Can you please sing a song for me?',
    'Brain, sing a song for me.',
    'Hey Brain, could you please sing a song for me?',
])
def test_singing_is_a_performance_instead_of_a_clarification(phrase):
    reply = commands.handle_voice_command(phrase, SimpleNamespace(companion=object()))
    assert isinstance(reply, commands.VoicePerformance)
    assert 'Hello world' in reply.lyrics


@pytest.mark.parametrize('phrase', [
    'Open the Cursor application and type hello world',
    'Can you please open Cursor and type hello world',
    'Brain, open Cursor and then type hello world',
    'Please launch the Cursor app then write hello world',
])
def test_cursor_request_reaches_the_executor_and_returns_its_verified_result(phrase, monkeypatch):
    calls = []
    def execute(app, text):
        calls.append((app, text))
        return ActionResult(True, 'Verified new unsaved document.')
    monkeypatch.setattr(commands, 'run_computer_action', execute)
    reply = commands.handle_voice_command(phrase, SimpleNamespace(companion=object()))
    assert calls == [('Cursor', 'hello world')]
    assert reply == 'Verified new unsaved document.'


def test_literal_typing_preserves_capitalization_unicode_and_shell_metacharacters():
    text = 'Hello World — नमस्ते $(no-shell) `literal`'
    request = parse_desktop_request(f'Open Cursor and type "{text}"')
    assert request.app == 'Cursor'
    assert request.text == text


def test_failed_desktop_action_does_not_claim_success(monkeypatch):
    monkeypatch.setattr(commands, 'run_computer_action', lambda *_: ActionResult(False, 'Accessibility permission is required.'))
    assert commands.handle_voice_command('Open Cursor and type hi', SimpleNamespace(companion=object())) == 'Accessibility permission is required.'


@pytest.mark.parametrize('phrase', ['Why is the sky blue?', 'Explain photosynthesis', 'What can you do?', 'Play some music'])
def test_ordinary_requests_reach_the_language_model_instead_of_an_unrelated_gesture(phrase):
    assert commands.handle_voice_command(phrase, SimpleNamespace(companion=object())) is None


def test_song_playback_reaches_the_singing_synthesizer(tmp_path, monkeypatch, qapp):
    from dock_twoo.brain import speech
    from dock_twoo.brain.audio import whistle_clip
    import threading
    calls = []
    monkeypatch.setattr(speech, 'synthesize_song', lambda text, *_: calls.append(text) or whistle_clip())
    playback = speech.SpeechPlayback()
    playback._play_worker(playback.generation, 'My original lyrics', threading.Event(), True)
    assert calls == ['My original lyrics']


def test_text_only_reply_releases_microphone_suppression(tmp_path, monkeypatch, qtbot):
    from dock_twoo.brain import manager as module
    from dock_twoo.brain.storage import BrainStore
    store=BrainStore(tmp_path)
    store.set_setting('voice_reply',False)
    manager=module.BrainManager(store=store,start_services=False)
    monkeypatch.setattr(manager.agent,'run',lambda *_args,**_kwargs:'Completed the local request.')
    manager._do_turn_complete('Open a test application')
    qtbot.waitUntil(lambda: manager.last_response['generation']>0)
    assert not manager.listener._output_active
    assert manager.listener._wake_armed
    manager.companion.close()
