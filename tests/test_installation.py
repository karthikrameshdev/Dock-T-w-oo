import json
import plistlib
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from dock_twoo.startup import StartupManager,IDENTIFIER
from dock_twoo.installation import install_bundle
from dock_twoo.storage_migration import migrate_voice_storage

@pytest.mark.parametrize('system,relative',[('Darwin','Contents/MacOS/DockTwoo'),('Linux','DockTwoo'),('Windows','DockTwoo.exe')])
def test_native_install_preserves_user_state_and_has_no_source_dependency(tmp_path,monkeypatch,system,relative):
    calls=[];monkeypatch.setattr('subprocess.run',lambda *a,**k:calls.append(a))
    monkeypatch.setattr(StartupManager,'set_enabled',lambda self,on:calls.append(('startup',on,self.command)))
    home=tmp_path/'home';config=home/'.dock_twoo';config.mkdir(parents=True);(config/'config.json').write_text(json.dumps({'keep_live':True,'edge':'left'}))
    source=tmp_path/'bundle';exe=source/relative;exe.parent.mkdir(parents=True);exe.write_text('native binary')
    target=install_bundle(source,home=home,system=system,start=False)
    assert (target/relative).read_text()=='native binary'
    settings=json.loads((config/'config.json').read_text());assert settings['keep_live'] and settings['start_on_boot'] and settings['edge']=='left'
    record=json.loads((config/'installation.json').read_text());assert Path(record['executable']).is_relative_to(target)
    exe.write_text('updated');install_bundle(source,home=home,system=system,start=False,autostart=False)
    assert (target/relative).read_text()=='updated' and json.loads((config/'config.json').read_text())['start_on_boot'] is False


def test_login_startup_files_are_user_scoped_and_disable_removes_only_ours(tmp_path):
    command=['/Applications/My Dock.app/Contents/MacOS/DockTwoo']
    mac=StartupManager(home=tmp_path,system='Darwin',command=command);mac.set_enabled(True)
    value=plistlib.loads(mac.path.read_bytes());assert value['ProgramArguments']==command and value['RunAtLoad'] and 'KeepAlive' not in value
    other=mac.path.parent/'other.plist';other.write_text('keep');mac.set_enabled(False);assert not mac.path.exists() and other.read_text()=='keep'
    linux=StartupManager(home=tmp_path,system='Linux',command=['/home/test/My App/DockTwoo']);linux.set_enabled(True)
    assert 'Exec="/home/test/My App/DockTwoo"' in linux.path.read_text();linux.set_enabled(False);assert not linux.path.exists()


def test_windows_startup_uses_quoted_current_user_run_key(tmp_path,monkeypatch):
    values={}
    class Key:
        def __enter__(self):return self
        def __exit__(self,*a):pass
    fake=SimpleNamespace(HKEY_CURRENT_USER='user',REG_SZ=1,CreateKey=lambda *a:Key(),SetValueEx=lambda k,n,r,t,v:values.update({n:v}),DeleteValue=lambda k,n:values.pop(n))
    monkeypatch.setitem(sys.modules,'winreg',fake)
    manager=StartupManager(home=tmp_path,system='Windows',command=[r'C:\Users\Me\My App\DockTwoo.exe']);manager.set_enabled(True)
    assert values[IDENTIFIER].startswith('"C:');manager.set_enabled(False);assert not values


def test_storage_migration_keeps_original_profiles_history_and_keys(tmp_path):
    old=tmp_path/'brain';old.mkdir();(old/'settings.json').write_text('{"active_character":"orbit","companion_visible":false}')
    (old/'cloud-credentials.key').write_bytes(b'key');(old/'memory').mkdir();(old/'memory/data').write_text('private memory')
    new=migrate_voice_storage(tmp_path)
    assert (new/'settings.json').read_bytes()==(old/'settings.json').read_bytes()
    assert (new/'cloud-credentials.key').read_bytes()==b'key' and (old/'memory/data').exists()
    (new/'settings.json').write_text('new state');migrate_voice_storage(tmp_path);assert (new/'settings.json').read_text()=='new state'


def test_storage_conflict_never_overwrites_either_copy(tmp_path):
    for name in ('brain','voice'):(tmp_path/name).mkdir();(tmp_path/name/'settings.json').write_text(name)
    with pytest.raises(RuntimeError,match='conflict'):migrate_voice_storage(tmp_path)
    assert (tmp_path/'brain/settings.json').read_text()=='brain' and (tmp_path/'voice/settings.json').read_text()=='voice'


def test_keep_live_persists_intent_but_exit_only_releases_runtime(tmp_path,monkeypatch):
    from dock_twoo.config import ConfigManager
    from dock_twoo.keep_awake import KeepAwake
    manager=ConfigManager(config_path=tmp_path/'config.json');awake=KeepAwake();awake.config=manager
    class Process:
        def poll(self):return None
        def terminate(self):pass
        def wait(self,timeout):return 0
    monkeypatch.setattr('dock_twoo.keep_awake.platform.system',lambda:'Darwin');monkeypatch.setattr('dock_twoo.keep_awake.subprocess.Popen',lambda *a,**k:Process())
    awake.set_enabled(True);awake.close();assert not awake.status()['enabled'] and manager.config.keep_live
    restored=KeepAwake();restored.bind(ConfigManager(config_path=tmp_path/'config.json'));assert restored.status()['enabled']
    restored.set_enabled(False);assert not restored.config.config.keep_live;restored.close()


def test_startup_config_failures_do_not_persist(qapp,tmp_path,monkeypatch):
    from dock_twoo.config import ConfigManager
    cfg=ConfigManager(config_path=tmp_path/'config.json')
    def failed(*a):raise OSError('No permission')
    monkeypatch.setattr(StartupManager,'set_enabled',failed)
    with pytest.raises(OSError):cfg.update({'start_on_boot':True})
    assert not cfg.config.start_on_boot
    with pytest.raises(ValueError):cfg.update({'start_on_boot':'false'})


def test_storage_relocation_uses_voice_and_never_overwrites_conflicts(tmp_path,monkeypatch):
    from dock_twoo.config import migrate_storage_data
    monkeypatch.setattr(Path,'home',lambda:tmp_path/'home')
    old=tmp_path/'old';(old/'brain').mkdir(parents=True);(old/'brain/settings.json').write_text('legacy')
    new=tmp_path/'new';migrate_storage_data(old,new)
    assert (new/'voice/settings.json').read_text()=='legacy' and not (new/'brain').exists()
    (new/'voice/settings.json').write_text('independent')
    with pytest.raises(ValueError,match='conflict'):migrate_storage_data(old,new)
    assert (new/'voice/settings.json').read_text()=='independent'
    (old/'voice').mkdir();(old/'voice/settings.json').write_text('active');(old/'.voice-storage-migrated').write_text('{}')
    second=tmp_path/'second';migrate_storage_data(old,second)
    assert (second/'voice/settings.json').read_text()=='active' and not (second/'brain').exists()
