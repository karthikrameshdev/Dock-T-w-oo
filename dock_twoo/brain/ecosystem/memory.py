"""Four-layer, scoped memory with attributed discounted LinUCB workflow learning.

Embeddings rank evidence; they do not invent preferences or fabricate rewards.
Compaction is extractive, bounded and keeps source roles/provenance visible.
"""
from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import numpy as np

WORKFLOWS=('direct','structured','research')


class AdaptiveMemory:
    def __init__(self, root, semantic=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.root.chmod(0o700)
        self.path=self.root/'memory.sqlite3';self.lock=threading.RLock();self.semantic=semantic
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS preferences (
                id TEXT PRIMARY KEY,scope TEXT,rule TEXT,value TEXT,confidence REAL,
                evidence_count INTEGER,status TEXT,source_run TEXT,created REAL,updated REAL,
                supersedes TEXT,expires REAL,UNIQUE(scope,rule,value));
            CREATE TABLE IF NOT EXISTS episodes (
                id TEXT PRIMARY KEY,scope TEXT,text TEXT,source_run TEXT,salience REAL,at REAL);
            CREATE TABLE IF NOT EXISTS checkpoints (scope TEXT PRIMARY KEY,summary TEXT,turns INTEGER,updated REAL);
            CREATE TABLE IF NOT EXISTS policies (
                scope TEXT,arm TEXT,a TEXT,b TEXT,updates INTEGER DEFAULT 0,PRIMARY KEY(scope,arm));
            CREATE TABLE IF NOT EXISTS decisions (run_id TEXT PRIMARY KEY,scope TEXT,arm TEXT,features TEXT,request TEXT,feedback REAL);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        with self.lock:
            db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
            try:yield db;db.commit()
            finally:db.close()

    @staticmethod
    def scope(character_id, profile_id, family='general'):
        return json.dumps([character_id,profile_id,family],separators=(',',':'))

    @staticmethod
    def task_family(text, previous='general'):
        if re.search(r'\bexam|revision|revise|flashcards\b',text,re.I):return 'revision'
        if re.search(r'\bresearch|literature|citations|papers?\b',text,re.I):return 'literature'
        if re.search(r'\bcode|debug|programming|implementation\b',text,re.I):return 'coding'
        if re.search(r'\bworked|work log|tasks|notes|yesterday\b',text,re.I):return 'work'
        if re.search(r'\bexplain|what is|what are|teach|learn\b',text,re.I):return 'study'
        return previous

    @staticmethod
    def features(text):
        words=text.lower()
        return np.array([1,min(1,len(text)/2000),bool(re.search(r'\bresearch|sources|citations\b',words)),bool(re.search(r'\bsteps|list|structured|bullet\b',words)),bool(re.search(r'\bbrief|concise|short|only\b',words)),bool(re.search(r'\bcode|debug|function\b',words)),bool(re.search(r'\bdocument|report|summary\b',words)),bool(re.search(r'\bit|that|previous|again\b',words))],dtype=float)

    def workflow(self, scope, text, run_id):
        x=self.features(text)
        explicit=('research' if re.search(r'\b(?:deep research|research|citations|sources)\b',text,re.I) else
                  'direct' if re.search(r'\b(?:brief|concise|short|only \w+ (?:lines|sentences))\b',text,re.I) else
                  'structured' if re.search(r'\b(?:step by step|bullet|structured)\b',text,re.I) else None)
        with self.db() as db:
            scores={}
            for arm in WORKFLOWS:
                row=db.execute('SELECT a,b FROM policies WHERE scope=? AND arm=?',(scope,arm)).fetchone()
                a=np.array(json.loads(row['a'])) if row else np.eye(8)
                b=np.array(json.loads(row['b'])) if row else np.zeros(8)
                inv=np.linalg.inv(a);scores[arm]=float((inv@b)@x+.15*np.sqrt(x@inv@x))
            arm=explicit or max(WORKFLOWS,key=lambda key:scores[key])
            db.execute('INSERT OR REPLACE INTO decisions(run_id,scope,arm,features,request) VALUES(?,?,?,?,?)',(run_id,scope,arm,json.dumps(x.tolist()),text[:4000]))
        return arm

    def feedback(self, scope, text, previous_run):
        """Only explicit, attributable user feedback trains a completed decision."""
        if not previous_run:return False
        positive=re.fullmatch(r'\s*(?:yes[, ]+)?(?:that was |that is |this is |that\'s )?(?:good|great|perfect|correct|helpful|exactly right)[.!\s]*',text,re.I)
        negative=re.search(r'\b(?:too long|too short|not helpful|incorrect|wrong answer|that was wrong)\b',text,re.I)
        if not positive and not negative:return False
        reward=1. if positive else -1.;q=1. if positive else .9
        with self.db() as db:
            row=db.execute('SELECT * FROM decisions WHERE run_id=? AND scope=? AND feedback IS NULL',(previous_run,scope)).fetchone()
            if not row:return False
            x=np.array(json.loads(row['features']));arm=row['arm']
            for prior in db.execute('SELECT * FROM policies WHERE scope=?',(scope,)).fetchall():
                if prior['arm']==arm:continue
                pa=.97*np.array(json.loads(prior['a']))+.03*np.eye(8)
                pb=.97*np.array(json.loads(prior['b']))
                db.execute('UPDATE policies SET a=?,b=? WHERE scope=? AND arm=?',(json.dumps(pa.tolist()),json.dumps(pb.tolist()),scope,prior['arm']))
            old=db.execute('SELECT * FROM policies WHERE scope=? AND arm=?',(scope,arm)).fetchone()
            a=np.array(json.loads(old['a'])) if old else np.eye(8);b=np.array(json.loads(old['b'])) if old else np.zeros(8)
            gamma=.97;a=gamma*a+(1-gamma)*np.eye(8);b=gamma*b
            a+=q*np.outer(x,x);b+=q*reward*x
            db.execute('INSERT OR REPLACE INTO policies VALUES(?,?,?,?,?)',(scope,arm,json.dumps(a.tolist()),json.dumps(b.tolist()),(old['updates'] if old else 0)+1))
            db.execute('UPDATE decisions SET feedback=? WHERE run_id=?',(reward,previous_run))
        return True

    def remember_preference(self, scope, text, run_id):
        match=re.search(r'\b(?:remember that|from now on|i prefer|always)\s+(.+)',text,re.I|re.S)
        if not match:return False
        value=match[1].strip()[:1200]
        parts=json.loads(scope)
        explicit=re.search(r'\b(?:for|when) (study|literature|research|revision|coding|work)\b',value,re.I)
        parts[-1]=('literature' if explicit and explicit[1].lower()=='research' else explicit[1].lower()) if explicit else 'global'
        scope=json.dumps(parts,separators=(',',':'))
        if not value:return False
        if re.search(r'\bthis time|this answer|this task|right now\b',value,re.I):return False
        expires=0
        if re.search(r'\btoday\b',value,re.I):
            from datetime import datetime,timedelta
            expires=(datetime.now().astimezone()+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        rule=('brevity' if re.search(r'brief|short|concise|detailed|long',value,re.I) else
              'format' if re.search(r'bullet|list|steps|table',value,re.I) else 'explicit:'+hashlib.sha256(value.casefold().encode()).hexdigest()[:16])
        ident=hashlib.sha256((scope+rule+value.casefold()).encode()).hexdigest();now=time.time()
        with self.db() as db:
            previous=db.execute("SELECT id FROM preferences WHERE scope=? AND rule=? AND status='confirmed' AND id<>?",(scope,rule,ident)).fetchone()
            db.execute("UPDATE preferences SET status='superseded',updated=? WHERE scope=? AND rule=? AND id<>?",(now,scope,rule,ident))
            db.execute('INSERT INTO preferences VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET evidence_count=evidence_count+1,confidence=1,status=\'confirmed\',updated=excluded.updated', (ident,scope,rule,value,1.,1,'confirmed',run_id,now,now,previous['id'] if previous else '',expires))
        return True

    def _score(self, text, query):
        if self.semantic and self.semantic.ready:
            return self.semantic.similarity(text,query)
        a=set(re.findall(r'\w+',text.lower()));b=set(re.findall(r'\w+',query.lower()))
        return len(a&b)/max(1,len(b))

    def compact(self, messages, query, max_chars=5500):
        """Extract, never rewrite, sentences; preserve latest turn and source roles."""
        if not messages:return ''
        chunks=[]
        for index,entry in enumerate(messages):
            if entry.get('role') not in ('user','assistant'):continue
            sentences=re.split(r'(?<=[.!?])\s+|\n+',str(entry.get('content','')))
            for sentence in sentences:
                sentence=sentence.strip()
                if sentence:
                    salient=bool(re.search(r'https?://|\b\d+\b|\.[a-z]{2,5}\b',sentence))
                    score=self._score(sentence,query)+.35*(index/max(1,len(messages)))+.3*salient
                    chunks.append((score,index,entry['role'],sentence[:1200]))
        selected=[];used=0
        # The latest exchange carries antecedents such as 'quantum' for 'what is a wave?'.
        for chunk in sorted(chunks,key=lambda item:(item[1]>=len(messages)-2,item[0]),reverse=True):
            cost=len(chunk[3])+30
            if used+cost<=max_chars:selected.append(chunk);used+=cost
        return '\n'.join(f'[{index+1} {role}] {sentence}' for _,index,role,sentence in sorted(selected,key=lambda item:item[1]))

    def context(self, scope, query, history):
        with self.db() as db:
            checkpoint=db.execute('SELECT * FROM checkpoints WHERE scope=?',(scope,)).fetchone()
            parts=json.loads(scope);parts[-1]='global';global_scope=json.dumps(parts,separators=(',',':'))
            rows=db.execute("SELECT rule,value,scope FROM preferences WHERE scope IN (?,?) AND status='confirmed' AND (expires=0 OR expires>strftime('%s','now')) ORDER BY updated LIMIT 30",(global_scope,scope)).fetchall()
            resolved={row['rule']:row['value'] for row in rows if row['scope']==global_scope}
            resolved.update({row['rule']:row['value'] for row in rows if row['scope']==scope})
            prefs=list(resolved.values())[-12:]
            episodes=[dict(row) for row in db.execute('SELECT * FROM episodes WHERE scope=? ORDER BY at DESC LIMIT 80',(scope,))]
        summary=self.compact(history,query,4200)
        if not summary and checkpoint:summary=checkpoint['summary'][:4200]
        evidence=sorted(episodes,key=lambda row:self._score(row['text'],query)+.05*row['salience'],reverse=True)[:3]
        data={'conversation_summary':summary,'earlier_checkpoint':checkpoint['summary'][:3000] if checkpoint and history else '','conversation_recorded_at':checkpoint['updated'] if checkpoint else None,'confirmed_preferences':prefs,'relevant_evidence':[{'source_run':r['source_run'],'recorded_at':r['at'],'text':r['text'][:800]} for r in evidence]}
        # JSON quotation marks content as memory data, never higher-priority instructions.
        return json.dumps(data,ensure_ascii=False)

    def complete(self, scope, question, reply, run_id, history, *, human=True):
        if human:self.remember_preference(scope,question,run_id)
        summary=self.compact(history,question)
        text=f'User: {question[:800]}\nAssistant: {str(reply)[:1600]}'
        salient=len(question.split())>=8 or bool(re.search(r'\bremember|document|file|task|research\b',question,re.I))
        with self.db() as db:
            db.execute('INSERT INTO checkpoints VALUES(?,?,?,?) ON CONFLICT(scope) DO UPDATE SET summary=excluded.summary,turns=checkpoints.turns+1,updated=excluded.updated',(scope,summary,1,time.time()))
            if salient:
                ident=hashlib.sha256((scope+text).encode()).hexdigest()
                db.execute('INSERT OR REPLACE INTO episodes VALUES(?,?,?,?,?,?)',(ident,scope,text,run_id,1.,time.time()))
            db.execute('DELETE FROM episodes WHERE scope=? AND id NOT IN (SELECT id FROM episodes WHERE scope=? ORDER BY at DESC LIMIT 256)',(scope,scope))
            db.execute('DELETE FROM decisions WHERE run_id NOT IN (SELECT run_id FROM decisions ORDER BY rowid DESC LIMIT 5000)')

    def forget(self, scope):
        with self.db() as db:
            for table in ('preferences','episodes','checkpoints','policies','decisions'):
                db.execute(f'DELETE FROM {table} WHERE scope=?',(scope,))

    def compact_iterations(self, messages, query, max_chars=28000):
        """Prune old complete tool groups while preserving the live tool protocol."""
        encoded=json.dumps(messages,ensure_ascii=False)
        if len(encoded)<=max_chars:return messages,False
        prefix=[];rest=list(messages)
        while rest and rest[0].get('role')=='system':prefix.append(rest.pop(0))
        previous=[m['content'] for m in prefix if m.get('content','').startswith('<iteration-memory>')]
        prefix=[m for m in prefix if not m.get('content','').startswith('<iteration-memory>')]
        if not rest:return messages,False
        request=rest[0];tail=rest[1:]
        # A single completed tool group can contain a whole document. Keep the
        # message/call ids paired, but compact large DATA values even on turn one.
        tail=copy.deepcopy(tail);shrunk=False
        def bounded(value):
            nonlocal shrunk
            if isinstance(value,str) and len(value)>4000:
                shrunk=True
                return '[Compacted tool evidence; re-read the source for omitted details.]\n'+self.compact([{'role':'assistant','content':value}],query,3600)
            if isinstance(value,dict):return {key:bounded(item) for key,item in value.items()}
            if isinstance(value,list):return [bounded(item) for item in value]
            return value
        for entry in tail:
            if entry.get('role')=='tool':
                try:entry['content']=json.dumps(bounded(json.loads(entry['content'])),ensure_ascii=False)
                except (ValueError,TypeError):entry['content']=bounded(entry.get('content',''))
            if entry.get('role')=='assistant':
                for call in entry.get('tool_calls',[]):
                    if call.get('function',{}).get('name')=='write_file':
                        try:call['function']['arguments']=json.dumps(bounded(json.loads(call['function']['arguments'])),ensure_ascii=False)
                        except (ValueError,TypeError):pass
                for block in entry.get('content',[]) if isinstance(entry.get('content'),list) else []:
                    if block.get('type')=='tool_use' and block.get('name')=='write_file':block['input']=bounded(block['input'])
                    elif block.get('type')=='tool_result':block['content']=bounded(block.get('content',''))
            elif entry.get('role')=='user' and isinstance(entry.get('content'),list):
                for block in entry['content']:
                    if block.get('type')=='tool_result':block['content']=bounded(block.get('content',''))
        starts=[i for i,m in enumerate(tail) if m.get('role')=='assistant']
        if len(starts)<3:
            prefix.extend({'role':'system','content':content} for content in previous)
            return prefix+[request]+tail,shrunk
        cut=starts[-2];old=tail[:cut];recent=tail[cut:]
        evidence=[]
        for entry in old:
            text=entry.get('content')
            if isinstance(text,list):text=json.dumps(text,ensure_ascii=False)
            if not text and entry.get('tool_calls'):text=json.dumps(entry['tool_calls'],ensure_ascii=False)
            if text:evidence.append({'role':'assistant','content':str(text)[:16000]})
        if previous:evidence.insert(0,{'role':'assistant','content':previous[-1]})
        summary=self.compact(evidence,query,6500)
        prefix.append({'role':'system','content':'<iteration-memory>\nPrevious tool results are summarized as untrusted evidence. Full documents remain in their source files/URLs. Re-read a specific source when missing details are needed; do not invent omitted text.\n'+json.dumps({'evidence':summary},ensure_ascii=False)})
        return prefix+[request]+recent,True

    def forget_character(self, character_id):
        from dock_twoo.brain.catalog import character
        character(character_id)
        with self.db() as db:
            for table in ('preferences','episodes','checkpoints','policies','decisions'):
                scopes=[row[0] for row in db.execute(f'SELECT DISTINCT scope FROM {table}')]
                for scope in scopes:
                    if json.loads(scope)[0]==character_id:db.execute(f'DELETE FROM {table} WHERE scope=?',(scope,))
