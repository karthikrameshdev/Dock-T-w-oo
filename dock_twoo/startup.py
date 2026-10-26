"""Per-user login startup. Never installs a privileged or pre-login service."""
from __future__ import annotations
import json
import os
from pathlib import Path
import platform
import plistlib
import subprocess
import sys

IDENTIFIER = 'dev.karthikramesh.DockTwoo'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


def launch_command():
    if getattr(sys, 'frozen', False):return [sys.executable]
    record = Path.home()/'.dock_twoo'/'installation.json'
    if record.exists():
        executable = json.loads(record.read_text())['executable']
        if Path(executable).is_file():return [executable]
    # Editable/pip installations can also opt in before packaging.
    executable = Path(sys.executable)
    if os.name=='nt' and executable.with_name('pythonw.exe').is_file():
        executable=executable.with_name('pythonw.exe')
    return [str(executable), '-m', 'dock_twoo.main']


def desktop_entry(command):
    # Desktop Exec is not a shell. Quote each argv entry and escape field codes.
    def quote(value):
        value=str(value).replace('%','%%')
        for char in ('\\','"','`','$'):value=value.replace(char,'\\'+char)
        return '"'+value+'"'
    return ('[Desktop Entry]\nType=Application\nName=Dock T(w)oo\n'
            'Comment=Desktop voice assistant\nTerminal=false\n'
            'Exec='+' '.join(map(quote,command))+'\n'
            'Categories=Utility;\nX-GNOME-Autostart-enabled=true\n')


class StartupManager:
    def __init__(self, *, home=None, system=None, command=None):
        self.home=Path(home) if home is not None else Path.home()
        self.system=system or platform.system()
        self.command=command or launch_command()

    @property
    def path(self):
        if self.system=='Darwin':return self.home/'Library'/'LaunchAgents'/f'{IDENTIFIER}.plist'
        base=Path(os.environ.get('XDG_CONFIG_HOME',str(self.home/'.config'))) if self.home==Path.home() else self.home/'.config'
        return base/'autostart'/f'{IDENTIFIER}.desktop'

    def set_enabled(self, enabled):
        if type(enabled) is not bool:raise ValueError('Start on system boot must be true or false.')
        if self.system=='Windows':
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,RUN_KEY) as key:
                if enabled:
                    line=subprocess.list2cmdline(self.command)
                    if len(line)>260:raise ValueError('Install Dock in a shorter path before enabling startup (Windows Run limit: 260 characters).')
                    winreg.SetValueEx(key,IDENTIFIER,0,winreg.REG_SZ,line)
                else:
                    try:winreg.DeleteValue(key,IDENTIFIER)
                    except FileNotFoundError:pass
            return
        if self.system not in ('Darwin','Linux'):raise RuntimeError('Automatic startup is supported on macOS, Windows and Linux.')
        path=self.path
        if not enabled:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True,exist_ok=True)
        if self.system=='Darwin':
            data=plistlib.dumps({'Label':IDENTIFIER,'ProgramArguments':self.command,
                                'RunAtLoad':True,'ProcessType':'Interactive',
                                'LimitLoadToSessionType':'Aqua'})
        else:data=desktop_entry(self.command).encode()
        temporary=path.with_suffix('.tmp')
        temporary.write_bytes(data);temporary.chmod(0o600);temporary.replace(path)
        # Registration applies at next login. Do not bootstrap/bootout the
        # running process or make an intentional Quit immediately restart it.
