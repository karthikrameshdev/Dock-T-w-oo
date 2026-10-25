import json
import sys
import threading
import time
from pathlib import Path
import pytest
from dock_twoo.brain.ecosystem.cli import CLIClient
from dock_twoo.brain.profiles import ProfileManager
from dock_twoo.brain.storage import BrainStore


def test_cli_profile_binding_and_real_subprocess_tool_roundtrip(tmp_path):
    profiles=ProfileManager(BrainStore(tmp_path))
    code="import sys,json; p=json.load(sys.stdin); print(json.dumps({'response':json.dumps({'text':'Ready','calls':[{'name':'system_status','arguments':{}}]}),'usage':{'input_tokens':120,'output_tokens':30}}))"
    saved=profiles.create_profile({'provider':'custom_cli','name':'CLI fixture','model':'fixture','executable':sys.executable,'arguments':['-c',code]})
    assert saved['kind']=='cli' and saved['status']=='configured' and not saved['key_configured']
    profiles.bind_character('parrot',saved['id']);assert profiles.character_profile('parrot')['id']==saved['id']
    client=CLIClient(saved)
    try:
        assert client.workspace.is_dir()
        result=client.turn([{'role':'user','content':'No shell $() `code`'}],[],threading.Event())
        assert result.text=='Ready' and result.calls[0]['name']=='system_status'
        assert result.usage['input_tokens']==120 and result.usage['output_tokens']==30
        messages=[];client.append_results(messages,[(result.calls[0]['id'],{'ok':True,'result':'known'})])
        assert messages[0]['role']=='tool'
    finally:client.close()
    assert not client.workspace.exists()


def test_cli_stop_terminates_owned_process_promptly(tmp_path):
    client=CLIClient({'provider':'custom_cli','model':'fixture','executable':sys.executable,'arguments':['-c','import time; time.sleep(60)']})
    token=threading.Event();timer=threading.Timer(.3,token.set);timer.start();started=time.monotonic()
    try:
        with pytest.raises(InterruptedError):client.turn([{'role':'user','content':'Wait'}],[],token)
        assert time.monotonic()-started<4
    finally:timer.cancel();client.close()


def test_explicit_network_profiles_require_no_local_model_installation(tmp_path):
    profiles=ProfileManager(BrainStore(tmp_path))
    saved=profiles.create_profile({'provider':'ollama','name':'Existing server','model':'my-model'})
    assert saved['status']=='configured' and saved['kind']=='network'
    assert saved['base_url']=='http://127.0.0.1:11434/v1'
    from dock_twoo.brain.ecosystem.models import model_client
    assert model_client(saved,'').config['provider']=='ollama'


def test_relative_document_tools_use_task_workspace(tmp_path):
    from types import SimpleNamespace
    from dock_twoo.brain.agent_tools import LocalTools
    workspace=tmp_path/'workspace';workspace.mkdir()
    tools=LocalTools(SimpleNamespace(workspace=workspace))
    result=tools.execute('write_file',{'path':'report.md','text':'Verified report'},threading.Event())
    assert result['created']==str(workspace/'report.md')
    assert tools.execute('read_file',{'path':'report.md'},threading.Event())['text']=='Verified report'


def test_large_section_reports_assemble_locally_without_model_output_replay(tmp_path):
    from types import SimpleNamespace
    from dock_twoo.brain.agent_tools import LocalTools
    sections=[]
    for i in range(3):
        path=tmp_path/f'section-{i}.md';path.write_text(f'# Section {i}\n'+('Verified evidence with citation. '*500));sections.append(str(path))
    tools=LocalTools(SimpleNamespace(workspace=tmp_path))
    result=tools.execute('assemble_document',{'path':'final.md','sections':sections,'introduction':'# Research report'},threading.Event())
    text=(tmp_path/'final.md').read_text()
    assert result['verified'] and all(f'# Section {i}' in text for i in range(3))
    assert len(text)>40000
    with pytest.raises(FileExistsError):tools.execute('assemble_document',{'path':'final.md','sections':sections},threading.Event())


def test_cli_task_does_not_inherit_another_provider_credential(monkeypatch):
    monkeypatch.setenv('HF_TOKEN','unrelated-secret')
    monkeypatch.setenv('OPENAI_API_KEY','another-provider-key')
    monkeypatch.setenv('AGENT_MODEL_API_KEY','stale-model-key')
    code="import os,json;assert all(k not in os.environ for k in ('HF_TOKEN','OPENAI_API_KEY','AGENT_MODEL_API_KEY'));print(json.dumps({'text':'Isolated','calls':[]}))"
    client=CLIClient({'provider':'custom_cli','model':'fixture','executable':sys.executable,'arguments':['-c',code]})
    try:assert client.turn([{'role':'user','content':'Test'}],[]).text=='Isolated'
    finally:client.close()
