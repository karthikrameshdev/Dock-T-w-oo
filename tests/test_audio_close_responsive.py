"""Native audio calls must never block Close or deliver a retired frame after Open."""
import array
import threading
import time
from types import SimpleNamespace

import pytest

from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore


@pytest.mark.parametrize('phase', ['vad', 'wake', 'stop', 'reset'])
def test_close_and_reopen_remain_responsive_during_native_frame(qapp, tmp_path, phase):
    manager = BrainManager(store=BrainStore(tmp_path), start_services=False)
    listener = manager.listener
    entered, release = threading.Event(), threading.Event()
    retired = threading.Event()
    callbacks = []
    listener.named_wake_started.connect(callbacks.append)

    def blocked(result):
        entered.set()
        assert release.wait(5)
        return result

    listener.endpoint_vad = SimpleNamespace(
        ready=True, reset=lambda: None,
        feed=lambda _: blocked(True) if phase == 'vad' else True)
    listener.wake_detector = SimpleNamespace(
        ready=True, reset=lambda: blocked(None) if phase == 'reset' else None,
        feed=lambda _: blocked('RIO') if phase == 'wake' else '')
    listener.stop_detector = SimpleNamespace(
        ready=True, reset=lambda: None, feed=lambda _: blocked('STOP'))
    if phase == 'stop':
        # Closing active document speech also calls arm_wake via reader.stop.
        manager.reader.active = True
        listener._output_active = True
    pcm = array.array('h', [500] * 1600).tobytes()
    worker = threading.Thread(target=listener._handle_pcm_frame,
                              kwargs={'pcm': pcm, 'session_stop': retired}, daemon=True)
    try:
        worker.start()
        assert entered.wait(2)
        started = time.monotonic()
        manager.close_assistant()
        assert time.monotonic() - started < .25
        assert listener.closed and not listener.is_recording
        started = time.monotonic()
        manager.start_talking()
        assert time.monotonic() - started < .25
        generation = listener._capture_generation
        assert listener.is_recording and not listener.closed
        release.set()
        worker.join(2)
        assert not worker.is_alive()
        qapp.processEvents()
        assert not callbacks
        assert listener._capture_generation == generation
        assert listener.is_recording and listener.speech_frames == []
        assert manager.companion.character_id == 'default'
    finally:
        release.set()
        worker.join(2)
        manager.shutdown()


def test_stop_does_not_join_audio_worker(qapp, tmp_path):
    manager = BrainManager(store=BrainStore(tmp_path), start_services=False)
    listener = manager.listener
    entered, release = threading.Event(), threading.Event()
    def worker_body():
        entered.set()
        release.wait(4)
    worker = threading.Thread(target=worker_body, daemon=True)
    listener.worker_thread = worker
    try:
        worker.start()
        assert entered.wait(1)
        started = time.monotonic()
        listener.stop()
        assert time.monotonic() - started < .1
        assert listener.worker_thread is worker and listener.stop_event.is_set()
    finally:
        release.set()
        worker.join(2)
        manager.shutdown()


def test_close_records_cancelled_runs_without_waiting_for_activity_storage(qapp, tmp_path, monkeypatch):
    from dock_twoo.brain.sessions import Turn
    manager = BrainManager(store=BrainStore(tmp_path), start_services=False)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def finish(run_id, state, **kwargs):
        entered.set()
        assert release.wait(4)
        calls.append((run_id, state))
    monkeypatch.setattr(manager.activity, 'finish', finish)
    manager._turn_queue.append(Turn('queued task', 'text', 'default', {}, '', 'old-queued'))
    manager._active_turn = Turn('reading task', 'text', 'default', {}, '', 'old-active')
    try:
        started = time.monotonic()
        manager.close_assistant()
        assert time.monotonic() - started < .25
        assert entered.wait(1)
        writer = manager._stop_trace_worker
        manager.start_talking()
        for _ in range(100):manager.stop_talking()
        assert manager._stop_trace_worker is writer
        assert not manager.listener.closed and not manager._turn_queue
        release.set()
        writer.join(2)
        assert sorted(calls) == [('old-active', 'stopped'), ('old-queued', 'stopped')]
        assert manager._stop_trace_worker is None
    finally:
        release.set()
        if manager._stop_trace_worker:manager._stop_trace_worker.join(2)
        manager.shutdown()


def test_finish_button_during_vad_does_not_route_tail_frame_as_another_wake(qapp, tmp_path, monkeypatch):
    manager = BrainManager(store=BrainStore(tmp_path), start_services=False)
    listener = manager.listener
    entered, release = threading.Event(), threading.Event()
    dispatched = []
    def feed(_):
        entered.set()
        assert release.wait(4)
        return True
    listener.endpoint_vad = SimpleNamespace(ready=True, reset=lambda: None, feed=feed)
    listener.wake_detector = SimpleNamespace(
        ready=True, reset=lambda: None,
        feed=lambda _: pytest.fail('Completed capture tail was routed as another wake'))
    monkeypatch.setattr(listener, '_dispatch_capture', lambda: dispatched.append(True))
    listener.start_recording()
    worker = threading.Thread(target=listener._handle_pcm_frame,
                              args=(array.array('h', [500] * 1600).tobytes(),), daemon=True)
    try:
        worker.start()
        assert entered.wait(1)
        started = time.monotonic()
        listener.stop_recording()
        assert time.monotonic() - started < .1
        assert dispatched == [True]
        release.set()
        worker.join(2)
        assert not worker.is_alive() and not listener.is_recording
        assert listener.speech_frames == []
    finally:
        release.set()
        worker.join(2)
        manager.shutdown()
