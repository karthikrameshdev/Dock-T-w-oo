"""Real agent/HTTP simulation: frozen profile selection and separate usage."""
from pathlib import Path
import sys,tempfile,json
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dock_twoo.brain.profiles import ProfileManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.agent import BrainAgent
from dock_twoo.brain.cloud import CloudClient
from dock_twoo.brain.agent_tools import LocalTools
with tempfile.TemporaryDirectory(prefix='brain-profiles-check-') as folder:
    store=BrainStore(Path(folder));profiles=ProfileManager(store)
    a=profiles.save_profile({'name':'Everyday','provider':'custom','model':'fixture-model','base_url':'https://fixture.example/v1','api_key':'fixture-key'})
    b=profiles.create_profile({'name':'Research','provider':'custom','model':'fixture-model','protocol':'anthropic','base_url':'https://fixture.example/v1','api_key':'fixture-key'})
    captured=[]
    def factory(config,key):
        captured.append((config['id'],key))
        # The user switches while this request is starting. Its captured config
        # and credential must continue to identify the original profile.
        profiles.activate_profile(b['id'])
        return CloudClient({**config,'base_url':'http://127.0.0.1:24930/cloud'},key,timeout=5,allow_test_endpoint=True)
    agent=BrainAgent(profiles,tools=LocalTools(SimpleNamespace(store=store)),client_factory=factory)
    assert 'Implemented cloud agent' in agent.run('record-work')
    first=agent.tracker.detail(agent.status()['run_id'])
    assert {call['profile_id'] for call in first['calls']}=={a['id']}
    assert 'Implemented cloud agent' in agent.run('recall-work')
    second=agent.tracker.detail(agent.status()['run_id'])
    assert {call['profile_id'] for call in second['calls']}=={b['id']}
    metrics=agent.tracker.metrics()
    assert metrics['summary']['total_tokens']==1100,metrics
    assert agent.tracker.metrics(profile_id=a['id'])['summary']['total_tokens']==480
    assert agent.tracker.metrics(profile_id=b['id'])['summary']['total_tokens']==620
    profiles.delete_profile(a['id'])
    assert agent.tracker.metrics(profile_id=a['id'])['summary']['total_tokens']==480
    print(json.dumps({'success':True,'http_calls':metrics['summary']['calls'],'overall_tokens':1100,'everyday_tokens':480,'research_tokens':620,'switch_kept_inflight_profile':True,'deleted_profile_history_retained':True,'live_cloud_calls':0},indent=2))
