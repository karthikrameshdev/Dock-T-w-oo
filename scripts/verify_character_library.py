"""Exercise selected/all companions in the real Qt WebGL renderer, without audio."""
import argparse,json,sys,time
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--ids',nargs='*');p.add_argument('--port',type=int,default=28842);args=p.parse_args()
catalog=json.loads((ROOT/'characters/catalog.json').read_text())
entries=[d for d in catalog['characters'] if not args.ids or d['id'] in args.ids]
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([]);view=QWebEngineView();view.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.WindowDoesNotAcceptFocus);view.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating);view.setWindowTitle('Brain · character library verification');view.resize(700,700);view.show()
report={'success':True,'characters':[],'errors':[]};index=-1;phase=-1;started=time.monotonic();pending=False;phase_time=0;first=None
checks=['idle','wave','walk','fly','talk','magnifier','read','scan_code']
out=ROOT/'characters/runtime-gallery';out.mkdir(exist_ok=True)
def next_character():
    global index,phase,started,phase_time,first
    index+=1
    if index==len(entries):
        report['success']=not report['errors'];name='webgl-sample-validation.json' if args.ids else 'webgl-validation.json'
        (ROOT/'characters'/name).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='characters'}),flush=True);timer.stop();view.close();app.exit(0 if report['success'] else 1);return
    phase=-1;started=time.monotonic();phase_time=started;first=None
    view.load(QUrl(f"http://127.0.0.1:{args.port}/brain3d/index.html?character={entries[index]['id']}"))
def fail(message):
    report['errors'].append({'id':entries[index]['id'],'error':message});print('FAIL',entries[index]['id'],message,flush=True);next_character()
def receive(raw):
    global pending,phase,phase_time,first
    pending=False
    try:data=json.loads(raw or '{}')
    except (TypeError,ValueError):return
    if data.get('ready')=='error':fail(data.get('status','Renderer error'));return
    d=data.get('diagnostics')
    if not d or data.get('ready')!='true':return
    if phase==-1:
        if d.get('characterId')!=entries[index]['id']:return
        assert len(d['clips'])==136 and 'antenna' in d['bones'],d
        phase=0;phase_time=time.monotonic()
        view.page().runJavaScript("document.querySelector('#controls').style.display='none';window.setBrainState({action:'idle',yaw:.35});")
        return
    if time.monotonic()-phase_time<.6:return
    action=checks[phase]
    if d.get('action')!=action:return
    if d.get('nonFinite'):fail('Nonfinite bone transform');return
    if d.get('speechMeshes')!=4:fail('Missing mouth surfaces');return
    if not d.get('indicator'):fail('Missing antenna indicator');return
    if action=='idle':
        view.grab().save(str(out/(entries[index]['id']+'.png')))
        first=d['poseSignature']
    elif action=='wave':
        change=sum((x-y)**2 for x,y in zip(first,d['poseSignature']))**.5
        if change<.01:fail('Wave did not change pose');return
    if phase==len(checks)-1:
        report['characters'].append({'id':entries[index]['id'],'assetHash':d['assetHash'],'clips':len(d['clips']),'checked':checks,'meshes':d['meshes'],'triangles':d['triangles'],'antenna':d['indicator']['name'],'speechMeshes':d['speechMeshes']})
        print('PASS',entries[index]['id'],d['triangles'],'triangles',flush=True);next_character();return
    phase+=1;phase_time=time.monotonic()
    view.page().runJavaScript('window.setBrainState('+json.dumps({'action':checks[phase],'activity':'idle','yaw':.35})+');')
def tick():
    global pending
    if index<0 or index>=len(entries) or pending:return
    if time.monotonic()-started>35:fail('Timed out loading or playing character');return
    pending=True
    view.page().runJavaScript("JSON.stringify({ready:document.body?.dataset.ready,status:document.querySelector('#status')?.textContent,diagnostics:window.brainDiagnostics})",receive)
timer=QTimer();timer.setInterval(120);timer.timeout.connect(tick);timer.start();next_character();sys.exit(app.exec())
