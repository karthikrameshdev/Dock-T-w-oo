from datetime import datetime, timezone
import threading
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo
import pytest
from dock_twoo.scheduler import ScheduleStore, next_occurrence
from dock_twoo.brain.agent_tools import LocalTools
from tests.test_multi_brain import manager_at, inventory


def epoch(value):return datetime.fromisoformat(value).timestamp()


def test_three_alerts_durable_deduplicated_and_daily(tmp_path):
    now=[epoch('2026-10-25T09:00:00+05:30')];store=ScheduleStore(tmp_path,lambda:now[0])
    row=store.add('Stand-up','2026-10-25T10:00',repeat='daily',timezone='Asia/Kolkata',character_id='fox')
    for stamp,lead in [('09:55',300),('09:59',60),('10:00',0)]:
        now[0]=epoch('2026-10-25T'+stamp+':00+05:30')
        alerts=store.poll();assert len(alerts)==1 and alerts[0]['lead']==lead and alerts[0]['character_id']=='fox'
        store.acknowledge([alerts[0]['id']])
        store=ScheduleStore(tmp_path,lambda:now[0])
        assert not store.poll()
    assert store.list()[0]['next_due']==epoch('2026-10-26T10:00:00+05:30')
    assert store.list()[0]['enabled']


def test_once_past_validation_duplicate_and_catchup(tmp_path):
    now=[epoch('2026-10-25T09:00:00+00:00')];store=ScheduleStore(tmp_path,lambda:now[0])
    with pytest.raises(ValueError):store.add('Past','2026-10-25T08:00',timezone='UTC')
    with pytest.raises(ValueError):store.add('Missing time','2026-10-26',timezone='UTC')
    row=store.add('Meeting','2026-10-26T10:00',timezone='UTC')
    assert store.add('Meeting','2026-10-26T10:00',timezone='UTC')['duplicate']
    now[0]=epoch('2026-10-26T11:00:00+00:00')
    alerts=store.poll();assert len(alerts)==1 and alerts[0]['lead']==0 and 'was due' in alerts[0]['text']
    assert store.list()[0]['enabled']==0
    assert store.pending_valid(row['id'])  # Completion must still speak the due alert.
    store.delete(row['id']);assert not store.poll()


def test_pause_and_resume_does_not_replay_old_warnings(tmp_path):
    now=[epoch('2026-10-25T09:00:00+00:00')];store=ScheduleStore(tmp_path,lambda:now[0])
    row=store.add('Review','2026-10-25T10:00',repeat='daily',timezone='UTC')
    store.set_enabled(row['id'],False);now[0]+=7200
    assert not store.pending_valid(row['id'])
    assert not store.poll()
    store.set_enabled(row['id'],True)
    assert store.pending_valid(row['id'])
    assert store.list()[0]['next_due']==epoch('2026-10-26T10:00:00+00:00')
    assert not store.poll()


def test_civil_time_dst_weekdays_and_month_end(tmp_path):
    store=ScheduleStore(tmp_path,lambda:epoch('2026-01-01T00:00:00+00:00'))
    row=store.add('DST','2026-03-07T02:30',repeat='daily',timezone='America/New_York')
    following=next_occurrence(row,row['next_due'])
    assert datetime.fromtimestamp(following,ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M')=='2026-03-08 03:00'
    again=next_occurrence(row,following)
    assert datetime.fromtimestamp(again,ZoneInfo('America/New_York')).hour==2
    row=store.add('Weekly','2026-10-23T10:00',repeat='weekdays',timezone='UTC')
    assert next_occurrence(row,row['next_due'])==epoch('2026-10-26T10:00:00+00:00')
    row=store.add('Month end','2026-01-31T10:00',repeat='monthly',timezone='UTC')
    assert next_occurrence(row,row['next_due'])==epoch('2026-02-28T10:00:00+00:00')


def test_tools_attach_addressed_character_without_cloud_call(qapp,tmp_path):
    manager=manager_at(tmp_path/'brain',inventory()[:1]);cancel=threading.Event()
    from dock_twoo.brain.ecosystem.coordinator import WorkerManager
    worker=WorkerManager(manager,'fox',tmp_path,threading.Lock(),cancel)
    tools=LocalTools(worker)
    future=datetime.now().astimezone()+__import__('datetime').timedelta(days=1)
    row=tools.execute('create_reminder',{'title':'Meeting','when':future.isoformat()},cancel)
    assert row['character_id']=='fox'
    assert len(tools.execute('list_reminders',{},cancel)['reminders'])==1
    tools.guard.approve=lambda *args:False
    with pytest.raises(PermissionError):tools.execute('delete_reminder',{'id':row['id']},cancel)
    assert len(tools.execute('list_reminders',{},cancel)['reminders'])==1
    manager.shutdown()


def test_scheduler_window_add_search_pause_delete(qtbot,tmp_path):
    from dock_twoo.config import DockConfig
    from dock_twoo.ui.apps.scheduler_app import SchedulerAppWidget
    config=DockConfig(storage_path=str(tmp_path))
    widget=SchedulerAppWidget(config);qtbot.addWidget(widget);widget.show();widget.new_reminder()
    widget.title.setText('Review research');widget.save()
    assert widget.stack.currentIndex()==0 and widget.list.count()==1
    widget.list.setCurrentRow(0);widget.toggle();assert not widget.store.list()[0]['enabled']
    widget.search.setText('no match');assert widget.list.count()==0
    widget.search.clear();widget.list.setCurrentRow(0);widget.remove();assert not widget.store.list()


def test_reminder_waits_for_microphone_and_speech(qapp,tmp_path,monkeypatch):
    manager=manager_at(tmp_path/'brain',inventory()[:1]);service=manager.reminders
    row=service.store.add('Example','2099-01-01T10:00',timezone='UTC')
    service.speech_queue.append({'reminder_id':row['id'],'character_id':'default','text':'Example'})
    calls=[];monkeypatch.setattr(manager,'_queue_turn',lambda *a,**k:calls.append((a,k)))
    manager.listener.is_recording=True;service._speak_next();assert not calls
    manager.listener.is_recording=False;service._speak_next();assert calls[0][1]['kind']=='reminder'
    assert not service.speech_queue
    manager.shutdown()


def test_unacknowledged_warning_is_superseded_after_restart(tmp_path):
    now=[epoch('2026-10-25T09:00:00+00:00')];store=ScheduleStore(tmp_path,lambda:now[0])
    store.add('Meeting','2026-10-25T10:00',timezone='UTC')
    assert store.poll(epoch('2026-10-25T09:55:00+00:00'))[0]['lead']==300
    # Crash before UI acknowledgment; restart after the actual time.
    again=ScheduleStore(tmp_path,lambda:epoch('2026-10-25T10:01:00+00:00'))
    alerts=again.poll();assert len(alerts)==1 and alerts[0]['lead']==0


def test_recurring_reminder_survives_reopen_without_provider(tmp_path):
    now=[epoch('2026-10-25T09:00:00+00:00')];store=ScheduleStore(tmp_path,lambda:now[0])
    row=store.add('Daily','2026-10-25T10:00',repeat='daily',timezone='UTC')
    now[0]=epoch('2026-11-25T10:00:01+00:00')
    alerts=ScheduleStore(tmp_path,lambda:now[0]).poll()
    assert len(alerts)==1  # Never emit a month of stale alerts at once.
    assert store.list()[0]['next_due']==epoch('2026-11-26T10:00:00+00:00')
