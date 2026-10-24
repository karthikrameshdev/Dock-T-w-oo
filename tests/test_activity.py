"""Cloud-only accounting, bounded retries and seven-day trace retention."""
from datetime import datetime,timedelta,timezone
import json
import threading
from types import SimpleNamespace
import pytest
from dock_twoo.brain.activity import ActivityStore,provider_usage
from dock_twoo.brain.agent import BrainAgent
from dock_twoo.brain.cloud import ModelTurn
from dock_twoo.brain.profiles import ProfileManager
from dock_twoo.brain.storage import BrainStore


def configured(tmp_path):
    profiles=ProfileManager(BrainStore(tmp_path/'brain'))
    profiles.save_profile({'provider':'custom','base_url':'https://fixture.example/v1','model':'fixture','api_key':'fixture-key'})
    return profiles


def call(store,run,usage,*,provider='custom',model='fixture',protocol='openai',retry=False):
    ident=store.begin_call(run,{'provider':provider,'model':model},{'messages':[{'role':'system','content':'private fixed instructions'},{'role':'user','content':'hello'}]},retry=retry)
    store.end_call(ident,{'model':model,'usage':usage},protocol,latency_ms=250)
    return ident


def test_cloud_usage_counts_context_cache_reasoning_once(tmp_path):
    store=ActivityStore(tmp_path);run=store.start('Request','voice')
    call(store,run,{'prompt_tokens':1000,'completion_tokens':250,'total_tokens':1250,'prompt_tokens_details':{'cached_tokens':600},'completion_tokens_details':{'reasoning_tokens':100}})
    total=store.metrics()['summary']
    assert (total['input_tokens'],total['output_tokens'],total['total_tokens'])==(1000,250,1250)
    assert total['cached_tokens']==600 and total['reasoning_tokens']==100
    assert total['calls']==1 and total['unique_models']==1 and total['unknown_usage_calls']==0
    assert total['cost_known_calls']==0
    detail=store.detail(run)
    assert 'private fixed instructions' not in json.dumps(detail)
    assert detail['events'][0]['payload']['payload']['messages'][0]['content']['instructions_omitted']


def test_anthropic_input_includes_cache_creation_and_reads():
    usage=provider_usage({'usage':{'input_tokens':100,'cache_creation_input_tokens':200,'cache_read_input_tokens':300,'output_tokens':50}},'anthropic')
    assert usage['input_tokens']==600 and usage['output_tokens']==50 and usage['total_tokens']==650


def test_provider_total_is_preserved_when_breakdown_is_incomplete(tmp_path):
    store=ActivityStore(tmp_path);run=store.start('Partial provider breakdown')
    call(store,run,{'prompt_tokens':2647,'completion_tokens':10,'total_tokens':2747})
    summary=store.metrics()['summary']
    assert summary['total_tokens']==2747 and summary['unattributed_tokens']==90
    assert summary['output_tokens']==10 and summary['reasoning_tokens']==0
    call(store,run,None)
    assert store.metrics()['summary']['unknown_usage_calls']==1


def test_missing_usage_is_unknown_not_an_estimate_and_no_local_tokens(tmp_path):
    store=ActivityStore(tmp_path);run=store.start('Read this locally','voice');store.finish(run,'complete','Read locally')
    assert store.metrics()['summary']['calls']==0
    ident=store.begin_call(run,{'provider':'custom','model':'fixture'},{})
    store.end_call(ident,{},'openai',status='error')
    summary=store.metrics()['summary']
    assert summary['calls']==1 and summary['unknown_usage_calls']==1 and summary['total_tokens']==0
    assert store.detail(run)['calls'][0]['input_tokens'] is None


def test_trace_retention_does_not_delete_monthly_usage(tmp_path):
    current=[datetime(2026,10,1,12,tzinfo=timezone.utc)]
    store=ActivityStore(tmp_path,clock=lambda:current[0]);run=store.start('Old private request')
    ident=call(store,run,{'prompt_tokens':12,'completion_tokens':3,'total_tokens':15});store.finish(run,'complete','Done')
    # A duplicate completion must never double-count a billed call.
    store.end_call(ident,{'usage':{'prompt_tokens':12,'completion_tokens':3,'total_tokens':15}},'openai')
    current[0]+=timedelta(days=8);store.prune()
    with pytest.raises(ValueError):store.detail(run)
    total=store.metrics()['summary'];assert total['total_tokens']==15 and total['calls']==1
    assert store.list()['runs']==[]


def test_range_boundaries_retry_and_model_counts(tmp_path):
    current=[datetime(2026,10,5,23,59,tzinfo=timezone(timedelta(hours=5,minutes=30)))]
    store=ActivityStore(tmp_path,clock=lambda:current[0]);run=store.start('First')
    call(store,run,{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12})
    current[0]+=timedelta(minutes=2)
    call(store,run,{'prompt_tokens':20,'completion_tokens':4,'total_tokens':24},model='second',retry=True)
    assert store.metrics(start='2026-10-05',end='2026-10-05')['summary']['total_tokens']==12
    summary=store.metrics(start='2026-10-05',end='2026-10-06')['summary']
    assert summary['total_tokens']==36 and summary['unique_models']==2 and summary['retries']==1
    with pytest.raises(ValueError):store.metrics(start='2026-10-06',end='2026-10-05')


def test_cloud_credentials_are_redacted_in_both_directions(tmp_path):
    store=ActivityStore(tmp_path);run=store.start('Hello');secret='private-provider-key'
    ident=store.begin_call(run,{'provider':'custom','model':'fixture'},{'api_key':secret,'messages':[{'role':'user','content':secret}]},secret=secret)
    store.end_call(ident,{'error':secret},'openai',secret=secret)
    assert secret not in json.dumps(store.detail(run))


def test_stalled_agent_stops_after_three_calls_without_a_final_paid_call(tmp_path):
    profiles=configured(tmp_path);turns=[]
    class Client:
        def __init__(self,*_args):pass
        def turn(self,*_args):
            turns.append(True)
            return ModelTurn({'role':'assistant','content':''},[{'id':str(len(turns)),'name':'read_file','arguments':{'wrong':str(len(turns))}}],'')
        def append_results(self,messages,results):pass
    agent=BrainAgent(profiles,client_factory=Client)
    reply=agent.run('Open Cursor and type hello world')
    assert len(turns)==3 and agent.status()['state']=='limited' and 'credits' in reply
    assert 'No measurable progress' in agent.status()['error']


def test_changing_observation_ids_does_not_reset_progress_guard(tmp_path):
    profiles=configured(tmp_path);turns=[]
    class Client:
        def __init__(self,*_args):pass
        def turn(self,*_args):
            turns.append(True)
            return ModelTurn({'role':'assistant','content':''},[{'id':str(len(turns)),'name':'observe_desktop','arguments':{}}],'')
        def append_results(self,*_args):pass
    outputs=[]
    def execute(*_args):
        outputs.append(True);return {'observation':str(len(outputs)),'controls':[{'id':'1','label':'same window'}]}
    agent=BrainAgent(profiles,tools=SimpleNamespace(execute=execute),client_factory=Client)
    agent.run('Complete a task')
    assert len(turns)==3 and len(outputs)==2 and agent.status()['state']=='limited'


def test_small_budget_blocks_a_cloud_call_before_it_is_sent(tmp_path):
    profiles=configured(tmp_path);profiles.store.set_setting('agent_token_budget',2000)
    calls=[]
    class Client:
        def __init__(self,*_args):pass
        def turn(self,*_args):calls.append(True)
    agent=BrainAgent(profiles,client_factory=Client)
    agent.run('A normal request')
    assert calls==[] and agent.status()['state']=='limited'


def test_legacy_large_loop_limit_migrates_to_eight(tmp_path):
    path=tmp_path/'settings.json';path.write_text(json.dumps({'agent_max_steps':64}))
    store=BrainStore(tmp_path)
    assert store.setting('agent_max_steps')==8


def test_stopping_audio_does_not_relabel_a_completed_cloud_request(tmp_path):
    profiles=configured(tmp_path)
    class Client:
        def __init__(self,*_args):pass
        def turn(self,*_args):return ModelTurn({'role':'assistant','content':'Done'},[],'Done')
    agent=BrainAgent(profiles,client_factory=Client);agent.run('Reply')
    ident=agent.status()['run_id'];agent.stop()
    assert agent.tracker.detail(ident)['run']['state']=='complete'


def test_cancelled_inflight_call_retains_returned_provider_usage(tmp_path):
    store=ActivityStore(tmp_path);run=store.start('Cancelled request')
    ident=store.begin_call(run,{'provider':'custom','model':'fixture'},{})
    store.finish(run,'stopped',reason='Stopped by user')
    store.end_call(ident,{'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}},'openai',status='cancelled')
    summary=store.metrics()['summary']
    assert summary['total_tokens']==110 and summary['cancelled_calls']==1
    assert store.detail(run)['run']['state']=='stopped'


def test_superseded_requests_do_not_start_overlapping_cloud_calls(tmp_path):
    profiles=configured(tmp_path);entered=threading.Event();release=threading.Event();sent=[]
    class Client:
        def __init__(self,*_args):pass
        def turn(self,messages,*_args):
            sent.append(messages[-1]['content'])
            if len(sent)==1:entered.set();release.wait(2)
            return ModelTurn({'role':'assistant','content':'Done'},[],'Done')
    agent=BrainAgent(profiles,client_factory=Client)
    first=threading.Event();second=threading.Event();errors=[]
    def run(text,token):
        try:agent.run(text,cancel=token)
        except InterruptedError:errors.append(text)
    a=threading.Thread(target=run,args=('First request',first));a.start();assert entered.wait(1)
    first.set();b=threading.Thread(target=run,args=('Second request',second));b.start()
    threading.Event().wait(.1)
    assert sent==['First request']
    release.set();a.join(2);b.join(2)
    assert sent==['First request','Second request'] and errors==['First request']
    assert not a.is_alive() and not b.is_alive()


def test_only_explicit_usd_cost_is_reported(tmp_path):
    store=ActivityStore(tmp_path);run=store.start('Cost metadata')
    call(store,run,{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12,'cost':.25},provider='openrouter')
    call(store,run,{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12,'cost':99},provider='custom')
    summary=store.metrics()['summary']
    assert summary['cost_usd']==.25 and summary['cost_known_calls']==1


def test_voice_trace_preserves_transcript_and_local_reading_has_no_cloud_tokens(tmp_path,qapp,monkeypatch):
    from dock_twoo.brain.manager import BrainManager
    manager=BrainManager(store=BrainStore(tmp_path/'brain'),start_services=False)
    monkeypatch.setattr(manager.speech,'start',lambda *_:None)
    manager.listener.last_completed_transcript='Brain, read aloud: hello world.'
    manager._do_turn_complete('read aloud: hello world.','voice')
    item=manager.activity.list()['runs'][0]
    assert item['request']=='Brain, read aloud: hello world.' and item['source']=='voice'
    assert item['cloud_calls']==0 and manager.activity.metrics()['summary']['calls']==0
    manager.shutdown()


def test_cyclic_collection_is_scheduled_on_the_gui_thread(qapp):
    import gc
    from dock_twoo.ui.lifecycle import GuiGarbageCollector
    previous=gc.isenabled();collector=GuiGarbageCollector(qapp)
    collected=[]
    class Cycle:
        def __init__(self):self.reference=self
        def __del__(self):collected.append(threading.current_thread().name)
    def allocate():
        for _ in range(100):Cycle()
    worker=threading.Thread(target=allocate,name='http-test-worker');worker.start();worker.join()
    assert not gc.isenabled() and collected==[]
    gc.collect()
    assert collected and set(collected)=={threading.current_thread().name}
    collector.stop();assert gc.isenabled()==previous


def test_status_requests_read_qt_objects_on_the_gui_thread(tmp_path,qtbot):
    from dock_twoo.brain.manager import BrainManager
    manager=BrainManager(store=BrainStore(tmp_path/'brain'),start_services=False)
    result=[]
    worker=threading.Thread(target=lambda:result.append(manager.get_status()))
    worker.start();qtbot.waitUntil(lambda:bool(result),timeout=2000);worker.join()
    assert result[0]['name']=='Brain' and 'character' in result[0]
    manager.shutdown()


def test_desktop_driver_refuses_to_introspect_its_own_embedded_browser():
    import os
    from dock_twoo.brain.desktop_driver import DesktopDriver
    driver=DesktopDriver();driver.frontmost_pid=os.getpid
    driver.AX=SimpleNamespace(AXUIElementCreateApplication=lambda *_:pytest.fail('Own Qt browser must never be queried from an agent worker.'))
    with pytest.raises(RuntimeError,match='own embedded browser'):driver._frontmost()
