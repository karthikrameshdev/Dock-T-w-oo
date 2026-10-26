from types import SimpleNamespace as NS
from PySide6.QtCore import QPoint,QRect
from PySide6.QtGui import QRegion
from dock_twoo.brain.navigation import find_route,segment_clear
from tests.test_multi_brain import manager_at,inventory


def test_routes_around_wall_without_cutting_through_it():
    area=QRect(0,0,600,400);shape=QRegion(0,0,30,40);wall=QRegion(220,0,40,270)
    start=QPoint(80,80);goal=QPoint(400,80)
    route=find_route(start,goal,area,shape,[wall])
    assert route and route[-1]==goal and any(p.y()>=270 for p in route)
    clear=lambda p:area.contains(shape.translated(p).boundingRect()) and not shape.translated(p).intersects(wall)
    previous=start
    for point in route:
        assert segment_clear(previous,point,clear);previous=point


def test_occupied_goal_and_blocked_edge_choose_reachable_refuge():
    shape=QRegion(0,0,30,40);area=QRect(-600,24,600,400)
    obstacle=QRegion(-400,24,200,340)
    start=QPoint(-500,30);goal=QPoint(-350,30)
    route=find_route(start,goal,area,shape,[obstacle])
    assert route and route[-1]!=goal and route[-1]!=start
    assert all(not shape.translated(p).intersects(obstacle) for p in route)
    assert all(area.contains(shape.translated(p).boundingRect()) for p in route)










def test_temporary_file_lock_does_not_leave_completed_worker_busy(qapp,tmp_path,monkeypatch):
    import threading
    manager=manager_at(tmp_path,inventory()[1:2]);coordinator=manager.coordinator
    parent,_=coordinator.begin('default','Research',{},threading.Event())
    task,workspace=coordinator.begin('fox','Write a report',{},threading.Event(),parent,assigning_identity='default')
    (workspace/'report.txt').write_text('Completed research')
    folder=coordinator.workspaces[task];cleanup=folder.cleanup
    monkeypatch.setattr(folder,'cleanup',lambda:(_ for _ in ()).throw(PermissionError('File in use')))
    outputs=coordinator.complete('fox',task,'Done')
    assert outputs and coordinator.agent_states['fox']=='idle'
    assert task not in coordinator.workspaces and task in coordinator.cleanup_pending
    assert next(job for job in coordinator.snapshot()['jobs'] if job['id']==task)['state']=='complete'
    monkeypatch.setattr(folder,'cleanup',cleanup)
    coordinator.cleanup_pending[task]=(folder,0)
    assert coordinator.cleanup_finished_workspaces()==0 and not workspace.exists()
    coordinator.complete('default',parent,'Done')
    assert len(manager.companions)==1
    manager.shutdown()


def test_budget_never_freezes_the_visible_assistant(qapp,tmp_path):
    manager=manager_at(tmp_path,inventory()[1:2]);actor=manager.companion
    # No GPU is needed to check the timer lifecycle; native soak checks pixels.
    class View:
        ready=True;parked=False
        def set_parked(self,value):self.parked=value
    actor.model_view=View()
    try:
        assert manager.resources.stats['target_cpu_percent'] is None
        for state in ('idle','listening','processing','thinking','queued','speaking'):
            actor.activity=state;manager.resources.level=4;manager.resources._budget()
            assert not actor.resource_resting and not actor.model_view.parked
            assert actor.activity_timer.isActive() and actor.roam_timer.isActive()
            assert actor.render_fps >= (10 if state=='idle' else 18)
    finally:
        actor.model_view=None;manager.shutdown()


def test_optional_cap_stops_only_body_motion_and_survives_restart(qapp,tmp_path):
    from dock_twoo.brain.storage import BrainStore
    manager=manager_at(tmp_path,inventory()[1:2]);actor=manager.companion
    try:
        menu=manager._build_context_menu()
        cap=next(a for a in menu.actions() if a.text()=='Cap resource to 25%')
        assert cap.isCheckable() and not cap.isChecked()
        actor.play_action('walk',actor.pos()+QPoint(100,0))
        assert actor.action=='walk'
        cap.setChecked(True)
        assert actor.resource_capped and not actor.motion_timer.isActive() and actor.action is None
        position=actor.pos()
        actor.play_action('wave');actor._roam();actor.turn_to_side()
        actor._follow_cursor_step(position+QPoint(150,100),.1)
        assert actor.pos()==position and actor.action is None and actor._yaw==0
        actor.set_activity('speaking');actor.set_mouth(.9);actor._blink();actor._animate_activity()
        assert actor.mouth_level>0 and actor.blinking and actor.activity_timer.isActive()
        assert BrainStore(tmp_path).setting('resource_cap_enabled') is True
        cap.setChecked(False)
        actor.play_action('wave');assert actor.action=='wave'
        assert manager.resources.stats['target_cpu_percent'] is None
        assert BrainStore(tmp_path).setting('resource_cap_enabled') is False
    finally:manager.shutdown()

def test_housekeeper_and_background_leases_never_create_character_windows(qapp,tmp_path):
    import threading
    manager=manager_at(tmp_path,inventory()[:2]);actor=manager.companion
    root,_=manager.coordinator.begin('orbit','Plan',{},threading.Event())
    child,_=manager.coordinator.begin('default','Research',{},threading.Event(),root,assigning_identity='orbit')
    manager.ecology.next['obsolete']=999
    manager.resources.tick()
    assert len(manager.companions)==1 and manager.companion is actor
    assert 'obsolete' not in manager.ecology.next
    assert manager.coordinator.agent_states['default']=='processing'
    manager.coordinator.complete('default',child,'Done')
    manager.coordinator.complete('orbit',root,'Combined')
    manager.notifications.clear()
    assert len(manager.companions)==1
    manager.shutdown()
