"""Exercise real local APIs and native Live Trail; no paid models or microphone.

Run on a desktop with .venv/bin/python scripts/verify_console_workspace.py.
"""
import json, os, sys, tempfile, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['PYTEST_CURRENT_TEST'] = 'console-workspace'
from PySide6.QtCore import Qt, QTimer, QUrl, QRect
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage
from dock_twoo.config import ConfigManager
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.server import WebConsoleServer
from dock_twoo.ui.attached_window import AttachedWindow

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
folder = tempfile.TemporaryDirectory(prefix='dock-console-'); root = Path(folder.name)
config = ConfigManager(root/'config.json')
config.config.storage_path = str(root/'storage'); config.config.server_port = 24948
config.config.theme_mode = 'dark'; config.config.attached_width = 390
store = BrainStore(config.config.get_voice_dir()); store.set_setting('companion_visible', False)
manager = BrainManager(store=store, start_services=False); BrainManager._instance = manager
from dock_twoo.displays import display_inventory
manager.configure_displays(display_inventory()[:1]); manager.listener.start = lambda: None
run = manager.activity.start('Summarize the project research folder', 'voice')
call = manager.activity.begin_call(run, {'provider':'openai','model':'research-model','id':'research','name':'Research profile','_character_id':'orbit','_character_name':'Orbit'}, {'messages':[{'role':'user','content':'Summarize the selected documents.'}]})
job, workspace = manager.coordinator.begin('orbit', 'Review the architecture documents', {}, threading.Event())
server = WebConsoleServer(config); server.start()
view = QWebEngineView(); view.resize(1280,900); view.setWindowTitle('Dock console verification')
view.setUrl(QUrl('http://127.0.0.1:24948/')); view.show()
drawer = AttachedWindow(config.config); trail = drawer._apps['activity']
assert trail.view is None, 'Closed drawer must not allocate a renderer'
started = time.monotonic(); stage = 0; pending = False; stage_at = started; checks = {}; errors = []

def finish():
    timer.stop()
    result = {'success':not errors,'checks':checks,'errors':errors}
    Path('/tmp/dock-console-workspace.json').write_text(json.dumps(result, indent=2)); print(json.dumps(result), flush=True)
    view.close(); drawer.close(); manager.shutdown(); server.stop(); app.exit(0 if not errors else 1)

def tick():
    global pending, stage, stage_at
    if pending:return
    if time.monotonic()-started > 55:errors.append(f'Timed out at stage {stage}'); finish(); return
    pending = True; current = view
    if stage == 0:
        source = "JSON.stringify({ready:!!document.querySelector('.assistant-awake-row'),previewOff:document.getElementById('consoleBody')?.classList.contains('hide-preview'),moved:!document.querySelector('[data-page=page-activity]')&&!document.getElementById('agentTaskTrail')})"
    elif stage == 1:
        source = "document.querySelector('[data-page=page-brain]').click();document.querySelector('[data-tab=brain-tab-awake]').click();JSON.stringify({count:document.querySelectorAll('.assistant-awake-row').length,brain:document.querySelector('[data-character=default] input')?.disabled})"
    elif stage == 2:
        current = trail.view
        source = "JSON.stringify({requests:document.querySelectorAll('.activity-run').length,calls:document.querySelectorAll('.activity-call').length,jobs:document.querySelectorAll('#agentTaskTrail details').length,open:document.querySelectorAll('details[open]').length})"
    elif stage == 3:
        current = trail.view
        source = "JSON.stringify((()=>{const call=document.querySelector('.activity-call');if(!call)return {};window._job=document.querySelector('#agentTaskTrail details');window._job.open=true;const wasClosed=!call.open;call.open=true;return {wasClosed,pending:document.body.textContent.includes('Waiting for the model response'),request:document.body.textContent.includes('Summarize the selected documents.')};})())"
    elif stage == 4:
        if time.monotonic()-stage_at < 6:pending=False;return
        current = trail.view
        source = "JSON.stringify({sameJob:window._job===document.querySelector('#agentTaskTrail details'),jobOpen:window._job.open,callOpen:document.querySelector('.activity-call')?.open,response:document.querySelector('.activity-call')?.textContent.includes('Reviewed the documents.'),overflow:document.documentElement.scrollWidth>innerWidth})"
    elif stage == 4.5:
        if time.monotonic()-stage_at < .8:pending=False;return
        trail.view.grab().save('/tmp/dock-live-trail-dark.png');checks['dark_screenshot']='/tmp/dock-live-trail-dark.png'
        drawer.hide_window();stage=5;stage_at=time.monotonic();pending=False;return
    elif stage == 5:
        if time.monotonic()-stage_at < 1:pending=False;return
        assert trail.view.page().lifecycleState() == QWebEnginePage.LifecycleState.Frozen
        checks['closed_page_frozen'] = True
        drawer.show_app('activity', QRect(1450,24,60,900), 500)
        stage = 6; stage_at = time.monotonic(); pending=False;return
    elif stage == 6:
        if time.monotonic()-stage_at < 1:pending=False;return
        current = trail.view
        source = "JSON.stringify({open:document.querySelector('.activity-call')?.open,active:!document.hidden})"
    elif stage == 7:
        current = trail.view
        source = "JSON.stringify({light:document.body.classList.contains('theme-light'),ready:!!document.querySelector('.activity-run')})"
    else:
        if time.monotonic()-stage_at < 1:pending=False;return
        trail.view.grab().save('/tmp/dock-live-trail-light.png'); checks['light_screenshot']='/tmp/dock-live-trail-light.png'
        pending=False;finish();return
    def receive(value):
        global pending, stage, stage_at
        pending=False
        data=json.loads(value or '{}')
        if stage==0:
            if not data.get('ready'):return
            assert data['previewOff'] and data['moved'],data; checks.update(data); stage=1
        elif stage==1:
            if data.get('count')!=30:return
            assert data['brain']; checks['awake_controls']=30; view.hide()
            drawer.show_app('activity', QRect(1450,24,60,900), 500); assert trail.view is not None
            checks['lazy_renderer']=True; stage=2
        elif stage==2:
            if not data.get('requests') or not data.get('jobs'):return
            assert data['calls']==0 and data['open']==0,data;checks['all_collapsed_by_default']=True
            trail.view.page().runJavaScript("document.querySelector('.activity-run').open=true");stage=3
        elif stage==3:
            if not data:return
            assert data['pending'] and data['request'] and data['wasClosed'],data; checks['in_flight_request_visible']=True
            manager.activity.end_call(call, {'usage':{'prompt_tokens':1250,'completion_tokens':320},'choices':[{'message':{'content':'Reviewed the documents.'}}]}, 'openai', latency_ms=1420)
            manager.activity.event(run,'tool_result',{'name':'read_file','result':{'ok':True,'pages':3}},1)
            manager.activity.finish(run,'complete','The documents cover architecture and test results.')
            manager.coordinator.complete('orbit',job,'Architecture review complete.')
            stage=4
        elif stage==4:
            assert data['sameJob'] and data['jobOpen'] and data['callOpen'] and data['response'] and not data['overflow'],data
            checks['live_response_and_expansion_retained']=True
            trail.view.page().runJavaScript("document.querySelector('.activity-call').scrollIntoView({block:'start'})");stage=4.5
        elif stage==6:
            assert data['open'] and data['active'],data;checks['reopen_retains_details']=True
            config.config.theme_mode='light';drawer.update_config(config.config);stage=7
        elif stage==7:
            if not data.get('ready') or not data.get('light'):return
            stage=8
        stage_at=time.monotonic()
    def safely(value):
        try:receive(value)
        except Exception as exc:errors.append(repr(exc));finish()
    current.page().runJavaScript(source,safely)

timer=QTimer();timer.setInterval(200);timer.timeout.connect(tick);timer.start();app.exec();folder.cleanup()
