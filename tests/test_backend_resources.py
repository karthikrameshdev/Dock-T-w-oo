"""Bound long-session bookkeeping without truncating task evidence on disk."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import gc
import json
from types import SimpleNamespace
import tracemalloc
import weakref

import numpy as np

from dock_twoo.brain.activity import ActivityStore
from dock_twoo.brain.agent import ProgressGuard
from dock_twoo.brain.ecosystem.bus import AgentBus
from dock_twoo.brain.ecosystem.semantic import SemanticModel
from dock_twoo.brain.security.privacy import LocalEntities


def semantic_fixture(tmp_path):
    model = SemanticModel(tmp_path)
    model.tokenizer = SimpleNamespace(encode=lambda text: SimpleNamespace(
        ids=[1, 2], attention_mask=[1, 1], type_ids=[0, 0]))
    model.session = SimpleNamespace(
        get_inputs=lambda: [SimpleNamespace(name='input_ids')],
        run=lambda *_: [np.ones((1, 384), dtype=np.float32)])
    return model


def test_embedding_cache_does_not_retain_documents_or_model_instances(tmp_path):
    model = semantic_fixture(tmp_path)
    tracemalloc.start()
    try:
        for index in range(1500):
            model.embed(str(index) + ' private document ' * 12000)
        retained, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(model._embeddings) == model.cache_limit
    assert retained < 2_000_000 and peak < 4_000_000
    assert all(type(key) is bytes and len(key) == 32 for key in model._embeddings)
    # Only the input actually consumed by the model determines the key.
    assert model.embed('a' * 6000 + 'first') is model.embed('a' * 6000 + 'second')
    reference = weakref.ref(model)
    del model
    gc.collect()
    assert reference() is None


def test_privacy_cache_discards_raw_text_without_skipping_trailing_entities():
    entities = LocalEntities()
    encoded_text = []

    def encode(text):
        encoded_text.append(len(text))
        # The entity in the final overflow window must still be scanned.
        return SimpleNamespace(ids=[0], attention_mask=[1], type_ids=[0],
            offsets=[(0, 1)], overflowing=[SimpleNamespace(ids=[1],
                attention_mask=[1], type_ids=[0], offsets=[(len(text)-4, len(text))])])

    entities.tokenizer = SimpleNamespace(encode=encode)
    entities.labels = {'0': 'O', '1': 'B-PER'}
    entities.session = SimpleNamespace(
        get_inputs=lambda: [SimpleNamespace(name='input_ids')],
        run=lambda _, data: [np.array([[[0., 1.]]]) if data['input_ids'][0][0] else np.array([[[1., 0.]]])])
    for index in range(600):
        document = str(index) + 'document ' * 10000 + 'Jane'
        assert entities.spans(document) == ((len(document)-4, len(document)),)
    assert len(entities._spans) == entities.cache_limit
    assert entities._cache_bytes <= entities.cache_byte_limit
    assert all(type(key) is bytes and len(key) == 32 for key in entities._spans)
    entities.spans(document)
    assert len(encoded_text) == 600  # A cache hit still avoids NER inference.
    entities.clear_cache()
    assert not entities._spans and entities._cache_bytes == 0


def test_progress_tracking_keeps_fingerprints_instead_of_entire_file_contents():
    guard = ProgressGuard()
    for index in range(1000):
        args = {'path': f'/analysis/{index}.txt'}
        output = {'text': 'verified content ' * 12000}
        assert guard.changed('read_file', args, output)
        assert not guard.changed('read_file', args, output)
    assert len(guard.seen) == 1000
    assert sum(len(item) for item in guard.seen) == 32000


def test_bus_polling_bounds_allocation_before_fetching_full_documents(tmp_path):
    bus = AgentBus(tmp_path)
    import time
    now = time.time()
    result = 'verified research ' * 7000
    payload = json.dumps({'result': result})
    with bus.db() as db:
        for index in range(130):
            db.execute('INSERT INTO jobs(id,parent_id,character_id,prompt,profile_id,state,result,started,finished) VALUES(?,?,?,?,?,?,?,?,?)',
                (str(index), '', 'default', result[:90000], '', 'complete', result, now-index, now-index))
            db.execute('INSERT INTO trail(at,character_id,task_id,kind,payload) VALUES(?,?,?,?,?)',
                (now, 'default', str(index), 'task_complete', payload))
    tracemalloc.start()
    try:
        for _ in range(12):
            snapshot = bus._snapshot('default', {})
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 5_000_000
    assert len(snapshot['jobs']) == 130
    assert len(snapshot['jobs'][0]['result']) == 3000
    assert snapshot['events'][0]['payload']['truncated']
    with bus.db() as db:
        assert db.execute('SELECT result FROM jobs WHERE id=?', ('0',)).fetchone()[0] == result


def test_activity_polling_keeps_previews_small_and_does_not_repeat_maintenance(tmp_path):
    current = [datetime(2026, 11, 1, tzinfo=timezone.utc)]
    store = ActivityStore(tmp_path, clock=lambda: current[0])
    run = store.start('a full request ' * 1000)
    full_reply = 'a full report ' * 10000
    store.finish(run, 'complete', full_reply)
    statements = []
    original_db = store.db

    @contextmanager
    def traced_db():
        with original_db() as db:
            db.set_trace_callback(statements.append)
            yield db

    store.db = traced_db
    current[0] += timedelta(seconds=61)
    for _ in range(30):
        page = store.list()
    assert len(page['runs'][0]['request']) == 240
    assert len(page['runs'][0]['reply']) == 1000
    assert sum('sum(length(payload))' in sql for sql in statements) == 1
    assert store.detail(run)['run']['reply_truncated']
    offset=0;parts=[]
    while offset is not None:
        page=store.text_page(run,'reply',offset)
        parts.append(page['text']);offset=page['next_offset']
    assert ''.join(parts) == full_reply
    store.prune()  # An explicit cleanup is never throttled.
    assert sum('sum(length(payload))' in sql for sql in statements) == 2


def test_activity_event_pages_keep_complete_evidence_and_stable_cursors(tmp_path):
    store=ActivityStore(tmp_path);run=store.start('Read a large report')
    text='Verified research with unicode: café 東京. '*3000
    for index in range(225):store.event(run,'tool_result',{'index':index,'text':text},index+1)
    latest=store.detail(run)
    assert len(latest['events'])==100 and latest['pagination']['event_count']==225
    assert latest['events'][-1]['payload_truncated']
    assert len(json.dumps(latest).encode())<1_000_000
    ids=[event['id'] for event in latest['events']]
    cursor=latest['pagination']['next_before']
    # Events arriving during browsing must not shift an older page cursor.
    store.event(run,'progress',{'message':'Still working'})
    while cursor is not None:
        page=store.detail(run,before=cursor)
        ids.extend(event['id'] for event in page['events'])
        cursor=page['pagination']['next_before']
    assert len(ids)==len(set(ids))==225
    event_id=latest['events'][0]['id'];offset=0;parts=[]
    while offset is not None:
        page=store.event_page(run,event_id,offset)
        assert not page['limited']
        parts.append(page['text']);offset=page['next_offset']
    assert json.loads(''.join(parts))['text']==text


def test_activity_legacy_compressed_payload_has_a_hard_decode_bound(tmp_path):
    import zlib
    store=ActivityStore(tmp_path);run=store.start('Legacy large trace')
    blob=zlib.compress(json.dumps({'text':'x'*16_000_000}).encode())
    with store.db() as db:
        event=db.execute('INSERT INTO events(run_id,at,kind,step,payload) VALUES(?,?,?,?,?)',
            (run,store.clock().isoformat(),'tool_result',1,blob)).lastrowid
    tracemalloc.start()
    try:
        detail=store.detail(run)
        page=store.event_page(run,event)
        _,peak=tracemalloc.get_traced_memory()
    finally:tracemalloc.stop()
    assert detail['events'][0]['payload_truncated'] and page['limited']
    assert len(page['text'])==8192 and peak<7_000_000


def test_event_pagination_does_not_change_whole_request_usage_totals(tmp_path):
    store=ActivityStore(tmp_path);run=store.start('Many iterative calls')
    for step in range(1,121):
        call=store.begin_call(run,{'provider':'custom','model':'fixture'},{'messages':[]},step=step)
        store.end_call(call,{'usage':{'prompt_tokens':10,'completion_tokens':2}},'openai',latency_ms=250)
    detail=store.detail(run)
    assert len(detail['calls'])==50 and len(detail['events'])==100
    assert detail['usage']=={'calls':120,'input_tokens':1200,'output_tokens':240,'retries':0,'latency_ms':30000,'known_usage_calls':120}
