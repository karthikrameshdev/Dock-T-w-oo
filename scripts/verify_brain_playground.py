"""Exercise two actual GLB renderers and local choreography, without mic/cloud.

Requires the resident local asset server. Writes a contact sheet and JSON report
under --output. Uses disposable settings and closes only its own characters.
"""
import argparse,json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QImage,QPainter,QColor,QFont
from PySide6.QtWidgets import QApplication
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.displays import display_inventory
from dock_twoo.brain.playground import GROUP_ACTIVITIES

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('/tmp/brain-playground-check'));args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
folder=tempfile.TemporaryDirectory(prefix='brain-playground-')
store=BrainStore(Path(folder.name));store.update_settings({'roaming':False,'wake_word_enabled':False,'companion_visible':True})
manager=BrainManager(store=store,start_services=False)
entries=display_inventory();manager.configure_displays(entries[:1],entries)
first=manager.companion;second=manager.add_brain(first.screen_id)
manager.playground.arrange()
started=time.monotonic();phase_started=None;phase=-1;phase_captured=False;captures=[];errors=[];samples=0;overlaps=0
checks=['listening','queued','responding',*GROUP_ACTIVITIES]

def capture(name):
 bounds=first.geometry().united(second.geometry())
 image=QImage(max(620,bounds.width()+40),max(340,bounds.height()+72),QImage.Format.Format_ARGB32);image.fill(QColor('#0f171d'))
 painter=QPainter(image);painter.setPen(QColor('#e8f6ff'));painter.setFont(QFont('',14));painter.drawText(20,28,name)
 offset=(image.width()-bounds.width())//2
 for actor in (first,second):
  painter.drawPixmap(offset+actor.x()-bounds.x(),48+actor.y()-bounds.y(),actor.model_view.grab())
 painter.end();path=args.output/(name+'.png');image.save(str(path));captures.append(str(path))

def finish():
 report={'success':not errors,'errors':errors,'samples':samples,'body_overlap_samples':overlaps,
         'characters':len(manager.companions),'shared_service_objects':{'agent':1,'listener':1,'speech':1},
         'version':first.model_view.version,'asset_hash':first.model_view.asset_hash,
         'captures':captures,'cloud_calls':manager.activity.metrics()['summary']['calls']}
 (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
 manager.shutdown();app.exit(0 if not errors else 1)

def step():
 global phase,phase_started,phase_captured,samples,overlaps
 now=time.monotonic()
 if now-started>90:
  errors.append('Playground renderer timed out');finish();return
 if not all(c.model_view.ready for c in (first,second)):return
 if phase<0 or now-phase_started>5.5:
  if phase>=0 and not phase_captured:capture(checks[phase])
  phase+=1
  if phase>=len(checks):finish();return
  for c in (first,second):
   c.stop_motion();c.social_kind='';c.social_until=0;c.set_activity('idle')
  manager.playground._groups.clear();manager.playground.arrange()
  name=checks[phase]
  if name in ('listening','queued','responding'):
   manager._listening_actor_id=first.actor_id if name=='listening' else None
   manager._listening_source='voice' if name=='listening' else None
   first.set_activity({'responding':'speaking'}.get(name,name));second.set_activity('idle')
  else:manager.playground.play(name,first.actor_id)
  phase_started=now;phase_captured=False
 if now-phase_started>3.2 and not phase_captured:
  capture(checks[phase]);phase_captured=True
 samples+=1
 if manager.playground.region(first).intersects(manager.playground.region(second)):
  overlaps+=1
  errors.append('Body footprints overlap during '+checks[phase])
  finish()

timer=QTimer();timer.setInterval(33);timer.timeout.connect(step);timer.start()
app.exec();folder.cleanup()
