"""Real local HTTP → shared Qt queue → Postman provider → per-profile ledger.

Start the existing cloud simulation on port 24930 first. This opens no microphone
and sends no live-provider request. Settings, tasks and credentials are fixtures.
"""
import json,os,sys,tempfile,threading,time,urllib.request
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect,QTimer
from dock_twoo.config import ConfigManager
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.cloud import CloudClient
from dock_twoo.server import WebConsoleServer

app=QApplication([]);app.setQuitOnLastWindowClosed(False)
folder=tempfile.TemporaryDirectory(prefix='brain-queue-http-');root=Path(folder.name)
config=ConfigManager(root/'config.json');config.update({'storage_path':str(root/'data'),'server_port':24941})
store=BrainStore(root/'data/brain');store.update_settings({'voice_reply':False,'roaming':False,'wake_word_enabled':False})
manager=BrainManager(store=store,start_services=False);BrainManager._instance=manager
# Isolate physical audio only; HTTP, queue, agent, tools and ledger remain real.
manager.listener.start=lambda:None
entries=[{'id':f'screen-{n}','screen':SimpleNamespace(availableGeometry=lambda x=x:QRect(x,0,1200,800),geometry=lambda x=x:QRect(x,0,1200,800))} for n,x in ((1,0),(4,3600))]
manager.configure_displays(entries,entries)
config.display_snapshot={'displays':[{'id':e['id'],'selected':True} for e in entries]}
base={'provider':'custom','model':'fixture-model','base_url':'https://fixture.example/v1','api_key':'fixture-key'}
a=manager.profile_mgr.save_profile({**base,'name':'Everyday'})
b=manager.profile_mgr.create_profile({**base,'name':'Research','protocol':'anthropic'})
entered=threading.Event();release=threading.Event();captured=[];errors=[];result={};started=time.monotonic()
def factory(profile,key):
 captured.append(profile['id'])
 if len(captured)==1:entered.set();release.wait(5)
 return CloudClient({**profile,'base_url':'http://127.0.0.1:24930/cloud'},key,timeout=5,allow_test_endpoint=True)
manager.agent.client_factory=factory
server=WebConsoleServer(config);server.start()
def post(text,screen):
 request=urllib.request.Request('http://127.0.0.1:24941/api/brain/request',data=json.dumps({'text':text,'screen_id':screen}).encode(),headers={'X-Brain-Request':'local'})
 with urllib.request.urlopen(request,timeout=3) as response:assert response.status==202

def client():
 try:
  post('record-work','screen-1');assert entered.wait(3)
  manager.profile_mgr.activate_profile(b['id']);post('recall-work','screen-4')
  manager.profile_mgr.activate_profile(a['id']);release.set()
 except Exception as exc:errors.append(str(exc));release.set()
threading.Thread(target=client,daemon=True).start()

def check():
 if time.monotonic()-started>20:errors.append('Queue verification timed out')
 if errors or (len(captured)==2 and not manager._active_turn and not manager._turn_queue):
  try:
   metrics=manager.activity.metrics()
   assert captured==[a['id'],b['id']],captured
   assert metrics['summary']['calls']==4 and metrics['summary']['total_tokens']==1100,metrics['summary']
   assert manager.activity.metrics(profile_id=a['id'])['summary']['total_tokens']==480
   assert manager.activity.metrics(profile_id=b['id'])['summary']['total_tokens']==620
   assert len(manager.activity.list()['runs'])==2
   assert not manager.queue_status()['worker_running']
   result.update(success=not errors,http_model_calls=4,cloud_tokens=1100,queued_profile_frozen=True,display_ids=['screen-1','screen-4'],shared_agent_instances=1,live_cloud_calls=0,errors=errors)
  except Exception as exc:errors.append(str(exc));result.update(success=False,errors=errors)
  timer.stop();print(json.dumps(result,indent=2),flush=True);manager.shutdown();app.exit(0 if result['success'] else 1)
timer=QTimer();timer.setInterval(30);timer.timeout.connect(check);timer.start();app.exec();server.stop();folder.cleanup()
