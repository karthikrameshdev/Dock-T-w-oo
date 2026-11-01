"""Queued worker UI callbacks must not survive a closed assistant session."""
import threading
import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QApplication

from dock_twoo.brain.agent_notifications import AgentNotifications
from dock_twoo.brain.security.approvals import FileApprovals, Request


@pytest.fixture
def ui_manager(qapp, monkeypatch):
    manager = QObject()
    manager.companion = SimpleNamespace(assigned_screen=QApplication.primaryScreen())
    monkeypatch.setattr('dock_twoo.brain.mascot.pin_native', lambda *_: None)
    return manager


@pytest.mark.parametrize('cancel_request', [False, True])
def test_queued_approval_cannot_reappear_after_close_and_reopen(qtbot, ui_manager, cancel_request):
    approvals = FileApprovals(ui_manager)
    emitted = threading.Event()
    captured = []
    results = []
    cancel = threading.Event()

    def capture(request):
        captured.append(request)
        emitted.set()

    approvals.requested.connect(capture, Qt.ConnectionType.DirectConnection)
    worker = threading.Thread(target=lambda: results.append(
        approvals.ask('delete', '/example/user.txt', 'Delete user file', cancel)))
    try:
        worker.start()
        # Do not run Qt yet: the worker signal is pending in the GUI event queue.
        assert emitted.wait(1)
        assert approvals.card is None and not approvals.queue
        if cancel_request:
            cancel.set()
        approvals.close()
        approvals.closed = False
        QApplication.processEvents()
        worker.join(1)
        assert not worker.is_alive() and results == [False]
        assert captured[0].done.is_set() and not captured[0].approved
        assert approvals.card is None and approvals.current is None
        assert not approvals.queue and not approvals.timer.isActive()

        # New-session requests must still offer the normal explicit approval.
        fresh = Request('update', '/example/fresh.txt', 'New request', threading.Event(),
                        generation=approvals._generation)
        approvals.enqueue(fresh)
        assert approvals.current is fresh and approvals.card.isVisible()
        approvals.approve_button.click()
        assert fresh.done.is_set() and fresh.approved
    finally:
        cancel.set()
        approvals.close()
        worker.join(1)


def invalidate(request, reason):
    if reason == 'cancelled':
        request.cancel.set()
    elif reason == 'done':
        request.approved = True
        request.done.set()
    else:
        request.expires = time.monotonic() - 1


@pytest.mark.parametrize('reason', ['cancelled', 'done', 'expired'])
def test_enqueue_rejects_invalid_approval_without_showing_card(ui_manager, reason):
    approvals = FileApprovals(ui_manager)
    request = Request('delete', '/example/user.txt', 'Stale request', threading.Event())
    invalidate(request, reason)
    try:
        approvals.enqueue(request)
        assert request.done.is_set() and not request.approved
        assert approvals.card is None and approvals.current is None
        assert not approvals.queue and not approvals.timer.isActive()
    finally:
        approvals.close()


@pytest.mark.parametrize('reason', ['cancelled', 'done', 'expired'])
def test_advance_skips_request_invalidated_while_waiting(ui_manager, reason):
    approvals = FileApprovals(ui_manager)
    current = Request('update', '/example/one.txt', 'First', threading.Event())
    stale = Request('delete', '/example/two.txt', 'Second', threading.Event())
    try:
        approvals.enqueue(current)
        approvals.enqueue(stale)
        assert approvals.queue == [stale]
        invalidate(stale, reason)
        approvals.resolve(False)
        assert stale.done.is_set() and not stale.approved
        assert approvals.card is None and approvals.current is None
        assert not approvals.queue and not approvals.timer.isActive()
    finally:
        approvals.close()


def test_queued_toast_cannot_reappear_after_close_and_reopen(qtbot, ui_manager):
    notifications = AgentNotifications(ui_manager)
    try:
        worker = threading.Thread(target=lambda: notifications.show('Old task completed'))
        worker.start()
        worker.join(1)
        assert not worker.is_alive() and notifications.card is None
        notifications.close()
        notifications.closed = False
        QApplication.processEvents()
        assert notifications.card is None and not notifications.lines
        assert not notifications.timer.isActive()

        worker = threading.Thread(target=lambda: notifications.show('New session task'))
        worker.start()
        worker.join(1)
        qtbot.waitUntil(lambda: notifications.card is not None)
        assert notifications.card.isVisible()
        assert list(notifications.lines) == ['New session task']
    finally:
        notifications.close()
