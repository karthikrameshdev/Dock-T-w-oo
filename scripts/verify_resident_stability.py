"""Native crowd soak: real renderers and OS clicks, isolated data/no mic or provider.

Run with --seconds 600. The production app should be stopped to avoid testing
against a second dock. Writes bounded evidence in the OS temporary directory.
"""
import argparse,json,os,random,sys,tempfile,threading,time
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['PYTEST_CURRENT_TEST']='resident-stability'
from PySide6.QtCore import QPoint,QTimer,Qt,QObject,QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.config import ConfigManager
import dock_twoo.config as config_module
from dock_twoo.displays import display_inventory
from dock_twoo.ui.lifecycle import GuiGarbageCollector
from dock_twoo.os_integration.margin_manager import DesktopMarginManager

parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=600)
parser.add_argument('--interval',type=int,default=45)
parser.add_argument('--output',type=Path,default=Path(tempfile.gettempdir())/'dock-resident-stability.json')
parser.add_argument('--keep-on-failure',action='store_true');args=parser.parse_args()
args.output.parent.mkdir(parents=True,exist_ok=True)
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([]);app.setApplicationName('Dock2 Stability Check');app.setQuitOnLastWindowClosed(False)
gc=GuiGarbageCollector(app)
folder=tempfile.TemporaryDirectory(prefix='dock-soak-');root=Path(folder.name)
class QuietHandler(SimpleHTTPRequestHandler):
 def log_message(self,*_):pass
server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(Path(__file__).resolve().parents[1]/'dock_twoo/server/static')))
threading.Thread(target=server.serve_forever,daemon=True).start()
config=ConfigManager(root/'config.json');config.config.storage_path=str(root/'storage');config.config.server_port=server.server_port
config.config.reserve_screen_space=False;config.config.theme_mode='dark'
# No desktop icon repositioning or external app resizing in this fixture.
DesktopMarginManager.start=lambda self:None
config_module.ConfigManager=lambda:config
manager=BrainManager(store=BrainStore(root/'brain'),start_services=False);BrainManager._instance=manager
manager.store.update_settings({'roaming':False,'wake_word_enabled':False,'voice_reply':False,'character_sounds':False})
manager.listener.start=lambda:None
entries=display_inventory();manager.configure_displays(entries[:1],entries);manager.add_all_characters()
from dock_twoo.ui.dock_window import DockWindow
dock=DockWindow(config,screen_id=entries[0]['id']);dock.show()
for actor in manager.companions.values():actor.roam_timer.stop()
actors=list(manager.companions.values());brain=manager.companion
started=time.monotonic();ready_at=None;last_tick=started;last_cycle=-999;last_action=0;testing=False;finished=False
lags=[];cycles=0;errors=[];samples=[];hidden_test=False;crash_test=False;hidden_frames={}
click_point=QPoint();events=[]
class InputTrace(QObject):
 def eventFilter(self,obj,event):
  if event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonRelease):
   events.append({'target':obj.objectName(),'type':str(event.type()),'at':time.monotonic()})
   del events[:-100]
  return False
trace=InputTrace(app)
for name,widget in [('tasks',dock._icon_buttons['tasks']),('close',dock.attached_window._apps['tasks'].close_btn)]:
 widget.setObjectName(name);widget.installEventFilter(trace)

def input_snapshot():
 from PySide6.QtWidgets import QWidget
 from dock_twoo.brain.mascot import mac_window
 import ctypes
 def describe(widget):
  if widget is None:return None
  data={'class':type(widget).__name__,'name':widget.objectName(),'visible':widget.isVisible(),'geometry':widget.geometry().getRect()}
  if sys.platform=='darwin':
   window,message=mac_window(widget.window())
   if window:
    data.update(ignored=message(ctypes.c_bool,window,'ignoresMouseEvents'),level=message(ctypes.c_long,window,'level'))
  return data
 data={'point':[click_point.x(),click_point.y()],'grabber':describe(QWidget.mouseGrabber()),'popup':describe(app.activePopupWidget()),
       'hit':describe(app.widgetAt(click_point)),'events':events[-20:],'actors':[]}
 for actor in actors:
  data['actors'].append({'actor':actor.character_id,'window':describe(actor),'visual':describe(actor.model_view),
                        'origin':str(actor.origin),'hits':actor.input_region.contains(click_point-actor.pos())})
 if sys.platform=='darwin':
  import Quartz as Q
  data['windows']=[dict(w) for w in Q.CGWindowListCopyWindowInfo(Q.kCGWindowListOptionOnScreenOnly,Q.kCGNullWindowID) if w.get('kCGWindowOwnerPID')==os.getpid()]
 (args.output.parent/'dock-resident-input-failure.json').write_text(json.dumps(data,indent=2,default=str))
 app.primaryScreen().grabWindow(0).save(str(args.output.parent/'dock-resident-input-failure.png'))

def fail(message):
 errors.append(message);print('FAIL',message,flush=True);input_snapshot()
 if args.keep_on_failure:timer.stop()
 else:finish()

def finish():
 global finished
 if finished:return
 finished=True;timer.stop()
 result={'success':not errors,'seconds':round(time.monotonic()-(ready_at or started),1),'characters':len(actors),
         'native_click_cycles':cycles,'input': 'OS mouse events' if sys.platform=='darwin' else 'Qt mouse events',
         'max_event_loop_delay_ms':round(max(lags or [0])*1000,1),'renderer_samples':samples[-90:],
         'hidden_freeze_checked':hidden_test,'renderer_restart_checked':crash_test,'errors':errors,'cloud_calls':0,'microphone_opened':False}
 args.output.write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='renderer_samples'}),flush=True)
 dock.close();manager.shutdown();server.shutdown();gc.stop(restore=False);app.exit(1 if errors else 0)

def click(widget,point=None,done=None):
 global click_point
 point=point or widget.rect().center();global_point=widget.mapToGlobal(point)
 click_point=global_point
 if sys.platform=='darwin':
  import Quartz as Q
  xy=(global_point.x(),global_point.y())
  def post(kind):Q.CGEventPost(Q.kCGHIDEventTap,Q.CGEventCreateMouseEvent(None,kind,xy,Q.kCGMouseButtonLeft))
  post(Q.kCGEventMouseMoved)
  QTimer.singleShot(80,lambda:post(Q.kCGEventLeftMouseDown))
  QTimer.singleShot(160,lambda:post(Q.kCGEventLeftMouseUp))
 else:QTest.mouseClick(widget,Qt.MouseButton.LeftButton,pos=point)
 if done:QTimer.singleShot(800,done)

def interaction_cycle():
 global testing
 testing=True;manager.stop_talking();brain.stop_motion()
 for a in actors:a.last_dragged=time.monotonic()
 def opened():
  if not dock.attached_window.is_showing_app('tasks'):return fail('Native dock click did not open Tasks')
  # Deliberately put a character's head behind the close control. Native mask
  # changes must never promote that invisible body above the interactive drawer.
  blocker=next(a for a in actors if a.character_id=='pixel')
  blocker.stop_motion()
  head=blocker.input_region.boundingRect().center()
  if not blocker.input_region.contains(head):return fail('Blocker fixture has no central body pixel')
  target=dock.attached_window._apps['tasks'].close_btn.mapToGlobal(dock.attached_window._apps['tasks'].close_btn.rect().center())
  blocker.move(target-head)
  if blocker.input_hit_region().contains(target-blocker.pos()):return fail('Character intercepts an open control surface')
  click(dock.attached_window._apps['tasks'].close_btn,done=closed)
 def closed():
  if dock.attached_window.isVisible():return fail('Native Tasks close click was swallowed')
  bounds=brain.input_region.boundingRect()
  points=[QPoint(x,y) for y in range(bounds.top(),bounds.bottom()+1) for x in range(bounds.left(),bounds.right()+1) if brain.input_region.contains(QPoint(x,y))]
  if not points:return fail('Brain has no clickable body')
  target=min(points,key=lambda p:(p-(bounds.topLeft()+QPoint(bounds.width()//2,bounds.height()//3))).manhattanLength())
  click(brain,target,listening)
 def listening():
  if not manager.listener.is_recording or brain.activity!='listening':return fail('Native character click did not start listening')
  # Finish via a second real click on the now stable head.
  b=brain.input_region.boundingRect();p=b.center()
  if not brain.input_region.contains(p):p=QPoint(b.center().x(),b.top()+b.height()//3)
  click(brain,p,completed)
 def completed():
  global testing,cycles
  if manager.listener.is_recording:return fail('Second character click did not finish listening')
  manager.stop_talking();cycles+=1;testing=False
  print(f'PASS native input cycle {cycles}, elapsed {time.monotonic()-ready_at:.1f}s',flush=True)
 if dock.attached_window.isVisible():dock.attached_window.hide_window()
 click(dock._icon_buttons['tasks'],done=opened)

def diagnostics(actor,label='sample',done=None):
 def receive(raw):
  if finished:return
  value=json.loads(raw) if raw else {}
  samples.append({'character':actor.character_id,'label':label,**value})
  if value.get('active',0)>2 or value.get('cached',0)>2:return fail('Animation mixer retained old clips')
  if done:done(value)
 actor.model_view.page().runJavaScript('JSON.stringify({frames:window.brainDiagnostics?.renderedFrames,active:window.brainDiagnostics?.activeActions,cached:window.brainDiagnostics?.cachedActions})',receive)

def tick():
 global ready_at,last_tick,last_cycle,last_action,hidden_test,crash_test,testing
 now=time.monotonic();lag=now-last_tick-.05;last_tick=now
 if ready_at is None:
  if all(a.model_view.ready and a.has_input_shape and not a.input_region.isEmpty() for a in actors):
   ready_at=now;manager.playground.arrange();print('30 real renderers ready',flush=True)
  elif now-started>150:fail('Renderer startup timed out')
  return
 lags.append(max(0,lag))
 elapsed=now-ready_at
 if elapsed>=args.seconds and not testing:return finish()
 if not testing and now-last_cycle>=args.interval:
  last_cycle=now;interaction_cycle();return
 if not testing and now-last_action>=4:
  last_action=now
  for actor in actors:
   choices=[k for k in actor.actions if k in ('wave','walk','run','dance','nod','clap','stretch','kick_ball','hammer')]
   actor.play_action(random.choice(choices))
  diagnostics(random.choice(actors))
 if not testing and elapsed>args.seconds*.4 and not hidden_test:
  testing=True;target=actors[-1]
  def before(value):
   hidden_frames.update(value);target.hide()
   def check():
    if target.model_view.timer.isActive():return fail('Hidden view still sends updates')
    from PySide6.QtWebEngineCore import QWebEnginePage
    if target.model_view.page().lifecycleState()!=QWebEnginePage.LifecycleState.Frozen:return fail('Hidden page was not frozen')
    target.show()
    def resumed():
     if not target.model_view.ready:return fail('Shown character did not resume')
     def verify(value):
      global testing,hidden_test
      if value.get('frames',0)<=hidden_frames.get('frames',0):return fail('Shown character stopped drawing')
      hidden_test=True;testing=False;print('PASS hidden freeze/resume',flush=True)
     diagnostics(target,'after_show',verify)
    QTimer.singleShot(1200,resumed)
   QTimer.singleShot(2500,check)
  diagnostics(target,'before_hide',before)
 if not testing and elapsed>args.seconds*.65 and not crash_test and sys.platform!='win32':
  testing=True;target=actors[-1];pid=target.model_view.page().renderProcessPid()
  if pid<=0 or pid==os.getpid():return fail('No isolated test renderer process to terminate')
  os.kill(pid,9)
  def recovered():
   global testing,crash_test
   if not target.model_view.ready or target.model_view.error or target.input_region.isEmpty():return fail('Crashed renderer did not recover')
   if target.model_view.page().renderProcessPid()==pid:return fail('Renderer process was not replaced')
   crash_test=True;testing=False;print('PASS isolated renderer recovery',flush=True)
  QTimer.singleShot(18000,recovered)
timer=QTimer();timer.timeout.connect(tick);timer.start(50)
exit_code=app.exec();folder.cleanup();sys.exit(exit_code)
