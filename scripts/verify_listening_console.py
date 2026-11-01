"""Exercise the real console and API with isolated storage and fake audio input.

QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu \
    .venv/bin/python scripts/verify_listening_console.py
No microphone, speakers, cloud models, keyboard monitor or user data is used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['PYTEST_CURRENT_TEST'] = 'listening-console'

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from dock_twoo.config import ConfigManager
import dock_twoo.config as config_module
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.local_tts import get_local_tts
from dock_twoo.server import WebConsoleServer


def main():
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    checks, errors = {}, []
    manager = server = view = None
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='dock-listening-console-') as folder:
        root = Path(folder)
        config = ConfigManager(root/'config.json')
        config.config.storage_path = str(root/'storage')
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            config.config.server_port = probe.getsockname()[1]
        config_module.ConfigManager = lambda: config
        store = BrainStore(config.config.get_voice_dir())
        store.update_settings({'companion_visible':False, 'roaming':False, 'voice_reply':False, 'character_sounds':False})
        manager = BrainManager(store=store, start_services=False)
        BrainManager._instance = manager
        listener = manager.listener
        counts = {'opened':0, 'closed':0}

        def close_input():
            counts['closed'] += 1

        def open_input():
            counts['opened'] += 1
            manager.audio_devices.source = SimpleNamespace(stop=close_input, deleteLater=lambda:None)
            manager.audio_devices.input_io = object()
            manager.audio_devices.input_state.emit(True, 'Isolated test input')

        manager.audio_devices._open_input = open_input
        listener.models.start_model_downloads = lambda:None
        for model in (listener.wake_detector, listener.stop_detector, listener.endpoint_vad):
            model.start = lambda:None
        manager.shortcut_listener.start = lambda:None
        manager.semantic_model.start = lambda:None
        get_local_tts().start = lambda:None
        manager.reader.backend.remember_frontmost = lambda:None
        real_start = listener.start

        def start_listener():
            marker = os.environ.pop('PYTEST_CURRENT_TEST', None)
            try:real_start()
            finally:
                if marker is not None:os.environ['PYTEST_CURRENT_TEST'] = marker

        listener.start = start_listener
        manager._services_enabled = True
        manager.set_listening_mode('automatic')
        server = WebConsoleServer(config)
        server.start()
        url = f'http://127.0.0.1:{server.port}'
        view = QWebEngineView()
        view.resize(1200, 1000)
        view.setUrl(QUrl(url))
        view.show()

        def wait(predicate, description, timeout=15):
            deadline = time.monotonic()+timeout
            while not predicate():
                if time.monotonic()>deadline:raise AssertionError('Timed out: '+description)
                app.processEvents()
                time.sleep(.01)
            app.processEvents()

        def js(source):
            result = []
            view.page().runJavaScript('JSON.stringify((()=>{'+source+'})())', result.append)
            wait(lambda:bool(result), 'JavaScript callback')
            return json.loads(result[0]) if result[0] else None

        def state():
            return js("""const e=id=>document.getElementById(id);const select=e('brainListeningMode');
                return {mode:select?.value,status:e('brainListeningModeStatus')?.textContent,diagnostics:e('brainWakeDiagnostics')?.textContent,
                talk:e('brainTalkBtn')?.disabled,talkLabel:e('brainTalkBtn')?.textContent,modeDisabled:select?.disabled,
                request:e('brainRequestSend')?.disabled,reading:document.querySelector('[data-reader=read_selected]')?.disabled,
                animation:e('brainLoopAnimBtn')?.disabled,closed:e('brainCloseBtn')?.disabled,
                searchable:!!select?.nextElementSibling?.querySelector('[role=combobox]'),
                requestStatus:e('brainRequestStatus')?.textContent,buttonOpacity:e('brainRequestSend')?getComputedStyle(e('brainRequestSend')).opacity:null};""")

        def select_mode(mode):
            label = {'automatic':'Automatic', 'manual':'Manual', 'off':'Microphone off'}[mode]
            js("document.getElementById('brainListeningMode').nextElementSibling.querySelector('[role=combobox]').click();return true;")
            js("const search=document.querySelector('.custom-dropdown-menu:not([hidden]) input');search.value="+json.dumps(label)+";search.dispatchEvent(new Event('input',{bubbles:true}));return true;")
            options = js("return [...document.querySelectorAll('.custom-dropdown-menu:not([hidden]) [role=option]')].map(e=>e.textContent);")
            assert len(options)==1, options
            js("document.querySelector('.custom-dropdown-menu:not([hidden]) [role=option]').click();return true;")
            wait(lambda:manager.listening_mode==mode and state()['mode']==mode and not state()['modeDisabled'], 'save '+mode)
            assert BrainStore(store.data_dir).setting('listening_mode')==mode

        try:
            wait(lambda:state().get('searchable') and 'Automatic mode' in (state().get('status') or ''), 'initial console')
            js("document.querySelector('[data-page=page-brain]').click();return true;")
            checks['standard_searchable_mode_dropdown'] = True
            select_mode('manual')
            wait(lambda:'microphone idle' in state()['status'], 'manual idle status')
            assert not manager.audio_devices._want_input and not state()['talk']
            assert 'preparing' not in state()['diagnostics']
            js("document.getElementById('brainTalkBtn').click();return true;")
            wait(lambda:listener.is_recording and 'Finish speaking' in state()['talkLabel'], 'manual Talk starts capture')
            assert manager.audio_devices._want_input
            js("document.getElementById('brainTalkBtn').click();return true;")
            wait(lambda:not listener.is_recording and not manager.audio_devices._want_input, 'manual second click closes input')
            checks['manual_click_start_finish_and_idle'] = True
            select_mode('off')
            wait(lambda:state()['talk'] and 'Microphone off' in state()['status'], 'off controls')
            assert not manager.audio_devices._want_input and not state()['request'] and not state()['reading']
            checks['off_disables_audio_preserves_text_reading'] = True
            select_mode('automatic')
            wait(lambda:manager.audio_devices._want_input and not state()['talk'], 'automatic wake input')
            checks['automatic_restores_wake_input'] = True
            js("document.getElementById('brainCloseBtn').click();return true;")
            wait(lambda:manager.assistant_closed and state()['closed'] and state()['request'], 'Close')
            closed = state()
            assert closed['talk'] and closed['animation'] and closed['reading'] and not closed['modeDisabled']
            wait(lambda:float(state()['buttonOpacity'])<.6, 'disabled controls visibly dim')
            assert not manager.audio_devices._want_input
            checks['close_stops_input_disables_actions_retains_mode_control'] = True
            select_mode('off')
            assert manager.assistant_closed and not manager.audio_devices._want_input
            js("document.getElementById('brainSummonBtn').click();return true;")
            wait(lambda:not manager.assistant_closed and not state()['closed'], 'Show saved off mode')
            assert manager.listening_mode=='off' and not manager.audio_devices._want_input and state()['talk']
            assert not state()['reading'] and not state()['request']
            assert 'Assistant closed' not in state()['requestStatus']
            checks['editing_closed_mode_does_not_reopen_and_show_preserves_it'] = True
            select_mode('manual')
            js("document.getElementById('brainCloseBtn').click();return true;")
            wait(lambda:manager.assistant_closed and state()['closed'], 'Close manual')
            js("document.getElementById('brainSummonBtn').click();return true;")
            wait(lambda:not manager.assistant_closed and not state()['closed'], 'Show manual')
            assert manager.listening_mode=='manual' and not manager.audio_devices._want_input and not state()['talk']
            checks['manual_close_reopen_keeps_input_idle'] = True
            select_mode('automatic')
            js("document.getElementById('brainCloseBtn').click();return true;")
            wait(lambda:manager.assistant_closed and state()['closed'], 'final Close')
            cli = shutil.which('postman')
            if cli:
                assertions = """pm.test('Close overrides saved automatic mode',()=>{const d=pm.response.json();pm.expect(d.assistant_state).to.equal('closed');pm.expect(d.voice_input.mode).to.equal('automatic');pm.expect(d.settings.listening_mode).to.equal('automatic');pm.expect(d.voice_input.enabled).to.equal(false);pm.expect(d.voice_input.automatic).to.equal(false);pm.expect(d.voice_input.listening).to.equal(false);});"""
                result = subprocess.run([cli,'request',url+'/api/brain/status','-H','X-Brain-Request:local','--report-events=false','--script-post-request',assertions],capture_output=True,text=True,timeout=30)
                checks['postman_exit_code'] = result.returncode
                checks['postman_assertions'] = 1
                assert result.returncode==0,result.stdout[-2000:]+result.stderr[-1000:]
            else:checks['postman'] = 'unavailable'
            view.grab().save('/tmp/dock-listening-console.png')
        except Exception as error:
            errors.append(repr(error))
        finally:
            view.close()
            manager.shutdown()
            server.stop()
            report = {'success':not errors,'seconds':round(time.monotonic()-started,1),'checks':checks,'errors':errors,
                      'fake_input':counts,'real_microphone_opened':False,'cloud_calls':0}
            Path('/tmp/dock-listening-console.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report),flush=True)
    return 1 if errors else 0


if __name__=='__main__':
    raise SystemExit(main())
