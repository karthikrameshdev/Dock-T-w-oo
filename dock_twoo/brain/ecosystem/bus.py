"""Authenticated loopback gRPC and durable, exclusive character task leases."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid

import grpc
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Struct
from dock_twoo.brain.catalog import characters

SERVICE = 'dock.agents.v1.AgentBus'
TERMINAL = {'complete', 'failed', 'cancelled', 'interrupted'}


def message(data):
    return ParseDict(data, Struct())


def deserialize(raw):
    return MessageToDict(Struct.FromString(raw))


class AgentBus:
    """Thirty equal peers; each identity owns at most one live task."""
    def __init__(self, root):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True); self.root.chmod(0o700)
        self.path = self.root / 'ecosystem.sqlite3'
        self.condition = threading.Condition(threading.RLock())
        self.credentials = {entry['id']: secrets.token_urlsafe(32) for entry in characters()}
        self.server = None; self.port = None
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, parent_id TEXT, character_id TEXT, prompt TEXT,
                profile_id TEXT, state TEXT, result TEXT DEFAULT '', error TEXT DEFAULT '',
                workspace TEXT DEFAULT '', artifacts TEXT DEFAULT '[]', started REAL, finished REAL);
            CREATE TABLE IF NOT EXISTS trail (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, character_id TEXT,
                task_id TEXT, kind TEXT, payload TEXT);
            CREATE INDEX IF NOT EXISTS trail_task ON trail(task_id,sequence);
            ''')
            db.execute("UPDATE jobs SET state='interrupted',finished=?,error='Application restarted.' WHERE state NOT IN ('complete','failed','cancelled','interrupted')", (time.time(),))
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_active_character ON jobs(character_id) WHERE state IN ('running','cancelling')")
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        with self.condition:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            try:
                yield db; db.commit()
            finally:
                db.close()

    def start(self):
        if self.server:
            return self
        self.server = grpc.server(ThreadPoolExecutor(max_workers=64, thread_name_prefix='agent-bus'), options=[('grpc.max_receive_message_length', 1_000_000)])
        handlers = {}
        for name in ('Assign', 'Report', 'Publish', 'Cancel', 'Snapshot'):
            handlers[name] = grpc.unary_unary_rpc_method_handler(self._handler(name), request_deserializer=deserialize, response_serializer=lambda value:message(value).SerializeToString())
        handlers['Watch'] = grpc.unary_stream_rpc_method_handler(self._watch, request_deserializer=deserialize, response_serializer=lambda value:message(value).SerializeToString())
        self.server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(SERVICE, handlers),))
        self.port = self.server.add_insecure_port('127.0.0.1:0')
        if not self.port:
            raise RuntimeError('Could not bind the local agent bus.')
        self.server.start(); return self

    def client(self, character_id='default'):
        if character_id not in self.credentials:
            raise ValueError('Unknown character identity.')
        self.start()
        return AgentClient(self.port, self.credentials[character_id])

    def _identity(self, context):
        authorization = dict(context.invocation_metadata()).get('authorization', '')
        for identity, credential in self.credentials.items():
            if secrets.compare_digest(authorization, 'Bearer '+credential):
                return identity
        context.abort(grpc.StatusCode.UNAUTHENTICATED, 'An agent credential is required.')

    def _handler(self, name):
        def invoke(data, context):
            identity = self._identity(context)
            try:
                return getattr(self, '_'+name.lower())(identity, data)
            except PermissionError as exc:
                context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))
            except ValueError as exc:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        return invoke

    def _event(self, db, identity, task_id, kind, payload):
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded.encode()) > 200_000:
            raise ValueError('Event payload exceeds the local trail limit.')
        db.execute('INSERT INTO trail(at,character_id,task_id,kind,payload) VALUES(?,?,?,?,?)', (time.time(),identity,task_id,kind,encoded))
        db.execute('DELETE FROM trail WHERE at<?', (time.time()-7*86400,))
        db.execute("DELETE FROM jobs WHERE finished<? AND state IN ('complete','failed','cancelled','interrupted')",(time.time()-7*86400,))
        self.condition.notify_all()

    def _assign(self, identity, data):
        target = data.get('character_id')
        if target not in self.credentials:
            raise ValueError('Choose one of the 30 catalog agents.')
        prompt = data.get('prompt', '')
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 100_000:
            raise ValueError('Supply a nonempty bounded task prompt.')
        with self.db() as db:
            parent = data.get('parent_id', '')
            if parent:
                owner = self._owned(db, identity, parent)
                if owner['state'] != 'running':
                    raise ValueError('Delegation requires a running parent task.')
                ancestors = {row[0] for row in db.execute(
                    'WITH RECURSIVE lineage(id,parent_id,character_id) AS '
                    '(SELECT id,parent_id,character_id FROM jobs WHERE id=? UNION ALL '
                    'SELECT j.id,j.parent_id,j.character_id FROM jobs j JOIN lineage l ON j.id=l.parent_id) '
                    'SELECT character_id FROM lineage', (parent,))}
                if target in ancestors:
                    raise ValueError('Cannot delegate to yourself or an ancestor waiting for this task.')
            elif target != identity:
                raise PermissionError('Start your own task before delegating to another agent.')
            busy = db.execute("SELECT id FROM jobs WHERE character_id=? AND state IN ('running','cancelling')", (target,)).fetchone()
            if busy:
                return {'accepted': False, 'busy_task': busy['id']}
            ident = uuid.uuid4().hex
            db.execute('INSERT INTO jobs(id,parent_id,character_id,prompt,profile_id,state,workspace,started) VALUES(?,?,?,?,?,?,?,?)', (ident,parent,target,prompt,data.get('profile_id',''),'running',data.get('workspace',''),time.time()))
            self._event(db,target,ident,'task_started',{'parent_id':parent,'profile_id':data.get('profile_id','')})
            return {'accepted': True, 'task_id': ident, 'character_id':target}

    def _owned(self, db, identity, task_id):
        row = db.execute('SELECT * FROM jobs WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise ValueError('Task does not exist.')
        if row['character_id'] != identity:
            raise PermissionError('This task belongs to a different character.')
        return row

    def _report(self, identity, data):
        state = data.get('state')
        if state not in TERMINAL:
            raise ValueError('Report a terminal task state.')
        result = str(data.get('result','')); error = str(data.get('error',''))
        artifacts = data.get('artifacts', [])
        if len(result) > 200_000 or len(error) > 4000 or not isinstance(artifacts, list) or len(artifacts) > 100 or any(not isinstance(path,str) or len(path)>4096 for path in artifacts):
            raise ValueError('Bound the task result and artifact list.')
        with self.db() as db:
            row = self._owned(db,identity,data.get('task_id',''))
            if row['state'] in TERMINAL:
                return {'reported':row['state']==state,'state':row['state']}
            db.execute('UPDATE jobs SET state=?,result=?,error=?,artifacts=?,finished=? WHERE id=?', (state,result,error,json.dumps(artifacts),time.time(),row['id']))
            self._event(db,identity,row['id'],'task_'+state,{'result':result,'error':error,'artifacts':artifacts})
            return {'reported':True,'state':state}

    def _publish(self, identity, data):
        kind = str(data.get('kind',''))
        if kind not in {'progress','review_required','recovery','message','artifact','heartbeat'}:
            raise ValueError('Unknown agent event type.')
        with self.db() as db:
            row = self._owned(db,identity,data.get('task_id',''))
            if row['state'] in TERMINAL:
                raise ValueError('Task has already finished.')
            self._event(db,identity,row['id'],kind,data.get('payload',{}))
        return {'published':True}

    def _cancel(self, identity, data):
        with self.db() as db:
            root = data.get('task_id','')
            self._owned(db, identity, root)
            ids = [row[0] for row in db.execute('WITH RECURSIVE tree(id) AS (SELECT id FROM jobs WHERE id=? UNION ALL SELECT jobs.id FROM jobs JOIN tree ON jobs.parent_id=tree.id) SELECT id FROM tree', (root,))]
            for ident in ids:
                # Keep the lease until the worker acknowledges termination.
                db.execute("UPDATE jobs SET state='cancelling' WHERE id=? AND state NOT IN ('complete','failed','cancelled','interrupted')", (ident,))
            self._event(db,identity,root,'cancellation_requested',{'tasks':ids})
        return {'task_ids':ids}

    def _snapshot(self, identity, data):
        with self.db() as db:
            db.execute('DELETE FROM trail WHERE at<?',(time.time()-7*86400,))
            db.execute("DELETE FROM jobs WHERE finished<? AND state IN ('complete','failed','cancelled','interrupted')",(time.time()-7*86400,))
            jobs = [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY CASE WHEN state IN ('running','cancelling') THEN 0 ELSE 1 END,started DESC LIMIT 130")]
            for row in jobs:
                latest = db.execute("SELECT at,payload FROM trail WHERE task_id=? AND kind='progress' ORDER BY sequence DESC LIMIT 1", (row['id'],)).fetchone()
                row['progress'] = json.loads(latest['payload']) if latest else {}
                row['last_reported'] = latest['at'] if latest else row['started']
            if 'after' in data:
                events = [dict(row) for row in db.execute('SELECT * FROM trail WHERE sequence>? ORDER BY sequence LIMIT 100', (int(data['after']),))]
            else:
                events = [dict(row) for row in db.execute('SELECT * FROM trail ORDER BY sequence DESC LIMIT 100')][::-1]
        for row in jobs:
            row['prompt']=row['prompt'][:1000];row['result']=row['result'][:3000]
            row['artifacts'] = json.loads(row['artifacts'])[:30]
        for row in events:
            value=json.loads(row['payload'])
            row['payload']=value if len(row['payload'])<4000 else {'preview':row['payload'][:3500],'truncated':True}
        result = {'jobs':jobs,'events':events,'agents':[{**entry,'role':'agent'} for entry in characters()]}
        while len(json.dumps(result,ensure_ascii=False).encode())>1_500_000:
            if len(events)>1:events.pop(-1 if 'after' in data else 0)
            else:
                old=next((job for job in reversed(jobs) if job['state'] in TERMINAL),None)
                if old is None:break
                jobs.remove(old)
        return result

    def _watch(self, data, context):
        identity = self._identity(context); after = int(data.get('after',0))
        while context.is_active():
            events = self._snapshot(identity, {'after':after})['events']
            for event in events:
                after = event['sequence']; yield event
            if not events:
                with self.condition:
                    self.condition.wait(.5)

    def close(self):
        if self.server:
            self.server.stop(1).wait(2); self.server = None


class AgentClient:
    def __init__(self, port, credential):
        self.channel = grpc.insecure_channel(f'127.0.0.1:{port}', options=[('grpc.max_receive_message_length',2_000_000)])
        self.metadata = (('authorization','Bearer '+credential),)

    def call(self, method, data=None, timeout=5):
        rpc = self.channel.unary_unary('/'+SERVICE+'/'+method, request_serializer=lambda value:message(value).SerializeToString(), response_deserializer=deserialize)
        return rpc(data or {}, metadata=self.metadata, timeout=timeout)

    def watch(self, after=0):
        rpc = self.channel.unary_stream('/'+SERVICE+'/Watch', request_serializer=lambda value:message(value).SerializeToString(), response_deserializer=deserialize)
        return rpc({'after':after}, metadata=self.metadata)

    def close(self):
        self.channel.close()
