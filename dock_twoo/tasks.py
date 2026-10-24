"""Persistent dated work log shared by the Tasks drawer and voice agent."""
from datetime import date,datetime
import json
from pathlib import Path
import sqlite3
import uuid

def day(value=None):
    return date.fromisoformat(value).isoformat() if value else datetime.now().astimezone().date().isoformat()

class TaskStore:
    def __init__(self,root=None):
        if root is None:
            from dock_twoo.config import ConfigManager
            root=ConfigManager().config.get_storage_path()/'tasks'
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'tasks.sqlite3'
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, day TEXT NOT NULL, title TEXT NOT NULL, details TEXT NOT NULL, status TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS tasks_day ON tasks(day)')
    def _connect(self):
        db=sqlite3.connect(self.path,timeout=5);db.row_factory=sqlite3.Row;return db
    def add(self,title,details='',date=None,status='done'):
        title=title.strip();date=day(date)
        if not title or len(title)>1000 or len(details)>16000:raise ValueError('Enter a task title and reasonably sized details.')
        if status not in ('todo','in_progress','done'):raise ValueError('Choose todo, in_progress or done.')
        now=datetime.now().astimezone().isoformat()
        with self._connect() as db:
            existing=db.execute('SELECT * FROM tasks WHERE day=? AND lower(title)=lower(?)',(date,title)).fetchone()
            if existing:return {**dict(existing),'duplicate':True}
            ident=uuid.uuid4().hex
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?)',(ident,date,title,details,status,now,now))
            return dict(db.execute('SELECT * FROM tasks WHERE id=?',(ident,)).fetchone())
    def list(self,date=None,start=None,end=None,query='',offset=0):
        clauses=[];params=[]
        for key,value,op in [('day',date,'='),('day',start,'>='),('day',end,'<=')]:
            if value:clauses.append(f'{key}{op}?');params.append(day(value))
        if query:clauses.append('(title LIKE ? OR details LIKE ?)');params.extend(['%'+query+'%']*2)
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        with self._connect() as db:
            rows=db.execute('SELECT * FROM tasks'+where+' ORDER BY day DESC,created LIMIT 101 OFFSET ?',params+[max(0,int(offset))]).fetchall()
            return {'tasks':[dict(row) for row in rows[:100]],'next_offset':int(offset)+100 if len(rows)>100 else None}
    def update(self,id,**changes):
        allowed={key:value for key,value in changes.items() if key in ('title','details','status','day')}
        if not allowed:raise ValueError('No task changes were supplied.')
        if 'day' in allowed:allowed['day']=day(allowed['day'])
        if allowed.get('status','todo') not in ('todo','in_progress','done'):raise ValueError('Invalid task status.')
        if 'title' in allowed and not str(allowed['title']).strip():raise ValueError('Task title cannot be empty.')
        allowed['updated']=datetime.now().astimezone().isoformat()
        with self._connect() as db:
            cursor=db.execute('UPDATE tasks SET '+','.join(key+'=?' for key in allowed)+' WHERE id=?',list(allowed.values())+[id])
            if not cursor.rowcount:raise ValueError('The task was not found.')
            return dict(db.execute('SELECT * FROM tasks WHERE id=?',(id,)).fetchone())

class NotesService:
    def __init__(self,root=None):
        if root is None:
            from dock_twoo.config import ConfigManager
            root=ConfigManager().config.get_notes_dir()
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
    def list(self,query=''):
        notes=[]
        for path in sorted(self.root.glob('*.json')):
            if path.name.startswith('.'):continue
            try:
                data=json.loads(path.read_text());data['id']=path.stem
                if query.casefold() in (data.get('title','')+' '+data.get('body','')).casefold():notes.append(data)
            except (ValueError,OSError):continue
        return {'notes':notes[:100],'truncated':len(notes)>100}
    def add(self,title,body):
        import time
        title=title.strip() or 'Voice note';body=body.strip()
        for note in self.list()['notes']:
            if note.get('title')==title and note.get('body')==body:return {**note,'duplicate':True}
        ident=uuid.uuid4().hex;now=time.time()
        data={'title':title,'body':body,'created_at':now,'updated_at':now}
        path=self.root/(ident+'.json');temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2));temporary.replace(path)
        return {'id':ident,**data}
