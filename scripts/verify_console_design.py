"""Check console navigation, responsive layout and theme with isolated storage.

Uses the actual local server and Qt WebEngine. No audio, paid models, user
settings or native pointer input are used. Artifacts: /tmp/dock-console-design.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['PYTEST_CURRENT_TEST'] = 'console-design'
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from dock_twoo.config import ConfigManager
import dock_twoo.config as config_module
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.server import WebConsoleServer


def main():
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    output = Path('/tmp/dock-console-design'); output.mkdir(exist_ok=True)
    checks, errors = {}, []
    with tempfile.TemporaryDirectory(prefix='dock-console-design-') as folder:
        root = Path(folder)
        config = ConfigManager(root/'config.json')
        config.config.storage_path = str(root/'storage')
        config.config.theme_mode = 'dark'
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            config.config.server_port = probe.getsockname()[1]
        config_module.ConfigManager = lambda: config
        store = BrainStore(config.config.get_voice_dir())
        store.update_settings({'companion_visible': False, 'voice_reply': False,
                               'roaming': False, 'character_sounds': False})
        manager = BrainManager(store=store, start_services=False)
        BrainManager._instance = manager
        server = WebConsoleServer(config); server.start()
        view = QWebEngineView(); view.resize(1440, 1000); view.show()
        view.setUrl(QUrl(f'http://127.0.0.1:{server.port}/'))

        def wait(predicate, message, timeout=15):
            end = time.monotonic()+timeout
            while not predicate():
                if time.monotonic() > end: raise AssertionError(message)
                app.processEvents(); time.sleep(.015)

        def js(code):
            result = []
            view.page().runJavaScript('JSON.stringify((()=>{'+code+'})())', result.append)
            wait(lambda: bool(result), 'JavaScript callback')
            return json.loads(result[0] or 'null')

        def settle():
            for _ in range(12): app.processEvents(); time.sleep(.03)

        try:
            wait(lambda: js('return !!document.querySelector(".assistant-awake-row");'), 'Console loads')
            assert js('return document.getElementById("consoleBody").classList.contains("hide-preview");')
            pages = js('return [...document.querySelectorAll(".nav-item")].map(x=>x.dataset.page);')
            for theme in ('dark', 'light'):
                js('applyThemeBody('+json.dumps(theme)+');return true;')
                for width in (1440, 900, 600):
                    view.resize(width, 1000)
                    for page in pages:
                        js('document.querySelector("[data-page='+page+']").click();window.scrollTo(0,0);return true;')
                        settle()
                        metrics = js('return {page:document.querySelector(".page-view.active").id,overflow:document.documentElement.scrollWidth>innerWidth,search:document.getElementById("settingsSearch").closest(".search-box").getBoundingClientRect().height,background:getComputedStyle(document.body).backgroundColor};')
                        assert metrics['page']==page and not metrics['overflow'], (theme,width,page,metrics)
                        assert metrics['search']>=40, metrics
                        checks[f'{theme}-{width}-{page}'] = metrics
                        if width==1440 or page in ('page-brain','page-dashboard','page-placement'):
                            assert view.grab().save(str(output/f'{theme}-{width}-{page}.png'))
            js('const field=document.getElementById("settingsSearch");field.value="Vault";field.dispatchEvent(new Event("input",{bubbles:true}));return true;')
            assert js('return [...document.querySelectorAll(".nav-item")].filter(x=>x.getClientRects().length).some(x=>x.dataset.page==="page-vault");')
            checks['search_reaches_vault'] = True
        except Exception as exc:
            errors.append(repr(exc))
            view.grab().save(str(output/'failure.png'))
        finally:
            view.close(); manager.shutdown(); server.stop()
    report = {'success':not errors,'checks':checks,'errors':errors,'cloud_calls':0,'user_data_written':False}
    (output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'success':not errors,'checks':len(checks),'errors':errors,'output':str(output)}),flush=True)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
