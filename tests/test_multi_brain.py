"""Display selection, shared execution, microphone handoff and crowd isolation."""
import threading
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject,QPoint,QRect,Signal
from dock_twoo.config import DockConfig,ConfigManager
from dock_twoo.displays import display_inventory,selected_displays,DisplayController
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.playground import fit_scale,free_position


class Screen(QObject):
    geometryChanged=Signal();availableGeometryChanged=Signal();logicalDotsPerInchChanged=Signal()
    def __init__(self,number,x):super().__init__();self.number=number;self.x=x
    def manufacturer(self):return 'Test'
    def model(self):return 'Monitor'
    def serialNumber(self):return str(self.number)
    def name(self):return f'Display {self.number}'
    def geometry(self):return QRect(self.x,0,1200,800)
    def availableGeometry(self):return QRect(self.x,24,1200,750)
    def devicePixelRatio(self):return 1.


def inventory():
    screens=[Screen(i+1,(i-1)*1200) for i in range(4)]
    return display_inventory(screens,screens[1])


def manager_at(tmp_path,entries):
    manager=BrainManager(store=BrainStore(tmp_path),start_services=False)
    manager.store.set_setting('roaming',False)
    manager.configure_displays(entries,entries)
    return manager


def test_select_only_screens_one_and_four_and_reconnect_without_reassigning(qapp):
    entries=inventory();ids=[entries[0]['id'],entries[3]['id']]
    config=DockConfig(display_mode='selected',display_ids=ids)
    assert [e['number'] for e in selected_displays(config,entries)[0]]==[1,4]
    assert selected_displays(config,[entries[1]])==([entries[1]],True)
    assert config.display_ids==ids
    reordered=display_inventory([e['screen'] for e in reversed(entries)],entries[1]['screen'])
    assert {e['id'] for e in selected_displays(config,reordered)[0]}==set(ids)
    assert len(selected_displays(DockConfig(display_mode='all'),entries)[0])==4
    assert len(selected_displays(DockConfig(screen_index=2),entries)[0])==1


def test_display_controller_keeps_one_service_and_only_selected_docks(qapp,tmp_path):
    entries=inventory();available=[entries]
    config=ConfigManager(tmp_path/'config.json')
    config.update({'display_mode':'selected','display_ids':[entries[0]['id'],entries[3]['id']]})
    manager=BrainManager(store=BrainStore(tmp_path/'brain'),start_services=False)
    class Dock(QObject):
        def __init__(self,config,screen_id,screen_index):
            super().__init__();self.screen_id=screen_id;self.index=screen_index;self.closed=False
        def show(self):pass
        def close(self):self.closed=True
        def set_display_index(self,index):self.index=index
    controller=DisplayController(config,manager,dock_factory=Dock,inventory=lambda:available[0])
    assert set(controller.docks)==set(config.config.display_ids)
    assert len(manager.companions)==2
    original=controller.docks[entries[3]['id']]
    available[0]=entries[:2];controller.refresh()
    assert original.closed and config.config.display_ids==[entries[0]['id'],entries[3]['id']]
    available[0]=entries;controller.refresh()
    assert len(controller.docks)==2
    assert sum(d['selected'] for d in config.display_snapshot['displays'])==2
    controller.close();manager.shutdown()


def test_invalid_display_selections_do_not_partially_save(qapp,tmp_path):
    config=ConfigManager(tmp_path/'config.json')
    for changes in ({'display_mode':'unknown'},{'display_mode':'selected','display_ids':[]},
                    {'display_ids':['a','a']},{'display_mode':'single','display_ids':['a','b']}):
        with pytest.raises(ValueError):config.update(changes)
    assert config.config.display_mode=='single' and config.config.display_ids==[]


def test_two_brains_single_screen_do_not_duplicate_services_or_overlap(qapp,tmp_path):
    entries=inventory()[:1];manager=manager_at(tmp_path,entries)
    services=(manager.listener,manager.speech,manager.agent,manager.audio_devices)
    first=manager.companion
    for _ in range(7):manager.add_brain(entries[0]['id'])
    assert len(manager.companions)==8
    assert services==(manager.listener,manager.speech,manager.agent,manager.audio_devices)
    actors=list(manager.companions.values())
    for i,a in enumerate(actors):
        assert entries[0]['screen'].availableGeometry().contains(a.geometry())
        assert all(not a.geometry().intersects(b.geometry()) for b in actors[i+1:])
    # Deliberately walk one actor into another; the playground resolves it.
    actors[1].move(actors[0].pos());manager.playground.step()
    assert not actors[1].geometry().intersects(actors[0].geometry())
    assert len(manager.store.setting('brain_instances'))==7
    manager.shutdown()


def test_fifo_freezes_profile_and_keeps_other_brain_queued_until_speech_finishes(qtbot,tmp_path,monkeypatch):
    manager=manager_at(tmp_path,inventory()[:2]);actors=list(manager.companions.values())
    entered=threading.Event();release=threading.Event();calls=[];concurrency=[0,0]
    config={'provider':'custom','model':'fixture','base_url':'https://example.test/v1'}
    a=manager.profile_mgr.save_profile({**config,'name':'Everyday','api_key':'first-secret'})
    b=manager.profile_mgr.create_profile({**config,'name':'Research','api_key':'second-secret'})
    def run(text,**kwargs):
        concurrency[0]+=1;concurrency[1]=max(concurrency);calls.append((text,kwargs['profile']['id'],kwargs['api_key'],manager.active_actor_id))
        entered.set();release.wait(3);concurrency[0]-=1
        return 'Reply to '+text
    spoken=[]
    def speak(text):spoken.append(text);manager.speech.activity.emit('speaking')
    monkeypatch.setattr(manager.agent,'run',run);monkeypatch.setattr(manager.speech,'start',speak)
    manager._do_turn_complete('first','console',actors[0].actor_id);assert entered.wait(1)
    manager.profile_mgr.activate_profile(b['id'])
    manager._do_turn_complete('second','console',actors[1].actor_id)
    manager.profile_mgr.activate_profile(a['id'])
    assert actors[0].activity=='processing' and actors[1].activity=='queued'
    assert 'secret' not in str(manager.queue_status())
    release.set();qtbot.waitUntil(lambda:len(spoken)==1)
    assert len(calls)==1 and actors[0].activity=='speaking' and actors[1].activity=='queued'
    manager._on_speech_finished();qtbot.waitUntil(lambda:len(spoken)==2)
    assert calls[1][1:]==(b['id'],'second-secret',actors[1].actor_id)
    assert calls[0][1]==a['id'] and concurrency[1]==1
    manager._on_speech_finished();assert not manager._active_turn
    manager.shutdown()


def test_stop_waits_for_cancelled_worker_before_starting_new_turn(qtbot,tmp_path,monkeypatch):
    manager=manager_at(tmp_path,inventory()[:1]);manager.store.set_setting('voice_reply',False)
    entered=threading.Event();release=threading.Event();calls=[]
    def run(text,**kwargs):
        calls.append(text);entered.set()
        if text=='blocked':release.wait(3)
        if kwargs['cancel'].is_set():raise InterruptedError()
        return text
    monkeypatch.setattr(manager.agent,'run',run)
    manager._do_turn_complete('blocked','console');assert entered.wait(1)
    manager._do_turn_complete('discard this','console');manager.stop_talking()
    manager._do_turn_complete('new turn','console')
    assert calls==['blocked'] and manager._worker_running
    release.set();qtbot.waitUntil(lambda:manager.last_response['text']=='new turn')
    assert calls==['blocked','new turn']
    manager.shutdown()


def test_microphone_handoff_finishes_old_turn_before_new_capture(qtbot,tmp_path,monkeypatch):
    from tests.test_voice_turns import feed,SPEECH,SILENCE
    manager=manager_at(tmp_path,inventory()[:2]);a,b=manager.companions.values()
    manager.store.set_setting('voice_reply',False)
    listener=manager.listener;listener._is_speech_frame=lambda pcm,*_:pcm!=SILENCE
    entered=threading.Event();release=threading.Event();calls=[]
    def decode(pcm):entered.set();release.wait(2);return 'first speaker request'
    monkeypatch.setattr(listener,'_transcribe_pcm',decode)
    monkeypatch.setattr(manager.agent,'run',lambda text,**_:calls.append(text) or 'Done')
    manager.toggle_talking(a.actor_id);feed(listener,SPEECH,8)
    manager.toggle_talking(b.actor_id);assert entered.wait(1)
    assert not listener.is_recording and manager._pending_listener==b.actor_id
    release.set();qtbot.waitUntil(lambda:listener.is_recording)
    assert manager._listening_actor_id==b.actor_id
    assert b.activity=='listening' and a.activity!='listening'
    assert len([c for c in manager.companions.values() if c.activity=='listening'])==1
    manager.shutdown()


def test_crowd_fit_and_negative_screen_coordinates():
    area=QRect(-1600,-900,1600,900)
    assert 0<fit_scale(area,100)<.5
    occupied=[QRect(-1600,-900,200,250)]
    point=free_position(area,(200,250),occupied,QPoint(-1600,-900))
    assert point is not None and area.contains(QRect(point.x(),point.y(),200,250))
    assert not occupied[0].intersects(QRect(point.x(),point.y(),200,250))


def test_roam_all_screens_can_be_disabled_and_restores_home(qapp,tmp_path,monkeypatch):
    entries=inventory();manager=manager_at(tmp_path,[entries[0]])
    manager._all_display_entries={e['id']:e for e in entries}
    actor=manager.companion
    monkeypatch.setattr('dock_twoo.brain.mascot.QApplication.screenAt',lambda point:entries[3]['screen'])
    actor._safe_position(QPoint(2600,200))
    assert actor.screen_id==entries[0]['id']
    manager.set_roam_all_screens(True)
    result=actor._safe_position(QPoint(2600,200))
    assert actor.screen_id==entries[3]['id'] and result.x()==2600
    manager.set_roam_all_screens(False)
    assert actor.screen_id==entries[0]['id']
    manager.shutdown()


def test_context_menu_adds_and_removes_brains_on_single_screen(qapp,tmp_path):
    manager=manager_at(tmp_path,inventory()[:1])
    menu=manager._build_context_menu()
    next(a for a in menu.actions() if a.text()=='Add another Brain').trigger()
    assert len(manager.companions)==2
    menu=manager._build_context_menu()
    sub=next(a.menu() for a in menu.actions() if a.text()=='Brains on this screen')
    next(a for a in sub.actions() if a.text().startswith('Remove Brain')).trigger()
    assert len(manager.companions)==1
    manager.shutdown()


def test_http_thread_captures_profile_before_gui_dispatch(qtbot,tmp_path,monkeypatch):
    manager=manager_at(tmp_path,inventory()[:1]);manager.store.set_setting('voice_reply',False)
    base={'provider':'custom','model':'fixture','base_url':'https://example.test/v1'}
    first=manager.profile_mgr.save_profile({**base,'name':'First','api_key':'first-key'})
    second=manager.profile_mgr.create_profile({**base,'name':'Second','api_key':'second-key'})
    calls=[]
    monkeypatch.setattr(manager.agent,'run',lambda text,**kwargs:calls.append((kwargs['profile']['id'],kwargs['api_key'])) or 'Done')
    sender=threading.Thread(target=lambda:manager.submit_request('Test request','console'));sender.start();sender.join(2)
    assert not sender.is_alive() and calls==[]
    manager.profile_mgr.activate_profile(second['id'])
    qtbot.waitUntil(lambda:bool(calls))
    assert calls==[(first['id'],'first-key')]
    qtbot.waitUntil(lambda:not manager._worker_running)
    manager.shutdown()


def test_passive_stop_and_speech_animation_dispatch_to_gui_thread(qtbot,tmp_path,monkeypatch):
    from PySide6.QtCore import QThread
    manager=manager_at(tmp_path,inventory()[:1]);actor=manager.companion
    stops=[]
    original=manager.stop_talking
    def stop():stops.append(QThread.currentThread());original()
    monkeypatch.setattr(manager,'stop_talking',stop)
    worker=threading.Thread(target=lambda:(manager._set_active_activity('speaking'),actor.set_mouth(.8)))
    worker.start();worker.join(2)
    assert actor.activity=='idle' and actor.mouth_level==0
    qtbot.waitUntil(lambda:actor.activity=='speaking' and actor.mouth_level>0)
    worker=threading.Thread(target=lambda:manager.listener.stop_requested.emit('Brain Stop'))
    worker.start();worker.join(2)
    assert not stops
    qtbot.waitUntil(lambda:bool(stops))
    assert stops==[manager.thread()] and manager.last_response['text']=='Stopped.'
    assert actor.activity=='idle'
    manager.shutdown()
