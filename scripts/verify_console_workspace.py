"""Render real console APIs; verify polling retains expanded job details."""
import json,os,sys,tempfile,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));os.environ['PYTEST_CURRENT_TEST']='console-workspace'
from PySide6.QtCore import Qt,QTimer,QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage
class DiagnosticPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        print(f"JS {source}:{line}: {message}", flush=True)
from dock_twoo.config import ConfigManager
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.server import WebConsoleServer
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
folder=tempfile.TemporaryDirectory(prefix='dock-console-');root=Path(folder.name)
config=ConfigManager(root/'config.json');config.config.storage_path=str(root/'storage');config.config.server_port=24948
store=BrainStore(config.config.get_voice_dir());store.set_setting('companion_visible',False)
manager=BrainManager(store=store,start_services=False);BrainManager._instance=manager
from dock_twoo.displays import display_inventory
manager.configure_displays(display_inventory()[:1]);manager.listener.start=lambda:None
run=manager.activity.start('Summarize the project research folder','voice')
call=manager.activity.begin_call(run,{'provider':'openai','model':'research-model','id':'research','name':'Research profile'}, {'messages':[{'role':'user','content':'Summarize the selected documents.'}]})
manager.activity.end_call(call,{'usage':{'prompt_tokens':1250,'completion_tokens':320},'choices':[{'message':{'content':'Reviewed the documents.'}}]},'openai',latency_ms=1420)
manager.activity.event(run,'tool_result',{'name':'read_file','result':{'ok':True,'pages':3}},1)
manager.activity.finish(run,'complete','The three documents cover the release plan, architecture and test results.')
job,workspace=manager.coordinator.begin('orbit','Review the architecture documents',{},threading.Event())
server=WebConsoleServer(config);server.start()
view=QWebEngineView();view.setPage(DiagnosticPage(view));view.resize(1280,900);view.setWindowTitle('Dock console verification');view.setUrl(QUrl('http://127.0.0.1:24948/'));view.show()
started=time.monotonic();stage=0;pending=False;stage_at=started;checks={};errors=[]
def js(source,receive):view.page().runJavaScript(source,receive)
def finish():
    timer.stop();result={'success':not errors,'checks':checks,'errors':errors};Path('/tmp/dock-console-workspace.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
    view.close();manager.shutdown();server.stop();app.exit(0 if not errors else 1)
def tick():
    global pending,stage,stage_at
    if pending:return
    if time.monotonic()-started>35:errors.append(f'Console verification timed out at stage {stage}');finish();return
    pending=True
    if stage==0:
        source="JSON.stringify({ready:!!document.querySelector('.activity-item'),previewOff:document.getElementById('consoleBody')?.classList.contains('hide-preview'),voiceLabel:document.body.textContent.includes('Voice Assistant Vault Location')})"
    elif stage==1:
        source="document.querySelector('[data-page=page-brain]').click();document.querySelector('[data-tab=brain-tab-profiles]').click();JSON.stringify({jobs:document.querySelectorAll('#agentTaskTrail details').length})"
    elif stage==2:
        source="window._expandedJob=document.querySelector('#agentTaskTrail details');window._expandedJob.open=true;JSON.stringify({open:window._expandedJob.open})"
    elif stage==3:
        if time.monotonic()-stage_at<7:pending=False;return
        source="JSON.stringify({same:window._expandedJob===document.querySelector('#agentTaskTrail details'),open:document.querySelector('#agentTaskTrail details')?.open})"
    elif stage==4:
        source="document.querySelector('[data-page=page-activity]').click();JSON.stringify({cards:document.querySelectorAll('.activity-detail .usage-kpi').length,calls:document.querySelectorAll('.activity-table tbody tr').length})"
    elif stage==5:
        if time.monotonic()-stage_at<1:pending=False;return
        view.grab().save('/tmp/dock-activity-redesign.png');checks['activity_screenshot']='/tmp/dock-activity-redesign.png'
        source="document.querySelector('[data-page=page-brain]').click();document.querySelector('[data-tab=brain-tab-awake]').click();JSON.stringify({count:document.querySelectorAll('.assistant-awake-row').length,brain:document.querySelector('[data-character=default] input')?.disabled})"
    elif stage==6:
        source="document.querySelector('[data-character=parrot] input').click();JSON.stringify({clicked:true})"
    else:
        if time.monotonic()-stage_at<1:pending=False;return
        assert not store.character_awake('parrot')
        view.grab().save('/tmp/dock-awake-settings.png');checks['awake_saved']=True;pending=False;finish();return
    def receive(value):
        global pending,stage,stage_at
        pending=False
        try:data=json.loads(value or '{}')
        except ValueError:return
        if stage==0:
            if not data.get('ready'):return
            assert data.get('previewOff') and data.get('voiceLabel'),data;checks.update(data);stage=1
        elif stage==1:
            if not data.get('jobs'):return
            stage=2
        elif stage==2:assert data.get('open');stage=3
        elif stage==3:
            assert data.get('same') and data.get('open'),data;checks['expanded_after_two_polls']=True;stage=4
        elif stage==4:
            assert data.get('cards',0)>=4 and data.get('calls')==1,data;checks.update(data);stage=5
        elif stage==5:
            if data.get('count')!=30:return
            assert data.get('brain'),data;checks['awake_controls']=30;stage=6
        elif stage==6:stage=7
        stage_at=time.monotonic()
    def safely(value):
        try:receive(value)
        except Exception as exc:errors.append(repr(exc));finish()
    js(source,safely)
timer=QTimer();timer.setInterval(200);timer.timeout.connect(tick);timer.start();app.exec();folder.cleanup()
