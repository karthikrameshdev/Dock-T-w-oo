"""Stop must not block the UI on model progress, gRPC or storage bookkeeping."""
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest

from dock_twoo.brain.agent import BrainAgent
from dock_twoo.brain.ecosystem.coordinator import Coordinator
from dock_twoo.brain.profiles import ProfileManager
from dock_twoo.brain.storage import BrainStore


def test_coordinator_stop_captures_ids_and_never_waits_for_stalled_bus(tmp_path):
    manager = SimpleNamespace(store=BrainStore(tmp_path))
    coordinator = Coordinator(manager)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def call(method, data=None, **_):
        assert method == 'Cancel'
        calls.append(data['task_id'])
        entered.set()
        release.wait(3)
    client = SimpleNamespace(call=call, close=lambda: None)
    coordinator.client = lambda *_: client
    coordinator.bus.port = 1
    original_cancel, new_cancel = threading.Event(), threading.Event()
    coordinator.current_tasks['default'] = 'old-task'
    coordinator.task_cancels['old-task'] = original_cancel
    coordinator.workers['old-task'] = SimpleNamespace(cancel=original_cancel)
    try:
        start = time.monotonic()
        coordinator.stop()
        assert time.monotonic() - start < .1
        assert original_cancel.is_set() and entered.wait(1)
        # Repeated stops cannot enqueue hundreds of duplicate RPCs while down.
        for _ in range(200):coordinator.stop()
        assert coordinator._cancel_pending == {}
        with coordinator.lock:
            coordinator.current_tasks['default'] = 'new-task'
            coordinator.task_cancels['new-task'] = new_cancel
        release.set()
        worker = coordinator._cancel_worker
        if worker:worker.join(2)
        assert calls == ['old-task'] and not new_cancel.is_set()
        # A fresh explicit Stop does cancel that new generation.
        coordinator.stop()
        worker = coordinator._cancel_worker
        if worker:worker.join(2)
        assert calls == ['old-task', 'new-task'] and new_cancel.is_set()
    finally:
        release.set()
        coordinator.close()


def test_agent_progress_never_holds_state_lock_during_rpc_and_stop_is_immediate(tmp_path):
    agent = BrainAgent(ProfileManager(BrainStore(tmp_path)))
    entered, release = threading.Event(), threading.Event()
    run = agent.tracker.start('Fixture')
    def publish(*_):
        entered.set()
        release.wait(3)
    agent.coordinator = SimpleNamespace(closed=False, publish=publish)
    def update():
        agent._context.token = agent.cancel
        agent._context.task_id = 'task'
        agent._context.character_id = 'default'
        agent._update(state='thinking', message='Working', run_id=run)
    worker = threading.Thread(target=update)
    worker.start()
    try:
        assert entered.wait(1)
        start = time.monotonic()
        assert agent.status()['message'] == 'Working'
        agent.stop()
        assert time.monotonic() - start < .1 and agent.cancel.is_set()
        stop_worker = agent._stop_worker
        if stop_worker:stop_worker.join(1)
        assert agent.tracker.detail(run)['run']['state'] == 'stopped'
    finally:
        release.set()
        worker.join(2)


def test_delayed_stop_cannot_change_next_request(tmp_path):
    agent = BrainAgent(ProfileManager(BrainStore(tmp_path)))
    old_token = agent.cancel
    # Simulate a delayed state update. Stop must return without this lock.
    with agent._lock:
        agent.stop()
        assert old_token.is_set()
        new_token = agent.cancel = threading.Event()
        agent._state.update(state='thinking', run_id='new-run', message='New request')
    worker = agent._stop_worker
    if worker:worker.join(1)
    assert not new_token.is_set()
    assert agent.status()['state'] == 'thinking' and agent.status()['message'] == 'New request'


def test_task_connections_close_on_success_and_rollback(tmp_path, monkeypatch):
    from dock_twoo.tasks import TaskStore
    real_connect = sqlite3.connect
    connections = []
    def connect(*args, **kwargs):
        db = real_connect(*args, **kwargs)
        connections.append(db)
        return db
    monkeypatch.setattr(sqlite3, 'connect', connect)
    store = TaskStore(tmp_path)
    task = store.add('Task')
    store.list()
    store.get(task['id'])
    store.update(task['id'], status='todo')
    with pytest.raises(ValueError):store.get('missing')
    for db in connections:
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            db.execute('SELECT 1')


def test_prompt_cache_connections_close_after_repeated_template_reads(tmp_path, monkeypatch):
    from dock_twoo.brain.ecosystem.cache import PromptCache
    real_connect = sqlite3.connect
    connections = []
    def connect(*args, **kwargs):
        db = real_connect(*args, **kwargs)
        connections.append(db)
        return db
    monkeypatch.setattr(sqlite3, 'connect', connect)
    cache = PromptCache(tmp_path)
    for _ in range(25):cache.prepare({'id':'fixture'}, 'default', '', [{'role':'system','content':'Test'}], [])
    for db in connections:
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            db.execute('SELECT 1')
