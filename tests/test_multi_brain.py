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
    assert len(manager.companions)==1
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




def test_same_character_serial_work_freezes_profile_and_queues_spoken_results(qtbot,tmp_path,monkeypatch):
    manager=manager_at(tmp_path,inventory()[:2]);actors=[manager.companion,manager.companion]
    entered=threading.Event();release=threading.Event();calls=[];concurrency=[0,0]
    config={'provider':'custom','model':'fixture','base_url':'https://example.test/v1'}
    a=manager.profile_mgr.save_profile({**config,'name':'Everyday','api_key':'first-secret'})
    b=manager.profile_mgr.create_profile({**config,'name':'Research','api_key':'second-secret'})
    def run(text,**kwargs):
        concurrency[0]+=1;concurrency[1]=max(concurrency);calls.append((text,kwargs['profile']['id'],kwargs['api_key'],kwargs['character_id']))
        entered.set();release.wait(3);concurrency[0]-=1
        return 'Reply to '+text
    spoken=[]
    def speak(text):spoken.append(text);manager.speech.activity.emit('speaking')
    monkeypatch.setattr(manager.agent,'run',run);monkeypatch.setattr(manager.speech,'start',speak)
    manager._do_turn_complete('first','console',actors[0].actor_id);assert entered.wait(1)
    manager.profile_mgr.activate_profile(b['id'])
    manager._do_turn_complete('second','console',actors[1].actor_id)
    manager.profile_mgr.activate_profile(a['id'])
    assert actors[0].activity=='processing' and len(manager._turn_queue)==1
    assert 'secret' not in str(manager.queue_status())
    release.set();qtbot.waitUntil(lambda:len(spoken)==1)
    qtbot.waitUntil(lambda:len(calls)==2)
    assert actors[0].activity=='speaking' and len(spoken)==1
    manager._on_speech_finished();qtbot.waitUntil(lambda:len(spoken)==2)
    assert calls[1][1:]==(b['id'],'second-secret','default')
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


def test_listening_aura_requires_voice_wake_owner_and_visible_peers_on_same_screen():
    from dock_twoo.brain.model_view import listening_aura_allowed
    first=SimpleNamespace(actor_id='first',screen_id='screen-1',isVisible=lambda:True)
    other=SimpleNamespace(actor_id='other',screen_id='screen-4',isVisible=lambda:True)
    manager=first.manager=other.manager=SimpleNamespace(companions={'first':first},_listening_actor_id='first',_listening_source='voice')
    assert not listening_aura_allowed(first)
    first.manager.companions['other']=other
    assert not listening_aura_allowed(first)  # One Brain per display.
    other.screen_id='screen-1'
    assert not listening_aura_allowed(first)
    assert not listening_aura_allowed(other)
    for source in ('click','shortcut',None):
        manager._listening_source=source
        assert not listening_aura_allowed(first)
    manager._listening_source='voice'
    other.isVisible=lambda:False
    assert not listening_aura_allowed(first)
    other.isVisible=lambda:True
    first.manager.companions.pop('other')
    assert not listening_aura_allowed(first)


def test_idle_click_recovers_stale_microphone_owner_and_follow_cursor_stays_clickable(qtbot,tmp_path):
    from PySide6.QtCore import Qt
    manager=manager_at(tmp_path,inventory()[:1]);actor=manager.companion
    actor.set_follow_cursor(True);actor.follow_timer.stop()
    manager._listening_actor_id=actor.actor_id  # Completed/expired capture, no decoder.
    assert not manager.listener.is_recording and manager.listener._decode_token is None
    assert not actor.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    qtbot.mouseClick(actor,Qt.MouseButton.LeftButton,pos=actor.rect().center())
    assert manager.listener.is_recording and actor.activity=='listening'
    assert manager._listening_source=='click'
    qtbot.mouseClick(actor,Qt.MouseButton.LeftButton,pos=actor.rect().center())
    assert not manager.listener.is_recording  # Silent capture finishes without a model call.
    manager.shutdown()








def test_speech_stop_cannot_turn_running_agent_green(qapp,tmp_path):
    from dock_twoo.brain.sessions import Turn
    manager=manager_at(tmp_path,inventory()[:1])
    turn=Turn('Request','console',manager.companion.actor_id,{},'',run_id='fixture')
    manager._processing_turns[turn.run_id]={'turn':turn,'cancel':threading.Event(),'agent':manager.agent}
    manager._worker_running=True
    manager.speech.stop()
    manager._refresh_actor_states()
    assert manager.companion.activity=='processing' and not manager._active_turn
    manager._processing_turns.clear();manager._worker_running=False
    manager.shutdown()

def test_selection_reuses_one_window_and_services_on_every_display(qapp,tmp_path):
    from dock_twoo.brain.catalog import characters
    entries=inventory();manager=manager_at(tmp_path,entries)
    actor=manager.companion
    services=(manager.listener,manager.speech,manager.agent,manager.audio_devices)
    try:
        for entry in characters():
            chosen=manager.choose_assistant(entry['id'])
            assert chosen is actor and len(manager.companions)==1
            assert actor.character_id==entry['id'] and len(actor.actions)==136
        manager.select_character('orbit',entries[-1]['id'])
        assert actor.screen_id==entries[-1]['id']
        assert services==(manager.listener,manager.speech,manager.agent,manager.audio_devices)
        menu=manager._build_context_menu()
        labels=[action.text() for action in menu.actions()]
        assert 'Choose assistant' in labels and 'Add assistant' not in labels and 'Play together' not in labels
        choices=next(a.menu() for a in menu.actions() if a.text()=='Choose assistant')
        assert len(choices.actions())==30
        next(a for a in choices.actions() if a.text()=='Rio').trigger()
        assert actor.character_id=='parrot'
        manager.hide_mini_agent();manager.show_mini_agent()
        assert actor.isVisible() and len(manager.companions)==1
    finally:manager.shutdown()


def test_saved_crowd_migrates_to_single_selection_and_survives_restart(qapp,tmp_path):
    store=BrainStore(tmp_path)
    store.set_setting('brain_instances',[{'id':'extra-fox','character_id':'fox','screen_id':'old'}])
    store.set_setting('active_character','orbit')
    manager=manager_at(tmp_path,inventory()[:2])
    assert len(manager.companions)==1 and manager.companion.character_id=='orbit'
    assert manager.store.setting('brain_instances')==[]
    manager.choose_assistant('parrot');manager.shutdown()
    manager=manager_at(tmp_path,inventory()[:2])
    assert manager.companion.character_id=='parrot' and len(manager.companions)==1
    manager.shutdown()


def test_selection_cancels_capture_but_not_background_processing(qapp,tmp_path):
    from dock_twoo.brain.sessions import Turn
    manager=manager_at(tmp_path,inventory()[:1]);actor=manager.companion
    token=threading.Event()
    turn=Turn('work','console',actor.actor_id,{},'',run_id='job')
    manager._processing_turns['job']={'turn':turn,'cancel':token,'agent':manager.agent}
    manager.start_talking()
    assert manager.listener.is_recording
    manager.choose_assistant('orbit')
    assert not manager.listener.is_recording and not token.is_set()
    assert turn.character_id=='default' and actor.character_id=='orbit'
    assert actor.activity=='idle'
    manager.toggle_talking();assert actor.activity=='listening'
    assert manager.listener.capture_character_id=='orbit'
    manager.toggle_talking();assert not manager.listener.is_recording
    manager._processing_turns.clear();manager.shutdown()
