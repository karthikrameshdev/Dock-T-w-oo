"""Install an already-built native bundle for the current user."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from dock_twoo.startup import StartupManager, desktop_entry, IDENTIFIER


def install_bundle(source, *, home=None, system=None, autostart=True, start=True):
    source=Path(source).resolve();home=Path(home) if home else Path.home()
    system=system or platform.system()
    if system=='Darwin':
        target=home/'Applications'/'DockTwoo.app';relative=Path('Contents/MacOS/DockTwoo')
    elif system=='Windows':
        base=Path(os.environ.get('LOCALAPPDATA',str(home/'AppData/Local'))) if home==Path.home() else home/'AppData/Local'
        target=base/'Programs'/'DockTwoo';relative=Path('DockTwoo.exe')
    elif system=='Linux':
        target=home/'.local/opt/DockTwoo';relative=Path('DockTwoo')
    else:raise RuntimeError('Unsupported installation platform.')
    if not (source/relative).is_file():raise ValueError('The native application bundle is missing its executable.')
    target.parent.mkdir(parents=True,exist_ok=True)
    if source!=target:
        # Stage first; preserve the working installation if copying fails.
        with tempfile.TemporaryDirectory(prefix='.dock-install-',dir=target.parent) as folder:
            staged=Path(folder)/target.name
            shutil.copytree(source,staged,symlinks=True)
            previous=Path(folder)/'previous'
            if target.exists():target.rename(previous)
            try:staged.rename(target)
            except Exception:
                if previous.exists():previous.rename(target)
                raise
    executable=target/relative
    command=[str(executable)]
    if system=='Linux':
        entry=home/'.local/share/applications'/f'{IDENTIFIER}.desktop'
        entry.parent.mkdir(parents=True,exist_ok=True);entry.write_text(desktop_entry(command))
    elif system=='Windows':
        # Use a Start menu shortcut, with no administrator or registry install.
        programs=home/'AppData/Roaming/Microsoft/Windows/Start Menu/Programs'
        programs.mkdir(parents=True,exist_ok=True)
        shortcut=programs/'Dock T(w)oo.lnk'
        env=dict(os.environ,DOCK_SHORTCUT=str(shortcut),DOCK_EXECUTABLE=str(executable))
        subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
            '$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:DOCK_SHORTCUT);'
            '$s.TargetPath=$env:DOCK_EXECUTABLE;$s.WorkingDirectory=[IO.Path]::GetDirectoryName($env:DOCK_EXECUTABLE);$s.Save()'],env=env,check=True,timeout=15)
    StartupManager(home=home,system=system,command=command).set_enabled(autostart)
    config_dir=home/'.dock_twoo';config_dir.mkdir(parents=True,exist_ok=True)
    (config_dir/'installation.json').write_text(json.dumps({'executable':str(executable),'bundle':str(target)}))
    config_file=config_dir/'config.json'
    config=json.loads(config_file.read_text()) if config_file.exists() else {}
    config['start_on_boot']=autostart
    temporary=config_file.with_suffix('.tmp');temporary.write_text(json.dumps(config,indent=2));temporary.replace(config_file)
    if start:
        if system=='Darwin':subprocess.run(['open',str(target)],check=True)
        else:subprocess.Popen(command,cwd=target,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=system!='Windows')
    return target


def main(argv=None):
    parser=argparse.ArgumentParser(description='Install a built DockTwoo bundle for this user.')
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--no-autostart',action='store_true')
    parser.add_argument('--no-start',action='store_true')
    args=parser.parse_args(argv)
    print('Installed:',install_bundle(args.bundle,autostart=not args.no_autostart,start=not args.no_start))
    return 0

if __name__=='__main__':raise SystemExit(main())
