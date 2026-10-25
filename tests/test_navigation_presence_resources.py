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


def test_budget_resumes_roaming_and_prioritizes_the_listener(qapp,tmp_path,monkeypatch):
    from PySide6.QtGui import QCursor
    manager=manager_at(tmp_path,inventory()[1:2]);actor=manager.companion
    # No GPU is needed to check the timer lifecycle; native soak checks pixels.
    class View:
        ready=True;parked=False
        def set_parked(self,value):self.parked=value
    actor.model_view=View()
    monkeypatch.setattr(QCursor,'pos',lambda:QPoint(-5000,-5000))
    try:
        manager.resources.level=4;manager.resources._budget()
        assert actor.resource_resting and not actor.roam_timer.isActive()
        manager.resources.level=0;manager.resources._budget()
        assert not actor.resource_resting and actor.roam_timer.isActive()
        actor.activity='listening';manager.resources.level=4;manager.resources._budget()
        assert not actor.resource_resting and not actor.model_view.parked
    finally:
        actor.model_view=None;manager.shutdown()

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
