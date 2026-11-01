"""Native renderer lifecycle smoke: isolated settings, no audio or paid models.

Run with .venv/bin/python scripts/verify_presentation_resources.py.
Only this fixture's own windows and localhost server are touched.
"""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['PYTEST_CURRENT_TEST'] = 'presentation-resources'
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebChannel import QWebChannel
from shiboken6 import isValid
from dock_twoo.config import ConfigManager
import dock_twoo.config as config_module
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.displays import display_inventory
from dock_twoo.server import WebConsoleServer
from dock_twoo.ui.apps.dashboard_app import DashboardAppWidget
from dock_twoo.ui.lifecycle import GuiGarbageCollector

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app = QApplication([])
app.setApplicationName('Dock2 resource verification')
app.setQuitOnLastWindowClosed(False)
gc = GuiGarbageCollector(app)
folder = tempfile.TemporaryDirectory(prefix='dock-presentation-')
root = Path(folder.name)
config = ConfigManager(root/'config.json')
config.config.storage_path = str(root/'storage')
with socket.socket() as probe:
    probe.bind(('127.0.0.1', 0))
    config.config.server_port = probe.getsockname()[1]
config_module.ConfigManager = lambda: config
store = BrainStore(config.config.get_voice_dir())
store.update_settings({'companion_visible':False,'roaming':False,
                       'wake_word_enabled':False,'voice_reply':False,'character_sounds':False})
manager = BrainManager(store=store, start_services=False)
BrainManager._instance = manager
manager.listener.start = lambda: None
manager.configure_displays(display_inventory()[:1])
server = WebConsoleServer(config)
server.start()
dashboard = DashboardAppWidget(config.config)
assert dashboard.view is None
dashboard.resize(400, 600)
actor = manager.companion
actor.move(100, 120)
actor.show()
view = actor.model_view
errors = []; samples = []; cycles = 0; phase = 'ready'; pending = False
started = phase_at = time.monotonic()
retired = None


def finish():
    timer.stop()
    result = {'success':not errors,'cycles':cycles,'errors':errors,
              'dashboard_lazy':True,'microphone_opened':False,'cloud_calls':0,
              'samples':samples,'seconds':round(time.monotonic()-started, 1)}
    Path('/tmp/dock-presentation-resources.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)
    dashboard.close();manager.shutdown();server.stop();gc.stop(restore=False)
    app.exit(1 if errors else 0)


def tick():
    global pending, phase, phase_at, cycles, retired
    if pending:return
    if time.monotonic()-started > 100:
        errors.append('Timed out during '+phase);finish();return
    try:
        if phase == 'ready':
            if not view.ready or not actor.has_input_shape:return
            assert view.error == ''
            assert len(manager.companions) == 1
            actor.play_action('wave')
            samples.append(manager.resources.meter.sample())
            actor.hide()
            assert not any(t.isActive() for t in (actor.motion_timer,actor.activity_timer,
                                                 actor.roam_timer,actor.follow_timer,actor.blink_timer,view.timer))
            assert not manager.input_router.timer.isActive()
            assert not manager.playground.timer.isActive()
            old_page, old_channel = view.page(), view.channel
            retired = old_page, old_channel
            view.release_resources()
            assert view._released and not view.ready
            phase = 'unloaded';phase_at = time.monotonic()
        elif phase == 'unloaded':
            if time.monotonic()-phase_at < .4:return
            assert not isValid(retired[0]), 'Old browser page remains alive'
            assert not isValid(retired[1]), 'Old native channel remains alive'
            assert len(view.findChildren(QWebEnginePage)) == 1, 'Browser pages accumulated'
            assert len(view.findChildren(QWebChannel)) == 1, 'Native channels accumulated'
            retired = None
            assert view.page().renderProcessPid() == 0
            assert view.url().isEmpty()
            assert not view.ready and not view._loading
            cycles += 1
            samples.append({'closed':True, **manager.resources.meter.sample()})
            print(f'PASS character page destroyed/recreated {cycles}', flush=True)
            if cycles < 8:
                actor.show();phase = 'ready'
            else:
                dashboard.show();phase = 'dashboard'
            phase_at = time.monotonic()
        elif phase == 'dashboard':
            if time.monotonic()-phase_at < 1:return
            assert dashboard.view is not None
            assert dashboard.view.page().lifecycleState() == QWebEnginePage.LifecycleState.Active
            dashboard.hide();phase = 'frozen';phase_at = time.monotonic()
        elif phase == 'frozen':
            if time.monotonic()-phase_at < .5:return
            assert dashboard.view.page().lifecycleState() == QWebEnginePage.LifecycleState.Frozen
            samples.append(manager.resources.meter.sample())
            finish()
    except Exception as exc:
        errors.append(repr(exc));finish()


timer = QTimer();timer.timeout.connect(tick);timer.start(50)
code = app.exec()
folder.cleanup()
sys.exit(code)
