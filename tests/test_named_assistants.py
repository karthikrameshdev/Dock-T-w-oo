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
    assert rio.activity=='processing' and brain is rio
    listener._begin_wake_capture([], 'default')
    assert manager._listening_actor_id==brain.actor_id
    assert brain.activity=='listening' and brain.character_id=='default'
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
    rio=manager.select_character('parrot',entries[1]['id'])
    turn=Turn('Research','console',rio.actor_id,{},'',run_id='fixture',character_id='parrot',character_name='Rio')
    manager._processing_turns[turn.run_id]={'turn':turn,'cancel':threading.Event(),'agent':manager.agent}
    manager.configure_displays(entries[:1],entries[:1])
    replacement=manager.actor_for(turn.actor_id)
    assert replacement.character_id=='parrot' and replacement.screen_id==entries[0]['id']
    assert turn.character_id=='parrot' and rio.actor_id in manager.companions and len(manager.companions)==1
    manager._processing_turns.clear();manager.shutdown()

def test_selected_species_uses_its_own_animation_library(qapp,tmp_path,monkeypatch):
    manager=manager_at(tmp_path,inventory()[:1]);manager.store.set_setting('roaming',True)
    monkeypatch.setattr(random,'random',lambda:0)
    monkeypatch.setattr(random,'choice',lambda values:values[0])
    for identity in ('default','parrot','owl','fox'):
        actor=manager.choose_assistant(identity)
        actor.last_dragged=0;actor._roam()
        assert actor.action in actor.actions
        assert len(manager.companions)==1
    manager.shutdown()


def test_delayed_animation_policy_cannot_animate_replacement_character(qapp,tmp_path):
    from concurrent.futures import Future
    manager=manager_at(tmp_path,inventory()[:1]);actor=manager.companion
    manager.store.set_setting('roaming',True)
    result=Future();result.set_result('wave')
    manager.ecology.pending.add(actor.actor_id)
    manager.choose_assistant('parrot')
    manager.ecology.apply(actor,actor.actor_id,result,'default')
    assert actor.action is None and actor.actor_id not in manager.ecology.pending
    manager.shutdown()


def test_delayed_reply_gesture_does_not_follow_character_switch(qtbot,tmp_path):
    from dock_twoo.brain.agent import AgentReply
    manager=manager_at(tmp_path,inventory()[:1])
    manager.animation_director.respond(AgentReply('Hello',gesture='wave'))
    manager.choose_assistant('owl')
    qtbot.wait(220)
    assert manager.companion.character_id=='owl' and manager.companion.action is None
    manager.shutdown()
