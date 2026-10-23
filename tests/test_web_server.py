"""Tests for Web Console HTTP server and REST endpoints."""

import json
import time
import urllib.request
from pathlib import Path

import pytest

from dock_twoo.config import ConfigManager, DockConfig
from dock_twoo.server import WebConsoleServer


@pytest.fixture
def test_server(tmp_path: Path):
    config_file = tmp_path / "config.json"
    mgr = ConfigManager(config_path=config_file)
    # Use random high port to avoid conflict
    import random
    port = random.randint(29000, 31000)
    mgr.update({"server_port": port, "server_host": "127.0.0.1"})

    server = WebConsoleServer(mgr)
    server.start()
    time.sleep(0.3)  # Give thread a moment to bind

    yield server, port, mgr

    server.stop()


def test_web_console_get_config(test_server):
    server, port, mgr = test_server
    url = f"http://127.0.0.1:{port}/api/config"

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=3) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "edge" in data
        assert "dock_width" in data
        assert data["server_port"] == port


def test_web_console_post_config_update(test_server):
    server, port, mgr = test_server
    url = f"http://127.0.0.1:{port}/api/config"

    payload = json.dumps({"edge": "left", "icon_size": 28}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=3) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["success"] is True
        assert data["config"]["edge"] == "left"
        assert data["config"]["icon_size"] == 28

    assert mgr.config.edge == "left"
    assert mgr.config.icon_size == 28


def test_web_console_status_endpoint(test_server):
    server, port, mgr = test_server
    url = f"http://127.0.0.1:{port}/api/status"

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=3) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["name"] == "Dock T(w)oo"
        assert data["running"] is True


def test_web_console_serves_html(test_server):
    server, port, mgr = test_server
    url = f"http://127.0.0.1:{port}/"

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=3) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "<title>Dock T(w)oo" in html
        assert "Settings Console" in html
