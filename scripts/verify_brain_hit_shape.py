"""Check the real GPU silhouette, or expose native click-through test controls.

Uses disposable settings and production floating Companions. Requires the local
asset server; never opens the microphone or calls a cloud provider. --interactive
leaves a link-like button underneath the character canvas for OS-click QA.
"""
import argparse,json,os,sys,tempfile,time
from pathlib import Path
os.environ['PYTEST_CURRENT_TEST']='native-brain-outline-fixture'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPoint,Qt,QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication,QWidget,QLabel,QPushButton
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.displays import display_inventory

parser=argparse.ArgumentParser();parser.add_argument('--interactive',action='store_true');parser.add_argument('--output',type=Path,default=Path('/tmp/brain-hit-shape-check'));args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([]);app.setApplicationName('Brain Outline Check');app.setQuitOnLastWindowClosed(False)
mouse_events=[]
class TraceLink(QPushButton):
 def mousePressEvent(self,event):
  p=event.globalPosition();mouse_events.append({'receiver':'underlying-link','global':[p.x(),p.y()]})
  super().mousePressEvent(event)
folder=tempfile.TemporaryDirectory(prefix='brain-outline-');store=BrainStore(Path(folder.name));store.update_settings({'roaming':False,'follow_cursor':False,'wake_word_enabled':False,'voice_reply':False})
manager=BrainManager(store=store,start_services=False);entries=display_inventory();manager.configure_displays(entries[:1],entries);first=manager.companion
manager.playground.timer.stop()
for actor in (first,):actor.activity_timer.stop();actor.roam_timer.stop();actor.follow_timer.stop()
panel=QWidget();panel.setWindowTitle('Brain Outline Check');panel.resize(960,680);panel.move(180,100)
label=QLabel(panel);label.setGeometry(20,20,920,90)
link=TraceLink('Underlying link: transparent margins and gaps must reach this button',panel);link.setGeometry(40,190,880,420)
clicks=[];link_clicks=0
original=manager.toggle_talking
def talking(target=None):
 original(target);clicks.append({'actor':target,'recording':manager.listener.is_recording});snapshot()
manager.toggle_talking=talking

def layout_actors():
 for actor,x in ((first,500),):
  actor.move(panel.mapToGlobal(QPoint(x,250)))
  actor.model_view.sync_geometry()

def mode(name):
 manager.stop_talking()
 for actor in (first,):
  actor.stop_motion();actor.set_character_scale(.65 if name=='small' else 1.);actor._yaw=1. if name=='side' else 0.;actor.turn_target=actor._yaw
  actor.set_activity('idle')
 if name=='glow':
  manager._listening_actor_id=first.actor_id;manager._listening_source='voice';manager._session_actor_id=first.actor_id;manager._session_source='voice';manager.listener.start_recording();manager._refresh_actor_states()
 elif name in ('wave','walk','climb','fly','balloon'):first.play_action(name,duration=5,keep_orientation=True)
 layout_actors()

for i,name in enumerate(('front','side','wave','glow','small')):
 b=QPushButton(name.title(),panel);b.setGeometry(20+i*150,120,140,36);b.clicked.connect(lambda checked=False,n=name:mode(n))
quit_button=QPushButton('Finish',panel);quit_button.setGeometry(800,120,130,36);quit_button.clicked.connect(app.quit)

def clicked_link():
 global link_clicks
 link_clicks+=1;snapshot()
link.clicked.connect(clicked_link)

def snapshot():
 actors=[]
 for actor in (first,):
  r=actor.input_region;b=r.boundingRect();count=sum(rect.width()*rect.height() for rect in r)
  actors.append({'id':actor.actor_id,'canvas':[actor.x(),actor.y(),actor.width(),actor.height()],
                 'body':b.getRect(),'body_pixels':count,'shape_ready':actor.has_input_shape,'activity':actor.activity,
                 'input_transparent_visual':bool(actor.model_view.windowFlags() & Qt.WindowType.WindowTransparentForInput)})
 label.setText(f'Brain clicks: {len(clicks)} | Link clicks: {link_clicks} | Recording: {manager.listener.is_recording}\nNative input follows only the live character silhouette.')
 result={'actors':actors,'brain_clicks':clicks,'link_clicks':link_clicks,'cursor':[QCursor.pos().x(),QCursor.pos().y()],
         'mouse_events':mouse_events[-20:],'cloud_calls':manager.activity.metrics()['summary']['calls']}
 (args.output/'state.json').write_text(json.dumps(result,indent=2)+'\n');return result

def native_hit_probes(done):
 """Allow WindowServer to commit each pointer gate, then read its mouse target.

 Native setters commit on the next AppKit iteration; a synchronous query in the
 setter's callback reads the previous state. These probes never dispatch input.
 """
 if sys.platform!='darwin':done([]);return
 import AppKit,ctypes
 from dock_twoo.brain.mascot import mac_window
 router=manager.input_router;router.timer.stop()
 # Hold the sampled pose's native mask while WindowServer commits its input
 # gate. This is a test snapshot; the production renderer never pauses masks.
 paused=[]
 for actor in (first,):
  paused.append((actor,actor.motion_timer.isActive(),actor.model_view.bridge.blockSignals(True)))
  actor.motion_timer.stop()
 bounds=first.input_region.boundingRect();head=QPoint(bounds.center().x(),bounds.top()+bounds.height()//3)
 if not first.input_region.contains(head):
  head=next(QPoint(x,y) for y in range(bounds.top(),bounds.bottom()+1) for x in range(bounds.left(),bounds.right()+1)
            if first.input_region.contains(QPoint(x,y)))
 gap=next((QPoint(x,y) for y in range(bounds.center().y(),bounds.bottom()) for x in range(bounds.center().x()-8,bounds.center().x()+9)
           if not first.input_region.contains(QPoint(x,y))),QPoint(5,100))
 cases=iter([('margin',QPoint(5,first.height()//2),False),('body',head,True),('gap',gap,False)]);probes=[]
 def advance():
  try:name,local,want_body=next(cases)
  except StopIteration:
   for actor,moving,blocked in paused:
    actor.model_view.bridge.blockSignals(blocked)
    if moving:actor.motion_timer.start()
   router.enabled=True;router.sync(force=True);router.timer.start();done(probes);return
  point=first.pos()+local;router.enabled=True;router.sync(point,force=True);router.enabled=False
  def inspect():
   proxy,send=mac_window(first);expected=send(ctypes.c_long,proxy,'windowNumber')
   ids=[]
   for actor in (first,):
    window,message=mac_window(actor);ids.append(message(ctypes.c_long,window,'windowNumber'))
   top=AppKit.NSScreen.screens()[0].frame().size.height
   actual=AppKit.NSWindow.windowNumberAtPoint_belowWindowWithWindowNumber_((point.x(),top-point.y()),0)
   correct=actual==expected if want_body else actual not in ids
   probes.append({'point':name,'body_expected':want_body,'correct':correct,
                  'native_ignored':send(ctypes.c_bool,proxy,'ignoresMouseEvents')});advance()
  QTimer.singleShot(80,inspect)
 advance()

checks=['front','side','walk','wave','climb','fly','balloon','glow','small'];index=-1;phase=0.;started=time.monotonic();results=[];errors=[];pending=False

def finish():
 report={'success':not errors,'checks':results,'errors':errors,'cloud_calls':0,'microphone_opened':False}
 (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True);app.exit(0 if not errors else 1)

def tick():
 global index,phase,pending
 if not all(c.model_view.ready and c.has_input_shape for c in (first,)):
  if time.monotonic()-started>40:errors.append('Silhouette or renderer timed out');finish()
  return
 if args.interactive:snapshot();return
 now=time.monotonic()
 if index<0:index=0;mode(checks[index]);phase=now
 if pending or now-phase<1.:return
 pending=True
 def checked(raw):
  global index,phase,pending
  runtime=json.loads(raw)
  def verify(probes):
   global index,phase,pending
   state=snapshot();name=checks[index]
   try:
    actor=state['actors'][0];assert actor['input_transparent_visual'] and actor['shape_ready']
    assert 100<actor['body_pixels']<first.width()*first.height()*.55
    assert not first.input_region.contains(QPoint(2,first.height()//2))
    assert first.model_view.geometry().topLeft()==first.pos()
    if name=='side':assert actor['body'][2]<results[0]['body'][2]
    if name=='glow':assert not runtime['listeningAura'] and actor['body_pixels']<first.width()*first.height()*.35
    if sys.platform=='darwin':assert all(p['correct'] for p in probes),probes
    first.model_view.grab().save(str(args.output/(name+'.png')))
    results.append({'scenario':name,'body':actor['body'],'pixels':actor['body_pixels'],'mask_ms':runtime.get('inputShapeMilliseconds'),
                    'native_targets':probes})
   except Exception as exc:errors.append(f'{name}: {exc}')
   index+=1;pending=False
   if errors or index==len(checks):finish();return
   mode(checks[index]);phase=time.monotonic()
  native_hit_probes(verify)
 first.model_view.page().runJavaScript('JSON.stringify(window.brainDiagnostics)',checked)

if args.interactive:panel.show()
layout_actors();timer=QTimer();timer.setInterval(150);timer.timeout.connect(tick);timer.start();app.aboutToQuit.connect(manager.shutdown);exit_code=app.exec();folder.cleanup();raise SystemExit(exit_code)
