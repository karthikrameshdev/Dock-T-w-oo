"""Verify real Blender canopy timing together with native desktop descent."""
import argparse,json,os,sys,tempfile,time
from pathlib import Path
os.environ['PYTEST_CURRENT_TEST']='parachute-descent-fixture'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QImage,QPainter,QColor
from PySide6.QtWidgets import QApplication
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.displays import display_inventory
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('/tmp/brain-parachute-check'));args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([]);app.setQuitOnLastWindowClosed(False);folder=tempfile.TemporaryDirectory(prefix='brain-parachute-')
store=BrainStore(Path(folder.name));store.update_settings({'roaming':False,'wake_word_enabled':False,'voice_reply':False})
manager=BrainManager(store=store,start_services=False);entries=display_inventory();manager.configure_displays(entries[:1],entries);actor=manager.companion
manager.playground.timer.stop();actor.roam_timer.stop();area=actor.assigned_screen.availableGeometry();actor.move(area.center().x()-actor.width()//2,area.bottom()-actor.height()-20)
started=time.monotonic();launched=False;seen_fly=False;seen_descent=False;seen_land=False;pending=False;samples=[];errors=[];saved=set();captures=[]
def finish():
 descent=[s for s in samples if s['action']=='parachute']
 try:
  assert seen_fly and seen_descent and seen_land
  assert max(s['y'] for s in descent)-min(s['y'] for s in descent)>100
  assert all(a['y']<=b['y']+1 for a,b in zip(descent,descent[1:]))
  deployed=[s for s in descent if .2<s['progress']<.86]
  assert deployed and all(s['canopy']>.99 for s in deployed)
  landing=[s for s in descent if .87<s['progress']<.9]
  assert landing and all(abs(s['y']-s['destination_y'])<=1 and s['canopy']>.99 for s in landing)
  assert any(s['progress']>.96 and s['canopy']<.4 for s in descent)
 except Exception as exc:errors.append(str(exc) or 'Descent or canopy timing assertion failed')
 report={'success':not errors,'samples':samples,'errors':errors,'captures':captures,'cloud_calls':0,'microphone_opened':False}
 (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'success':report['success'],'samples':len(samples),'descent_pixels':max((s['y'] for s in descent),default=0)-min((s['y'] for s in descent),default=0),'errors':errors,'captures':captures},indent=2),flush=True)
 manager.shutdown();app.exit(0 if not errors else 1)
def tick():
 global launched,seen_fly,seen_descent,seen_land,pending
 now=time.monotonic()
 if now-started>25:errors.append('Flight timed out');finish();return
 if not actor.model_view.ready or not actor.has_input_shape:return
 if not launched:actor.play_action('parachute');launched=True
 action=actor.action;progress=min(1,max(0,(now-actor.motion_started)/actor.motion_duration))
 seen_fly |= action=='fly';seen_descent |= action=='parachute';seen_land |= action=='land'
 if seen_land and action is None:finish();return
 if pending:return
 pending=True
 current_y=actor.y();destination_y=actor.destination.y() if actor.destination is not None else current_y
 def read(raw):
  global pending
  data=json.loads(raw);canopy=data['propScales']['propparachute'];samples.append({'action':action,'progress':round(progress,3),'y':current_y,'destination_y':destination_y,'canopy':round(canopy,4)})
  stage='launch' if action=='fly' and progress>.6 else ('open' if action=='parachute' and .16<progress<.23 else ('descent' if action=='parachute' and .46<progress<.54 else ('landed-open' if action=='parachute' and .87<progress<.9 else ('stowed' if action=='land' else ''))))
  if stage and stage not in saved:
   saved.add(stage);image=QImage(area.width(),area.height(),QImage.Format.Format_ARGB32);image.fill(QColor('#19232a'));p=QPainter(image);p.setPen(QColor('#dbeafe'));p.drawText(20,30,f'{stage} · y={current_y}');p.drawPixmap(actor.x()-area.left(),actor.y()-area.top(),actor.model_view.grab());p.end();path=args.output/(stage+'.png');image.scaledToHeight(600).save(str(path));captures.append(str(path))
  pending=False
 actor.model_view.page().runJavaScript('JSON.stringify(window.brainDiagnostics)',read)
timer=QTimer();timer.setInterval(40);timer.timeout.connect(tick);timer.start();code=app.exec();folder.cleanup();raise SystemExit(code)
