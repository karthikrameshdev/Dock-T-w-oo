"""Validated local tools used by the cloud agent; never execute generated code."""
from __future__ import annotations
import csv
from datetime import datetime
import fnmatch
import io
import json
import os
from pathlib import Path
import re
import threading
import urllib.parse
import webbrowser
from dock_twoo.brain.animation import ACTIONS


def tool(name,description,properties=None,required=None):
    return {'type':'function','function':{'name':name,'description':description,'parameters':{
        'type':'object','properties':properties or {},'required':required or [],'additionalProperties':False}}}
S={'type':'string'};I={'type':'integer'}
TOOLS=[
 tool('list_files','List a folder with pagination. Read all returned pages before claiming a complete folder summary.',{'path':S,'offset':I,'recursive':{'type':'boolean'}},['path']),
 tool('search_files','Find matching filenames beneath a specific folder; supports glob patterns.',{'path':S,'pattern':S,'offset':I},['path','pattern']),
 tool('read_file','Read local text, PDF, DOCX or HTML. Continue at next_offset until done; image bytes are never sent to cloud.',{'path':S,'offset':I},['path']),
 tool('write_file','Create a new UTF-8 document. Existing files are never overwritten.',{'path':S,'text':S},['path','text']),
 tool('open_app','Open an installed app. For open-and-type requests supply text in this same call; supported editors get a new scratch document.',{'name':S,'text':S},['name']),
 tool('open_url','Open a user-requested HTTPS web page in the browser.',{'url':S},['url']),
 tool('observe_desktop','Get a fresh text accessibility tree with control ids; no screenshot is uploaded.'),
 tool('click','Click a control from the latest observation; observe again afterwards.',{'observation':S,'control':S},['observation','control']),
 tool('type_text','Enter literal text into the focused editable field, without submitting it.',{'observation':S,'text':S},['observation','text']),
 tool('press_key','Press a key or shortcut in the observed app, such as cmd+s, tab or enter.',{'observation':S,'key':S},['observation','key']),
 tool('scroll','Smoothly scroll the observed app. Positive pixels scroll downward.',{'observation':S,'pixels':I},['observation','pixels']),
 tool('drag','Drag between two observed control ids.',{'observation':S,'source':S,'target':S},['observation','source','target']),
 tool('get_selected_text','Read existing selected text without changing the selection.'),
 tool('describe_image','Generate a local ONNX caption and local OCR for an image file. Returns text only.',{'path':S},['path']),
 tool('describe_active_window','Locally caption and OCR the active window. Only text is returned to the model.'),
 tool('system_status','Read the current local time, OS, and battery status.'),
 tool('character_action','Play a local character gesture or move to a corner using walk, run, jump, fly or roll.',{'action':{'type':'string','enum':sorted(ACTIONS)+['follow_cursor','stop_follow_cursor']},'destination':{'type':'string','enum':['top_left','top_right','bottom_left','bottom_right','center']}},['action']),
 tool('read_aloud','Immediately start local continuous reading of selected text, the active window, or supplied text.',{'source':{'type':'string','enum':['selected','window','text']},'text':S},['source']),
 tool('add_task','Record a work item in the persistent Tasks app. Repeated identical items on the same day are deduplicated.',{'title':S,'details':S,'date':S,'status':{'type':'string','enum':['todo','in_progress','done']}},['title']),
 tool('list_tasks','Query the work log by ISO date or date range; the final answer is also displayed in Tasks. Use current local date for today/yesterday and include the year for specific dates. Paginate before claiming a complete summary.',{'date':S,'start':S,'end':S,'query':S,'offset':I,'status':{'type':'string','enum':['todo','in_progress','done']}}),
 tool('update_task','Change a recorded task by its returned id.',{'id':S,'title':S,'details':S,'status':S,'day':S},['id']),
 tool('add_note','Create a note in the existing Notes application.',{'title':S,'body':S},['title','body']),
 tool('list_notes','Read existing Notes, optionally filtering by text.',{'query':S}),
 tool('keep_awake','Enable or disable prevention of idle display/system sleep. Manual locks remain possible.',{'enabled':{'type':'boolean'}},['enabled']),
 tool('open_dock_app','Open Dock Notes, Tasks, Vault, Dashboard, or its Settings/Control console.',{'app':{'type':'string','enum':['notes','tasks','vault','settings','brain','dashboard']}},['app']),
 tool('finish','Finish the task with the spoken answer and an appropriate reaction. Only claim actions confirmed by tool results.',
      {'text':S,'emotion':{'type':'string','enum':['neutral','happy','excited','curious','concerned','calm']},
       'gesture':{'type':'string','enum':['none','nod','wave','handshake','celebrate','whistle','think','read']},
       'delivery':{'type':'string','enum':['speak','sing']}},['text'])]
SCHEMAS={t['function']['name']:t['function']['parameters'] for t in TOOLS}


def validate_arguments(name,args):
    if name not in SCHEMAS:raise ValueError('Unknown tool: '+name)
    schema=SCHEMAS[name]
    if not isinstance(args,dict) or any(k not in schema['properties'] for k in args):raise ValueError('Invalid tool arguments.')
    if any(k not in args for k in schema['required']):raise ValueError('A required tool argument is missing.')
    for key,value in args.items():
        rule=schema['properties'][key];kind=rule['type']
        if (kind=='string' and not isinstance(value,str)) or (kind=='integer' and type(value)!=int) or (kind=='boolean' and type(value)!=bool):raise ValueError('Incorrect argument type: '+key)
        if 'enum' in rule and value not in rule['enum']:raise ValueError('Unsupported value: '+key)
    return args


def allowed_file(value):
    path=Path(value).expanduser().resolve()
    if any(part in ('.ssh','.gnupg','.aws') for part in path.parts) or path.name == '.env' or path.name.startswith('.env.') or path.name in ('cloud-credentials.key','cloud-credentials.enc') or path.suffix.lower() in ('.pem','.key'):
        raise PermissionError('Credential and private key files are excluded from model context.')
    return path


class LocalTools:
    def __init__(self,manager=None,driver=None):
        from dock_twoo.brain.desktop_driver import DesktopDriver
        self.manager=manager;self.driver=driver or DesktopDriver()

    def on_main(self, callback, cancel):
        """Wait for the GUI action to run and propagate its actual error."""
        ready = threading.Event()
        outcome = {}
        def invoke():
            try:
                if cancel.is_set():raise InterruptedError('Request stopped.')
                outcome['result'] = callback()
            except Exception as exc:
                outcome['error'] = exc
            finally:
                ready.set()
        self.manager.run_on_main_thread(invoke)
        for _ in range(100):
            if cancel.is_set():raise InterruptedError('Request stopped.')
            if ready.wait(.05):
                if 'error' in outcome:raise outcome['error']
                return outcome.get('result')
        cancel.set()
        raise RuntimeError('The application did not accept the action in time.')

    def desktop_pid(self,cancel):
        def resolve():
            from AppKit import NSWorkspace
            current=NSWorkspace.sharedWorkspace().frontmostApplication()
            pid=int(current.processIdentifier()) if current else None
            if pid is not None and pid!=os.getpid():return pid
            # Brain's overlay/drawer can be foreground. Retain the external
            # document beneath it; never introspect Qt WebEngine on its worker.
            backend=getattr(getattr(self.manager,'reader',None),'backend',None)
            target=backend.remember_frontmost() if backend else None
            if target and target.pid!=os.getpid():return target.pid
            raise RuntimeError('Open or focus the target application first. For open-and-type requests use open_app with both name and text.')
        return self.on_main(resolve,cancel)

    def execute(self,name,args,cancel):
        validate_arguments(name,args)
        if cancel.is_set():raise InterruptedError('Request stopped.')
        if name in ('list_files','search_files'):
            root=allowed_file(args['path'])
            if not root.is_dir():raise ValueError('The requested folder does not exist.')
            offset=max(0,args.get('offset',0));items=[];matched=0;scanned=0
            recursive=name=='search_files' or args.get('recursive',False)
            iterator=os.walk(root) if recursive else [(str(root),[],sorted(p.name for p in root.iterdir()))]
            stopped=False
            for folder,dirs,files in iterator:
                dirs[:]=sorted(d for d in dirs if d not in ('.git','node_modules','.venv','.ssh','.aws','.gnupg'))
                for entry in sorted(files):
                    if cancel.is_set():raise InterruptedError('Request stopped.')
                    scanned+=1
                    if scanned>100000:raise RuntimeError('Search is too broad. Choose a more specific folder.')
                    path=Path(folder)/entry
                    try:allowed_file(str(path))
                    except PermissionError:continue
                    if name=='search_files' and not fnmatch.fnmatch(entry,args['pattern']):continue
                    if matched>=offset:
                        if len(items)==100:stopped=True;break
                        items.append({'path':str(path),'directory':path.is_dir(),'bytes':path.stat().st_size})
                    matched+=1
                if stopped:break
            return {'items':items,'next_offset':offset+len(items) if stopped else None,'complete':not stopped}
        if name=='read_file':
            path=allowed_file(args['path'])
            if not path.is_file():raise ValueError('The requested file does not exist.')
            if path.stat().st_size>32*1024*1024:raise ValueError('This file is larger than the 32 MB document limit.')
            suffix=path.suffix.lower()
            if suffix=='.pdf':
                from pypdf import PdfReader
                text='\n'.join(page.extract_text() or '' for page in PdfReader(path).pages)
            elif suffix=='.docx':
                from docx import Document
                doc=Document(path);text='\n'.join(p.text for p in doc.paragraphs)
                text+='\n'+'\n'.join(' | '.join(cell.text for cell in row.cells) for table in doc.tables for row in table.rows)
            elif suffix in ('.png','.jpg','.jpeg','.webp','.gif','.bmp'):
                raise ValueError('Use describe_image for image files.')
            else:
                raw=path.read_bytes()
                if b'\0' in raw[:4096]:raise ValueError('This binary file format is not supported as text.')
                text=raw.decode('utf-8-sig',errors='replace')
                if suffix in ('.html','.htm'):
                    from html.parser import HTMLParser
                    class Plain(HTMLParser):
                        def __init__(self):super().__init__();self.parts=[];self.skip=0
                        def handle_starttag(self,tag,attrs):self.skip+=tag in ('script','style')
                        def handle_endtag(self,tag):self.skip=max(0,self.skip-(tag in ('script','style')))
                        def handle_data(self,data):
                            if not self.skip:self.parts.append(data)
                    parser=Plain();parser.feed(text);text=' '.join(parser.parts)
            offset=max(0,args.get('offset',0));end=offset+16000
            return {'path':str(path),'text':text[offset:end],'total_characters':len(text),'next_offset':end if end<len(text) else None,'untrusted_content':True}
        if name=='write_file':
            path=allowed_file(args['path']);path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('x',encoding='utf-8') as target:target.write(args['text'])
            return {'created':str(path),'verified':path.read_text()==args['text']}
        if name in ('add_task','list_tasks','update_task','add_note','list_notes'):
            from dock_twoo.tasks import TaskStore,NotesService
            root=self.manager.store.data_dir.parent if self.manager else None
            if name.endswith('task') or name=='list_tasks':
                store=TaskStore(root/'tasks' if root else None)
                if name=='add_task':return store.add(**args)
                if name=='update_task':return store.update(**args)
                return store.list(**args)
            notes=NotesService(root/'notes' if root else None)
            result=notes.add(**args) if name=='add_note' else notes.list(**args)
            if self.manager and name=='add_note':self.manager.app_data_changed.emit('notes')
            return result
        if name=='keep_awake':
            from dock_twoo.keep_awake import get_keep_awake
            return get_keep_awake().set_enabled(args['enabled'])
        if name=='open_dock_app':
            if self.manager is None:raise RuntimeError('The Dock app is not running.')
            self.on_main(lambda:self.manager.app_open_requested.emit(args['app']),cancel)
            return {'requested_app':args['app']}
        if name=='open_app':
            target=args['name'].lower().strip()
            if target in ('settings','control','dock settings','brain settings','notes','tasks','vault','dashboard'):
                return self.execute('open_dock_app',{'app':'settings' if target in ('settings','control','dock settings','brain settings') else target},cancel)
            if target in ('mac settings','macos settings','system settings'):args={**args,'name':'System Settings'}
            if target=='windows settings':
                import platform
                if platform.system()!='Windows':raise RuntimeError('Windows Settings is available on a Windows computer. This computer runs '+platform.system()+'.')
                os.startfile('ms-settings:');return {'opened':'Windows Settings'}
            from dock_twoo.brain.computer_actions import run_desktop_request
            result=run_desktop_request(args['name'],args.get('text'))
            if not result:raise RuntimeError(result.message)
            return {'result':result.message,'verified':True}
        if name=='open_url':
            url=args['url'];address=urllib.parse.urlsplit(url)
            if address.scheme!='https' or not address.hostname or address.username or address.password:raise ValueError('Use a public HTTPS URL without embedded credentials.')
            if not webbrowser.open(url):raise RuntimeError('The browser could not open the URL.')
            return {'opened':url,'page_loaded_verified':False}
        if self.manager and hasattr(self.manager,'run_on_main_thread') and name in ('observe_desktop','click','type_text','press_key','scroll','drag','get_selected_text'):
            self.driver.frontmost_pid=lambda:self.desktop_pid(cancel)
        if name=='observe_desktop':return self.driver.observe()
        if name=='click':return self.driver.click(**args)
        if name=='type_text':return self.driver.type_text(**args)
        if name=='press_key':return self.driver.key(**args)
        if name=='scroll':return self.driver.scroll(**args,cancel=cancel)
        if name=='drag':return self.driver.drag(**args,cancel=cancel)
        if name=='get_selected_text':return self.driver.selected_text()
        if name=='describe_image':
            from dock_twoo.brain.local_vision import describe_image
            return describe_image(allowed_file(args['path']),cancel)
        if name=='describe_active_window':
            from dock_twoo.brain.local_vision import describe_active_window
            return describe_active_window(cancel)
        if name=='system_status':
            from dock_twoo.brain.providers import get_system_summary
            return {'time':datetime.now().astimezone().isoformat(),'system':get_system_summary()}
        if name in ('read_aloud','character_action'):
            if self.manager is None:raise RuntimeError('The desktop application is not running.')
            if name=='read_aloud':
                if args['source']=='text' and not args.get('text','').strip():raise ValueError('Supply the text to read.')
                self.on_main(lambda:self.manager._read_text_now(args['text']) if args['source']=='text' else self.manager._start_reading_now(args['source']),cancel)
                return {'started_reading':args['source']}
            action=args['action']
            from dock_twoo.brain.animation import ACTIONS
            if action=='follow_cursor':
                self.on_main(lambda:self.manager.companion.set_follow_cursor(True),cancel)
            elif action=='stop_follow_cursor':
                self.on_main(lambda:self.manager.companion.set_follow_cursor(False),cancel)
            elif args.get('destination'):
                if args['destination'] not in ('top_left','top_right','bottom_left','bottom_right','center'):raise ValueError('Unknown destination.')
                if action not in ('walk','run','jump','fly','roll'):raise ValueError('Choose walk, run, jump, fly or roll for travel.')
                self.on_main(lambda:self.manager.companion.travel_to_corner(args['destination'],style=action),cancel)
            elif action in ACTIONS:self.on_main(lambda:self.manager.companion.play_action(action),cancel)
            else:raise ValueError('Unknown animation action.')
            return {'started_action':action}
        raise ValueError('This tool cannot be executed directly.')
