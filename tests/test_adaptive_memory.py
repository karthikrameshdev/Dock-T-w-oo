import json
from dock_twoo.brain.ecosystem.memory import AdaptiveMemory
from dock_twoo.brain.ecosystem.cache import PromptCache,native_cache_payload


def test_compaction_keeps_antecedents_is_scoped_and_bounded(tmp_path):
    memory=AdaptiveMemory(tmp_path)
    history=[{'role':'user','content':'What is quantum computing?'},{'role':'assistant','content':'Quantum computing uses qubits and quantum states.'},{'role':'user','content':'What is wave?'},{'role':'assistant','content':'A quantum wave represents probability amplitudes.'}]
    scope=memory.scope('parrot','profile-a')
    memory.complete(scope,'What is wave?','A quantum wave represents probability amplitudes.','r1',history)
    compact=memory.context(scope,'What does that mean?',[])
    assert 'quantum' in compact and len(compact)<6500
    assert 'quantum' not in memory.context(memory.scope('fox','profile-a'),'What does that mean?',[])
    large=[{'role':'user','content':('research topic '+str(i)+' and evidence. ')*200} for i in range(100)]
    assert len(memory.compact(large,'research topic',5000))<=5000


def test_learning_requires_explicit_attributed_feedback_and_respects_override(tmp_path):
    memory=AdaptiveMemory(tmp_path);scope=memory.scope('default','one')
    assert memory.workflow(scope,'Deep research on quantum computing','r1')=='research'
    assert not memory.feedback(scope,'Tell me about waves','r1')
    assert not memory.feedback(scope,'','r1')
    assert memory.feedback(scope,'That was helpful','r1')
    assert not memory.feedback(scope,'That was helpful','r1')
    assert memory.workflow(scope,'Only three lines for this answer','r2')=='direct'
    for _ in range(14):assert not memory.remember_preference(scope,'Research Intel processors','r1')
    assert memory.remember_preference(scope,'I prefer concise responses','r3')
    assert memory.remember_preference(scope,'I prefer concise responses','r4')
    with memory.db() as db:
        assert db.execute('SELECT count(*) FROM preferences').fetchone()[0]==1
        assert db.execute('SELECT evidence_count FROM preferences').fetchone()[0]==2
    assert memory.remember_preference(scope,'From now on use detailed responses','r5')
    assert 'detailed' in memory.context(scope,'Explain waves',[])
    parts=json.loads(scope);parts[-1]='global'
    memory.forget(json.dumps(parts,separators=(',',':')))
    memory.forget(scope)
    assert 'detailed' not in memory.context(scope,'Explain waves',[])


def test_templates_are_isolated_and_native_hints_do_not_claim_hits(tmp_path):
    cache=PromptCache(tmp_path);profile={'id':'a','provider':'openai','model':'model','base_url':'https://example.test'}
    args=(profile,'default','credential',[{'role':'system','content':'fixed policy'}],[])
    _,cold=cache.prepare(*args);_,warm=cache.prepare(*args)
    assert not cold['local_template_hit'] and warm['local_template_hit']
    assert cold['key']==warm['key']
    _,other=cache.prepare(profile,'parrot','credential',args[3],[])
    assert other['key']!=cold['key']
    assert native_cache_payload(profile,{'model':'model'},warm['key'])['prompt_cache_key']==warm['key']
    assert 'prompt_cache_key' not in native_cache_payload({**profile,'provider':'custom'},{'model':'model'},warm['key'])
    payload=native_cache_payload({'protocol':'anthropic'},{'system':'fixed\n<runtime-context>\nchanging time','tools':[]})
    assert payload['system'][0]['cache_control']=={'type':'ephemeral'}
    assert 'cache_control' not in payload['system'][1]


def test_one_large_tool_group_compacts_without_breaking_call_ids(tmp_path):
    memory=AdaptiveMemory(tmp_path)
    original=[{'role':'system','content':'Stable provider cache prefix'}, {'role':'user','content':'Write the report'},
              {'role':'assistant','tool_calls':[{'id':'a1','type':'function','function':{'name':'write_file','arguments':json.dumps({'path':'/tmp/report.md','text':'Verified source detail. '*3000})}}]},
              {'role':'tool','tool_call_id':'a1','content':json.dumps({'ok':True,'result':{'created':'/tmp/report.md','verified':True}})}]
    compact,changed=memory.compact_iterations(original,'report',8000)
    assert changed and len(json.dumps(compact))<8000
    assert compact[0]==original[0] and compact[1]==original[1]
    assert compact[-1]['tool_call_id']==compact[-2]['tool_calls'][0]['id']=='a1'
    assert len(json.loads(original[-2]['tool_calls'][0]['function']['arguments'])['text'])>40000
    assert '/tmp/report.md' in json.dumps(compact) and 'omitted' in json.dumps(compact)


def test_template_cache_covers_api_network_and_cli_without_storing_user_requests(tmp_path):
    cache=PromptCache(tmp_path)
    for provider in ('openai','anthropic','gemini','openrouter','custom','ollama','network','codex_cli','gemini_cli','claude_cli','kilo_cli','custom_cli'):
        profile={'id':provider,'provider':provider,'model':'test'}
        args=(profile,'default','secret-for-'+provider,[{'role':'system','content':'Immutable staged policy'}],[])
        _,cold=cache.prepare(*args);_,warm=cache.prepare(*args)
        assert not cold['local_template_hit'] and warm['local_template_hit']
        assert 'secret-for-' not in cache.path.read_bytes().decode(errors='ignore')
