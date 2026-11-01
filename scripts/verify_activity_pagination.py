"""Bounded Live Trail verification using synthetic data and the actual local UI.

QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu \
    .venv/bin/python scripts/verify_activity_pagination.py
No microphone, hardware input, cloud model or user storage is touched.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['PYTEST_CURRENT_TEST']='activity-pagination'
from PySide6.QtCore import Qt,QTimer,QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from dock_twoo.config import ConfigManager
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.server import WebConsoleServer

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
folder=tempfile.TemporaryDirectory(prefix='dock-activity-');root=Path(folder.name)
config=ConfigManager(root/'config.json');config.config.storage_path=str(root/'storage');config.config.server_port=24949
store=BrainStore(config.config.get_voice_dir());store.set_setting('companion_visible',False)
manager=BrainManager(store=store,start_services=False);BrainManager._instance=manager
run=manager.activity.start('Read many synthetic documents','test')
for index in range(225):manager.activity.event(run,'tool_result',{'index':index,'text':'Synthetic verified evidence. '*1000},index+1)
manager.activity.finish(run,'complete','Synthetic report paragraph. '*1000)
server=WebConsoleServer(config);server.start()
checks={};errors=[]
cli=shutil.which('postman')
if cli:
    assertions="""pm.test('bounded latest event page',()=>{const d=pm.response.json();pm.expect(d.events.length).to.equal(100);pm.expect(d.pagination.event_count).to.equal(225);pm.expect(d.pagination.next_before).to.be.a('number');});pm.test('bounded previews retain full-data markers',()=>{const d=pm.response.json();pm.expect(d.run.reply_truncated).to.equal(1);pm.expect(d.events[0].payload_truncated).to.equal(true);pm.expect(pm.response.text().length).to.be.below(1000000);});"""
    result=subprocess.run([cli,'request',f'http://127.0.0.1:24949/api/activity/{run}','-H','X-Brain-Request:local','--report-events=false','--script-post-request',assertions],capture_output=True,text=True,timeout=30)
    checks['postman_exit_code']=result.returncode
    checks['postman_assertions']=2
    if result.returncode:errors.append('Postman checks failed: '+result.stdout[-1000:]+result.stderr[-1000:])
else:checks['postman']='unavailable'
view=QWebEngineView();view.resize(900,850);view.setUrl(QUrl('http://127.0.0.1:24949/live-trail.html'));view.show()
started=time.monotonic();stage=0;pending=False

def finish():
    timer.stop();view.close();manager.shutdown();server.stop()
    result={'success':not errors,'checks':checks,'errors':errors}
    Path('/tmp/dock-activity-pagination.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True);app.exit(1 if errors else 0)

def tick():
    global pending,stage
    if pending:return
    if time.monotonic()-started>45:errors.append(f'Timed out at stage {stage}');finish();return
    pending=True
    prefix="const buttons=(root=document)=>Array.from(root.querySelectorAll('button'));const click=(text,root=document)=>buttons(root).find(b=>b.textContent===text)?.click();const row=document.querySelector('.activity-run');const timeline=()=>Array.from(document.querySelectorAll('.activity-detail>details.activity-event'));const chosen=()=>document.querySelector('[data-event=\"'+window._chosen+'\"]');const text=()=>chosen()?.querySelector('.activity-text-pages');"
    steps={
      0:"return {ready:!!row,collapsed:row&&!row.open,events:timeline().length};",
      1:"if(timeline().length!==100)return {};window._chosen=timeline().at(-1).dataset.event;chosen().open=true;click('Read full event data',chosen());return {events:timeline().length};",
      2:"if(text()?.querySelector('pre')?.textContent.length!==8192)return {};click('Next text',text());return {firstPage:true};",
      3:"return {secondPage:text()?.querySelector('p')?.textContent.includes('8,193')};",
      4:"return {fresh:document.querySelector('.activity-detail')?.textContent.includes('New synthetic event'),open:chosen()?.open,secondPage:text()?.querySelector('p')?.textContent.includes('8,193'),count:timeline().length};",
      5:"return {older:document.querySelector('.activity-detail')?.textContent.includes('Earlier activity'),count:timeline().length,missing:!chosen()};",
      6:"return {latest:document.querySelector('.activity-detail')?.textContent.includes('Latest activity'),open:chosen()?.open,secondPage:text()?.querySelector('p')?.textContent.includes('8,193')};",
      7:"return {reply:document.querySelector('[data-text-page=reply] pre')?.textContent.length===8192,overflow:document.documentElement.scrollWidth>innerWidth};",
    }
    source='JSON.stringify((()=>{'+prefix+steps[stage]+'})())'
    def receive(value):
        global pending,stage
        pending=False;data=json.loads(value or '{}')
        try:
            if stage==0:
                if not data.get('ready'):return
                assert data['collapsed'] and data['events']==0,data
                checks['collapsed_requests_fetch_no_events']=True
                view.page().runJavaScript("document.querySelector('.activity-run').open=true");stage=1
            elif stage==1:
                if not data:return
                checks['bounded_dom_events']=data['events'];stage=2
            elif stage==2:
                if not data:return
                stage=3
            elif stage==3:
                if not data.get('secondPage'):return
                manager.activity.event(run,'progress',{'message':'New synthetic event'},226)
                view.page().runJavaScript("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Refresh').click()")
                stage=4
            elif stage==4:
                if not data.get('fresh') or not data.get('open') or not data.get('secondPage'):return
                assert data['count']==100,data
                checks['expansion_and_text_page_retained_after_live_refresh']=True
                view.page().runJavaScript("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Older events').click()");stage=5
            elif stage==5:
                if not data.get('older'):return
                assert data['count']==100 and data['missing'],data
                checks['older_events']=True
                view.page().runJavaScript("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Newer events').click()");stage=6
            elif stage==6:
                if not data.get('latest'):return
                assert data['open'] and data['secondPage'],data
                checks['newer_page_restores_expansion']=True
                view.page().runJavaScript("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Read full response').click()");stage=7
            elif stage==7:
                if not data.get('reply'):return
                assert not data['overflow'],data
                checks['full_response_paged']=True;finish()
        except Exception as exc:errors.append(repr(exc));finish()
    view.page().runJavaScript(source,receive)

timer=QTimer();timer.setInterval(150);timer.timeout.connect(tick);timer.start();app.exec();folder.cleanup()
