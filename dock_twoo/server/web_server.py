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

from dock_twoo.brain import get_brain_manager
from dock_twoo.config import ConfigManager, DockConfig


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

        if path == "/api/brain/status":
            bm = get_brain_manager()
            self._set_headers(HTTPStatus.OK, "application/json")
            self.wfile.write(json.dumps(bm.get_status()).encode("utf-8"))
            return

        if path == "/api/brain/profiles":
            bm = get_brain_manager()
            self._set_headers(HTTPStatus.OK, "application/json")
            self.wfile.write(
                json.dumps({
                    "profiles": bm.profile_mgr.get_profiles(),
                    "active": bm.profile_mgr.get_active_profile(),
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

        if path == "/api/brain/activate-profile":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
                bm = get_brain_manager()
                success = bm.profile_mgr.activate_profile(body.get("profile_id", ""))
                self._set_headers(HTTPStatus.OK, "application/json")
                self.wfile.write(
                    json.dumps({"success": success, "active": bm.profile_mgr.get_active_profile()}).encode("utf-8")
                )
            except Exception as e:
                self._set_headers(HTTPStatus.BAD_REQUEST, "application/json")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        if path == "/api/brain/profile":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
                bm = get_brain_manager()
                saved = bm.profile_mgr.save_profile(body)
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
                bm = get_brain_manager()
                updated = bm.store.update_settings(body)
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
                bm = get_brain_manager()
                bm.profile_mgr.set_key(body.get("provider", "gemini"), body.get("key", ""))
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
                bm = get_brain_manager()
                action = body.get("action")
                if action == "summon":
                    bm.show_mini_agent()
                elif action == "hide":
                    bm.hide_mini_agent()
                elif action == "talk":
                    bm.start_talking()
                elif action == "animation":
                    anim_name = body.get("name", "wave")
                    bm.action_requested.emit(anim_name)
                self._set_headers(HTTPStatus.OK, "application/json")
                self.wfile.write(json.dumps({"success": True, "action": action}).encode("utf-8"))
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
