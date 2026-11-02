"""Persistent dated work log and notes shared by the Tasks/Notes drawers and voice agent."""
from datetime import date, datetime, timedelta
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
import uuid

def day(value=None):
    return date.fromisoformat(value).isoformat() if value else datetime.now().astimezone().date().isoformat()

class TaskStore:
    def __init__(self, root=None):
        if root is None:
            from dock_twoo.config import ConfigManager
            root = ConfigManager().config.get_storage_path() / 'tasks'
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'tasks.sqlite3'
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, day TEXT NOT NULL, title TEXT NOT NULL, details TEXT NOT NULL, status TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL, deleted_at TEXT)')
            try:
                db.execute('ALTER TABLE tasks ADD COLUMN deleted_at TEXT')
            except sqlite3.OperationalError:
                pass
            db.execute('CREATE INDEX IF NOT EXISTS tasks_day ON tasks(day)')
            db.execute('CREATE INDEX IF NOT EXISTS tasks_deleted ON tasks(deleted_at)')
        self.purge_expired(days=30)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5); db.row_factory = sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def purge_expired(self, days=30):
        """Hard-delete tasks that have been in soft-delete state for more than specified days."""
        cutoff = (datetime.now().astimezone() - timedelta(days=days)).isoformat()
        with self._connect() as db:
            db.execute('DELETE FROM tasks WHERE deleted_at IS NOT NULL AND deleted_at < ?', (cutoff,))

    def add(self, title, details='', date=None, status='done'):
        title = title.strip(); date = day(date)
        if not title or len(title) > 1000 or len(details) > 16000: raise ValueError('Enter a task title and reasonably sized details.')
        if status not in ('todo', 'in_progress', 'done'): raise ValueError('Choose todo, in_progress or done.')
        now = datetime.now().astimezone().isoformat()
        with self._connect() as db:
            existing = db.execute('SELECT * FROM tasks WHERE day=? AND lower(title)=lower(?) AND deleted_at IS NULL', (date, title)).fetchone()
            if existing: return {**dict(existing), 'duplicate': True}
            ident = uuid.uuid4().hex
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,NULL)', (ident, date, title, details, status, now, now))
            return dict(db.execute('SELECT * FROM tasks WHERE id=?', (ident,)).fetchone())

    def list(self, date=None, start=None, end=None, query='', offset=0, status=None, include_deleted=False):
        clauses = []; params = []
        if not include_deleted:
            clauses.append('deleted_at IS NULL')
        if start and end and day(start) > day(end): raise ValueError('The From date must be on or before the To date.')
        if status not in (None, '', 'todo', 'in_progress', 'done'): raise ValueError('Choose a valid task status.')
        for key, value, op in [('day', date, '='), ('day', start, '>='), ('day', end, '<=')]:
            if value: clauses.append(f'{key}{op}?'); params.append(day(value))
        if status: clauses.append('status=?'); params.append(status)
        if query:
            query = str(query).replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            clauses.append("(title LIKE ? ESCAPE '\\' OR details LIKE ? ESCAPE '\\')"); params.extend(['%' + query + '%'] * 2)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        offset = max(0, int(offset))
        with self._connect() as db:
            counts = {key: 0 for key in ('todo', 'in_progress', 'done')}
            for row in db.execute('SELECT status,count(*) count FROM tasks' + where + ' GROUP BY status', params): counts[row['status']] = row['count']
            rows = db.execute('SELECT * FROM tasks' + where + ' ORDER BY day DESC,created,id LIMIT 101 OFFSET ?', params + [offset]).fetchall()
            return {'tasks': [dict(row) for row in rows[:100]], 'next_offset': offset + 100 if len(rows) > 100 else None,
                    'total': sum(counts.values()), 'counts': counts}

    def get(self, id):
        with self._connect() as db:
            row = db.execute('SELECT * FROM tasks WHERE id=?', (id,)).fetchone()
            if row is None: raise ValueError('The task was not found.')
            return dict(row)

    def update(self, id, **changes):
        allowed = {key: value for key, value in changes.items() if key in ('title', 'details', 'status', 'day')}
        if not allowed: raise ValueError('No task changes were supplied.')
        if 'day' in allowed: allowed['day'] = day(allowed['day'])
        if allowed.get('status', 'todo') not in ('todo', 'in_progress', 'done'): raise ValueError('Invalid task status.')
        if 'title' in allowed and not str(allowed['title']).strip(): raise ValueError('Task title cannot be empty.')
        if 'title' in allowed:
            allowed['title'] = str(allowed['title']).strip()
            if len(allowed['title']) > 1000: raise ValueError('Use at most 1,000 characters for a task title.')
        if 'details' in allowed and len(allowed['details']) > 16000: raise ValueError('Use at most 16,000 characters for task details.')
        allowed['updated'] = datetime.now().astimezone().isoformat()
        with self._connect() as db:
            cursor = db.execute('UPDATE tasks SET ' + ','.join(key + '=?' for key in allowed) + ' WHERE id=?', list(allowed.values()) + [id])
            if not cursor.rowcount: raise ValueError('The task was not found.')
            return dict(db.execute('SELECT * FROM tasks WHERE id=?', (id,)).fetchone())

    def delete(self, id, soft=True):
        """Soft-delete by default with 30-day recovery; or hard-delete."""
        self.purge_expired(days=30)
        now = datetime.now().astimezone().isoformat()
        with self._connect() as db:
            if soft:
                cursor = db.execute('UPDATE tasks SET deleted_at=? WHERE id=? AND deleted_at IS NULL', (now, id))
                if not cursor.rowcount:
                    row = db.execute('SELECT * FROM tasks WHERE id=?', (id,)).fetchone()
                    if row is None: raise ValueError('The task was not found.')
                    return dict(row)
                return dict(db.execute('SELECT * FROM tasks WHERE id=?', (id,)).fetchone())
            else:
                cursor = db.execute('DELETE FROM tasks WHERE id=?', (id,))
                if not cursor.rowcount: raise ValueError('The task was not found.')
                return {'id': id, 'deleted': True, 'hard': True}

    def restore(self, id):
        """Restore a soft-deleted task."""
        with self._connect() as db:
            cursor = db.execute('UPDATE tasks SET deleted_at=NULL WHERE id=?', (id,))
            if not cursor.rowcount: raise ValueError('The task was not found.')
            return dict(db.execute('SELECT * FROM tasks WHERE id=?', (id,)).fetchone())


class NotesService:
    def __init__(self, root=None):
        if root is None:
            from dock_twoo.config import ConfigManager
            root = ConfigManager().config.get_notes_dir()
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.trash = self.root / '.trash'
        self.trash.mkdir(parents=True, exist_ok=True)
        self.purge_expired(days=30)

    def purge_expired(self, days=30):
        """Permanently delete trash notes older than 30 days."""
        cutoff = time.time() - (days * 86400)
        for path in self.trash.glob('*.json'):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                deleted_at = data.get('deleted_at', path.stat().st_mtime)
                if deleted_at < cutoff:
                    path.unlink(missing_ok=True)
            except Exception:
                pass

    def list(self, query='', include_deleted=False):
        notes = []
        source_dirs = [self.root]
        if include_deleted:
            source_dirs.append(self.trash)
        for d in source_dirs:
            for path in sorted(d.glob('*.json')):
                if path.name.startswith('.'): continue
                try:
                    data = json.loads(path.read_text(encoding='utf-8'))
                    data['id'] = path.stem
                    data['deleted'] = (d == self.trash or bool(data.get('deleted_at')))
                    if not include_deleted and data['deleted']:
                        continue
                    if query.casefold() in (data.get('title', '') + ' ' + data.get('body', '')).casefold():
                        notes.append(data)
                except (ValueError, OSError): continue
        return {'notes': notes[:100], 'truncated': len(notes) > 100}

    def get(self, id):
        path = self.root / f'{id}.json'
        if not path.exists():
            trash_path = self.trash / f'{id}.json'
            if trash_path.exists():
                data = json.loads(trash_path.read_text(encoding='utf-8'))
                data['id'] = id
                data['deleted'] = True
                return data
            raise ValueError('The note was not found.')
        data = json.loads(path.read_text(encoding='utf-8'))
        data['id'] = id
        return data

    def add(self, title, body):
        title = title.strip() or 'Voice note'; body = body.strip()
        for note in self.list()['notes']:
            if note.get('title') == title and note.get('body') == body: return {**note, 'duplicate': True}
        ident = uuid.uuid4().hex; now = time.time()
        data = {'title': title, 'body': body, 'created_at': now, 'updated_at': now}
        path = self.root / f'{ident}.json'; temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8'); temporary.replace(path)
        return {'id': ident, **data}

    def update(self, id, title=None, body=None):
        path = self.root / f'{id}.json'
        if not path.exists():
            raise ValueError('The note was not found.')
        data = json.loads(path.read_text(encoding='utf-8'))
        if title is not None: data['title'] = str(title).strip()
        if body is not None: data['body'] = str(body).strip()
        data['updated_at'] = time.time()
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(path)
        return {'id': id, **data}

    def delete(self, id, soft=True):
        """Soft-delete note into .trash with 30-day recovery; or hard-delete."""
        self.purge_expired(days=30)
        path = self.root / f'{id}.json'
        trash_path = self.trash / f'{id}.json'
        if not path.exists() and not trash_path.exists():
            raise ValueError('The note was not found.')
        if not path.exists() and trash_path.exists():
            if not soft:
                trash_path.unlink(missing_ok=True)
                return {'id': id, 'deleted': True, 'hard': True}
            data = json.loads(trash_path.read_text(encoding='utf-8'))
            return {'id': id, **data, 'deleted': True}
        if soft:
            data = json.loads(path.read_text(encoding='utf-8'))
            data['deleted_at'] = time.time()
            temp = trash_path.with_suffix('.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(trash_path)
            path.unlink(missing_ok=True)
            return {'id': id, **data, 'deleted': True}
        else:
            path.unlink(missing_ok=True)
            return {'id': id, 'deleted': True, 'hard': True}

    def restore(self, id):
        """Restore note from .trash."""
        trash_path = self.trash / f'{id}.json'
        if not trash_path.exists():
            path = self.root / f'{id}.json'
            if path.exists(): return self.get(id)
            raise ValueError('The note was not found in trash.')
        data = json.loads(trash_path.read_text(encoding='utf-8'))
        data.pop('deleted_at', None)
        path = self.root / f'{id}.json'
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)
        trash_path.unlink(missing_ok=True)
        return {'id': id, **data}

