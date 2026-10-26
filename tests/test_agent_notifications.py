import threading

from PySide6.QtCore import Qt
from tests.test_multi_brain import manager_at, inventory


def test_worker_toast_is_visible_on_assistant_display_and_expires(qtbot,tmp_path,monkeypatch):
    manager=manager_at(tmp_path,inventory()[1:2]);notes=manager.notifications
    pinned=[]
    monkeypatch.setattr('dock_twoo.brain.mascot.pin_native',pinned.append)
    try:
        thread=threading.Thread(target=lambda:notes.show('Orbit assigned Brain: research'))
        thread.start();thread.join()
        qtbot.waitUntil(lambda:notes.card is not None and notes.card.isVisible())
        assert pinned==[notes.card] and 'Orbit assigned Brain' in notes.label.text()
        assert notes.card.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
        assert notes.card.windowFlags() & Qt.WindowType.WindowTransparentForInput
        assert manager.companion.assigned_screen.availableGeometry().contains(notes.card.geometry())
        assert notes.timer.interval()==3000
        notes.timer.start(20)
        qtbot.waitUntil(lambda:not notes.card.isVisible())
        assert not notes.lines
        notes.close();notes.show('late callback')
        assert notes.card is None
    finally:manager.shutdown()


def test_normal_and_delegated_tasks_both_emit_start_and_finish_toasts(qapp,tmp_path):
    manager=manager_at(tmp_path,inventory()[1:2]);notes=manager.notifications;cancel=threading.Event()
    try:
        root,_=manager.coordinator.begin('parrot','Open Notes',{},cancel)
        assert 'Rio is working' in notes.lines[-1]
        child,_=manager.coordinator.begin('default','Research',{},cancel,root,assigning_identity='parrot')
        assert 'Rio assigned Brain' in notes.lines[-1]
        manager.coordinator.complete('default',child,'Done')
        assert 'Brain finished its task for Rio' in notes.lines[-1]
        manager.coordinator.complete('parrot',root,'Done')
        assert 'Rio finished the request' in notes.lines[-1]
        assert len(notes.lines)==3
    finally:manager.shutdown()
