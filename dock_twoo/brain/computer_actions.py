"""Literal local app activation and text insertion with explicit results."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import platform
import plistlib
import re
import subprocess
import time


@dataclass
class DesktopRequest:
    app: str
    text: str | None = None
    file_path: str | None = None


@dataclass
class MediaCommand:
    action: str  # 'volume_up', 'volume_down', 'set_volume', 'mute', 'unmute', 'play_pause', 'play', 'pause', 'next_track', 'previous_track'
    app: str | None = None
    value: float | int | None = None


@dataclass
class ActionResult:
    success: bool
    message: str
    def __bool__(self):return self.success


def normalize_request(text):
    text=re.sub(r"^\s*(?:(?:hey|hello|hi)\s+)?(?:brain|buddy)[,.:!\s]*",'',text,flags=re.I).strip()
    return re.sub(r"^(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?",'',text,flags=re.I).strip()


def parse_desktop_request(text):
    text=normalize_request(text)

    # 1. "open <path> in <app>" or "play <path> in <app>" or "open <path> with <app>"
    match = re.fullmatch(r'(?:open|play|launch)\s+([\'"].+?[\'"]|[^\s]+(?:\.[a-zA-Z0-9]+|\b))\s+(?:in|with)\s+(.+?)[.!]?', text, re.I)
    if match:
        raw_path, app = match.groups()
        raw_path = raw_path.strip('\'" ')
        app = re.sub(r'^the\s+', '', app.strip(), flags=re.I)
        app = re.sub(r'\s+(?:app|application)$', '', app, flags=re.I).strip()
        if app and raw_path:
            return DesktopRequest(app=app, file_path=raw_path)

    # 2. "open <app> and (open|play) [a/the]? [video/file/movie/document]? (from|at)? <path>"
    match = re.fullmatch(r'(?:open|launch|start)\s+(.+?)\s+(?:and(?:\s+then)?|then)\s+(?:open|play)(?:\s+(?:a|the)\s+(?:video|file|movie|document|audio|song|track))?(?:\s+(?:from|at))?\s+(.+?)[.!]?', text, re.I)
    if match:
        app, raw_path = match.groups()
        app = re.sub(r'^the\s+', '', app.strip(), flags=re.I)
        app = re.sub(r'\s+(?:app|application)$', '', app, flags=re.I).strip()
        raw_path = raw_path.strip('\'" ')
        if app and raw_path and not re.match(r'^(?:type|write|enter)\b', raw_path, re.I):
            return DesktopRequest(app=app, file_path=raw_path)

    # 3. "open <app> and (type|write|enter) <text>"
    match = re.fullmatch(r'(?:open|launch|start)\s+(.+?)\s+(?:and(?:\s+then)?|then)\s+(?:type|write|enter(?:\s+(?:the\s+)?message)?)\s+(.+)', text, re.I | re.S)
    if match:
        app, value = match.groups()
    else:
        match = re.fullmatch(r'(?:open|launch|start)\s+(.+?)[.!]?\s*', text, re.I)
        if not match:
            return None
        app, value = match.group(1), None

    app = re.sub(r'^the\s+', '', app.strip(), flags=re.I)
    app = re.sub(r'\s+(?:app|application)$', '', app, flags=re.I).strip()
    if not app or any(char in app for char in '/\\\n\r";'):
        return None
    if value:
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in '\"\'':
            value = value[1:-1]
    return DesktopRequest(app, value)


def parse_media_command(text: str) -> MediaCommand | None:
    text = normalize_request(text)
    clean = re.sub(r"^(hey\s+brain|brain)[,\s]*", "", text, flags=re.I).strip()

    # 1. Volume Up
    m = re.fullmatch(r'(?:(?:increase|turn\s+up|raise|boost)\s+(?:the\s+)?volume|volume\s+up)(?:\s+(?:on|in|for)\s+(.+?))?[.!]?', clean, re.I)
    if m:
        target = m.group(1).strip() if m.group(1) else None
        return MediaCommand('volume_up', app=target)

    # 2. Volume Down
    m = re.fullmatch(r'(?:(?:decrease|turn\s+down|lower|reduce)\s+(?:the\s+)?volume|volume\s+down)(?:\s+(?:on|in|for)\s+(.+?))?[.!]?', clean, re.I)
    if m:
        target = m.group(1).strip() if m.group(1) else None
        return MediaCommand('volume_down', app=target)

    # 3. Set Volume
    m = re.fullmatch(r'(?:set|change)\s+(?:the\s+)?volume\s+(?:to\s+)?(\d+)%?(?:\s+(?:on|in|for)\s+(.+?))?[.!]?', clean, re.I)
    if m:
        val = int(m.group(1))
        target = m.group(2).strip() if m.group(2) else None
        return MediaCommand('set_volume', app=target, value=val)

    # 4. Mute / Unmute
    m = re.fullmatch(r'mute(?:\s+(?:the\s+)?(?:sound|audio|volume|system))?(?:\s+(?:on|in|for)\s+(.+?))?[.!]?', clean, re.I)
    if m:
        target = m.group(1).strip() if m.group(1) else None
        return MediaCommand('mute', app=target)
    m = re.fullmatch(r'unmute(?:\s+(?:the\s+)?(?:sound|audio|volume|system))?(?:\s+(?:on|in|for)\s+(.+?))?[.!]?', clean, re.I)
    if m:
        target = m.group(1).strip() if m.group(1) else None
        return MediaCommand('unmute', app=target)

    # 5. Play / Pause / Resume
    m = re.fullmatch(r'(?:pause|stop)(?:\s+(?:the\s+)?(?:video|audio|music|playback|player|movie|track|song))?(?:\s+(?:on|in|for)\s+(.+?))?[.!]?', clean, re.I)
    if m:
        target = m.group(1).strip() if m.group(1) else None
        return MediaCommand('pause', app=target)
    m = re.fullmatch(r'(?:play|resume)(?:\s+(?:the\s+)?(?:video|audio|music|playback|player|movie|track|song))?(?:\s+(?:on|in|for)\s+(.+?))?[.!]?', clean, re.I)
    if m:
        target = m.group(1).strip() if m.group(1) else None
        return MediaCommand('play', app=target)
    m = re.fullmatch(r'(?:toggle\s+(?:play|playback)|play\s+or\s+pause|play\s+pause)(?:\s+(?:on|in|for)\s+(.+?))?[.!]?', clean, re.I)
    if m:
        target = m.group(1).strip() if m.group(1) else None
        return MediaCommand('play_pause', app=target)

    # 6. Next / Previous track
    if re.fullmatch(r'(?:next|skip)(?:\s+(?:track|song|video))?[.!]?', clean, re.I):
        return MediaCommand('next_track')
    if re.fullmatch(r'(?:previous|prev|back)(?:\s+(?:track|song|video))?[.!]?', clean, re.I):
        return MediaCommand('previous_track')

    return None


def open_file_in_app(app_name: str, file_path: str) -> ActionResult:
    """Open an existing file or media item with the specified application."""
    if platform.system() != 'Darwin':
        return ActionResult(False, 'Opening files in applications is currently supported on macOS.')
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        return ActionResult(False, f'I could not find the file at {file_path}.')

    clean_app = re.sub(r'\s+(?:app|application)$', '', app_name.strip(), flags=re.I)
    path, bundle = resolve_application(clean_app)

    # QuickTime Player integration
    if clean_app.lower() in ('quicktime', 'quicktime player') or (bundle and 'quicktime' in bundle.lower()):
        script = f'''
        tell application "QuickTime Player"
            activate
            open POSIX file "{str(p)}"
            delay 0.4
            if (count of documents) > 0 then
                play document 1
            end if
        end tell
        '''
        res = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=8)
        if res.returncode == 0:
            return ActionResult(True, f'Opened and playing {p.name} in QuickTime Player.')
        try:
            subprocess.run(['open', '-a', 'QuickTime Player', str(p)], check=True, timeout=8)
            return ActionResult(True, f'Opened {p.name} in QuickTime Player.')
        except Exception as exc:
            return ActionResult(False, f'Could not open {p.name} in QuickTime Player: {exc}')

    app_target = str(path) if path else clean_app
    try:
        subprocess.run(['open', '-a', app_target, str(p)], check=True, timeout=8)
        return ActionResult(True, f'Opened {p.name} in {clean_app}.')
    except Exception as exc:
        return ActionResult(False, f'Could not open {p.name} in {clean_app}: {exc}')


def control_media(action: str, target_app: str | None = None, value: float | int | None = None) -> ActionResult:
    """Control audio volume, mute, and playback for applications or system audio."""
    if platform.system() != 'Darwin':
        return ActionResult(False, 'Media and volume controls are currently supported on macOS.')

    app_lower = (target_app or '').lower().strip()
    is_qt = 'quicktime' in app_lower
    is_spotify = 'spotify' in app_lower
    is_music = app_lower in ('music', 'itunes', 'apple music')
    is_system = app_lower in ('system', 'mac', 'macos', 'speaker', 'speakers', 'master')

    # Auto-detect running QuickTime Player with open documents if no target was specified
    if not (is_qt or is_spotify or is_music or is_system):
        try:
            qt_check = subprocess.run(
                ['osascript', '-e', 'tell application "System Events" to return (name of processes) contains "QuickTime Player"'],
                capture_output=True, text=True, timeout=2,
            )
            if qt_check.stdout.strip() == 'true':
                qt_docs = subprocess.run(
                    ['osascript', '-e', 'tell application "QuickTime Player" to return count of documents'],
                    capture_output=True, text=True, timeout=2,
                )
                if int(qt_docs.stdout.strip() or 0) > 0:
                    is_qt = True
        except Exception:
            pass

    # QuickTime Player controls
    if is_qt:
        try:
            if action == 'volume_up':
                script = '''
                tell application "QuickTime Player"
                    if (count of documents) > 0 then
                        set cur to audio volume of document 1
                        set nxt to cur + 0.1
                        if nxt > 1.0 then set nxt to 1.0
                        set audio volume of document 1 to nxt
                        return round (nxt * 100)
                    else
                        error "No open video or audio in QuickTime Player."
                    end if
                end tell
                '''
                out = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=4)
                if out.returncode == 0:
                    return ActionResult(True, f"QuickTime Player volume increased to {out.stdout.strip()}%.")
            elif action == 'volume_down':
                script = '''
                tell application "QuickTime Player"
                    if (count of documents) > 0 then
                        set cur to audio volume of document 1
                        set nxt to cur - 0.1
                        if nxt < 0.0 then set nxt to 0.0
                        set audio volume of document 1 to nxt
                        return round (nxt * 100)
                    else
                        error "No open video or audio in QuickTime Player."
                    end if
                end tell
                '''
                out = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=4)
                if out.returncode == 0:
                    return ActionResult(True, f"QuickTime Player volume decreased to {out.stdout.strip()}%.")
            elif action == 'set_volume':
                v = max(0.0, min(1.0, (float(value) / 100.0) if value is not None else 0.5))
                script = f'''
                tell application "QuickTime Player"
                    if (count of documents) > 0 then
                        set audio volume of document 1 to {v}
                        return round ({v} * 100)
                    else
                        error "No open video or audio in QuickTime Player."
                    end if
                end tell
                '''
                out = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=4)
                if out.returncode == 0:
                    return ActionResult(True, f"QuickTime Player volume set to {out.stdout.strip()}%.")
            elif action in ('play_pause', 'play', 'pause'):
                branch = (
                    'if playing of document 1 then pause document 1 return "Paused" else play document 1 return "Playing" end if'
                    if action == 'play_pause'
                    else 'pause document 1 return "Paused"'
                    if action == 'pause'
                    else 'play document 1 return "Playing"'
                )
                script = f'''
                tell application "QuickTime Player"
                    if (count of documents) > 0 then
                        {branch}
                    else
                        error "No open video or audio in QuickTime Player."
                    end if
                end tell
                '''
                out = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=4)
                if out.returncode == 0:
                    return ActionResult(True, f"{out.stdout.strip()} QuickTime Player.")
        except Exception:
            pass

    # Spotify controls
    if is_spotify:
        try:
            if action == 'volume_up':
                subprocess.run(['osascript', '-e', 'tell application "Spotify" to set sound volume to (sound volume + 10)'], capture_output=True, text=True, timeout=3)
                return ActionResult(True, "Spotify volume increased.")
            elif action == 'volume_down':
                subprocess.run(['osascript', '-e', 'tell application "Spotify" to set sound volume to (sound volume - 10)'], capture_output=True, text=True, timeout=3)
                return ActionResult(True, "Spotify volume decreased.")
            elif action == 'play_pause':
                subprocess.run(['osascript', '-e', 'tell application "Spotify" to playpause'], capture_output=True, text=True, timeout=3)
                return ActionResult(True, "Toggled Spotify playback.")
            elif action == 'play':
                subprocess.run(['osascript', '-e', 'tell application "Spotify" to play'], capture_output=True, text=True, timeout=3)
                return ActionResult(True, "Playing Spotify.")
            elif action == 'pause':
                subprocess.run(['osascript', '-e', 'tell application "Spotify" to pause'], capture_output=True, text=True, timeout=3)
                return ActionResult(True, "Paused Spotify.")
        except Exception:
            pass

    # Music controls
    if is_music:
        try:
            if action == 'volume_up':
                subprocess.run(['osascript', '-e', 'tell application "Music" to set sound volume to (sound volume + 10)'], capture_output=True, text=True, timeout=3)
                return ActionResult(True, "Music volume increased.")
            elif action == 'volume_down':
                subprocess.run(['osascript', '-e', 'tell application "Music" to set sound volume to (sound volume - 10)'], capture_output=True, text=True, timeout=3)
                return ActionResult(True, "Music volume decreased.")
            elif action in ('play_pause', 'play', 'pause'):
                cmd = 'playpause' if action == 'play_pause' else action
                subprocess.run(['osascript', '-e', f'tell application "Music" to {cmd}'], capture_output=True, text=True, timeout=3)
                return ActionResult(True, f"{action.replace('_', ' ').capitalize()} Music.")
        except Exception:
            pass

    # System audio controls (fallback or default)
    try:
        if action == 'volume_up':
            out = subprocess.run(['osascript', '-e', '''
            set cur to output volume of (get volume settings)
            set nxt to cur + 10
            if nxt > 100 then set nxt to 100
            set volume output volume nxt
            return nxt
            '''], capture_output=True, text=True, timeout=3)
            return ActionResult(True, f"Volume increased to {out.stdout.strip()}%.")
        elif action == 'volume_down':
            out = subprocess.run(['osascript', '-e', '''
            set cur to output volume of (get volume settings)
            set nxt to cur - 10
            if nxt < 0 then set nxt to 0
            set volume output volume nxt
            return nxt
            '''], capture_output=True, text=True, timeout=3)
            return ActionResult(True, f"Volume decreased to {out.stdout.strip()}%.")
        elif action == 'set_volume':
            val = max(0, min(100, int(value if value is not None else 50)))
            subprocess.run(['osascript', '-e', f'set volume output volume {val}'], capture_output=True, text=True, timeout=3)
            return ActionResult(True, f"Volume set to {val}%.")
        elif action == 'mute':
            subprocess.run(['osascript', '-e', 'set volume output muted true'], capture_output=True, text=True, timeout=3)
            return ActionResult(True, "Audio muted.")
        elif action == 'unmute':
            subprocess.run(['osascript', '-e', 'set volume output muted false'], capture_output=True, text=True, timeout=3)
            return ActionResult(True, "Audio unmuted.")
        elif action in ('play_pause', 'pause', 'play'):
            return ActionResult(True, "Playback toggled.")
    except Exception as exc:
        return ActionResult(False, f"Could not adjust audio or media: {exc}")

    return ActionResult(False, f"Unsupported action {action}.")


def resolve_application(name):
    aliases={'visual studio code':'code','vscode':'code','cursor editor':'cursor','quicktime':'QuickTime Player','quicktime player':'QuickTime Player'}
    wanted=aliases.get(name.casefold(),name.casefold())
    for folder in (Path('/Applications'),Path.home()/'Applications',Path('/System/Applications'),Path('/System/Applications/Utilities')):
        if not folder.exists():continue
        for path in folder.glob('*.app'):
            try:
                info=plistlib.loads((path/'Contents/Info.plist').read_bytes())
                names={path.stem.casefold(),str(info.get('CFBundleName','')).casefold(),str(info.get('CFBundleDisplayName','')).casefold()}
                if wanted in names:return path,info.get('CFBundleIdentifier')
            except (OSError,ValueError):continue
    return None,None


def run_desktop_request(app_name, text=None, file_path=None):
    if file_path:
        return open_file_in_app(app_name, file_path)
    if platform.system()!='Darwin':
        return ActionResult(False,'Opening and typing into applications is currently supported on macOS.')
    path,bundle=resolve_application(app_name)
    if not path or not bundle:return ActionResult(False,f'I could not find an installed application named {app_name}.')
    try:
        import ApplicationServices as AX
        import AppKit
        import Quartz
        if text is not None and path.stem.casefold() in ('cursor','visual studio code','code'):
            # The editor's supported stdin integration creates a new scratch
            # document. Cursor 3's default launch surface is Agents, where
            # Command-N and even the File menu can target a chat instead.
            binary=path/'Contents/Resources/app/bin'/('cursor' if path.stem.casefold()=='cursor' else 'code')
            if binary.is_file():
                subprocess.run([str(binary),'--reuse-window','--classic','-'],input=text,text=True,
                               check=True,capture_output=True,timeout=10)
                if not AX.AXIsProcessTrusted():
                    return ActionResult(False,f'{path.stem} received your text in a new scratch document, but Accessibility permission is needed to verify the editor contents.')
                AX.AXUIElementSetMessagingTimeout(AX.AXUIElementCreateSystemWide(),.5)
                def attr(element,key):
                    if element is None:return None
                    error,value=AX.AXUIElementCopyAttributeValue(element,key,None)
                    return value if error==0 else None
                deadline=time.monotonic()+8
                ide_opened=False
                while time.monotonic()<deadline:
                    apps=AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle)
                    for app in apps:
                        application=AX.AXUIElementCreateApplication(app.processIdentifier())
                        AX.AXUIElementSetAttributeValue(application,'AXManualAccessibility',True)
                        AX.AXUIElementSetAttributeValue(application,'AXEnhancedUserInterface',True)
                        focused=attr(application,'AXFocusedUIElement')
                        if 'editor' in str(attr(focused,'AXDescription') or '').casefold() and text in str(attr(focused,'AXValue') or ''):
                            return ActionResult(True,f'Opened {path.stem} and verified your text in a new scratch document.')
                        if not ide_opened:
                            window=attr(application,'AXFocusedWindow')
                            pending=[window] if window else []
                            scanned=0
                            scan_deadline=time.monotonic()+2
                            while pending and scanned<400 and time.monotonic()<scan_deadline:
                                node=pending.pop(0);scanned+=1
                                if attr(node,'AXRole')=='AXButton' and str(attr(node,'AXTitle') or attr(node,'AXDescription') or '').strip() in ('IDE','Open in IDE'):
                                    if AX.AXUIElementPerformAction(node,'AXPress')==0:
                                        ide_opened=True
                                        time.sleep(.8)
                                        subprocess.run([str(binary),'--reuse-window','--classic','-'],input=text,text=True,
                                                       check=True,capture_output=True,timeout=10)
                                        deadline=min(deadline+2,time.monotonic()+4)
                                    break
                                pending.extend(attr(node,'AXChildren') or [])
                    time.sleep(.2)
                return ActionResult(False,f'{path.stem} received a new scratch document, but its editor contents could not be verified. Please check the editor.')
        subprocess.run(['open','-a',str(path)],check=True,timeout=5,capture_output=True)
        if text is None:return ActionResult(True,f'Opened {path.stem}.')
        if not AX.AXIsProcessTrusted():
            return ActionResult(False,f'{path.stem} opened, but macOS Accessibility permission is needed to type into it. Enable Dock or its Python host under Privacy & Security, Accessibility.')
        def get(element,attribute):
            if element is None:return None
            error,value=AX.AXUIElementCopyAttributeValue(element,attribute,None)
            return value if error==0 else None
        system=AX.AXUIElementCreateSystemWide()
        AX.AXUIElementSetMessagingTimeout(system, .5)
        def frontmost_pid():
            # NSWorkspace caches foreground state on worker threads without an
            # AppKit run loop. Ask WindowServer's accessibility tree each time.
            focused_app=get(system,'AXFocusedApplication')
            if focused_app is None:
                app=AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
                return int(app.processIdentifier()) if app is not None else None
            error,pid=AX.AXUIElementGetPid(focused_app,None)
            return pid if error==0 else None
        deadline=time.monotonic()+6
        target=None
        while time.monotonic()<deadline:
            applications=AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle)
            target=applications[0] if applications else None
            if target and frontmost_pid()==target.processIdentifier():break
            time.sleep(.1)
        if not target or frontmost_pid()!=target.processIdentifier():
            return ActionResult(False,f'{path.stem} opened, but did not become active. I did not type into another application.')
        pid=target.processIdentifier()
        def key(code,flags=0):
            for pressed in (True,False):
                event=Quartz.CGEventCreateKeyboardEvent(None,code,pressed)
                Quartz.CGEventSetFlags(event,flags)
                Quartz.CGEventPostToPid(pid,event)
        # Use a new unsaved document in editors; never overwrite the user's file.
        application=AX.AXUIElementCreateApplication(pid)
        AX.AXUIElementSetAttributeValue(application,'AXManualAccessibility',True)
        AX.AXUIElementSetAttributeValue(application,'AXEnhancedUserInterface',True)
        previous_focus=get(application,'AXFocusedUIElement')
        previous_description=str(get(previous_focus,'AXDescription') or '')
        def find(root, predicate, limit=600):
            pending=[root]
            visited=0
            until=time.monotonic()+3
            while pending and visited<limit and time.monotonic()<until:
                node=pending.pop(0);visited+=1
                if predicate(node):return node
                pending.extend(get(node,'AXChildren') or [])
            return None
        if path.stem.casefold() in ('cursor','visual studio code','code'):
            # Cursor 3 binds Command-N to a new agent chat. Use the explicit
            # New Text File menu command, never an agent prompt or existing file.
            created=False
            menu_deadline=time.monotonic()+12
            while time.monotonic()<menu_deadline:
                bar=get(application,'AXMenuBar')
                file_menu=find(bar,lambda node:get(node,'AXTitle')=='File',50) if bar else None
                if file_menu:
                    AX.AXUIElementPerformAction(file_menu,'AXPress')
                    time.sleep(.15)
                    item=find(file_menu,lambda node:get(node,'AXTitle') in ('New Text File','New File'),200)
                    if item and AX.AXUIElementPerformAction(item,'AXPress')==0:
                        created=True;break
                    key(53) # Close a menu that cannot create a document.
                window=get(application,'AXFocusedWindow')
                ide=find(window,lambda node:get(node,'AXRole')=='AXButton' and
                         str(get(node,'AXTitle') or get(node,'AXDescription') or '').strip() in ('IDE','Open in IDE')) if window else None
                if ide:AX.AXUIElementPerformAction(ide,'AXPress');time.sleep(.7)
                else:time.sleep(.3)
            if not created:
                return ActionResult(False,f'{path.stem} opened, but I could not create a new text file. I did not type into its agent chat.')
        elif path.stem.casefold()=='textedit':
            key(45,Quartz.kCGEventFlagMaskCommand)
        focused=None
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if frontmost_pid()!=pid:
                return ActionResult(False,'The active application changed before typing. I stopped to avoid typing into the wrong place.')
            focused=get(application,'AXFocusedUIElement')
            description=str(get(focused,'AXDescription') or get(focused,'AXTitle') or '').casefold() if focused else ''
            editable=focused and (get(focused,'AXRole') in ('AXTextArea','AXTextField','AXComboBox') or 'editor' in description)
            is_code_editor=path.stem.casefold() in ('cursor','visual studio code','code')
            fresh_document=(not is_code_editor or ('editor' in description and 'untitled' in description
                            and description!=previous_description.casefold() and not str(get(focused,'AXValue') or '').strip()))
            if editable and fresh_document:break
            time.sleep(.1)
        if not focused or not editable or not fresh_document:
            return ActionResult(False,f'{path.stem} opened, but a new empty text editor was not confirmed. I did not modify an existing document.')
        error=AX.AXUIElementSetAttributeValue(focused,'AXSelectedText',text)
        if error!=0:
            # Unicode events are literal text, with no shell or AppleScript interpolation.
            for offset in range(0,len(text),16):
                if frontmost_pid()!=pid:
                    return ActionResult(False,'The active application changed while typing. I stopped the action.')
                chunk=text[offset:offset+16]
                for pressed in (True,False):
                    event=Quartz.CGEventCreateKeyboardEvent(None,0,pressed)
                    Quartz.CGEventKeyboardSetUnicodeString(event,len(chunk.encode('utf-16-le'))//2,chunk)
                    Quartz.CGEventPostToPid(pid,event)
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            value=get(focused,'AXValue')
            if value is not None and text in str(value):
                return ActionResult(True,f'Opened {path.stem} and typed your text into a new unsaved document.' if path.stem.casefold() in ('cursor','visual studio code','code','textedit') else f'Opened {path.stem} and typed your text.')
            time.sleep(.1)
        return ActionResult(False,f'{path.stem} opened and received the text input, but it did not expose enough accessibility text to verify it. Please check the editor.')
    except Exception as exc:
        return ActionResult(False,f'I could not complete the action in {app_name}: {type(exc).__name__}.')
