"""Names, rig isolation, shared voice ownership and collision continuation."""
import random
import threading
import time

import pytest
from PySide6.QtCore import QPoint
from dock_twoo.brain.catalog import characters, character, named_prefix
from dock_twoo.brain.model_view import listening_aura_allowed
from tests.test_multi_brain import manager_at, inventory

@pytest.mark.parametrize('entry', characters(), ids=lambda c:c['name'])
def test_each_name_has_exact_anchored_wake_and_own_actions(entry):
    for prefix in ('', 'Hey ', 'Hello ', 'Hi '):
        assert named_prefix(prefix+entry['name']+', open Cursor') == (entry['id'], 'open Cursor')
        assert named_prefix(prefix+entry['name'])[0] == entry['id']
    assert named_prefix('Please ask '+entry['name']+' to help')[0] is None
    assert len(character(entry['id'])['actions']) == 136
    assert named_prefix(entry['name']+'s are here')[0] is None


def test_all_thirty_on_one_screen_deduplicate_and_restore(qapp,tmp_path):
    entries=inventory()[:1]; manager=manager_at(tmp_path,entries)
    shared=(manager.listener,manager.speech,manager.agent,manager.audio_devices)
    manager.add_all_characters()
    assert len(manager.companions)==30
    for entry in characters():
        a=manager.add_brain(entries[0]['id'],entry['id'])
        assert a.character_id==entry['id'] and a.character_name==entry['name']
        assert len(a.actions)==136 and not listening_aura_allowed(a)
    assert len(manager.companions)==30
    actors=list(manager.companions.values())
    for i,a in enumerate(actors):
        assert all(not manager.playground.region(a).intersects(manager.playground.region(b)) for b in actors[i+1:])
    assert shared==(manager.listener,manager.speech,manager.agent,manager.audio_devices)
    saved=manager.store.setting('brain_instances'); manager.shutdown()
    manager=manager_at(tmp_path,entries)
    assert len(manager.companions)==30 and manager.store.setting('brain_instances')==saved
    manager.shutdown()


def test_named_summon_queue_and_single_mic(qapp,tmp_path,monkeypatch):
    manager=manager_at(tmp_path,inventory()[:1]); listener=manager.listener
    manager.listener.start=lambda:None
    brain=manager.companion
    manager.coordinator.agent_states['parrot']='processing'
    # A running Rio job does not prevent Rio from hearing a full new sentence.
    listener._begin_wake_capture([], 'parrot')
    rio=manager.actor_for(manager._listening_actor_id)
    assert rio.character_name=='Rio' and rio.activity=='listening'
    assert sum(a.activity=='listening' for a in manager.companions.values())==1
    listener.last_completed_transcript='Hey Rio, open Cursor and type hello world'
    manager._on_named_turn_completed('parrot','open Cursor and type hello world',listener.last_completed_transcript,False)
    turn=manager._turn_queue[0]
    assert turn.character_name=='Rio' and turn.text=='open Cursor and type hello world'
    assert rio.activity=='processing' and brain is not rio
    listener._begin_wake_capture([], 'default')
    assert manager._listening_actor_id==brain.actor_id
    assert brain.activity=='listening' and rio.activity=='processing'
    assert not any(listening_aura_allowed(a) for a in manager.companions.values())
    manager._worker_running=False;manager.shutdown()


def test_followup_prefix_routes_to_named_character_without_chopping_request(qapp,tmp_path,monkeypatch):
    manager=manager_at(tmp_path,inventory()[:1]); listener=manager.listener
    manager.coordinator.agent_states['parrot']='processing'; manager.listener.start=lambda:None
    listener.start_recording(); listener.has_spoken=True
    monkeypatch.setattr(listener,'_transcribe_pcm',lambda pcm:'Hey Rio, summarize my tasks for yesterday')
    listener._process_utterance([b'\0'*16000])
    qapp.processEvents()
    turn=manager._turn_queue[0]
    assert turn.character_id=='parrot' and turn.text=='summarize my tasks for yesterday'
    assert manager.activity.detail(turn.run_id)['run']['request']=='Hey Rio, summarize my tasks for yesterday'
    manager._worker_running=False;manager.shutdown()


def test_collision_keeps_clip_route_and_callback_and_resumes(qapp,tmp_path):
    manager=manager_at(tmp_path,inventory()[:1]);a=manager.companion;b=manager.add_brain(character_id='parrot')
    area=a.assigned_screen.availableGeometry();a.move(area.topLeft()+QPoint(150,200));b.move(a.pos()+QPoint(300,0))
    destination=b.pos()+QPoint(150,0);a.play_action('walk',destination,duration=2)
    marker=lambda:None;a.arrival=marker
    # Advancing shapes can cause contact even while the route is clear.
    b.move(a.pos());manager.playground.step()
    assert a.action=='walk' and a.destination==destination and a.arrival is marker
    assert not manager.playground.region(a).intersects(manager.playground.region(b))
    start=QPoint(a.pos());a._last_motion_tick=time.monotonic()-.05;a._advance_motion()
    assert a.action=='walk' and a.pos()!=start
    manager.shutdown()


def test_roaming_uses_species_clip_independently(qapp,tmp_path,monkeypatch):
    manager=manager_at(tmp_path,inventory()[:1]);a=manager.companion;b=manager.add_brain(character_id='parrot')
    manager.store.set_setting('roaming',True)
    monkeypatch.setattr(random,'random',lambda:0)
    monkeypatch.setattr(random,'choice',lambda values:values[0])
    for actor in (a,b):
        actor.last_dragged=0;actor._roam()
        assert actor.action in actor.actions
    assert b.character['actions'][b.action]['category']=='species'
    action,start=b.action,b.motion_started
    a.play_action('dance')
    manager.playground._next_social=0;manager.playground.step()
    assert b.action==action and b.motion_started==start
    manager.shutdown()


def test_acoustic_greeting_alias_and_short_noise_rejection():
    from dock_twoo.brain.listener import command_after_keyword
    assert named_prefix('Hei Bao, open my notes.',acoustic=True)==('panda','open my notes.')
    assert named_prefix('Hei Bao, open my notes.')[0] is None
    assert command_after_keyword('unrelated short noise','Rio',strict=True)==(False,'')
    assert command_after_keyword('I like green','Rio',strict=True)==(False,'')
    assert command_after_keyword('open my notes','Rio',strict=True)==(True,'open my notes')


def test_running_character_keeps_identity_when_its_display_disconnects(qapp,tmp_path):
    from dock_twoo.brain.sessions import Turn
    entries=inventory()[:2];manager=manager_at(tmp_path,entries)
    rio=manager.add_brain(entries[1]['id'],'parrot')
    turn=Turn('Research','console',rio.actor_id,{},'',run_id='fixture',character_id='parrot',character_name='Rio')
    manager._processing_turns[turn.run_id]={'turn':turn,'cancel':threading.Event(),'agent':manager.agent}
    manager.configure_displays(entries[:1],entries[:1])
    replacement=manager.actor_for(turn.actor_id)
    assert replacement.character_id=='parrot' and replacement.screen_id==entries[0]['id']
    assert turn.character_id=='parrot' and rio.actor_id not in manager.companions
    manager._processing_turns.clear();manager.shutdown()
