"""Render the native Dashboard with isolated synthetic cloud usage; no microphone/API key."""
from pathlib import Path
import sys,tempfile,time,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication
from dock_twoo.config import ConfigManager
from dock_twoo.server import WebConsoleServer
from dock_twoo.brain.activity import ActivityStore
from dock_twoo.ui.apps.dashboard_app import DashboardAppWidget
from datetime import datetime,timedelta

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([])
folder=tempfile.TemporaryDirectory(prefix='brain-usage-render-fixture-')
config=ConfigManager(config_path=Path(folder.name)/'config.json')
config.update({'storage_path':str(Path(folder.name)/'storage'),'server_port':24941,'theme_mode':'dark'})
clock=[datetime.now().astimezone()]
store=ActivityStore(config.config.get_brain_dir()/'activity',clock=lambda:clock[0])
for offset in range(7):
 clock[0]=datetime.now().astimezone()-timedelta(days=offset)
 run=store.start('SYNTHETIC UI VERIFICATION: read work log','console')
 call=store.begin_call(run,{'provider':'fixture','model':'test-model'},{'messages':[{'role':'user','content':'fixture'}]})
 store.end_call(call,{'usage':{'prompt_tokens':900+offset*150,'completion_tokens':100+offset*20,'total_tokens':1000+offset*170}},'openai',latency_ms=220+offset*30)
 store.finish(run,'complete','Synthetic response.')
server=WebConsoleServer(config);server.start()
widget=DashboardAppWidget(config.config);widget.title_label.setText('Dashboard · test data');widget.setWindowTitle('Dashboard · synthetic verification')
widget.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.WindowDoesNotAcceptFocus)
widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
widget.setStyleSheet('DashboardAppWidget {background:#0b0f17;}');widget.resize(390,880);widget.show()
started=time.monotonic();pending=False;result={}
def sample():
 global pending
 if pending:return
 pending=True
 def state(value):
  global pending
  pending=False
  try:value=json.loads(value) if isinstance(value,str) and value else value
  except ValueError:pass
  if value and value.get('cards')==6 and value.get('charts')==4 and not value.get('loading'):
   widget.grab().save('/tmp/brain-usage-native.png');result.update(value);app.quit()
  elif time.monotonic()-started>20:
   widget.grab().save('/tmp/brain-usage-native-failure.png');result.update({'error':'Dashboard did not finish loading','state':value,'url':widget.view.url().toString()});app.quit()
 widget.view.page().runJavaScript("JSON.stringify({cards:document.querySelectorAll('.usage-kpi').length,charts:document.querySelectorAll('svg').length,loading:(document.body?.innerText||'').includes('Loading cloud usage'),text:(document.body?.innerText||'').slice(0,600)})",state)
timer=QTimer();timer.timeout.connect(sample);timer.start(350)
app.exec();print(result,flush=True)
widget.close();server.stop();folder.cleanup()
if 'error' in result:raise SystemExit(1)
