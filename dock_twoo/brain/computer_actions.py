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
    match=re.fullmatch(r'(?:open|launch|start)\s+(.+?)\s+(?:and(?:\s+then)?|then)\s+(?:type|write|enter(?:\s+(?:the\s+)?message)?)\s+(.+)',text,re.I|re.S)
    if match:app,value=match.groups()
    else:
        match=re.fullmatch(r'(?:open|launch)\s+(.+?)[.!]?\s*',text,re.I)
        if not match:return None
        app,value=match.group(1),None
    app=re.sub(r'^the\s+','',app.strip(),flags=re.I)
    app=re.sub(r'\s+(?:app|application)$','',app,flags=re.I).strip()
    if not app or any(char in app for char in '/\\\n\r";'):return None
    if value:
        value=value.strip()
        if len(value)>1 and value[0]==value[-1] and value[0] in '\"\'':value=value[1:-1]
    return DesktopRequest(app,value)


def resolve_application(name):
    aliases={'visual studio code':'code','vscode':'code','cursor editor':'cursor'}
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


def run_desktop_request(app_name,text=None):
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
                               check=True,capture_output=True,timeout=20)
                if not AX.AXIsProcessTrusted():
                    return ActionResult(False,f'{path.stem} received your text in a new scratch document, but Accessibility permission is needed to verify the editor contents.')
                AX.AXUIElementSetMessagingTimeout(AX.AXUIElementCreateSystemWide(),.5)
                def attr(element,key):
                    if element is None:return None
                    error,value=AX.AXUIElementCopyAttributeValue(element,key,None)
                    return value if error==0 else None
                deadline=time.monotonic()+10
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
                                                       check=True,capture_output=True,timeout=20)
                                        deadline=time.monotonic()+10
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
            if focused_app is None:return None
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
