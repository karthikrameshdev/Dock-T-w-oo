"""Qt/agent/real HTTP tool calls → persisted reminder → due alert → shared speech lane.
Run the Postman cloud simulation on port 24930 first. No live provider or microphone.
"""
import json,os,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen');os.environ['PYTEST_CURRENT_TEST']='reminder-simulation'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.cloud import CloudClient
from tests.test_multi_brain import inventory
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
folder=tempfile.TemporaryDirectory(prefix='dock-reminder-verify-');root=Path(folder.name)
manager=BrainManager(store=BrainStore(root/'brain'),start_services=False)
manager.configure_displays(inventory()[1:2]);manager.store.set_setting('voice_reply',False)
manager.listener.start=lambda:None
profile=manager.profile_mgr.save_profile({'name':'Reminder fixture','provider':'custom','model':'fixture','base_url':'https://fixture.example/v1','api_key':'fixture-key'})
manager.profile_mgr.activate_profile(profile['id'])
manager.agent.client_factory=lambda cfg,key:CloudClient({**cfg,'base_url':'http://127.0.0.1:24930/cloud'},key,allow_test_endpoint=True,timeout=10)
spoken=[]
manager.speech.start=lambda text:spoken.append((manager.companion.character_id,text))
from dock_twoo.brain.catalog import character
manager.submit_request('Hey '+character('fox')['name']+', reminder-fixture','console')
started=time.monotonic();result={}
def finish():
 print(json.dumps(result,indent=2),flush=True)
 Path('/tmp/dock-reminder-agent-verification.json').write_text(json.dumps(result,indent=2))
 timer.stop();manager.shutdown();app.exit(0 if result.get('success') else 1)
def check():
 if time.monotonic()-started>20:result.update(success=False,error='Timed out');finish();return
 if manager.last_response['generation'] and not manager._processing_turns and not manager._active_turn:
  try:
   rows=manager.reminders.store.list();assert len(rows)==1 and rows[0]['character_id']=='fox',rows
   row=rows[0];alerts=manager.reminders.store.poll(row['next_due']-300)
   assert len(alerts)==1 and alerts[0]['lead']==300
   manager.reminders.deliver(alerts)
   assert manager.reminders.toast.isVisible()
   manager.reminders._speak_next()
   assert spoken and spoken[0][0]=='fox' and 'Synthetic meeting' in spoken[0][1],spoken
   assert manager.activity.metrics()['summary']['calls']==2
   result.update(success=True,provider_calls=2,live_provider_calls=0,character='fox',persistent_reminders=1,notification_visible=True,spoken_reply_queued=True)
  except Exception as exc:result.update(success=False,error=repr(exc))
  finish()
timer=QTimer();timer.timeout.connect(check);timer.start(50);app.exec();folder.cleanup()
