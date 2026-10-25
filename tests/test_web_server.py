"""Tests for Web Console HTTP server and REST endpoints."""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path

import pytest

from dock_twoo.config import ConfigManager, DockConfig
from dock_twoo.server import WebConsoleServer


@pytest.fixture
def test_server(tmp_path: Path):
    config_file = tmp_path / "config.json"
    mgr = ConfigManager(config_path=config_file)
    # Use random high port to avoid conflict
    import random
    port = random.randint(29000, 31000)
    mgr.update({"server_port": port, "server_host": "127.0.0.1", "storage_path": str(tmp_path / "storage")})

    server = WebConsoleServer(mgr)
    server.start()
    time.sleep(0.3)  # Give thread a moment to bind

    yield server, port, mgr

    server.stop()


def test_web_console_get_config(test_server):
    server, port, mgr = test_server
    url = f"http://127.0.0.1:{port}/api/config"

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=3) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "edge" in data
        assert "dock_width" in data
        assert data["server_port"] == port


def test_web_console_post_config_update(test_server):
    server, port, mgr = test_server
    url = f"http://127.0.0.1:{port}/api/config"

    payload = json.dumps({"edge": "left", "icon_size": 28}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=3) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["success"] is True
        assert data["config"]["edge"] == "left"
        assert data["config"]["icon_size"] == 28

    assert mgr.config.edge == "left"
    assert mgr.config.icon_size == 28


def test_web_console_status_endpoint(test_server):
    server, port, mgr = test_server
    url = f"http://127.0.0.1:{port}/api/status"

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=3) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["name"] == "Dock T(w)oo"
        assert data["running"] is True


def test_web_console_serves_html(test_server):
    server, port, mgr = test_server
    url = f"http://127.0.0.1:{port}/"

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=3) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "<title>Dock T(w)oo" in html
        assert "Settings Console" in html
        assert "Global Storage &amp; Data" in html or "Global Storage & Data" in html
        assert "cursor: pointer !important;" in html


def test_web_console_storage_endpoint_and_migration(test_server, tmp_path):
    server, port, mgr = test_server
    url = f"http://127.0.0.1:{port}/api/storage"

    # 1. GET /api/storage returns root path and subdirectories
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=3) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "storage_path" in data
        assert "subsystems" in data
        assert "notes" in data["subsystems"]
        assert "vault" in data["subsystems"]
        assert "models" in data["subsystems"]
        assert "brain" in data["subsystems"]

    # 2. POST /api/storage/change migrates safely to new directory
    target_storage = tmp_path / "custom_dock2_storage"
    change_url = f"http://127.0.0.1:{port}/api/storage/change"
    payload = json.dumps({"new_path": str(target_storage)}).encode("utf-8")
    req = urllib.request.Request(change_url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["success"] is True
        assert data["storage_path"] == str(target_storage.resolve())
        assert (target_storage / "notes").exists()
        assert (target_storage / "vault").exists()
        assert (target_storage / "models").exists()
        assert (target_storage / "brain").exists()


def test_web_console_brain_providers_catalog(test_server):
    server, port, mgr = test_server
    url = f"http://127.0.0.1:{port}/api/brain/providers"

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=3) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "catalog" in data
        catalog = data["catalog"]
        for p in ("gemini", "openai", "anthropic", "openrouter", "deepseek", "xai", "huggingface", "custom"):
            assert p in catalog
        assert "roles" in data
        for r in ("text_output", "computer_use"):
            assert r in data["roles"]


def test_voice_check_requires_explicit_local_control(test_server, monkeypatch):
    from types import SimpleNamespace
    from dock_twoo.brain.manager import BrainManager
    calls = []
    monkeypatch.setattr(BrainManager, '_instance', SimpleNamespace(listener=SimpleNamespace(begin_voice_check=lambda: calls.append(True))))
    _, port, _ = test_server
    url = f'http://127.0.0.1:{port}/api/brain/voice-check'
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(urllib.request.Request(url, data=b''), timeout=3)
    assert calls == []
    request = urllib.request.Request(url, data=b'', headers={'X-Brain-Voice-Check': 'local'})
    with urllib.request.urlopen(request, timeout=3) as response:
        assert json.load(response) == {'success': True, 'seconds': 30}
    assert calls == [True]


def test_external_websites_cannot_read_diagnostic_transcripts(test_server, monkeypatch):
    from types import SimpleNamespace
    from dock_twoo.brain.manager import BrainManager
    def status():
        return {'last_response': {'generation':1,'text':'Private conversation'}, 'voice_input': {'wake_diagnostics': {'voice_check': {'heard': [{'heard': 'Hey Brain'}]}}}}
    monkeypatch.setattr(BrainManager, '_instance', SimpleNamespace(get_status=status))
    _, port, _ = test_server
    request = urllib.request.Request(f'http://127.0.0.1:{port}/api/brain/status', headers={'Origin': 'https://example.com'})
    with urllib.request.urlopen(request, timeout=3) as response:
        result=json.load(response)
        assert result['voice_input']['wake_diagnostics']['voice_check']['heard'] == []
        assert 'last_response' not in result


def test_reader_actions_require_local_controls_and_dispatch_to_manager(test_server, monkeypatch):
    from types import SimpleNamespace
    from dock_twoo.brain.manager import BrainManager
    calls = []
    manager = SimpleNamespace(start_reading=lambda mode: calls.append(mode), stop_reading=lambda: calls.append('stop'))
    monkeypatch.setattr(BrainManager, '_instance', manager)
    _server, port, _mgr = test_server
    def request(action, headers):
        return urllib.request.Request(f'http://127.0.0.1:{port}/api/brain/action',
            data=json.dumps({'action': action}).encode(), headers={'Content-Type':'application/json', **headers})
    for headers in ({}, {'X-Brain-Reader':'local', 'Origin':'https://example.com'}):
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request('read_desktop', headers), timeout=3)
        assert error.value.code == 400
    assert calls == []
    for action in ('read_desktop', 'read_window', 'stop_reading'):
        with urllib.request.urlopen(request(action, {'X-Brain-Reader':'local', 'Origin':f'http://127.0.0.1:{port}'}), timeout=3) as response:
            assert json.loads(response.read())['success']
    assert calls == ['window', 'window', 'stop']


def test_reader_action_reports_missing_desktop_manager(test_server, monkeypatch):
    from dock_twoo.brain.manager import BrainManager
    monkeypatch.setattr(BrainManager, '_instance', None)
    _server, port, _mgr = test_server
    request = urllib.request.Request(f'http://127.0.0.1:{port}/api/brain/action',
        data=b'{"action":"read_desktop"}', headers={'X-Brain-Reader':'local'})
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=3)
    assert 'not running' in json.loads(error.value.read())['error']


def test_text_requests_are_local_validated_and_queued(test_server, monkeypatch):
    from types import SimpleNamespace
    from dock_twoo.brain.manager import BrainManager
    calls=[]
    monkeypatch.setattr(BrainManager, '_instance', SimpleNamespace(turn_complete_requested=SimpleNamespace(emit=calls.append)))
    _,port,_=test_server
    url=f'http://127.0.0.1:{port}/api/brain/request'
    def request(text, headers):
        return urllib.request.Request(url,data=json.dumps({'text':text}).encode(),headers={'Content-Type':'application/json',**headers})
    for text,headers in [('Open Cursor',{}),('Open Cursor',{'X-Brain-Request':'local','Origin':'https://example.com'}),('',{'X-Brain-Request':'local'}),(7,{'X-Brain-Request':'local'}),('x'*2001,{'X-Brain-Request':'local'})]:
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(request(text,headers),timeout=3)
    assert calls==[]
    with urllib.request.urlopen(request('  Open the Cursor application and type hello world  ',{'X-Brain-Request':'local','Origin':f'http://127.0.0.1:{port}'}),timeout=3) as response:
        assert response.status==202 and json.load(response)['success']
    assert calls==['Open the Cursor application and type hello world']


def test_dated_tasks_api_persists_filters_and_updates(test_server):
    from dock_twoo.tasks import TaskStore
    _,port,mgr=test_server
    base=f'http://127.0.0.1:{port}/api/tasks'
    def post(body,headers=None):
        request=urllib.request.Request(base,data=json.dumps(body).encode(),headers={'X-Brain-Request':'local','Content-Type':'application/json',**(headers or {})})
        return json.load(urllib.request.urlopen(request,timeout=3))
    first=post({'title':'Reviewed cloud agent','date':'2026-01-05'})['task']
    assert post({'title':'Reviewed cloud agent','date':'2026-01-05'})['task']['duplicate']
    post({'title':'Improved reading','date':'2026-01-06'})
    with urllib.request.urlopen(base+'?date=2026-01-05',timeout=3) as response:
        assert [entry['id'] for entry in json.load(response)['tasks']]==[first['id']]
    assert post({'id':first['id'],'status':'todo'})['task']['status']=='todo'
    assert len(TaskStore(mgr.config.get_storage_path()/'tasks').list()['tasks'])==2
    for request in (urllib.request.Request(base,headers={'Origin':'https://example.com'}),
                    urllib.request.Request(base,data=b'{"title":"foreign"}',headers={'Content-Type':'application/json'})):
        with pytest.raises(urllib.error.HTTPError) as error:urllib.request.urlopen(request,timeout=3)
        assert error.value.code==403


def test_cloud_config_api_redacts_key_and_rejects_local_models(test_server,monkeypatch,tmp_path):
    from types import SimpleNamespace
    from dock_twoo.brain.storage import BrainStore
    from dock_twoo.brain.profiles import ProfileManager
    from dock_twoo.brain.manager import BrainManager
    store=BrainStore(tmp_path/'isolated-brain');profiles=ProfileManager(store)
    monkeypatch.setattr(BrainManager,'_instance',SimpleNamespace(store=store,profile_mgr=profiles))
    _,port,_=test_server
    base=f'http://127.0.0.1:{port}/api/brain/'
    def request(path,body):
        return urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Brain-Request':'local'})
    with urllib.request.urlopen(base+'model',timeout=3) as response:assert json.load(response)['model']['status']=='not configured'
    with urllib.request.urlopen(request('model',{'provider':'custom','base_url':'https://fixture.example/v1','model':'test-model','api_key':'private-test-key'}),timeout=3) as response:
        result=response.read().decode();assert 'private-test-key' not in result and json.loads(result)['model']['key_configured']
    assert profiles.get_key('custom')=='private-test-key'
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(request('model',{'provider':'custom','base_url':'http://localhost:11434','model':'local'}),timeout=3)
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(request('settings',{'cloud_keys':{'custom':'unsafe'}}),timeout=3)
    assert 'private-test-key' not in store.settings_file.read_text()


def test_keep_awake_api_requires_explicit_boolean_and_local_origin(test_server,monkeypatch):
    from types import SimpleNamespace
    import dock_twoo.keep_awake as module
    state={'enabled':False}
    def toggle(enabled):state['enabled']=enabled;return dict(state)
    monkeypatch.setattr(module,'get_keep_awake',lambda:SimpleNamespace(status=lambda:dict(state),set_enabled=toggle))
    _,port,_=test_server
    base=f'http://127.0.0.1:{port}/api/keep-awake'
    def post(value,headers=None):
        req=urllib.request.Request(base,data=json.dumps({'enabled':value}).encode(),headers={'X-Brain-Request':'local',**(headers or {})})
        return json.load(urllib.request.urlopen(req,timeout=3))
    assert post(True)['enabled'] is True
    assert post(False)['enabled'] is False
    with pytest.raises(urllib.error.HTTPError):post('true')
    with pytest.raises(urllib.error.HTTPError):post(True,{'Origin':'https://example.com'})
    assert state['enabled'] is False


def test_console_serves_new_native_icons(test_server):
    _,port,_=test_server
    for name in ('logo','tasks','coffee'):
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/icons/{name}.svg',timeout=3) as response:
            assert response.status==200 and '<svg' in response.read().decode()


def test_activity_and_usage_endpoints_are_local_and_share_the_ledger(test_server):
    from dock_twoo.brain.activity import ActivityStore
    _,port,mgr=test_server
    store=ActivityStore(mgr.config.get_brain_dir()/'activity');ident=store.start('An isolated test request','console')
    call=store.begin_call(ident,{'provider':'custom','model':'fixture'},{'messages':[{'role':'user','content':'hello'}]})
    store.end_call(call,{'usage':{'prompt_tokens':10,'completion_tokens':4,'total_tokens':14}},'openai');store.finish(ident,'complete','Done')
    for path in ('/api/activity','/api/activity/'+ident,'/api/usage'):
        url=f'http://127.0.0.1:{port}'+path
        for headers in ({},{'X-Brain-Request':'local','Origin':'https://example.com'}):
            with pytest.raises(urllib.error.HTTPError) as error:urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=3)
            assert error.value.code==403
        with urllib.request.urlopen(urllib.request.Request(url,headers={'X-Brain-Request':'local'}),timeout=3) as response:
            data=json.load(response)
            if path=='/api/activity':assert data['runs'][0]['cloud_calls']==1
            elif path=='/api/usage':assert data['summary']['total_tokens']==14
            else:assert data['run']['request']=='An isolated test request' and len(data['events'])==2


def test_tasks_api_search_status_ranges_and_full_counts(test_server):
    from urllib.parse import urlencode
    from dock_twoo.tasks import TaskStore
    _,port,mgr=test_server
    store=TaskStore(mgr.config.get_storage_path()/'tasks')
    store.add('Release review',details='Audio validation',date='2026-01-05',status='done')
    store.add('Pending review',details='Audio research',date='2026-01-06',status='todo')
    store.add('Older review',details='Audio validation',date='2025-12-31')
    query=urlencode({'start':'2026-01-01','end':'2026-01-31','query':'Audio','status':'done'})
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/tasks?'+query,timeout=3) as response:
        data=json.load(response)
    assert data['total']==1 and data['tasks'][0]['title']=='Release review'
    assert data['counts']=={'done':1,'todo':0,'in_progress':0}
    for query in ('start=2026-02-01&end=2026-01-01','status=invalid','offset=bad'):
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/api/tasks?'+query,timeout=3)
        assert error.value.code==400


def test_cloud_profile_crud_switch_and_foreign_origin_protection(test_server,tmp_path,monkeypatch):
    from dock_twoo.brain.profiles import ProfileManager
    from dock_twoo.brain.storage import BrainStore
    from dock_twoo.server import web_server as module
    _,port,_=test_server;manager=ProfileManager(BrainStore(tmp_path/'profiles'))
    monkeypatch.setattr(module,'_get_safe_profile_mgr',lambda:manager)
    root=f'http://127.0.0.1:{port}'
    def request(path,body=None,origin=None):
        headers={'X-Brain-Request':'local','Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        req=urllib.request.Request(root+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with urllib.request.urlopen(req,timeout=3) as response:return json.load(response)
    first=request('/api/brain/model',{'name':'Everyday','provider':'custom','model':'same','base_url':'https://models.example/v1','api_key':'first-secret'})['model']
    second=request('/api/brain/profiles',{'name':'Research','provider':'custom','model':'same','base_url':'https://models.example/v1','api_key':'second-secret'})['profile']
    data=request('/api/brain/profiles')
    assert len(data['profiles'])==2 and data['active']['id']==first['id']
    assert 'secret' not in json.dumps(data)
    request('/api/brain/activate-profile',{'profile_id':second['id']})
    assert request('/api/brain/model')['model']['id']==second['id']
    assert manager.get_key('custom')=='second-secret'
    for path,body in (('/api/brain/profiles',{}),('/api/brain/activate-profile',{'profile_id':first['id']}),('/api/brain/profile/delete',{'profile_id':second['id']})):
        with pytest.raises(urllib.error.HTTPError) as error:request(path,body,'https://example.com')
        assert error.value.code==403
    request('/api/brain/profile/delete',{'profile_id':second['id']})
    assert request('/api/brain/model')['model']['id']==first['id']
    with pytest.raises(urllib.error.HTTPError) as error:request('/api/brain/activate-profile',{'profile_id':'unknown'})
    assert error.value.code==400


def test_usage_api_filters_profiles_and_keeps_deleted_history(test_server,tmp_path,monkeypatch):
    from dock_twoo.brain.activity import ActivityStore
    from dock_twoo.brain.profiles import ProfileManager
    from dock_twoo.brain.storage import BrainStore
    from dock_twoo.server import web_server as module
    _,port,settings=test_server;manager=ProfileManager(BrainStore(tmp_path/'profiles'))
    monkeypatch.setattr(module,'_get_safe_profile_mgr',lambda:manager)
    profile=manager.save_profile({'name':'Everyday','provider':'custom','model':'same','base_url':'https://models.example/v1'})
    tracker=ActivityStore(settings.config.get_brain_dir()/'activity')
    for config,count in ((profile,10),({**profile,'id':'other','name':'Other profile'},30)):
        run=tracker.start('Synthetic');call=tracker.begin_call(run,config,{})
        tracker.end_call(call,{'usage':{'prompt_tokens':count,'completion_tokens':2,'total_tokens':count+2}},'openai');tracker.finish(run,'complete')
    def get(query=''):
        request=urllib.request.Request(f'http://127.0.0.1:{port}/api/usage'+query,headers={'X-Brain-Request':'local'})
        with urllib.request.urlopen(request,timeout=3) as response:return json.load(response)
    assert get()['summary']['total_tokens']==44
    assert get('?profile='+profile['id'])['summary']['total_tokens']==12
    manager.delete_profile(profile['id'])
    data=get('?profile='+profile['id']);assert data['summary']['total_tokens']==12
    assert next(p for p in data['profile_options'] if p['id']==profile['id'])['historical']


def test_displays_api_and_selected_subset_are_local_and_persistent(test_server):
    _,port,config=test_server
    config.display_snapshot={'mode':'single','display_ids':['first'],'fallback':False,'displays':[
        {'id':str(i),'number':i,'name':f'Screen {i}','geometry':[i*1200,0,1200,800],'primary':i==1,'selected':i==1}
        for i in range(1,5)]}
    url=f'http://127.0.0.1:{port}'
    with pytest.raises(urllib.error.HTTPError):urllib.request.urlopen(url+'/api/displays',timeout=3)
    with urllib.request.urlopen(urllib.request.Request(url+'/api/displays',headers={'X-Brain-Request':'local'}),timeout=3) as response:
        assert len(json.load(response)['displays'])==4
    for payload,valid in [({'display_mode':'selected','display_ids':['1','4']},True),
                          ({'display_mode':'selected','display_ids':[]},False),
                          ({'display_mode':'single','display_ids':['1','4']},False)]:
        request=urllib.request.Request(url+'/api/config',data=json.dumps(payload).encode(),headers={'X-Brain-Request':'local'})
        if valid:
            with urllib.request.urlopen(request,timeout=3) as response:assert json.load(response)['success']
        else:
            with pytest.raises(urllib.error.HTTPError):urllib.request.urlopen(request,timeout=3)
    assert config.config.display_ids==['1','4']
    request=urllib.request.Request(url+'/api/config',data=b'{"display_mode":"all"}',headers={'X-Brain-Request':'local','Origin':'https://foreign.example'})
    with pytest.raises(urllib.error.HTTPError) as error:urllib.request.urlopen(request,timeout=3)
    assert error.value.code==403 and config.config.display_mode=='selected'


def test_request_validates_target_display_before_dispatch(test_server,monkeypatch):
    from types import SimpleNamespace
    from dock_twoo.brain.manager import BrainManager
    _,port,config=test_server;calls=[]
    config.display_snapshot={'displays':[{'id':'screen-1','selected':True},{'id':'screen-2','selected':False}]}
    monkeypatch.setattr(BrainManager,'_instance',SimpleNamespace(submit_request=lambda *args:calls.append(args)))
    url=f'http://127.0.0.1:{port}/api/brain/request'
    for screen,valid in [('screen-1',True),('screen-2',False),('absent',False),(3,False)]:
        request=urllib.request.Request(url,data=json.dumps({'text':'test turn','screen_id':screen}).encode(),headers={'X-Brain-Request':'local'})
        if valid:
            with urllib.request.urlopen(request,timeout=3) as response:assert response.status==202
        else:
            with pytest.raises(urllib.error.HTTPError):urllib.request.urlopen(request,timeout=3)
    assert calls==[('test turn','console','screen-1')]
