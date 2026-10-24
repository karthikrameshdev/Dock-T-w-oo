"""Private seven-day traces and durable provider-reported cloud usage totals."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
import uuid
import zlib

RETENTION_DAYS = 7
DETAIL_LIMIT = 128 * 1024 * 1024


def now():
    return datetime.now().astimezone()


def encode(value):
    return json.dumps(value, ensure_ascii=False, default=str, separators=(',', ':'))


def safe_payload(value, secret=''):
    """Credentials never enter traces; fixed instructions are represented by size/hash."""
    def clean(node):
        if isinstance(node, dict):
            result = {}
            for key, item in node.items():
                if key.lower() in ('authorization', 'x-api-key', 'api_key', 'apikey', 'password', 'access_token'):
                    result[key] = '[redacted]'
                elif key == 'system' or (key == 'content' and node.get('role') == 'system'):
                    text = item if isinstance(item, str) else encode(item)
                    result[key] = {'instructions_omitted': True, 'characters': len(text), 'sha256': hashlib.sha256(text.encode()).hexdigest()}
                else:
                    result[key] = clean(item)
            return result
        if isinstance(node, list):
            return [clean(item) for item in node]
        if isinstance(node, str) and secret:
            return node.replace(secret, '[redacted]')
        return node
    return clean(value)


def provider_usage(data, protocol):
    """Unknown usage stays unknown. Cached/reasoning details are not double counted."""
    raw = data.get('usage') if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {'input_tokens': None, 'output_tokens': None, 'total_tokens': None, 'cached_tokens': 0, 'reasoning_tokens': 0, 'cost_usd': None}
    def count(value):
        return value if type(value) is int and value >= 0 else None
    if protocol == 'anthropic':
        base = count(raw.get('input_tokens'))
        cached = count(raw.get('cache_read_input_tokens')) or 0
        creation = count(raw.get('cache_creation_input_tokens')) or 0
        incoming = base + cached + creation if base is not None else None
        outgoing = count(raw.get('output_tokens'))
        reasoning = 0
    else:
        incoming = count(raw.get('prompt_tokens', raw.get('input_tokens')))
        outgoing = count(raw.get('completion_tokens', raw.get('output_tokens')))
        cached = count((raw.get('prompt_tokens_details') or raw.get('input_tokens_details') or {}).get('cached_tokens')) or 0
        reasoning = count((raw.get('completion_tokens_details') or raw.get('output_tokens_details') or {}).get('reasoning_tokens')) or 0
    total = count(raw.get('total_tokens'))
    if total is None and incoming is not None and outgoing is not None:
        total = incoming + outgoing
    cost = raw.get('cost')
    if type(cost) not in (float, int) or not math.isfinite(cost) or cost < 0:
        cost = None
    return {'input_tokens': incoming, 'output_tokens': outgoing, 'total_tokens': total,
            'cached_tokens': cached, 'reasoning_tokens': reasoning, 'cost_usd': cost}


class ActivityStore:
    def __init__(self, root, clock=now):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self.path = self.root / 'activity.sqlite3'
        self.clock = clock
        self.lock = threading.RLock()
        with self.db() as db:
            db.execute('PRAGMA auto_vacuum=INCREMENTAL')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY, started TEXT, finished TEXT, source TEXT, request TEXT,
              state TEXT, reply TEXT DEFAULT '', stop_reason TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY, run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
              at TEXT, kind TEXT, step INTEGER, payload BLOB);
            CREATE INDEX IF NOT EXISTS events_run ON events(run_id,id);
            CREATE TABLE IF NOT EXISTS calls (
              id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
              started TEXT, day TEXT, finished TEXT, provider TEXT, model TEXT, requested_model TEXT,
              step INTEGER, retry INTEGER, status TEXT, input_tokens INTEGER, output_tokens INTEGER,
              total_tokens INTEGER, cached_tokens INTEGER DEFAULT 0, reasoning_tokens INTEGER DEFAULT 0,
              cost_usd REAL, latency_ms INTEGER DEFAULT 0);
            CREATE INDEX IF NOT EXISTS calls_run ON calls(run_id);
            CREATE TABLE IF NOT EXISTS daily_usage (
              day TEXT, provider TEXT, model TEXT, calls INTEGER DEFAULT 0,
              input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, total_tokens INTEGER DEFAULT 0,
              cached_tokens INTEGER DEFAULT 0, reasoning_tokens INTEGER DEFAULT 0,
              known_usage_calls INTEGER DEFAULT 0, failed_calls INTEGER DEFAULT 0, cancelled_calls INTEGER DEFAULT 0,
              retries INTEGER DEFAULT 0, latency_ms INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0,
              cost_known_calls INTEGER DEFAULT 0, PRIMARY KEY(day,provider,model));
            ''')
            db.execute('INSERT OR IGNORE INTO metadata VALUES(?,?)',('tracking_started',self.clock().isoformat()))
        self.path.chmod(0o600)
        self.prune()

    @contextmanager
    def db(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            try:
                yield db
                db.commit()
            finally:
                db.close()

    def start(self, request, source='text'):
        self.prune()
        ident = uuid.uuid4().hex
        with self.db() as db:
            db.execute('INSERT INTO runs(id,started,source,request,state) VALUES(?,?,?,?,?)',
                       (ident, self.clock().isoformat(), source, str(request), 'running'))
        return ident

    def finish(self, ident, state, reply='', reason=''):
        with self.db() as db:
            db.execute('UPDATE runs SET finished=?,state=?,reply=?,stop_reason=? WHERE id=?',
                       (self.clock().isoformat(), state, str(reply), str(reason), ident))

    def event(self, ident, kind, payload, step=0):
        raw = encode(payload).encode()
        if len(raw) > 1024 * 1024:
            raw = encode({'truncated': True, 'original_bytes': len(raw), 'preview': raw[:900000].decode(errors='replace')}).encode()
        with self.db() as db:
            if not db.execute('SELECT 1 FROM runs WHERE id=?', (ident,)).fetchone():return
            db.execute('INSERT INTO events(run_id,at,kind,step,payload) VALUES(?,?,?,?,?)',
                       (ident, self.clock().isoformat(), kind, step, zlib.compress(raw)))

    def begin_call(self, run_id, config, payload, step=1, retry=False, secret=''):
        ident = uuid.uuid4().hex
        started = self.clock()
        with self.db() as db:
            db.execute('INSERT INTO calls(id,run_id,started,day,provider,model,requested_model,step,retry,status) VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (ident, run_id, started.isoformat(), started.date().isoformat(), config['provider'], config['model'], config['model'], step, int(retry), 'in_flight'))
        self.event(run_id, 'cloud_request', {'call_id': ident, 'provider': config['provider'], 'model': config['model'],
                    'retry': bool(retry), 'payload': safe_payload(payload, secret)}, step)
        return ident

    def end_call(self, ident, response, protocol, *, status='success', error='', latency_ms=0, secret=''):
        usage = provider_usage(response, protocol)
        with self.db() as db:
            row = db.execute('SELECT * FROM calls WHERE id=? AND finished IS NULL', (ident,)).fetchone()
            if row is None:return
            model = response.get('model') if isinstance(response, dict) else None
            model = str(model or row['model'])[:200]
            raw_usage=response.get('usage') if isinstance(response,dict) else None
            if not isinstance(raw_usage,dict):raw_usage={}
            if row['provider']!='openrouter' and raw_usage.get('cost_currency')!='USD':usage['cost_usd']=None
            db.execute('UPDATE calls SET finished=?,model=?,status=?,input_tokens=?,output_tokens=?,total_tokens=?,cached_tokens=?,reasoning_tokens=?,cost_usd=?,latency_ms=? WHERE id=?',
                (self.clock().isoformat(), model, status, usage['input_tokens'], usage['output_tokens'], usage['total_tokens'],
                 usage['cached_tokens'], usage['reasoning_tokens'], usage['cost_usd'], latency_ms, ident))
            fields = ['calls','input_tokens','output_tokens','total_tokens','cached_tokens','reasoning_tokens','known_usage_calls',
                      'failed_calls','cancelled_calls','retries','latency_ms','cost_usd','cost_known_calls']
            values = [1,usage['input_tokens'] or 0,usage['output_tokens'] or 0,usage['total_tokens'] or 0,
                      usage['cached_tokens'],usage['reasoning_tokens'],int(usage['input_tokens'] is not None and usage['output_tokens'] is not None),
                      int(status=='error'),int(status in ('cancelled','interrupted')),row['retry'],latency_ms,usage['cost_usd'] or 0,int(usage['cost_usd'] is not None)]
            db.execute('INSERT INTO daily_usage(day,provider,model,'+','.join(fields)+') VALUES('+','.join('?' for _ in range(3+len(fields)))+') '
                       'ON CONFLICT(day,provider,model) DO UPDATE SET '+','.join(f'{field}={field}+excluded.{field}' for field in fields),
                       [row['day'],row['provider'],model]+values)
        self.event(row['run_id'], 'cloud_response', {'call_id': ident, 'status': status, 'error': error,
                    'usage': usage, 'latency_ms': latency_ms, 'response': safe_payload(response, secret)}, row['step'])

    def run_usage(self, ident):
        with self.db() as db:
            row = db.execute('SELECT count(*) calls,coalesce(sum(total_tokens),0) tokens,coalesce(sum(retry),0) retries FROM calls WHERE run_id=?',(ident,)).fetchone()
            return dict(row)

    def recover_interrupted(self):
        with self.db() as db:
            calls = db.execute('SELECT id FROM calls WHERE finished IS NULL').fetchall()
            db.execute("UPDATE runs SET state='interrupted',finished=?,stop_reason='Application exited before completion.' WHERE state='running'",(self.clock().isoformat(),))
        for row in calls:
            self.end_call(row['id'], {}, 'openai', status='interrupted', error='Application exited; provider usage unavailable.')

    def prune(self):
        cutoff = (self.clock()-timedelta(days=RETENTION_DAYS)).isoformat()
        with self.db() as db:
            db.execute('DELETE FROM runs WHERE started<? AND state<>?',(cutoff,'running'))
            size = db.execute('SELECT coalesce(sum(length(payload)),0) FROM events').fetchone()[0]
            if size > DETAIL_LIMIT:
                rows = db.execute("SELECT r.id,coalesce(sum(length(e.payload)),0) bytes FROM runs r LEFT JOIN events e ON e.run_id=r.id WHERE r.state<>'running' GROUP BY r.id ORDER BY r.started").fetchall()
                for row in rows:
                    if size <= DETAIL_LIMIT:break
                    db.execute('DELETE FROM runs WHERE id=?',(row['id'],));size-=row['bytes']
            db.execute('PRAGMA incremental_vacuum(256)')

    def list(self, offset=0, limit=30):
        self.prune()
        offset=max(0,int(offset));limit=max(1,min(50,int(limit)))
        with self.db() as db:
            rows=db.execute('''SELECT r.*,count(c.id) cloud_calls,count(DISTINCT c.provider||':'||c.model) models,
                coalesce(sum(c.total_tokens),0) total_tokens,coalesce(sum(c.retry),0) retries,
                (SELECT coalesce(max(id),0) FROM events WHERE run_id=r.id) last_event
                FROM runs r LEFT JOIN calls c ON c.run_id=r.id GROUP BY r.id ORDER BY r.started DESC LIMIT ? OFFSET ?''',(limit+1,offset)).fetchall()
        return {'runs':[{**dict(row),'request':row['request'][:240]} for row in rows[:limit]],
                'next_offset':offset+limit if len(rows)>limit else None,'retention_days':RETENTION_DAYS}

    def detail(self, ident):
        self.prune()
        with self.db() as db:
            row=db.execute('SELECT * FROM runs WHERE id=?',(ident,)).fetchone()
            if row is None:raise ValueError('This activity was not found or its seven-day retention expired.')
            events=[{**dict(event),'payload':json.loads(zlib.decompress(event['payload']))} for event in db.execute('SELECT * FROM events WHERE run_id=? ORDER BY id',(ident,))]
            calls=[dict(call) for call in db.execute('SELECT * FROM calls WHERE run_id=? ORDER BY started',(ident,))]
        return {'run':dict(row),'calls':calls,'events':events,'retention_days':RETENTION_DAYS}

    def metrics(self, start=None, end=None, period='month'):
        today=self.clock().date()
        if period not in ('month','7d','custom'):raise ValueError('Choose month, 7d, or custom.')
        if period=='custom' and (not start or not end):raise ValueError('Choose both From and To dates.')
        first=date.fromisoformat(start) if start else (today-timedelta(days=6) if period=='7d' else today.replace(day=1))
        last=date.fromisoformat(end) if end else today
        if first>last or (last-first).days>730:raise ValueError('Choose a valid date range of up to two years.')
        with self.db() as db:
            tracking_started=db.execute("SELECT value FROM metadata WHERE key='tracking_started'").fetchone()[0]
            rows=[dict(row) for row in db.execute('SELECT * FROM daily_usage WHERE day BETWEEN ? AND ? ORDER BY day',(first.isoformat(),last.isoformat()))]
        fields=['calls','input_tokens','output_tokens','total_tokens','cached_tokens','reasoning_tokens','known_usage_calls','failed_calls','cancelled_calls','retries','latency_ms','cost_usd','cost_known_calls']
        # Some compatible APIs report a total larger than their input/output
        # breakdown. Preserve the total without inventing a reasoning count.
        for row in rows:row['unattributed_tokens']=max(0,row['total_tokens']-row['input_tokens']-row['output_tokens'])
        fields.append('unattributed_tokens')
        total={field:sum(row[field] for row in rows) for field in fields}
        total['unique_models']=len({(row['provider'],row['model']) for row in rows})
        total['unknown_usage_calls']=total['calls']-total['known_usage_calls']
        total['average_latency_ms']=round(total['latency_ms']/max(1,total['calls']))
        total['successful_calls']=total['calls']-total['failed_calls']-total['cancelled_calls']
        daily={};models={}
        for row in rows:
            for group,key in ((daily,row['day']),(models,row['provider']+'/'+row['model'])):
                if key not in group:group[key]={field:0 for field in fields}
                for field in fields:group[key][field]+=row[field]
        days=[];current=first
        while current<=last:
            days.append({'day':current.isoformat(),**daily.get(current.isoformat(),{field:0 for field in fields})});current+=timedelta(days=1)
        return {'from':first.isoformat(),'to':last.isoformat(),'tracking_started':tracking_started,'summary':total,'daily':days,
                'models':[{'model':key,**value} for key,value in models.items()],
                'source':'Provider-reported cloud API usage only. Local speech/vision are excluded.',
                'retention_days':RETENTION_DAYS,'totals_retention':'Daily aggregates retained; detailed requests and responses expire after seven days.'}
