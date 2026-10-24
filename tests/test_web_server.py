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
