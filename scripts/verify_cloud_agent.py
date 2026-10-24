"""Run the real agent and local tools against Postman cloud contract fixtures."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dock_twoo.brain.agent import BrainAgent
from dock_twoo.brain.cloud import CloudClient
from dock_twoo.brain.profiles import ProfileManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.agent_tools import LocalTools

results=[]
with tempfile.TemporaryDirectory(prefix='brain-agent-fixture-') as folder:
    root=Path(folder);docs=root/'documents';docs.mkdir()
    (docs/'one.txt').write_text('Orchid launch is on Friday.')
    (docs/'two.txt').write_text('The budget is 120 units.')
    store=BrainStore(root/'brain');profiles=ProfileManager(store)
    for protocol in ('openai','anthropic'):
        profiles.save_profile({'provider':'custom','base_url':'https://fixture.example/v1','model':'fixture-model','protocol':protocol,'api_key':'fixture-key'})
        def factory(config,key,port=24930,timeout=3):
            return CloudClient({**config,'base_url':f'http://127.0.0.1:{port}/cloud'},key,timeout=timeout,allow_test_endpoint=True)
        agent=BrainAgent(profiles,tools=LocalTools(SimpleNamespace(store=store)),client_factory=factory)
        reply=agent.run('Summarize all documents. folder='+str(docs))
        assert 'Orchid launch' in reply and '120 units' in reply,reply
        assert reply.gesture=='nod' and agent.status()['step']==3
        ledger=agent.tracker.detail(agent.status()['run_id'])
        expected=720 if protocol=='openai' else 930
        assert sum(call['total_tokens'] for call in ledger['calls'])==expected
        assert all(call['input_tokens'] is not None and call['output_tokens'] is not None for call in ledger['calls'])
        assert 'rejected' in agent.run('invalid-arguments')
        assert 'Implemented cloud agent' in agent.run('record-work')
        recall=agent.run('recall-work')
        assert 'Implemented cloud agent' in recall and recall.tasks_query=={'date':'2026-01-05'}
        results.append({'protocol':protocol,'folder_summary':'passed','invalid_tool_recovery':'passed','dated_tasks':'passed'})
    profiles.save_profile({'provider':'custom','base_url':'https://fixture.example/v1','model':'fixture-model','protocol':'openai','api_key':'fixture-key'})
    from dock_twoo.brain import computer_actions
    actual=computer_actions.run_desktop_request;opened=[]
    computer_actions.run_desktop_request=lambda name,text=None:opened.append((name,text)) or computer_actions.ActionResult(True,'Verified synthetic editor document.')
    try:
        agent=BrainAgent(profiles,tools=LocalTools(),client_factory=factory)
        assert 'hello world' in agent.run('open-and-type')
        assert opened==[('Cursor','hello world')] and agent.tracker.run_usage(agent.status()['run_id'])['calls']==2
    finally:computer_actions.run_desktop_request=actual
    results.append({'case':'combined_open_and_type','cloud_calls':2,'native_integration':'isolated fixture'})
    for request in ('loop-errors','loop-observe'):
        driver=SimpleNamespace(observe=lambda:{'observation':'fresh-id','controls':[{'id':'1','label':'unchanged'}]})
        agent=BrainAgent(profiles,tools=LocalTools(driver=driver),client_factory=factory)
        reply=agent.run(request)
        run=agent.status()['run_id'];detail=agent.tracker.detail(run)
        assert agent.status()['state']=='limited' and 'credits' in reply
        assert len(detail['calls'])==3 and detail['calls'][1]['retry'] and detail['calls'][2]['retry']
        assert sum(call['total_tokens'] for call in detail['calls'])==720
        assert 'fixture-key' not in json.dumps(detail)
        results.append({'case':request,'cloud_calls':3,'stopped_without_extra_call':True,'provider_tokens':720})
    profiles.store.set_setting('agent_max_steps',5);profiles.store.set_setting('agent_token_budget',64000)
    agent=BrainAgent(profiles,tools=LocalTools(),client_factory=factory)
    agent.run('progress-budget folder='+str(docs))
    assert agent.status()['state']=='limited' and agent.tracker.run_usage(agent.status()['run_id'])['calls']==5
    results.append({'case':'hard_call_budget','cloud_calls':5})
    profiles.store.set_setting('agent_max_steps',8)
    denied=BrainAgent(profiles,tools=LocalTools(),client_factory=lambda config,key:factory(config,'invalid-fixture-key'))
    assert 'rejected the API key' in denied.run('Summarize folder='+str(docs))
    results.append({'case':'http_401','state':denied.status()['state']})
    for case,port,timeout in [('http_503',24931,2),('timeout',24932,.15),('unreachable',24933,.15)]:
        agent=BrainAgent(profiles,tools=LocalTools(),client_factory=lambda config,key,p=port,t=timeout:factory(config,key,p,t))
        reply=agent.run('Summarize folder='+str(docs))
        assert agent.status()['state']=='error' and reply,reply
        results.append({'case':case,'state':agent.status()['state']})
print(json.dumps({'success':True,'cases':results},indent=2))
