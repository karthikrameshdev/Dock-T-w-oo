"""Check all console select bindings in a native web view using isolated data."""
from pathlib import Path
import json,os,sys,tempfile,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt,QTimer,QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from dock_twoo.config import ConfigManager
from dock_twoo.server import WebConsoleServer

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([])
folder=tempfile.TemporaryDirectory(prefix='brain-console-controls-')
os.environ['DOCK_TWOO_BRAIN_DATA_DIR']=str(Path(folder.name)/'brain')
config=ConfigManager(config_path=Path(folder.name)/'config.json')
config.update({'server_port':24945,'storage_path':str(Path(folder.name)/'storage')})
server=WebConsoleServer(config);server.start()
view=QWebEngineView();view.setWindowTitle('Console · isolated control verification')
view.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.WindowDoesNotAcceptFocus)
view.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
view.resize(1100,850);view.setUrl(QUrl('http://127.0.0.1:24945/'));view.show()
started=time.monotonic();pending=False;result={}
script="""JSON.stringify({selects:document.querySelectorAll('select:not([multiple])').length,enhanced:document.querySelectorAll('.custom-dropdown-trigger').length,missing:[...document.querySelectorAll('select:not([multiple])')].filter(el=>!el._hasCustomDropdown||getComputedStyle(el).opacity!=='0').map(el=>el.id),animations:document.querySelector('#brainCharacterAction')?.options.length||0,searchHeight:document.querySelector('.search-box')?.getBoundingClientRect().height||0})"""
def check():
 global pending
 if pending:return
 pending=True
 def receive(value):
  global pending
  pending=False
  try:data=json.loads(value) if value else {}
  except ValueError:data={}
  if data.get('selects',0)>=12 and data.get('animations',0)>=30:
   result.update(data)
   result['success']=data['selects']==data['enhanced'] and not data['missing'] and data['searchHeight']>=46
   app.quit()
  elif time.monotonic()-started>20:result.update(error='Console controls did not initialize',state=data);app.quit()
 view.page().runJavaScript(script,receive)
timer=QTimer();timer.timeout.connect(check);timer.start(250)
app.exec();view.close();server.stop();folder.cleanup();print(json.dumps(result),flush=True)
if not result.get('success'):raise SystemExit(1)
