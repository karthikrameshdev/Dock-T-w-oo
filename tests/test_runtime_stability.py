"""Resident characters must retain bounded work and never retain pointer capture."""
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from PySide6.QtCore import QPoint,QPointF,QRect,Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import QEvent

from dock_twoo.brain.model_view import CharacterView,render_budget
from tests.test_brain_input_shape import payload
from tests.test_multi_brain import manager_at,inventory


def test_native_signal_emission_preserves_python_singletons_and_exits_cleanly():
    # Audio-level updates emit throughout the app's lifetime. Qt 6.12.0's
    # Linux binding decrements True on every emit, eventually aborting Python
    # <3.12. Isolate the real native call so a regression cannot kill pytest.
    result = subprocess.run([sys.executable, '-c', '''
import sys
from PySide6.QtCore import QObject, Signal
class Source(QObject):
    level = Signal(float)
source = Source()
source.level.emit(0.2)
before = (sys.getrefcount(True), sys.getrefcount(False))
for _ in range(10000):
    source.level.emit(0.2)
after = (sys.getrefcount(True), sys.getrefcount(False))
assert after == before, (before, after)
'''], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_mixer_releases_old_clips_after_long_running_transitions():
    node=shutil.which('node')
    if not node:pytest.skip('Node is needed for the Three.js lifecycle regression')
    result=subprocess.run([node,str(Path(__file__).resolve().parents[1]/'scripts/verify_animation_lifecycle.mjs')],capture_output=True,text=True,timeout=40)
    assert result.returncode==0,result.stdout+result.stderr


def test_slow_renderer_has_only_one_pending_update(qapp,monkeypatch):
    calls=[];clock=[0.0]
    monkeypatch.setattr('dock_twoo.brain.model_view.time.monotonic',lambda:clock[0])
    monkeypatch.setattr('dock_twoo.brain.model_view.isValid',lambda _:True)
    actor=NS(isVisible=lambda:True,geometry=lambda:QRect(-1000,-1000,200,200),action='walk',activity='idle',
             motion_started=0,motion_duration=5,reduced_motion=False,_yaw=0,gait_distance=0,blink_amount=0,
             mouth_level=0,_gaze_offset=QPointF())
    actor.manager=NS(companions={'a':actor})
    view=NS(companion=actor,_sync_pending=False,_sync_started=0,_epoch=1,_healthy_since=0,connectivity=NS(online=True),
            timer=NS(setInterval=lambda _:None),page=lambda:NS(runJavaScript=lambda code,callback:calls.append((code,callback))))
    for _ in range(100):CharacterView._sync(view)
    assert len(calls)==1
    actor.action='wave'
    calls[0][1](None)
    CharacterView._sync(view)
    assert len(calls)==2 and '"action": "wave"' in calls[-1][0]
    # A late callback belonging to a previous page must not unlock a new update.
    view._epoch+=1
    calls[-1][1](None)
    assert view._sync_pending
    failures=[];view._recover_renderer=lambda reason:failures.append(reason)
    clock[0]=6;CharacterView._sync(view)
    assert failures and len(calls)==2


def test_hidden_character_does_not_load_a_browser_or_enqueue_updates(qapp):
    actor=NS(isVisible=lambda:False)
    view=NS(companion=actor,_loading=False,ready=False)
    CharacterView._load(view)
    CharacterView._sync(view)


def test_crowd_budget_and_interacting_character_priority():
    assert render_budget(30)['pixelRatio']==1
    assert render_budget(30)['shapeFps']<render_budget(1)['shapeFps']
    assert render_budget(30,True)==render_budget(1)


def test_shape_updates_do_not_remove_pressed_pixel_before_release(qapp,tmp_path):
    manager=manager_at(tmp_path,inventory()[:1]);actor=manager.companion
    initial=payload(actor.size(),[QRect(80,20,80,180)])
    actor.set_input_shape(initial);mask=actor.mask()
    actor.origin=QPoint(100,100);actor.press_point=QPoint(100,100)
    actor.set_input_shape(payload(actor.size(),[QRect(120,20,40,180)]))
    assert actor.mask()==mask and actor.input_region!=mask
    called=[]
    manager.toggle_talking=lambda owner:called.append((owner,actor.origin,actor.press_point))
    release=QMouseEvent(QEvent.Type.MouseButtonRelease,QPointF(100,100),QPointF(100,100),
                        Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)
    actor.mouseReleaseEvent(release)
    assert called==[(actor.actor_id,None,None)]
    assert actor.mask()==actor.input_region
    manager.shutdown()


def test_hiding_cancels_capture_and_stops_idle_paint_timer(qapp,tmp_path):
    manager=manager_at(tmp_path,inventory()[:1]);actor=manager.companion
    actor.origin=QPoint(1,1);actor.press_point=QPoint(2,2)
    actor.hide()
    assert actor.origin is None and actor.press_point is None
    assert not actor.activity_timer.isActive()
    actor.show();assert actor.activity_timer.isActive()
    manager.shutdown()


def test_gui_gc_uses_young_generation_until_old_collection_due(qapp,monkeypatch):
    from dock_twoo.ui.lifecycle import GuiGarbageCollector
    collector=GuiGarbageCollector(qapp);collector.timer.stop();calls=[]
    monkeypatch.setattr('gc.collect',lambda generation:calls.append(generation))
    monkeypatch.setattr('gc.get_threshold',lambda:(700,10,10))
    for counts in [(800,1,1),(800,11,1),(800,11,11),(1,1,1)]:
        monkeypatch.setattr('gc.get_count',lambda c=counts:c)
        collector.collect()
    assert calls==[0,1,2]
    collector.stop()


def test_finishing_load_while_hidden_freezes_page(qapp):
    from PySide6.QtWebEngineCore import QWebEnginePage
    states=[]
    actor=NS(isVisible=lambda:False,character_name='Brain',character={'asset_sha256':'hash'},setToolTip=lambda _:None,update=lambda:None)
    page=NS(setVisible=lambda value:states.append(value),setLifecycleState=lambda value:states.append(value))
    view=NS(companion=actor,page=lambda:page)
    CharacterView._ready(view,'1','hash')
    assert view.ready and not view._loading
    assert states==[False,QWebEnginePage.LifecycleState.Frozen]


def test_hidden_crash_retains_retry_until_next_show(qapp):
    from PySide6.QtWidgets import QWidget
    class Probe(QWidget):
        def __init__(self):
            super().__init__();self._epoch=0;self._sync_pending=True;self._recoveries=0;self._reload_pending=False
            self.error='';self.ready=False;self._loading=False;self.detached=False;self.loads=0
            self.companion=NS(isVisible=lambda:False)
        def _error(self,reason):self.error=reason
        def _load(self):
            # Real load guard preserves the pending retry while hidden.
            CharacterView._load(self)
        def page(self):return NS(setLifecycleState=lambda _:None)
        def sync_geometry(self):pass
    view=Probe()
    CharacterView._recover_renderer(view,'crash')
    view._load()
    assert view._reload_pending and view._recoveries==1
    # On show, the deferred retry is scheduled even though an error is present.
    view._load=lambda:setattr(view,'loads',view.loads+1)
    CharacterView.show_visual(view)
    qapp.processEvents()
    assert view.loads==1
    view.deleteLater();qapp.processEvents()


def test_lost_mouse_release_recovers_without_triggering_listening(qapp,tmp_path,monkeypatch):
    manager=manager_at(tmp_path,inventory()[:1]);actor=manager.companion
    router=manager.input_router;router.close();router.enabled=True
    held=[True]
    monkeypatch.setitem(sys.modules,'AppKit',NS(NSEvent=NS(pressedMouseButtons=lambda:int(held[0]))))
    monkeypatch.setattr('dock_twoo.brain.mascot.mac_window',lambda _:(None,None))
    actor.origin=QPoint(10,10);actor.press_point=QPoint(20,20)
    router._release_checks.add(id(actor))
    router._recover_release(actor)
    assert actor.origin is not None  # Never revoke a live drag.
    held[0]=False
    router._recover_release(actor)
    assert actor.origin is None and actor.press_point is None
    assert not manager.listener.is_recording
    router.enabled=False;manager.shutdown()


def test_native_click_through_flags_are_reasserted_after_idle(qapp,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QWidget
    manager=manager_at(tmp_path,inventory()[:1]);actor=manager.companion
    visual=QWidget();visual.show();actor.model_view=visual
    calls=[];clock=[10.0]
    monkeypatch.setattr('dock_twoo.brain.native_input.time.monotonic',lambda:clock[0])
    def native(widget):
        return 1,lambda *args:calls.append((widget,args[-1][1]))
    monkeypatch.setattr('dock_twoo.brain.mascot.mac_window',native)
    router=manager.input_router;router.timer.stop();router.enabled=True
    router.sync(QPoint(-2000,-2000),force=True)
    assert (visual,True) in calls
    calls.clear();router.sync(QPoint(-2000,-2000));assert not calls
    clock[0]+=.6;router.sync(QPoint(-2000,-2000))
    assert (visual,True) in calls and (actor,True) in calls
    actor.model_view=None;visual.close();router.enabled=False;manager.shutdown()


def test_dock_controls_exclude_character_hit_region_without_changing_collision_body(qapp,tmp_path):
    from PySide6.QtWidgets import QWidget
    from dock_twoo.brain.control_surfaces import protect_controls
    manager=manager_at(tmp_path,inventory()[:1]);actor=manager.companion
    actor.move(100,100)
    actor.set_input_shape(payload(actor.size(),[QRect(40,20,120,180)]))
    body=actor.body_region()
    panel=QWidget();panel.setGeometry(180,100,100,240);protect_controls(panel)
    panel.show();qapp.processEvents()
    assert actor.body_region()==body  # Collision geometry stays the real silhouette.
    assert not actor.mask().contains(QPoint(100,50))
    assert not actor.input_hit_region().contains(QPoint(100,50))
    assert actor.mask().contains(QPoint(50,50))
    panel.move(120,100);qapp.processEvents()
    assert not actor.mask().contains(QPoint(50,50))
    panel.hide();qapp.processEvents()
    assert actor.mask()==body and actor.input_hit_region()==body
    panel.show();qapp.processEvents()
    from shiboken6 import delete
    delete(panel);qapp.processEvents()
    assert actor.mask()==body
    manager.shutdown()
