"""Input policy is independent of character visibility, output, and Close."""
import array
import json
import threading

import pytest

from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore


@pytest.fixture
def manager(qapp, tmp_path, monkeypatch):
    manager = BrainManager(store=BrainStore(tmp_path), start_services=False)
    listener = manager.listener
    # Run the actual listener/hardware-routing decisions with a fake transport.
    # No native microphone, keyboard monitor, local inference, or network is used.
    monkeypatch.setattr(manager.audio_devices, '_open_input', lambda: manager.audio_devices.input_state.emit(True, 'Test microphone'))
    monkeypatch.setattr(listener.models, 'start_model_downloads', lambda: None)
    for model in (listener.wake_detector, listener.stop_detector, listener.endpoint_vad):
        monkeypatch.setattr(model, 'start', lambda: None)
    monkeypatch.setattr(manager.shortcut_listener, 'start', lambda: None)
    monkeypatch.setattr(manager.semantic_model, 'start', lambda: None)
    from dock_twoo.brain.local_tts import get_local_tts
    monkeypatch.setattr(get_local_tts(), 'start', lambda: None)
    real_start = listener.start
    def start():
        # Pytest restores its environment marker before each test call phase.
        with monkeypatch.context() as env:
            env.delenv('PYTEST_CURRENT_TEST', raising=False)
            real_start()
    monkeypatch.setattr(listener, 'start', start)
    manager._services_enabled = True
    yield manager
    manager.shutdown()
    with listener._audio_workers_lock:workers = list(listener._audio_workers)
    for worker in workers:worker.join(1)


@pytest.mark.parametrize('mode', ['automatic', 'manual', 'off'])
def test_modes_survive_visibility_close_and_reopen(manager, mode):
    manager.set_listening_mode(mode)
    manager.show_mini_agent()
    assert manager.is_mini_agent_visible()
    assert manager.audio_devices._want_input == (mode == 'automatic')
    manager.hide_mini_agent()
    assert not manager.is_mini_agent_visible() and manager.assistant_available
    assert manager.audio_devices._want_input == (mode == 'automatic')
    manager.show_mini_agent()
    assert manager.listening_mode == mode
    manager.close_assistant()
    assert not manager.audio_devices._want_input and not manager.is_mini_agent_visible()
    assert manager.listening_mode == mode
    manager.show_mini_agent()
    assert manager.is_mini_agent_visible() and manager.listening_mode == mode
    assert manager.audio_devices._want_input == (mode == 'automatic')
    assert BrainStore(manager.store.data_dir).setting('listening_mode') == mode
    manager.toggle_talking()
    assert manager.listener.is_recording == (mode != 'off')
    assert manager.audio_devices._want_input == (mode != 'off')


@pytest.mark.parametrize('finish', ['click', 'silence'])
def test_manual_complete_capture_closes_hardware_while_asr_continues(manager, monkeypatch, qtbot, finish):
    manager.set_listening_mode('manual')
    listener = manager.listener
    entered, release = threading.Event(), threading.Event()
    requests = []
    def transcribe(_):
        entered.set()
        assert release.wait(4)
        return 'Summarize my notes'
    monkeypatch.setattr(listener, '_transcribe_pcm', transcribe)
    monkeypatch.setattr(manager, '_queue_turn', lambda text, *args, **kwargs: requests.append(text))
    manager.toggle_talking()
    listener.speech_frames = [array.array('h', [500] * 8000).tobytes()]
    listener.has_spoken = True
    listener._endpoint.speech = .5
    try:
        if finish == 'click':
            manager.toggle_talking()
        else:
            monkeypatch.setattr(listener, '_is_speech_frame', lambda *_: False)
            listener._endpoint.silence = 1.4
            listener._handle_pcm_frame(array.array('h', [0] * 1600).tobytes())
        assert entered.wait(1)
        assert not manager.audio_devices._want_input and not listener.is_running
        assert listener._decode_token is not None  # Stopping hardware preserves captured ASR.
        release.set()
        qtbot.waitUntil(lambda: requests == ['Summarize my notes'])
        assert not listener.is_recording and not manager.audio_devices._want_input
        manager._on_speech_activity('speaking')
        assert not manager.audio_devices._want_input and not listener._passive_stop
        manager._on_speech_activity('idle')
        manager._on_speech_finished()
        assert not listener.is_recording and not manager.audio_devices._want_input
    finally:release.set()


def test_manual_configured_shortcut_captures_only_while_pressed_and_off_ignores_it(manager):
    manager.set_listening_mode('manual')
    manager.apply_voice_settings({'push_to_talk_shortcut': 'ctrl_r'})
    assert manager.shortcut_listener.shortcut_key == 'ctrl_r'
    manager.shortcut_listener.on_press_cb()
    assert manager.listener.is_recording and manager.audio_devices._want_input
    assert manager._listening_source == 'shortcut'
    manager.shortcut_listener.on_release_cb()
    assert not manager.listener.is_recording and not manager.audio_devices._want_input
    manager.set_listening_mode('off')
    manager.shortcut_listener.on_press_cb()
    manager.shortcut_listener.on_release_cb()
    manager._on_named_keyword_started('rio')
    manager._do_wake_detected()
    manager._on_speech_activity('speaking')
    assert not manager.listener.is_recording and not manager.audio_devices._want_input
    assert manager.companion.character_id == 'default'


def test_mode_change_invalidates_delayed_input_but_preserves_processing(manager, monkeypatch):
    pending, delivered = [], []
    monkeypatch.setattr(manager, 'run_on_main_thread', pending.append)
    manager._dispatch_assistant_callback(lambda: delivered.append('old input'))
    token = threading.Event()
    manager._processing_turns['in-flight'] = {'cancel': token, 'turn': type('Turn', (), {'character_id': 'default'})()}
    try:
        manager.set_listening_mode('off')
        manager.set_listening_mode('manual')
        pending.pop()()
        assert not delivered and not token.is_set()
        assert not manager.audio_devices._want_input
    finally:manager._processing_turns.clear()


def test_manual_never_uses_character_names_to_handoff_capture(manager, monkeypatch):
    manager.set_listening_mode('manual')
    requests = []
    monkeypatch.setattr(manager, '_queue_turn', lambda text, *args, **kwargs: requests.append(text))
    manager.toggle_talking()
    manager.listener._emit_statement('Rio is the city in my notes')
    assert manager.companion.character_id == 'default'
    assert requests == ['Rio is the city in my notes']


@pytest.mark.parametrize('enabled,expected', [(True, 'automatic'), (False, 'manual')])
def test_wake_setting_migration_and_compatibility(tmp_path, enabled, expected):
    (tmp_path / 'settings.json').write_text(json.dumps({'wake_word_enabled': enabled}))
    store = BrainStore(tmp_path)
    assert store.setting('listening_mode') == expected
    store.set_setting('listening_mode', 'off')
    assert not store.setting('wake_word_enabled')
    store.set_setting('wake_word_enabled', enabled)
    assert store.setting('listening_mode') == expected
    store.update_settings({'listening_mode': 'off', 'wake_word_enabled': True})
    assert store.setting('listening_mode') == 'off' and not store.setting('wake_word_enabled')


def test_switch_to_automatic_during_reading_keeps_wake_suppressed(manager):
    manager.set_listening_mode('off')
    manager.reader.active = True
    manager.set_listening_mode('automatic')
    assert manager.audio_devices._want_input
    assert manager.listener._wake_suspended
    manager._on_speech_activity('idle')
    assert manager.listener.wake_suppressed
