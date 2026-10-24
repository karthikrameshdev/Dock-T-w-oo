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
        assert 'rejected' in agent.run('invalid-arguments')
        assert 'Implemented cloud agent' in agent.run('record-work')
        assert 'Implemented cloud agent' in agent.run('recall-work')
        results.append({'protocol':protocol,'folder_summary':'passed','invalid_tool_recovery':'passed','dated_tasks':'passed'})
    denied=BrainAgent(profiles,tools=LocalTools(),client_factory=lambda config,key:factory(config,'invalid-fixture-key'))
    assert 'rejected the API key' in denied.run('Summarize folder='+str(docs))
    results.append({'case':'http_401','state':denied.status()['state']})
    for case,port,timeout in [('http_503',24931,2),('timeout',24932,.15),('unreachable',24933,.15)]:
        agent=BrainAgent(profiles,tools=LocalTools(),client_factory=lambda config,key,p=port,t=timeout:factory(config,key,p,t))
        reply=agent.run('Summarize folder='+str(docs))
        assert agent.status()['state']=='error' and reply,reply
        results.append({'case':case,'state':agent.status()['state']})
print(json.dumps({'success':True,'cases':results},indent=2))
