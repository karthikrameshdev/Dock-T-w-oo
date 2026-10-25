"""Local HTTP Web Console server for Dock T(w)oo configuration.

Provides REST API endpoints and serves the modern web settings interface.
"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from dock_twoo.brain.profiles import ProfileManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.config import ConfigManager, DockConfig


def _get_safe_profile_mgr() -> ProfileManager:
    from dock_twoo.brain.manager import BrainManager
    if BrainManager._instance is not None:
        return BrainManager._instance.profile_mgr
    return ProfileManager(BrainStore())


def _get_safe_brain_store() -> BrainStore:
    from dock_twoo.brain.manager import BrainManager
    if BrainManager._instance is not None:
        return BrainManager._instance.store
    return BrainStore()


def get_static_dir() -> Path:
    return Path(__file__).resolve().parent / "static"


class ConsoleHTTPServer(ThreadingHTTPServer):
    # Several console tabs, the native dashboard and the character renderer can
    # load together. The default five-connection backlog drops those bursts.
    request_queue_size = 64

    def __init__(self,*args,**kwargs):
        self.activity_store = None
        self.activity_store_lock = threading.Lock()
        super().__init__(*args,**kwargs)


class ConsoleRequestHandler(BaseHTTPRequestHandler):
    """Handles static files and REST API requests for Web Console."""

    config_manager: ConfigManager = None  # Injected by server

    def _set_headers(
        self,
        status: int = HTTPStatus.OK,
        content_type: str = "application/json",
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self._set_headers(HTTPStatus.NO_CONTENT)

    def _local_control(self, write=False):
        port=self.server.server_address[1]
        origin=self.headers.get('Origin')
        return (not origin or origin in (f'http://127.0.0.1:{port}',f'http://localhost:{port}')) and (not write or self.headers.get('X-Brain-Request')=='local')

    def _json(self, status, value):
        self._set_headers(status,'application/json')
        self.wfile.write(json.dumps(value).encode())

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == '/api/displays':
            if not self._local_control() or self.headers.get('X-Brain-Request') != 'local':
                self._json(403, {'error': 'Use the local application console.'})
                return
            self._json(200, getattr(self.config_manager, 'display_snapshot', {
                'mode': self.config_manager.config.display_mode,
                'display_ids': list(self.config_manager.config.display_ids), 'fallback': False, 'displays': []}))
            return
        if path in ('/api/activity','/api/usage') or path.startswith('/api/activity/'):
            if not self._local_control() or self.headers.get('X-Brain-Request') != 'local':
                self._json(403,{'error':'Use the local application controls.'});return
            try:
                from urllib.parse import parse_qs,urlsplit
                from dock_twoo.brain.activity import ActivityStore
                from dock_twoo.brain.manager import BrainManager
                manager=BrainManager._instance
                tracker=getattr(manager,'activity',None)
                if tracker is None:
                    with self.server.activity_store_lock:
                        root=self.config_manager.config.get_brain_dir()/'activity'
                        if self.server.activity_store is None or self.server.activity_store.root!=root:
                            self.server.activity_store=ActivityStore(root)
                        tracker=self.server.activity_store
                query=parse_qs(urlsplit(self.path).query)
                if path=='/api/activity':result=tracker.list(offset=query.get('offset',[0])[0])
                elif path=='/api/usage':
                    result=tracker.metrics(start=query.get('from',[None])[0],end=query.get('to',[None])[0],period=query.get('period',['month'])[0],profile_id=query.get('profile',[None])[0])
                    options={p['id']:p for p in result['profile_options']}
                    for profile in _get_safe_profile_mgr().get_profiles():options[profile['id']]={'id':profile['id'],'name':profile['name'],'historical':False}
                    result['profile_options']=list(options.values())
                    for row in result['profiles']:
                        if row['profile_id'] in options:row['name']=options[row['profile_id']]['name']
                else:result=tracker.detail(path.removeprefix('/api/activity/'))
                self._json(200,result)
            except (ValueError,TypeError) as exc:self._json(400,{'error':str(exc)})
            return
        if path in ('/api/brain/model','/api/tasks','/api/keep-awake'):
            if not self._local_control():
                self._json(HTTPStatus.FORBIDDEN,{'success':False,'error':'Use the local application console.'});return
            try:
                if path=='/api/brain/model':
                    pm=_get_safe_profile_mgr();self._json(200,{'model':pm.get_active_profile(),'profiles':pm.get_profiles(),**pm.get_provider_catalog()})
                elif path=='/api/tasks':
                    from urllib.parse import parse_qs,urlsplit
                    from dock_twoo.tasks import TaskStore
                    query=parse_qs(urlsplit(self.path).query)
                    filters={key:query[key][0] for key in ('date','start','end','query','status','offset') if key in query}
                    self._json(200,TaskStore(self.config_manager.config.get_storage_path()/'tasks').list(**filters))
                else:
                    from dock_twoo.keep_awake import get_keep_awake
                    self._json(200,get_keep_awake().status())
            except Exception as exc:self._json(400,{'success':False,'error':str(exc)})
            return


        if path == "/api/config":
            cfg_dict = self.config_manager.config.to_dict()
            self._set_headers(HTTPStatus.OK, "application/json")
            self.wfile.write(json.dumps(cfg_dict).encode("utf-8"))
            return

        if path == "/api/status":
            status_data = {
                "name": "Dock T(w)oo",
                "version": "0.1.0",
                "edge": self.config_manager.config.edge,
                "theme": self.config_manager.config.get_effective_theme(),
                "running": True,
            }
            self._set_headers(HTTPStatus.OK, "application/json")
            self.wfile.write(json.dumps(status_data).encode("utf-8"))
            return

        if path == "/api/storage":
            cfg = self.config_manager.config
            storage_root = cfg.get_storage_path()
            subdirs = {
                "notes": cfg.get_notes_dir(),
                "vault": cfg.get_vault_dir(),
                "models": cfg.get_models_dir(),
                "brain": cfg.get_brain_dir(),
                "tasks": storage_root / "tasks",
            }
            folder_info = {}
            total_files = 0
            total_bytes = 0
            for name, p in subdirs.items():
                count = 0
                bytes_val = 0
                if p.exists():
                    for f in p.rglob("*"):
                        if f.is_file():
                            count += 1
                            bytes_val += f.stat().st_size
                total_files += count
                total_bytes += bytes_val
                folder_info[name] = {
                    "path": str(p),
                    "file_count": count,
                    "size_mb": round(bytes_val / (1024 * 1024), 2),
                }

            storage_data = {
                "storage_path": str(storage_root),
                "total_files": total_files,
                "total_size_mb": round(total_bytes / (1024 * 1024), 2),
                "subsystems": folder_info,
            }
            self._set_headers(HTTPStatus.OK, "application/json")
            self.wfile.write(json.dumps(storage_data).encode("utf-8"))
            return

        if path == "/api/brain/providers":
            from dock_twoo.brain.providers import PRESETS, PROVIDER_CATALOG, ROLES
            self._set_headers(HTTPStatus.OK, "application/json")
            self.wfile.write(
                json.dumps({
                    "catalog": PROVIDER_CATALOG,
                    "presets": PRESETS,
                    "roles": list(ROLES),
                }).encode("utf-8")
            )
            return

        if path == "/api/brain/status":
            from dock_twoo.brain.manager import BrainManager
            if BrainManager._instance is not None:
                status_dict = BrainManager._instance.get_status()
            else:
                pm = _get_safe_profile_mgr()
                active = pm.get_active_profile()
                status_dict = {
                    "active_profile": active["name"] if active else "None",
                    "provider": active["provider"] if active else "none",
                    "model": active["model"] if active else "none",
                    "status": "idle",
                    "speech_enabled": True,
                    "wake_word_enabled": True,
                    "auto_listen": True,
                    "companion_visible": False,
                    "voice_input": {
                        "enabled": True,
                        "listening": False,
                        "error": "Brain voice listener has not initialized.",
                    },
                }
            origin = self.headers.get("Origin")
            port = self.server.server_address[1]
            if self.headers.get('X-Brain-Request') != 'local' or (origin and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}')):
                status_dict.pop('last_response', None)
                status_dict.pop('queue', None)
            if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                check = status_dict.get("voice_input", {}).get("wake_diagnostics", {}).get("voice_check")
                if check:
                    check["heard"] = []
            self._set_headers(HTTPStatus.OK, "application/json")
            self.wfile.write(json.dumps(status_dict).encode("utf-8"))
            return

        if path == "/api/brain/profiles":
            if not self._local_control():
                self._json(403,{"error":"Use the local application controls."});return
            pm = _get_safe_profile_mgr()
            self._set_headers(HTTPStatus.OK, "application/json")
            self.wfile.write(
                json.dumps({
                    "profiles": pm.get_profiles(),
                    "active": pm.get_active_profile(),
                    "catalog": pm.get_provider_catalog(),
                }).encode("utf-8")
            )
            return

        # Serve static files
        static_dir = get_static_dir()
        if path in ("/", "/index.html"):
            target_file = static_dir / "index.html"
        else:
            rel_path = path.lstrip("/")
            target_file = static_dir / rel_path

        if target_file.exists() and target_file.is_file():
            mime_type, _ = mimetypes.guess_type(str(target_file))
            mime_type = mime_type or "application/octet-stream"
            try:
                with open(target_file, "rb") as f:
                    content = f.read()
                self._set_headers(HTTPStatus.OK, mime_type)
                self.wfile.write(content)
                return
            except Exception as e:
                self._set_headers(HTTPStatus.INTERNAL_SERVER_ERROR, "text/plain")
                self.wfile.write(f"Error reading file: {e}".encode("utf-8"))
                return

        # Check in assets/icons
        if path.startswith("/icons/"):
            icon_name = path.replace("/icons/", "")
            from dock_twoo.icons import get_icons_dir
            icons_dir = get_icons_dir().resolve()
            icon_file = (icons_dir / icon_name).resolve()
            if icon_file.parent != icons_dir:
                self._json(404, {'error': 'Icon not found.'})
                return
            if icon_file.exists() and icon_file.is_file():
                with open(icon_file, "rb") as f:
                    content = f.read()
                self._set_headers(HTTPStatus.OK, "image/svg+xml")
                self.wfile.write(content)
                return

        self._set_headers(HTTPStatus.NOT_FOUND, "text/plain")
        self.wfile.write(b"404 Not Found")

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        if path in ('/api/brain/settings', '/api/brain/profile', '/api/brain/key', '/api/brain/activate-profile', '/api/brain/profile/delete', '/api/brain/profiles') and not self._local_control(write=True):
            self._json(403, {'success': False, 'error': 'Use the local application controls.'})
            return
        if path in ('/api/brain/model','/api/brain/model/test','/api/brain/stop','/api/tasks','/api/keep-awake','/api/brain/profiles','/api/brain/profile','/api/brain/activate-profile','/api/brain/profile/delete'):
            if not self._local_control(write=True):
                self._json(403,{'success':False,'error':'Use the local application controls.'});return
            try:
                length=int(self.headers.get('Content-Length',0))
                if length>32000:raise ValueError('Request is too large.')
                body=json.loads(self.rfile.read(length) or b'{}')
                if not isinstance(body,dict):raise ValueError('Supply a JSON object.')
                if path=='/api/brain/profiles':
                    self._json(200,{'success':True,'profile':_get_safe_profile_mgr().create_profile(body)})
                elif path=='/api/brain/profile':
                    self._json(200,{'success':True,'profile':_get_safe_profile_mgr().save_profile(body)})
                elif path=='/api/brain/activate-profile':
                    pm=_get_safe_profile_mgr();pm.activate_profile(body.get('profile_id',''))
                    self._json(200,{'success':True,'active':pm.get_active_profile()})
                elif path=='/api/brain/profile/delete':
                    pm=_get_safe_profile_mgr();pm.delete_profile(body.get('profile_id',''))
                    self._json(200,{'success':True,'active':pm.get_active_profile()})
                elif path=='/api/brain/model':
                    pm=_get_safe_profile_mgr();model=pm.save_profile(body)
                    self._json(200,{'success':True,'model':model})
                elif path=='/api/brain/model/test':
                    from dock_twoo.brain.cloud import CloudClient
                    from dock_twoo.brain.agent_tools import TOOLS
                    pm=_get_safe_profile_mgr();config=pm.get_active_profile()
                    if body.get('profile_id'):
                        config=next((p for p in pm.get_profiles() if p['id']==body['profile_id']),None)
                        if config is None:raise ValueError('Cloud profile not found.')
                    turn=CloudClient(config,pm.get_key(config['provider'],config.get('id'))).turn([{'role':'user','content':'Test connection. Use finish with text Ready.'}],[TOOLS[-1]])
                    self._json(200,{'success':True,'message':'Connection successful. '+('Tool calling verified.' if turn.calls else 'Text response verified; tool calling was not exercised.')})
                elif path=='/api/brain/stop':
                    from dock_twoo.brain.manager import BrainManager
                    if BrainManager._instance:BrainManager._instance.run_on_main_thread(BrainManager._instance.stop_talking)
                    self._json(200,{'success':True})
                elif path=='/api/tasks':
                    from dock_twoo.tasks import TaskStore
                    store=TaskStore(self.config_manager.config.get_storage_path()/'tasks')
                    task=store.update(**body) if 'id' in body else store.add(**body)
                    self._json(200,{'success':True,'task':task})
                else:
                    from dock_twoo.keep_awake import get_keep_awake
                    if type(body.get('enabled'))!=bool:raise ValueError('Supply enabled as true or false.')
                    self._json(200,{'success':True,**get_keep_awake().set_enabled(body['enabled'])})
            except Exception as exc:self._json(400,{'success':False,'error':str(exc)})
            return


        if path == "/api/brain/request":
            try:
                port = self.server.server_address[1]
                origin = self.headers.get('Origin')
                if self.headers.get('X-Brain-Request') != 'local' or (origin and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}')):
                    raise ValueError('Send requests from the local Brain console.')
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 16000:
                    raise ValueError('The request is empty or too long.')
                body = json.loads(self.rfile.read(length))
                text = body.get('text')
                if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                    raise ValueError('Enter a request of up to 2000 characters.')
                from dock_twoo.brain.manager import BrainManager
                bm = BrainManager._instance
                if bm is None:
                    raise RuntimeError('Start the desktop application before sending a request.')
                screen_id = body.get('screen_id')
                if screen_id is not None:
                    displays = getattr(self.config_manager, 'display_snapshot', {}).get('displays', [])
                    if not isinstance(screen_id, str) or not any(d['id'] == screen_id and d['selected'] for d in displays):
                        raise ValueError('Choose a connected display showing Dock T(w)oo.')
                if hasattr(bm,'submit_request'):
                    if screen_id is None:bm.submit_request(text.strip(),'console')
                    else:bm.submit_request(text.strip(),'console',screen_id)
                else:bm.turn_complete_requested.emit(text.strip())
                self._set_headers(HTTPStatus.ACCEPTED, 'application/json')
                self.wfile.write(b'{"success":true}')
            except Exception as exc:
                self._set_headers(HTTPStatus.BAD_REQUEST, 'application/json')
                self.wfile.write(json.dumps({'success':False,'error':str(exc)}).encode())
            return

        if path == "/api/config":
            # Existing configuration saves are same-origin; all display mutations
            # also require the local control header used by the console.
            if not self._local_control() or (self.headers.get('Origin') and not self._local_control(write=True)):
                self._json(403, {'success': False, 'error': 'Use the local application console.'})
                return
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                if not 0 < content_length <= 256000:
                    raise ValueError('Configuration request is empty or too large.')
                body = self.rfile.read(content_length).decode("utf-8")
                updates = json.loads(body)
                if not isinstance(updates, dict):
                    raise ValueError('Supply a JSON object.')
                if any(key in updates for key in ('display_mode','display_ids')) and not self._local_control(write=True):
                    self._json(403, {'success': False, 'error': 'Use the local application controls.'})
                    return

                updated = self.config_manager.update(updates)
                self._set_headers(HTTPStatus.OK, "application/json")
                self.wfile.write(
                    json.dumps({"success": True, "config": updated.to_dict()}).encode("utf-8")
                )
            except Exception as e:
                self._set_headers(HTTPStatus.BAD_REQUEST, "application/json")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        if path == "/api/reset":
            try:
                default_cfg = DockConfig()
                self.config_manager.update(default_cfg.to_dict())
                self._set_headers(HTTPStatus.OK, "application/json")
                self.wfile.write(
                    json.dumps({"success": True, "config": default_cfg.to_dict()}).encode("utf-8")
                )
            except Exception as e:
                self._set_headers(HTTPStatus.INTERNAL_SERVER_ERROR, "application/json")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        if path == "/api/brain/voice-check":
            try:
                if self.headers.get("X-Brain-Voice-Check") != "local":
                    raise RuntimeError("Start the microphone check from the local Brain console.")
                from dock_twoo.brain.manager import BrainManager
                bm = BrainManager._instance
                if bm is None:
                    raise RuntimeError("Brain has not initialized.")
                bm.listener.begin_voice_check()
                self._set_headers(HTTPStatus.OK, "application/json")
                self.wfile.write(json.dumps({"success": True, "seconds": 30}).encode("utf-8"))
            except Exception as exc:
                self._set_headers(HTTPStatus.BAD_REQUEST, "application/json")
                self.wfile.write(json.dumps({"success": False, "error": str(exc)}).encode("utf-8"))
            return

        if path == "/api/brain/enroll-owner":
            try:
                from dock_twoo.brain.manager import BrainManager
                bm = BrainManager._instance
                if bm is None:
                    raise RuntimeError("Start the Brain voice listener before enrolling your voice.")
                bm.enroll_owner_voice()
                self._set_headers(HTTPStatus.OK, "application/json")
                self.wfile.write(json.dumps({"success": True, "message": "Your voice is enrolled on this device."}).encode("utf-8"))
            except Exception as e:
                self._set_headers(HTTPStatus.BAD_REQUEST, "application/json")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        if path == "/api/brain/settings":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
                store = _get_safe_brain_store()
                if any(key in body for key in ('cloud_keys', 'cloud_model', 'cloud_profiles', 'profiles', 'active_profile')):
                    raise ValueError('Use Cloud Profiles to configure model profiles securely.')
                for key,low,high in (('agent_max_steps',1,12),('agent_token_budget',2000,64000),('agent_no_progress_turns',2,3),('agent_max_output_tokens',128,2048)):
                    if key in body and (type(body[key]) is not int or not low<=body[key]<=high):
                        raise ValueError(f'{key} must be an integer between {low} and {high}.')
                updated = store.update_settings(body)
                from dock_twoo.brain.manager import BrainManager
                if BrainManager._instance is not None:
                    bm = BrainManager._instance
                    bm.run_on_main_thread(lambda changes=dict(body): bm.apply_voice_settings(changes))
                    if "mascot_corner" in body:
                        bm.companion.travel_to_corner(body["mascot_corner"])
                    if "companion_visible" in body:
                        if body["companion_visible"]:
                            bm.show_mini_agent()
                        else:
                            bm.hide_mini_agent()
                self._set_headers(HTTPStatus.OK, "application/json")
                self.wfile.write(json.dumps({"success": True, "settings": updated}).encode("utf-8"))
            except Exception as e:
                self._set_headers(HTTPStatus.BAD_REQUEST, "application/json")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        if path == "/api/brain/key":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
                pm = _get_safe_profile_mgr()
                pm.set_key(body.get("provider", "gemini"), body.get("key", ""),body.get("profile_id"))
                from dock_twoo.brain.manager import BrainManager
                if BrainManager._instance is not None:
                    BrainManager._instance.run_on_main_thread(BrainManager._instance.companion.update)
                self._set_headers(HTTPStatus.OK, "application/json")
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            except Exception as e:
                self._set_headers(HTTPStatus.BAD_REQUEST, "application/json")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        if path == "/api/brain/action":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
                action = body.get("action")
                if action in ("read_desktop", "read_window", "read_selected", "stop_reading"):
                    port = self.server.server_address[1]
                    origin = self.headers.get("Origin")
                    if self.headers.get("X-Brain-Reader") != "local" or (origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")):
                        raise RuntimeError("Start reading from the local Brain controls.")
                from dock_twoo.brain.manager import BrainManager
                if BrainManager._instance is None and action in ("read_desktop", "read_window", "read_selected", "stop_reading"):
                    raise RuntimeError("Brain is not running. Start the desktop application first.")
                if BrainManager._instance is not None:
                    bm = BrainManager._instance
                    if action == "summon":
                        bm.show_mini_agent()
                    elif action == "hide":
                        bm.hide_mini_agent()
                    elif action == "talk":
                        bm.toggle_talking()
                    elif action in ("read_desktop", "read_window", "read_selected"):
                        bm.start_reading("selected" if action=="read_selected" else "window")
                    elif action == "stop_reading":
                        bm.stop_reading()
                    elif action in ("move", "corner"):
                        corner_name = body.get("name") or body.get("corner", "top_left")
                        bm.companion.travel_to_corner(corner_name)
                    elif action == "animation":
                        anim_name = body.get("name", "wave")
                        bm.action_requested.emit(anim_name)
                self._set_headers(HTTPStatus.OK, "application/json")
                self.wfile.write(json.dumps({"success": True, "action": action}).encode("utf-8"))
            except Exception as e:
                self._set_headers(HTTPStatus.BAD_REQUEST, "application/json")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        if path == "/api/storage/change":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
                new_path_str = body.get("new_path", "").strip()
                if not new_path_str:
                    raise ValueError("Target root storage path cannot be empty.")
                new_path = Path(new_path_str).expanduser().resolve()
                old_path = self.config_manager.config.get_storage_path()
                from dock_twoo.config import migrate_storage_data
                res = migrate_storage_data(old_path, new_path)
                self.config_manager.update({"storage_path": str(new_path)})
                self._set_headers(HTTPStatus.OK, "application/json")
                self.wfile.write(json.dumps({
                    "success": True,
                    "storage_path": str(new_path),
                    "migration": res,
                }).encode("utf-8"))
            except Exception as e:
                self._set_headers(HTTPStatus.BAD_REQUEST, "application/json")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        if path == "/api/storage/browse":
            try:
                import subprocess
                script = 'POSIX path of (choose folder with prompt "Select Dock 2 Root Storage Folder:")'
                res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=60)
                if res.returncode == 0 and res.stdout.strip():
                    chosen = res.stdout.strip()
                    self._set_headers(HTTPStatus.OK, "application/json")
                    self.wfile.write(json.dumps({"success": True, "path": chosen}).encode("utf-8"))
                else:
                    self._set_headers(HTTPStatus.OK, "application/json")
                    self.wfile.write(json.dumps({"success": False, "cancelled": True}).encode("utf-8"))
            except Exception as e:
                self._set_headers(HTTPStatus.INTERNAL_SERVER_ERROR, "application/json")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        self._set_headers(HTTPStatus.NOT_FOUND, "text/plain")
        self.wfile.write(b"404 Not Found")

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy console log messages
        pass


class WebConsoleServer:
    """Manages the background HTTP server for Web Console."""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.port = config_manager.config.server_port
        self.host = config_manager.config.server_host

    def start(self) -> None:
        """Start server in background daemon thread."""
        if self.server:
            return

        handler_cls = type(
            "BoundConsoleRequestHandler",
            (ConsoleRequestHandler,),
            {"config_manager": self.config_manager},
        )

        try:
            self.server = ConsoleHTTPServer((self.host, self.port), handler_cls)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            print(f"[Dock T(w)oo] Web Console running at http://{self.host}:{self.port}")
        except Exception as e:
            print(f"[Dock T(w)oo] Failed to start Web Console on {self.host}:{self.port}: {e}")

    def stop(self) -> None:
        """Stop background server."""
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None

    def open_browser(self) -> None:
        """Open web console in default browser."""
        url = f"http://{self.host}:{self.port}"
        webbrowser.open(url)
