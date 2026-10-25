"""Real Qt → Orbit → gRPC → parallel/nested/reused peers → Postman HTTP → documents/ledger.

Requires the repository's cloud simulation on 24930. No microphone, physical
input or live provider is opened. The source pages are clearly synthetic fixtures.
"""
import json,os,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));os.environ.setdefault('QT_QPA_PLATFORM','offscreen');os.environ.setdefault('PYTEST_CURRENT_TEST','ecosystem-fixture')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect,QTimer
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.cloud import CloudClient
from dock_twoo.brain.ecosystem.web import PublicWeb
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
folder=tempfile.TemporaryDirectory(prefix='dock-ecosystem-verification-');root=Path(folder.name)
store=BrainStore(root/'brain');store.update_settings({'voice_reply':False,'roaming':False,'wake_word_enabled':False})
manager=BrainManager(store=store,start_services=False);manager.listener.start=lambda:None
screen=SimpleNamespace(availableGeometry=lambda:QRect(0,0,1440,900),geometry=lambda:QRect(0,0,1440,900))
manager.configure_displays([{'id':'fixture-screen','screen':screen}])
a=manager.profile_mgr.save_profile({'name':'Primary fixture','provider':'custom','model':'fixture','base_url':'https://fixture.example/v1','api_key':'fixture-key'})
b=manager.profile_mgr.create_profile({'name':'Rio fixture','provider':'custom','protocol':'anthropic','model':'fixture','base_url':'https://fixture.example/v1','api_key':'fixture-key'})
manager.profile_mgr.activate_profile(a['id']);manager.profile_mgr.bind_character('default',b['id'])
manager.agent.client_factory=lambda config,key:CloudClient({**config,'base_url':'http://127.0.0.1:24930/cloud'},key,allow_test_endpoint=True,timeout=10)
manager.research_client=PublicWeb(search_url='http://127.0.0.1:24930/cloud/sources/search?q=',allow_test_endpoint=True)
started=time.monotonic();peak=0;result={};finished=False
manager.submit_request('Hey Orbit, peer-research','console','fixture-screen')
def tick():
 global peak,finished
 peak=max(peak,len(manager.coordinator.workers))
 if finished:return
 if time.monotonic()-started>40:
  result.update(success=False,error='Ecosystem verification timed out',agent=manager.agent.status());finish();return
 if manager.last_response['generation'] and not manager._active_turn and not manager._worker_running:
  try:
   jobs=manager.coordinator.snapshot()['jobs'];assert len(jobs)==5,jobs
   assert {job['character_id'] for job in jobs}=={'orbit','default','fox','owl'}
   assert all(job['state']=='complete' for job in jobs),jobs
   assert peak>=2,peak
   metrics=manager.activity.metrics();assert metrics['summary']['calls']==18,metrics['summary']
   assert metrics['summary']['total_tokens']==4880,metrics['summary']
   assert manager.activity.metrics(character_id='default')['summary']['total_tokens']==2480
   assert manager.activity.metrics(profile_id=a['id'])['summary']['total_tokens']==2400
   assert sum(row['total_tokens'] for row in metrics['characters'])==4880
   outputs=list((root/'brain/documents').rglob('*.md'));assert len(outputs)==4,outputs
   assert all(path.stat().st_size>40 for path in outputs)
   assert any(path.name=='peer-report.md' for path in outputs)
   events=manager.coordinator.snapshot()['events'];assert sum(e['kind']=='task_started' for e in events)==5
   assert len(manager.companions)==1 and manager.companion.character_id=='orbit'
   assert not manager.coordinator.workspaces
   result.update(success=True,agents=4,jobs=5,concurrent_workers=peak,model_calls=18,reported_tokens=4880,documents=len(outputs),grpc_events=len(events),single_visible_character=True,workspaces_released=True,live_provider_calls=0)
  except Exception as exc:result.update(success=False,error=repr(exc),agent=manager.agent.status())
  finish()
def finish():
 global finished
 finished=True;timer.stop();print(json.dumps(result,indent=2),flush=True);Path('/tmp/dock-ecosystem-verification.json').write_text(json.dumps(result,indent=2));manager.shutdown();app.exit(0 if result['success'] else 1)
timer=QTimer();timer.setInterval(25);timer.timeout.connect(tick);timer.start();app.exec();folder.cleanup()
