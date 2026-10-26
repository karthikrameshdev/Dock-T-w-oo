"""Native cap/toast/renderer + generated speech -> real KWS/VAD/ASR -> HTTP -> TTS.

Uses isolated settings and the Postman fixture. No microphone input or hardware
speaker output is opened; the speech PCM and lip envelopes are real local models.
"""
import json,os,sys,tempfile,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['PYTEST_CURRENT_TEST']='responsive-native'
import numpy as np
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication
from dock_twoo.config import ConfigManager
import dock_twoo.config as config_module
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.cloud import CloudClient
from dock_twoo.brain.local_tts import get_local_tts
from dock_twoo.brain.audio_devices import MicrophoneConverter
from dock_twoo.displays import display_inventory
from dock_twoo.server import WebConsoleServer
from dock_twoo.os_integration.margin_manager import DesktopMarginManager
from dock_twoo.ui.lifecycle import GuiGarbageCollector
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([]);app.setQuitOnLastWindowClosed(False);app.setApplicationName('Assistant responsiveness check');gc=GuiGarbageCollector(app)
folder=tempfile.TemporaryDirectory(prefix='dock-response-');root=Path(folder.name)
config=ConfigManager(root/'config.json');config.config.storage_path=str(root/'storage');config.config.server_port=24947;config.config.reserve_screen_space=False
config_module.ConfigManager=lambda:config;DesktopMarginManager.start=lambda self:None
manager=BrainManager(store=BrainStore(config.config.get_voice_dir()),start_services=False,voice_model_dir=Path.home()/'.dock2/brain/models');BrainManager._instance=manager
manager.store.update_settings({'roaming':False,'follow_cursor':False,'voice_reply':True,'wake_word_enabled':True,'character_sounds':False})
assert manager.store.setting('resource_cap_enabled') is False
manager.set_resource_cap(True);manager.listener.start=lambda:None
entries=display_inventory();manager.configure_displays(entries[:1],entries)
manager.profile_mgr.save_profile({'provider':'custom','model':'fixture','base_url':'https://fixture.example/v1','api_key':'fixture-key'})
manager.agent.client_factory=lambda config,key:CloudClient({**config,'base_url':'http://127.0.0.1:24930/cloud'},key,allow_test_endpoint=True,timeout=10)
server=WebConsoleServer(config);server.start()
from dock_twoo.ui.dock_window import DockWindow
dock=DockWindow(config,screen_id=entries[0]['id']);dock.show()
engine=get_local_tts();assert engine.load(allow_download=False),engine.error
assert manager.listener.wake_detector.load(allow_download=False),manager.listener.wake_detector.error
assert manager.listener.models.recognizer.load(allow_download=False),manager.listener.models.recognizer.error
assert manager.listener.endpoint_vad.load(allow_download=False),manager.listener.endpoint_vad.error
manager.listener._transcribe_pcm=manager.listener.models.recognizer.transcribe
played=[];mouth=[];states=set();toasts=[];results=[];errors=[];samples=[]
manager.speech.mouth.connect(lambda value:mouth.append(value))
def playback(clip,cancel,frame,align):
    played.append(clip.frames);align(time.monotonic())
    for cursor in range(0,clip.frames,max(1,int(clip.rate*.02))):
        if cancel.wait(.02):break
        frame(cursor)
manager.audio_devices.play=playback
started=time.monotonic();sent=0;last_done=0;pending=False;finished=False;last_tick=started;lags=[]
identities=[('default','Brain'),('parrot','Rio')]
def feed(name):
    try:
        listener=manager.listener;listener.arm_wake();listener.set_output_active(False)
        clip=engine.clip('Hey '+name+', open my notes.',threading.Event());chunks=MicrophoneConverter(clip.rate).feed(np.frombuffer(clip.pcm,dtype='<i2').astype(np.float32)/32768)
        samples=np.concatenate((np.zeros(4800,dtype='<i2'),np.frombuffer(b''.join(chunks),dtype='<i2'),np.zeros(40000,dtype='<i2')))
        for offset in range(0,len(samples),1600):listener._handle_pcm_frame(samples[offset:offset+1600].tobytes());time.sleep(.025)
    except Exception as exc:errors.append(repr(exc))
def finish():
    global finished
    if finished:return
    finished=True;timer.stop()
    try:
        assert len(results)==2,results
        assert len(manager.companions)==1
        assert max(mouth or [0])>.1 and len(played)>=2, {"clips":len(played), "mouth":max(mouth or [0])}
        assert samples and all(sample.get('faceOnly') for sample in samples),[sample for sample in samples if not sample.get('faceOnly')][:3]
        assert any('working' in text for text in toasts) and any('finished' in text for text in toasts),toasts
        assert dock.attached_window.is_showing_app('notes')
        manager.set_resource_cap(False);manager.companion.play_action('wave')
        assert not manager.store.setting('resource_cap_enabled')
    except Exception as exc:errors.append(repr(exc))
    report={'success':not errors,'named_requests':results,'tts_clips':len(played),'mouth_frames':len(mouth),'max_mouth':max(mouth or [0]),'renderer_samples':len(samples),'toasts':list(dict.fromkeys(toasts)),'states':sorted(states),'max_gui_delay_ms':round(max(lags or [0])*1000),'errors':errors,'live_provider_calls':0,'physical_microphone_opened':False,'hardware_speaker_opened':False}
    Path('/tmp/dock-responsiveness.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    dock.close();manager.shutdown();server.stop();gc.stop(restore=False);app.exit(0 if not errors else 1)
def tick():
    global sent,last_done,pending,last_tick
    now=time.monotonic();lags.append(now-last_tick);last_tick=now
    actor=manager.companion;states.add(actor.activity)
    if manager.notifications.card and manager.notifications.card.isVisible():toasts.extend(manager.notifications.lines)
    if errors or now-started>100:return finish()
    if actor.model_view and actor.model_view.ready and not pending:
        pending=True
        def receive(value):
            global pending
            pending=False
            try:
                data=json.loads(value)
                if 'faceOnly' in data:samples.append({key:data[key] for key in ('characterId','faceOnly','action','actionTime','mouth') if key in data})
            except (ValueError,TypeError):pass
        actor.model_view.page().runJavaScript('JSON.stringify(window.brainDiagnostics||{})',receive)
    if sent<2 and (sent==0 or len(results)==sent) and now-last_done>2 and actor.model_view and actor.model_view.ready:
        name=identities[sent][1];sent+=1;threading.Thread(target=feed,args=(name,),daemon=True).start()
    if sent>len(results) and manager.last_response['generation']>len(results) and not manager._worker_running and not manager.speech.playing and not manager._reply_queue and not manager._awaiting_reply:
        results.append({'character':actor.character_name,'reply':manager.last_response['text']});last_done=now
        actor.model_view.grab().save('/tmp/dock-cap-'+actor.character_id+'.png')
        if len(results)==2:QTimer.singleShot(400,finish)
timer=QTimer();timer.setInterval(80);timer.timeout.connect(tick);timer.start();app.exec();folder.cleanup()
