"""Presentation work sleeps when hidden and drops its scene when closed."""
from types import SimpleNamespace as NS

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from dock_twoo.brain.model_view import CharacterView
from tests.test_multi_brain import manager_at, inventory


def test_unused_drawers_do_not_start_visualization_timers_or_dashboard(qapp):
    from dock_twoo.config import DockConfig
    from dock_twoo.ui.attached_window import AttachedWindow
    drawer = AttachedWindow(DockConfig())
    try:
        assert drawer._apps['dashboard'].view is None
        assert not drawer._apps['brain'].orb._timer.isActive()
        orb = drawer._apps['brain'].orb
        drawer.stack.setCurrentWidget(drawer._apps['brain'])
        drawer.show()
        assert orb._timer.isActive()
        drawer.hide()
        assert not orb._timer.isActive()
    finally:
        drawer.close();drawer.deleteLater()


def test_hide_show_cycles_stop_all_presentation_timers_and_restore_blinks(qapp, tmp_path):
    manager = manager_at(tmp_path, inventory()[:1])
    actor = manager.companion
    try:
        actor.set_follow_cursor(True)
        for _ in range(100):
            actor.hide()
            assert not any(timer.isActive() for timer in (
                actor.blink_timer, actor.roam_timer, actor.motion_timer,
                actor.follow_timer, actor.activity_timer))
            actor._blink()  # A stale queued callback must not start another blink.
            assert not actor.blinking
            assert not manager.playground.timer.isActive()
            actor.show()
            assert manager.playground.timer.isActive()
            assert actor.blink_timer.isActive()
            assert actor.activity_timer.isActive()
            assert actor.roam_timer.isActive()
            assert actor.follow_timer.isActive()
        manager.set_resource_cap(True)
        actor.hide(); actor.show()
        assert actor.blink_timer.isActive() and actor.activity_timer.isActive()
        assert not actor.roam_timer.isActive() and not actor.follow_timer.isActive()
    finally:
        manager.shutdown()


def test_pointer_monitor_lifecycle_does_not_accumulate_or_poll_when_hidden(qapp, tmp_path, monkeypatch):
    manager = manager_at(tmp_path, inventory()[:1])
    router = manager.input_router
    router.enabled = True  # Exercise lifecycle independently of the host OS.
    added, removed = [], []
    monkeypatch.setattr(router, '_observe_pointer', lambda: added.append(1))
    monkeypatch.setattr(router, '_remove_monitors', lambda: removed.append(1))
    monkeypatch.setattr(router, 'sync', lambda **_: None)
    try:
        for _ in range(100):
            router.refresh_visibility()
            router.refresh_visibility()
            assert router.timer.isActive()
            manager.companion.hide()
            assert not router.timer.isActive()
            router.refresh_visibility()
            manager.companion.show()
        assert len(added) == 101 and len(removed) == 100
        router.set_active(False)
        assert len(added) == len(removed) and not router.timer.isActive()
    finally:
        manager.shutdown()


def test_release_handles_loading_failed_and_ready_pages_without_stale_revival(qapp):
    class Probe(QWidget):
        def __init__(self):
            super().__init__()
            self.companion = NS(isVisible=lambda: False)
            self._released = False; self._hidden_since = 1.0
            self._loading = True; self.ready = False; self._discarded = False
            self.parked = False; self._reload_pending = True
            self._epoch = 0; self.attempts = 1; self._sync_pending = True
            self._healthy_since = 0.0; self.error = 'Failed load'; self.snapshot = None
            self.timer = QTimer(self); self.timer.start(50)
            self.urls = []; self.stop = lambda: None
            self._replace_page = lambda: self.urls.append('replacement')
            self.page = lambda: NS(setVisible=lambda _: None, setLifecycleState=lambda _: None)
            self.release_resources = lambda: CharacterView.release_resources(self)
    for ready in (False, True):
        view = Probe(); view.ready = ready
        CharacterView.release_hidden_page(view, 47.0)
        assert view._released and not view.ready and not view._loading
        assert not view.timer.isActive() and not view._sync_pending
        assert view.urls == ['replacement']
        CharacterView._ready(view, 'old-version', 'old-hash')
        CharacterView._loaded(view, False)
        CharacterView._error(view, 'Discarded renderer exited')
        CharacterView._recover_renderer(view, 'Discarded renderer exited')
        assert not view.ready and view._released
        assert view.error == '' and not view._reload_pending
        view.release_resources()
        assert view.urls == ['replacement']
        view.deleteLater()
    qapp.processEvents()
