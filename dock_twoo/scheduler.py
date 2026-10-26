"""Durable local reminders with civil-time recurrence and an alert outbox."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import calendar
from pathlib import Path
import sqlite3
import time
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REPEATS = {'once':'Once', 'daily':'Every day', 'weekdays':'Weekdays', 'weekly':'Every week', 'monthly':'Every month'}
UTC = timezone.utc


def local_zone():
    from PySide6.QtCore import QTimeZone
    return bytes(QTimeZone.systemTimeZoneId()).decode() or 'UTC'


def civil_time(value, zone):
    """Choose the first repeated DST time; move gaps forward to the next valid minute."""
    for _ in range(181):
        aware = value.replace(tzinfo=zone, fold=0)
        if aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == value:return aware
        value += timedelta(minutes=1)
    raise ValueError('This local time does not exist in the selected time zone.')


def next_occurrence(row, after):
    if row['repeat']=='once':return None
    zone = ZoneInfo(row['timezone'])
    original = datetime.fromisoformat(row['local_start'])
    local = datetime.fromtimestamp(after, zone).replace(tzinfo=None)
    date = max(original.date(), local.date())
    for offset in range(370):
        candidate_date = date+timedelta(days=offset)
        repeat = row['repeat']
        if repeat=='weekdays' and candidate_date.weekday()>4:continue
        if repeat=='weekly' and candidate_date.weekday()!=original.weekday():continue
        if repeat=='monthly' and candidate_date.day!=min(original.day,calendar.monthrange(candidate_date.year,candidate_date.month)[1]):continue
        candidate = civil_time(datetime.combine(candidate_date,original.time()),zone).timestamp()
        if candidate>after:return candidate
    raise ValueError('Could not calculate the next reminder.')


class ScheduleStore:
    def __init__(self, root, clock=time.time):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root/'scheduler.sqlite3'; self.clock = clock
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, character_id TEXT NOT NULL,
                local_start TEXT NOT NULL, timezone TEXT NOT NULL, repeat TEXT NOT NULL,
                next_due REAL, enabled INTEGER NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY, reminder_id TEXT NOT NULL REFERENCES reminders(id) ON DELETE CASCADE,
                due REAL NOT NULL, lead INTEGER NOT NULL, text TEXT NOT NULL,
                created REAL NOT NULL, shown INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS alerts_pending ON alerts(shown, created);''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=3)
        db.row_factory = sqlite3.Row; db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:yield db
        finally:db.close()

    def add(self, title, when, repeat='once', timezone=None, character_id='default'):
        from dock_twoo.brain.catalog import character
        character(character_id)
        title = title.strip()
        if not title or len(title)>2000:raise ValueError('Enter a reminder of at most 2,000 characters.')
        if repeat not in REPEATS:raise ValueError('Choose a supported recurrence.')
        zone_name = timezone or local_zone()
        try:zone = ZoneInfo(zone_name)
        except ZoneInfoNotFoundError as exc:raise ValueError('Choose an IANA time zone, such as Asia/Kolkata.') from exc
        try:
            if not isinstance(when,str) or len(when)<16:raise ValueError('Missing time')
            value = datetime.fromisoformat(when)
        except ValueError as exc:raise ValueError('Supply the complete date and time in ISO format.') from exc
        if value.tzinfo:value = value.astimezone(zone).replace(tzinfo=None)
        value = value.replace(second=0,microsecond=0)
        due = civil_time(value,zone).timestamp(); now = self.clock()
        row = dict(id=uuid.uuid4().hex, title=title, character_id=character_id, local_start=value.isoformat(),
                   timezone=zone_name, repeat=repeat, next_due=due, enabled=1, created=now)
        if repeat=='weekdays' and value.weekday()>4:row['next_due']=next_occurrence(row,due-1)
        if row['next_due']<=now:
            if repeat=='once':raise ValueError('Choose a future date and time.')
            row['next_due']=next_occurrence(row,now)
        with self.db() as db:
            old=db.execute('SELECT * FROM reminders WHERE title=? AND character_id=? AND local_start=? AND timezone=? AND repeat=? AND enabled=1',
                           (title,character_id,value.isoformat(),zone_name,repeat)).fetchone()
            if old:return {**dict(old),'duplicate':True}
            db.execute('INSERT INTO reminders VALUES(?,?,?,?,?,?,?,?,?)',tuple(row.values()))
        return {**row,'alerts_minutes_before':[5,1,0]}

    def list(self):
        with self.db() as db:return [dict(row) for row in db.execute('SELECT * FROM reminders ORDER BY enabled DESC,next_due,id')]

    def delete(self, id):
        with self.db() as db:
            if not db.execute('DELETE FROM reminders WHERE id=?',(id,)).rowcount:raise ValueError('Reminder not found.')
        return {'deleted':id}

    def set_enabled(self, id, enabled):
        with self.db() as db:
            row=db.execute('SELECT * FROM reminders WHERE id=?',(id,)).fetchone()
            if row is None:raise ValueError('Reminder not found.')
            due=row['next_due']
            if enabled and (due is None or due<=self.clock()):
                due=next_occurrence(row,self.clock())
                if due is None:raise ValueError('This one-time reminder has passed. Create a new reminder.')
            db.execute('UPDATE reminders SET enabled=?,next_due=? WHERE id=?',(int(enabled),due,id))
            if not enabled:db.execute('DELETE FROM alerts WHERE reminder_id=? AND shown=0',(id,))
        return {'id':id,'enabled':bool(enabled)}

    def poll(self, now=None):
        now = self.clock() if now is None else now
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for row in db.execute('SELECT * FROM reminders WHERE enabled=1 AND next_due IS NOT NULL').fetchall():
                due = row['next_due']
                # Resume without a burst of stale five/one-minute warnings.
                eligible = [lead for lead in (300,60,0) if row['created']<=due-lead<=now]
                if eligible:
                    lead=min(eligible); key=f"{row['id']}:{due:.0f}:{lead}"
                    stamp=datetime.fromtimestamp(due,ZoneInfo(row['timezone'])).strftime('%d %b at %I:%M %p')
                    timing=(f'in {lead//60} minutes ({stamp})' if lead else f'now ({stamp})')
                    if not lead and now-due>90:timing=f'was due on {stamp}'
                    text=f"Reminder {timing}: {row['title']}"
                    db.execute('INSERT OR IGNORE INTO alerts(id,reminder_id,due,lead,text,created) VALUES(?,?,?,?,?,?)',
                               (key,row['id'],due,lead,text,now))
                if due<=now:
                    following=next_occurrence(row,now)
                    db.execute('UPDATE reminders SET next_due=?,enabled=? WHERE id=?',(following,int(following is not None),row['id']))
            db.execute('DELETE FROM alerts WHERE shown=1 AND created<?',(now-7*86400,))
            # Crash/sleep recovery supersedes an unsent earlier stage.
            db.execute('DELETE FROM alerts WHERE shown=0 AND EXISTS (SELECT 1 FROM alerts newer WHERE newer.reminder_id=alerts.reminder_id AND newer.due=alerts.due AND newer.lead<alerts.lead)')
            return [dict(row) for row in db.execute('SELECT a.*,r.character_id,r.title FROM alerts a JOIN reminders r ON r.id=a.reminder_id WHERE shown=0 ORDER BY a.created,a.id LIMIT 100')]

    def acknowledge(self, ids):
        with self.db() as db:db.executemany('UPDATE alerts SET shown=1 WHERE id=?',[(id,) for id in ids])

    def pending_valid(self, reminder_id):
        # A completed one-time reminder still needs its final spoken alert;
        # an explicitly paused reminder must not speak an already queued warning.
        with self.db() as db:
            return db.execute('SELECT 1 FROM reminders WHERE id=? AND (enabled=1 OR next_due IS NULL)',
                              (reminder_id,)).fetchone() is not None
