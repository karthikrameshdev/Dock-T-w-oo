"""Cloud profile isolation, migration and durable per-profile usage."""
from datetime import datetime,timedelta,timezone
import json,sqlite3
import pytest
from dock_twoo.brain.profiles import ProfileManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.activity import ActivityStore


def config(name,key,**extra):
    return {'name':name,'provider':'custom','base_url':'https://models.example/v1','model':'same-model','api_key':key,**extra}


def test_multiple_profiles_isolate_keys_switch_and_reload(tmp_path):
    manager=ProfileManager(BrainStore(tmp_path))
    first=manager.save_profile(config('Everyday','first-secret'))
    second=manager.create_profile(config('Research','second-secret'))
    assert first['id']!=second['id'] and manager.get_active_profile()['id']==first['id']
    assert manager.get_key('custom',first['id'])=='first-secret'
    assert manager.get_key('custom',second['id'])=='second-secret'
    manager.activate_profile(second['id'])
    restored=ProfileManager(BrainStore(tmp_path))
    assert restored.get_active_profile()['id']==second['id'] and restored.get_key('custom')=='second-secret'
    restored.save_profile(config('Renamed','',id=second['id']))
    assert restored.get_key('custom')=='second-secret'
    assert all(secret not in json.dumps(restored.get_profiles()) for secret in ('first-secret','second-secret'))
    assert 'secret' not in restored.store.settings_file.read_text()
    with pytest.raises(ValueError):restored.create_profile(config('Everyday','third'))
    restored.delete_profile(second['id']);assert restored.get_active_profile()['id']==first['id']
    assert restored.get_key('custom',second['id'])==''
    restored.delete_profile(first['id']);assert restored.get_profiles()==[]
    assert restored.get_active_profile()['status']=='not configured'


def test_single_model_and_provider_key_migrate_once(tmp_path):
    store=BrainStore(tmp_path);store.set_setting('cloud_model',config('Old',''))
    manager=ProfileManager(store)
    # Emulate the previous encrypted provider-only credential file.
    manager._save_keys({'custom':'existing-secret'});store.set_setting('cloud_profiles',None)
    migrated=ProfileManager(BrainStore(tmp_path))
    assert migrated.get_active_profile()['model']=='same-model'
    assert migrated.get_key('custom')=='existing-secret'
    new=migrated.create_profile(config('Other',''))
    assert not new['key_configured'] and migrated.get_key('custom',new['id'])==''


def tracked_call(store,profile,input_tokens,output_tokens):
    run=store.start('Synthetic request');call=store.begin_call(run,profile,{})
    store.end_call(call,{'model':profile['model'],'usage':{'prompt_tokens':input_tokens,'completion_tokens':output_tokens,'total_tokens':input_tokens+output_tokens}},'openai')
    store.finish(run,'complete','Synthetic reply');return run


def test_same_provider_model_counts_are_separate_and_survive_trace_expiry(tmp_path):
    now=[datetime(2026,10,2,tzinfo=timezone.utc)]
    store=ActivityStore(tmp_path,clock=lambda:now[0])
    a={'id':'first','name':'Everyday','provider':'custom','model':'same'}
    b={**a,'id':'second','name':'Research'}
    tracked_call(store,a,100,20);tracked_call(store,b,300,40)
    assert store.metrics()['summary']['total_tokens']==460
    assert store.metrics(profile_id='first')['summary']['total_tokens']==120
    assert store.metrics(profile_id='second')['summary']['total_tokens']==340
    assert {p['profile_id'] for p in store.metrics()['profiles']}=={'first','second'}
    now[0]+=timedelta(days=8);store.prune()
    assert not store.list()['runs']
    assert store.metrics(profile_id='second')['summary']['total_tokens']==340


def test_previous_daily_usage_migrates_without_changing_totals(tmp_path):
    store=ActivityStore(tmp_path)
    tracked_call(store,{'provider':'custom','model':'old'},100,20)
    # Reproduce the original aggregate schema without profile columns.
    with store.db() as db:
        columns=[row[1] for row in db.execute('PRAGMA table_info(daily_usage)') if row[1] not in ('profile_id','profile_name')]
        db.execute('CREATE TABLE old_usage AS SELECT '+','.join(columns)+' FROM daily_usage')
        db.execute('DROP TABLE daily_usage');db.execute('ALTER TABLE old_usage RENAME TO daily_usage')
    restored=ActivityStore(tmp_path)
    assert restored.metrics()['summary']['total_tokens']==120
    assert restored.metrics(profile_id='__legacy__')['summary']['total_tokens']==120
    assert restored.metrics()['profile_options']==[{'id':'__legacy__','name':'Earlier activity','historical':True}]


def test_dock_context_menu_switches_the_selected_profile(qapp,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QMenu
    from PySide6.QtCore import QPoint
    from dock_twoo.brain.manager import BrainManager
    manager=BrainManager(store=BrainStore(tmp_path),start_services=False)
    profile=manager.profile_mgr.create_profile(config('Research','fixture-key'))
    spoken=[]
    monkeypatch.setattr(manager.reader,'_remember',lambda:None)
    monkeypatch.setattr(manager.speech,'start',spoken.append)
    root=manager._build_context_menu()
    menu=next(child for child in root.findChildren(QMenu) if 'Model Profile' in child.title())
    action=next(action for action in menu.actions() if action.text().startswith('Research'))
    action.trigger()
    assert manager.profile_mgr.get_active_profile()['id']==profile['id']
    assert spoken==['Switched profile to Research.']
    manager.shutdown()
