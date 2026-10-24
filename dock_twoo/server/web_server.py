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

    def do_GET(self) -> None:
        path = self.path.split("?")[0]

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
            if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                check = status_dict.get("voice_input", {}).get("wake_diagnostics", {}).get("voice_check")
                if check:
                    check["heard"] = []
            self._set_headers(HTTPStatus.OK, "application/json")
            self.wfile.write(json.dumps(status_dict).encode("utf-8"))
            return

        if path == "/api/brain/profiles":
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
            icon_file = static_dir.parent.parent / "assets" / "icons" / icon_name
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

        if path == "/api/config":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                updates = json.loads(body)

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

        if path == "/api/brain/activate-profile":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
                pm = _get_safe_profile_mgr()
                profile_id = body.get("profile_id", "")
                success = pm.activate_profile(profile_id)
                from dock_twoo.brain.manager import BrainManager
                if BrainManager._instance is not None:
                    BrainManager._instance._update_status_indicator()
                self._set_headers(HTTPStatus.OK, "application/json")
                self.wfile.write(
                    json.dumps({"success": success, "active": pm.get_active_profile()}).encode("utf-8")
                )
            except Exception as e:
                self._set_headers(HTTPStatus.BAD_REQUEST, "application/json")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        if path == "/api/brain/profile":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
                pm = _get_safe_profile_mgr()
                saved = pm.save_profile(body)
                self._set_headers(HTTPStatus.OK, "application/json")
                self.wfile.write(json.dumps({"success": True, "profile": saved}).encode("utf-8"))
            except Exception as e:
                self._set_headers(HTTPStatus.BAD_REQUEST, "application/json")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        if path == "/api/brain/settings":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
                store = _get_safe_brain_store()
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
                pm.set_key(body.get("provider", "gemini"), body.get("key", ""))
                from dock_twoo.brain.manager import BrainManager
                if BrainManager._instance is not None:
                    BrainManager._instance._update_status_indicator()
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
                from dock_twoo.brain.manager import BrainManager
                if BrainManager._instance is not None:
                    bm = BrainManager._instance
                    if action == "summon":
                        bm.show_mini_agent()
                    elif action == "hide":
                        bm.hide_mini_agent()
                    elif action == "talk":
                        bm.start_talking()
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

        if path == "/api/brain/profile/delete":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
                pm = _get_safe_profile_mgr()
                deleted = pm.delete_profile(body.get("profile_id", ""))
                self._set_headers(HTTPStatus.OK, "application/json")
                self.wfile.write(json.dumps({"success": deleted}).encode("utf-8"))
            except Exception as e:
                self._set_headers(HTTPStatus.BAD_REQUEST, "application/json")
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
            self.server = ThreadingHTTPServer((self.host, self.port), handler_cls)
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
