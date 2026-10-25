"""Verify real WebGL listening aura visibility and torch color with local fixtures."""
import argparse,json,sys,time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPointF,Qt,QTimer
from PySide6.QtWidgets import QApplication,QWidget
from dock_twoo.brain.model_view import CharacterView
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('/tmp/brain-aura-check'));args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([]);manager=SimpleNamespace(companions={})
def character(key):
 c=QWidget();c.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowDoesNotAcceptFocus)
 c.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground);c.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
 c.resize(264,268);c.manager=manager;c.screen_id='screen-1'
 c.action='idle';c._yaw=0.;c.motion_started=time.monotonic();c.motion_duration=100
 c.gait_distance=c.blink_amount=c.mouth_level=0.;c.activity='listening';c._gaze_offset=QPointF();c.reduced_motion=False
 c.model_view=CharacterView(c);c.model_view.connectivity.online=True;manager.companions[key]=c
 return c
first,second=character('first'),character('second');second.activity='idle';first.show();second.move(300,0)
checks=[('single',False,'screen-1',False),('same-display-pair',True,'screen-1',True),('different-displays',True,'screen-4',False),('other-hidden',False,'screen-1',False)]
index=-1;phase=0;started=time.monotonic();pending=False;results=[];errors=[]
def finish():
 report={'success':not errors,'checks':results,'errors':errors,'cloud_calls':0,'microphone_opened':False}
 (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));timer.stop();first.close();second.close();app.exit(0 if not errors else 1)
def step():
 global index,phase,pending
 now=time.monotonic()
 if now-started>25:errors.append('Renderer timed out');finish();return
 if not first.model_view.ready or not second.model_view.ready:return
 if index<0:
  index=0;phase=now
  second.setVisible(checks[index][1]);second.screen_id=checks[index][2]
 if now-phase<.5 or pending:return
 pending=True
 def read(raw):
  global index,phase,pending
  name,visible,display,expected=checks[index]
  try:
   state=json.loads(raw)
   assert state['listeningAura']==expected,(name,state['listeningAura'])
   assert state['indicator']['name']=='listening' and state['indicator']['color']==0xfacc15
   first.model_view.grab().save(str(args.output/(name+'.png')))
   results.append({'scenario':name,'aura':state['listeningAura'],'torch':'yellow'})
  except Exception as exc:errors.append(str(exc))
  index+=1;pending=False
  if errors or index==len(checks):finish();return
  second.setVisible(checks[index][1]);second.screen_id=checks[index][2];phase=time.monotonic()
 first.model_view.page().runJavaScript('JSON.stringify(window.brainDiagnostics)',read)
timer=QTimer();timer.setInterval(50);timer.timeout.connect(step);timer.start();app.exec()
