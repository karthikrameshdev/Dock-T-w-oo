"""Thirty independent embedded WebGL scenes; no mic, cloud calls or user settings."""
import argparse,json,sys,time
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QUrl
from PySide6.QtWidgets import QApplication,QWidget,QGridLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dock_twoo.brain.catalog import characters,character
p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=24942);p.add_argument('--count',type=int,default=30);args=p.parse_args()
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([]);root=QWidget();root.setWindowTitle('Voice Assistant · isolated character verification');root.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating);root.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus);root.resize(1000,800);layout=QGridLayout(root)
views=[];results={};errors=[];started=time.monotonic();changed_at=0;phase=0
entries=characters()[:args.count]
for i,entry in enumerate(entries):
 view=QWebEngineView(root);layout.addWidget(view,i//6,i%6);view.load(QUrl(f"http://127.0.0.1:{args.port}/brain3d/index.html?embedded&character={entry['id']}"));views.append(view)
root.show()
def finish():
 timer.stop();report={'success':not errors,'renderers':len(results),'independent_scenes':len(views),'cloud_calls':0,'errors':errors,'characters':results}
 Path('/tmp/dock-named-renderers.json').write_text(json.dumps(report,indent=2));root.grab().save('/tmp/dock-named-renderers.png');print(json.dumps({k:v for k,v in report.items() if k!='characters'}),flush=True);root.close();app.exit(0 if not errors else 1)
def receive(entry,data):
 global phase,changed_at
 if not data:return
 d=json.loads(data)
 if d.get('characterId')!=entry['id']:return
 if d.get('nonFinite'):errors.append(entry['id']+': nonfinite pose');finish();return
 if phase==0:
  if entry['id'] not in results:print('READY',entry['name'],flush=True)
  results[entry['id']]={'name':entry['name'],'clips':len(d['clips']),'first':d.get('poseSignature'),'frames':d['renderedFrames']}
  if len(results)==len(views):
   phase=1;changed_at=time.monotonic()
   for v,e in zip(views,entries):
    actions=character(e['id'])['actions'];species=[k for k,m in actions.items() if m['category']=='species'];action=species[0] if species else ('wave' if e['index']%2 else 'walk')
    results[e['id']]['action']=action
    v.page().runJavaScript('window.setBrainState('+json.dumps({'action':action,'progress':.4,'distance':24+e['index'],'yaw':.3})+');')
 elif phase==1 and time.monotonic()-changed_at>2:
  r=results[entry['id']]
  if d['action']!=r['action'] or d['renderedFrames']<=r['frames']:return
  first=r['first'];r['pose_changed']=any(abs(x-y)>1e-4 for x,y in zip(first,d['poseSignature']));r['frames']=d['renderedFrames'];r['indicator']=bool(d.get('indicator'));r.pop('first',None)
  if all('pose_changed' in r for r in results.values()):
   errors.extend(k+': action did not change pose' for k,r in results.items() if not r['pose_changed'] or not r['indicator'] or r['clips']!=136);finish()
def tick():
 if time.monotonic()-started>100:errors.append('Timed out: '+','.join(e['name'] for e in entries if e['id'] not in results));finish();return
 for view,entry in zip(views,entries):
  if phase==1 and 'pose_changed' in results.get(entry['id'],{}):continue
  view.page().runJavaScript('window.brainDiagnostics && JSON.stringify(window.brainDiagnostics)',lambda value,e=entry:receive(e,value))
timer=QTimer();timer.setInterval(300);timer.timeout.connect(tick);timer.start();sys.exit(app.exec())
