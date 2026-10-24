"""Cloud-only configuration and validated local capabilities."""
from datetime import date
from pathlib import Path
import threading
from types import SimpleNamespace
import pytest
from dock_twoo.brain.cloud import validate_config,NOT_CONFIGURED
from dock_twoo.brain.profiles import ProfileManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.agent import BrainAgent
from dock_twoo.brain.agent_tools import LocalTools,validate_arguments
from dock_twoo.tasks import TaskStore,NotesService


def test_local_profile_migrates_to_an_unconfigured_cloud_model(tmp_path):
    store=BrainStore(tmp_path)
    store.set_setting('profiles',[{'id':'local','provider':'local','model':'local'}]);store.set_setting('active_profile','local')
    manager=ProfileManager(store)
    assert manager.get_active_profile()['status']=='not configured'
    assert manager.get_profiles()[0]['id']=='cloud'
    assert store.setting('profiles')==[]
    assert BrainAgent(manager).run('Open Cursor')==NOT_CONFIGURED


def test_config_requires_https_external_url_and_explicit_model():
    for url in ('http://example.com/v1','http://127.0.0.1:11434/v1','https://127.0.0.1/v1','https://user:key@example.com/v1'):
        with pytest.raises(ValueError):validate_config({'provider':'custom','model':'example','base_url':url})
    assert validate_config({'provider':'anthropic','model':'configured-model'})['protocol']=='anthropic'


def test_legacy_keys_are_migrated_and_never_returned_in_settings(tmp_path):
    store=BrainStore(tmp_path);store.set_setting('cloud_keys',{'gemini':'private-test-secret'})
    manager=ProfileManager(store)
    assert manager.get_key('gemini')=='private-test-secret'
    assert 'private-test-secret' not in store.settings_file.read_text()
    assert 'private-test-secret' not in (tmp_path/'cloud-credentials.enc').read_bytes().decode('latin1')
    assert (tmp_path/'cloud-credentials.key').stat().st_mode & 0o077==0


def test_work_entries_persist_by_date_and_deduplicate(tmp_path):
    store=TaskStore(tmp_path)
    first=store.add('Implemented cloud agent',date='2026-01-05')
    duplicate=store.add('Implemented cloud agent',date='2026-01-05')
    assert duplicate['duplicate'] and duplicate['id']==first['id']
    store.add('Reviewed voice latency',date='2026-01-06')
    assert len(TaskStore(tmp_path).list(date='2026-01-05')['tasks'])==1
    assert len(store.list(start='2026-01-05',end='2026-01-06')['tasks'])==2
    assert store.update(first['id'],status='in_progress')['status']=='in_progress'
    with pytest.raises(ValueError):store.list(date='January fifth')


def test_voice_notes_use_the_existing_drawer_format(tmp_path):
    notes=NotesService(tmp_path)
    item=notes.add('Today','I worked on the voice driver.')
    assert item['id']==notes.add('Today','I worked on the voice driver.')['id']
    assert NotesService(tmp_path).list('voice')['notes'][0]['body']=='I worked on the voice driver.'
    assert (tmp_path/(item['id']+'.json')).exists()


def test_file_tools_read_complete_paginated_content_and_exclude_secrets(tmp_path):
    root=tmp_path/'files';root.mkdir();(root/'one.txt').write_text('A'*17000)
    tools=LocalTools();cancel=threading.Event()
    found=tools.execute('list_files',{'path':str(root)},cancel)
    assert len(found['items'])==1
    first=tools.execute('read_file',{'path':str(root/'one.txt')},cancel)
    second=tools.execute('read_file',{'path':str(root/'one.txt'),'offset':first['next_offset']},cancel)
    assert first['text']+second['text']=='A'*17000 and second['next_offset'] is None
    (root/'.env').write_text('secret')
    with pytest.raises(PermissionError):tools.execute('read_file',{'path':str(root/'.env')},cancel)
    with pytest.raises(ValueError):validate_arguments('read_file',{'path':'ok','extra':'no'})
    cancel.set()
    with pytest.raises(InterruptedError):tools.execute('list_files',{'path':str(root)},cancel)


def test_file_creation_never_overwrites_existing_content(tmp_path):
    tools=LocalTools();cancel=threading.Event();path=tmp_path/'new.txt'
    assert tools.execute('write_file',{'path':str(path),'text':'original'},cancel)['verified']
    with pytest.raises(FileExistsError):tools.execute('write_file',{'path':str(path),'text':'replacement'},cancel)
    assert path.read_text()=='original'


def test_stop_prevents_tool_execution_after_a_provider_returns(tmp_path):
    from dock_twoo.brain.cloud import ModelTurn
    store=BrainStore(tmp_path/'brain');profiles=ProfileManager(store)
    profiles.save_profile({'provider':'custom','base_url':'https://fixture.example/v1','model':'fixture','api_key':'fixture'})
    cancel=threading.Event();calls=[]
    class Client:
        def __init__(self,*_args):pass
        def turn(self,*_args):
            cancel.set()
            return ModelTurn({'role':'assistant','content':''},[{'id':'one','name':'write_file','arguments':{'path':'x','text':'x'}}],'')
    agent=BrainAgent(profiles,tools=SimpleNamespace(execute=lambda *_:calls.append(True)),client_factory=Client)
    with pytest.raises(InterruptedError):agent.run('Create a document',cancel=cancel)
    assert calls==[]


def test_model_animation_decisions_respect_reduced_motion(tmp_path,qapp,monkeypatch):
    from dock_twoo.brain.manager import BrainManager
    from dock_twoo.brain.agent import AgentReply
    manager=BrainManager(store=BrainStore(tmp_path),start_services=False)
    manager.store.set_setting('reduced_motion',True)
    manager.animation_director.respond(AgentReply('Great',emotion='excited',gesture='celebrate'))
    assert manager.animation_director.last_decision['action']=='celebrate'
    manager.animation_director.cancel();manager.companion.close()


def test_cancelled_queued_gui_action_does_not_execute():
    callbacks=[];executed=[];cancel=threading.Event()
    tools=LocalTools(SimpleNamespace(run_on_main_thread=callbacks.append))
    def run():
        with pytest.raises(InterruptedError):tools.on_main(lambda:executed.append(True),cancel)
    thread=threading.Thread(target=run);thread.start()
    while not callbacks:threading.Event().wait(.001)
    cancel.set();callbacks[0]();thread.join(1)
    assert not thread.is_alive() and executed==[]


def test_keep_awake_releases_only_its_owned_process(monkeypatch):
    import dock_twoo.keep_awake as module
    calls=[]
    class Process:
        def poll(self):return None
        def terminate(self):calls.append('terminate')
        def wait(self,timeout):calls.append('wait')
    monkeypatch.setattr(module.platform,'system',lambda:'Darwin')
    monkeypatch.setattr(module.subprocess,'Popen',lambda args,**kwargs:calls.append(args) or Process())
    awake=module.KeepAwake()
    assert awake.set_enabled(True)['enabled']
    assert calls[0][:4]==['/usr/bin/caffeinate','-d','-i','-w']
    assert awake.set_enabled(False)['enabled'] is False
    assert calls[1:]==['terminate','wait']
    awake.close();assert calls[1:]==['terminate','wait']
