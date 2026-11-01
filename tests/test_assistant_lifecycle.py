"""Close is a hardware/privacy boundary; Hide is only presentation visibility."""
import threading
from types import SimpleNamespace

import pytest

from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from tests.test_multi_brain import inventory


@pytest.fixture
def manager(qapp, tmp_path):
    instance = BrainManager(store=BrainStore(tmp_path), start_services=False)
    instance.configure_displays(inventory()[:1])
    yield instance
    instance.shutdown()


def test_close_disables_hardware_cancels_work_and_persists_without_quitting_dock(manager, monkeypatch):
    listener = manager.listener
    manager.start_talking()
    assert listener.is_recording
    calls = []
    monkeypatch.setattr(manager.audio_devices, 'stop_input', lambda: calls.append('mic stopped'))
    manager.close_assistant()
    assert calls and listener.closed and not listener.is_running and not listener.is_recording
    assert not manager.audio_devices.timer.isActive()
    assert not manager.reader.remember_timer.isActive() and not manager.ecology.timer.isActive()
    assert not manager.session_timer.isActive()
    assert not manager.is_mini_agent_visible()
    assert not manager.coordinator.closed and not manager.reminders.closed and not manager.resources.closed
    saved = BrainStore(manager.store.data_dir)
    assert saved.setting('assistant_closed') and not saved.setting('companion_visible')
    assert saved.setting('wake_word_enabled')  # Preserve the preference for explicit reopen.
    status = manager.get_status()
    assert status['assistant_state'] == 'closed' and not status['voice_input']['enabled']


def test_hide_is_wakeable_but_close_rejects_names_settings_shortcuts_and_reading(manager, monkeypatch):
    manager.hide_mini_agent()
    assert not manager.assistant_closed and not manager.listener.closed
    manager._on_named_keyword_started('orbit')
    assert manager.is_mini_agent_visible() and manager.companion.character_id == 'orbit'
    manager.close_assistant()
    monkeypatch.setattr(manager.listener, 'start', lambda: pytest.fail('Closed assistant reopened microphone'))
    monkeypatch.setattr(manager.speech, 'start', lambda *_: pytest.fail('Closed assistant spoke'))
    manager._on_named_keyword_started('default')
    manager._on_named_turn_completed('default', 'hello', 'Brain hello', False)
    manager._do_wake_detected()
    manager._on_shortcut_press()
    manager._on_shortcut_release()
    manager._on_session_timeout()
    manager._on_speech_activity('thinking')
    manager._on_speech_finished()
    manager._on_reading_failed('late reader failure')
    manager._read_text_now('late text')
    manager._start_reading_now('window')
    manager._do_action('wave')
    manager.apply_voice_settings({'wake_word_enabled': True, 'push_to_talk_shortcut': 'cmd_r'})
    manager.submit_request('Brain, please act')
    manager._drain_turns()
    assert not manager.is_mini_agent_visible() and not manager._turn_queue
    assert not manager.listener.is_recording and manager.companion.character_id == 'orbit'


def test_reopen_is_explicit_and_closed_state_survives_restart(manager):
    manager.close_assistant()
    again = BrainManager(store=BrainStore(manager.store.data_dir), start_services=False)
    try:
        again.configure_displays(inventory()[:1])
        assert again.assistant_closed and again.listener.closed
        assert not again.is_mini_agent_visible()
        again.choose_assistant('orbit')
        assert not again.assistant_closed and again.is_mini_agent_visible()
        assert not again.listener.closed and again.listener._wake_armed
        again.close_assistant()
        again.show_mini_agent()
        assert not again.assistant_closed and again.is_mini_agent_visible()
        again.close_assistant()
        again.toggle_talking()
        assert again.listener.is_recording and not again.assistant_closed
    finally:
        again.shutdown()


def test_queued_microphone_callback_cannot_survive_close_and_immediate_reopen(manager, monkeypatch):
    pending, called = [], []
    monkeypatch.setattr(manager, 'run_on_main_thread', pending.append)
    manager._dispatch_assistant_callback(lambda: called.append(True))
    manager.close_assistant()
    manager.show_mini_agent()
    pending.pop()()
    assert not called
    manager._dispatch_assistant_callback(lambda: called.append(True))
    pending.pop()()
    assert called == [True]


def test_delayed_model_reply_cannot_resume_or_reopen_after_close(manager, qtbot, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def run(*args, **kwargs):
        entered.set()
        release.wait(3)
        return 'A late answer from a cancelled worker'
    monkeypatch.setattr(manager.agent, 'run', run)
    replies = []
    manager.reply_received.connect(replies.append)
    manager.submit_request('Do research for me')
    assert entered.wait(1)
    manager.close_assistant()
    release.set()
    qtbot.waitUntil(lambda: not manager._worker_running)
    assert not replies and not manager._reply_queue and not manager.is_mini_agent_visible()
    assert manager.listener.closed


def test_model_release_waits_for_asr_and_is_not_retried_after_reopen(manager, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def decode():
        entered.set()
        release.wait(3)
    manager.listener._start_decode_worker(decode, ())
    assert entered.wait(1)
    manager.close_assistant()
    called = []
    from dock_twoo.brain.local_tts import get_local_tts
    for component in (manager.listener.models, manager.listener.wake_detector,
                      manager.listener.stop_detector, manager.listener.endpoint_vad, get_local_tts()):
        monkeypatch.setattr(component, 'release_if_idle', lambda: called.append(True) or True)
    manager.release_closed_resources()
    assert not called and manager._models_release_pending
    release.set()
    # Join the tracked worker without asking Qt to process unrelated callbacks.
    with manager.listener._decode_workers_lock:
        threads = list(manager.listener._decode_workers)
    for thread in threads:thread.join(2)
    manager.release_closed_resources()
    assert len(called) == 5 and not manager._models_release_pending
    manager.show_mini_agent()
    manager.release_closed_resources()
    assert len(called) == 5


def test_closed_reminders_keep_notifications_without_voice_or_summoning(manager, monkeypatch):
    manager.close_assistant()
    alerts = [{'reminder_id': 'test', 'id': 'one', 'text': 'Meeting soon', 'character_id': 'orbit'}]
    shown = []
    manager.reminders.toast = SimpleNamespace(present=lambda items: shown.extend(items), close=lambda: None)
    monkeypatch.setattr(manager.reminders.store, 'acknowledge', lambda *_: None)
    manager.reminders.deliver(alerts)
    manager.reminders._speak_next()
    assert shown == alerts and not manager.reminders.speech_queue
    assert not manager.is_mini_agent_visible() and manager.listener.closed


def test_context_menu_has_distinct_close_hide_and_reopen(manager):
    menu = manager._build_context_menu()
    labels = [action.text() for action in menu.actions()]
    assert 'Hide assistant (keep voice wake)' in labels
    close = next(a for a in menu.actions() if a.text() == 'Close assistant (microphone off)')
    close.trigger()
    assert manager.assistant_closed
    menu.deleteLater()
    menu = manager._build_context_menu()
    reopen = next(a for a in menu.actions() if a.text() == 'Open assistant')
    reopen.trigger()
    assert not manager.assistant_closed and manager.is_mini_agent_visible()
    menu.deleteLater()
