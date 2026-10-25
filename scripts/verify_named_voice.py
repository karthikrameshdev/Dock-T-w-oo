"""Generated local speech through production KWS, ASR, endpoint and named signals."""
from pathlib import Path
import os,sys,threading,time,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('PYTEST_CURRENT_TEST','named-voice-offline-check')
import numpy as np
from PySide6.QtCore import QCoreApplication
from dock_twoo.brain.catalog import characters
from dock_twoo.brain.local_tts import get_local_tts
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.listener import AudioListener
from dock_twoo.brain.audio_devices import MicrophoneConverter
app=QCoreApplication([]);engine=get_local_tts();assert engine.load(allow_download=False),engine.error
listener=AudioListener(store=BrainStore());listener.enable_character_names()
assert listener.wake_detector.load(allow_download=False),listener.wake_detector.error
assert listener.models.recognizer.load(allow_download=False),listener.models.recognizer.error
def transcribe(pcm):
 text=listener.models.recognizer.transcribe(pcm)
 if os.environ.get('NAMED_VOICE_TRACE'):print('ASR',repr(text),flush=True)
 return text
listener._transcribe_pcm=transcribe
listener._is_speech_frame=lambda pcm,*_:float(np.sqrt(np.mean(np.frombuffer(pcm,dtype='<i2').astype(float)**2)))>20
found=[];listener.named_turn_completed.connect(lambda *args:found.append(args));report=[]
for entry in [c for c in characters() if not sys.argv[1:] or c['name'] in sys.argv[1:]]:
 listener.arm_wake();listener.set_output_active(False);found.clear()
 engine.voice='af_heart';clip=engine.clip('Hey '+entry['name']+', open my notes.',threading.Event())
 chunks=MicrophoneConverter(clip.rate).feed(np.frombuffer(clip.pcm,dtype='<i2').astype(np.float32)/32768)
 samples=np.concatenate((np.zeros(4800,dtype='<i2'),np.frombuffer(b''.join(chunks),dtype='<i2'),np.zeros(40000,dtype='<i2')))
 for offset in range(0,len(samples),1600):
  listener._handle_pcm_frame(samples[offset:offset+1600].tobytes());app.processEvents();time.sleep(.003)
 until=time.monotonic()+15
 while not found and time.monotonic()<until:app.processEvents();time.sleep(.01)
 result=found[0] if found else None
 success=bool(result and result[0]==entry['id'] and result[1].lower().strip(' .!')=='open my notes' and not result[3])
 report.append({'name':entry['name'],'success':success,'result':result});print(entry['name'],success,result,flush=True)
 if not success:print(listener.last_wake_decision,listener.last_error,listener.last_wake_checks,listener.last_wake_matches,flush=True)
listener.audio_devices.close()
result={'success':all(r['success'] for r in report),'matched':sum(r['success'] for r in report),'total':len(report),'cloud_calls':0,'characters':report}
Path('/tmp/dock-named-voice.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='characters'}),flush=True)
sys.exit(0 if result['success'] else 1)
