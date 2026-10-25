"""Cached ONNX speech → one multi-name Zipformer; no microphone or cloud calls."""
from pathlib import Path
import sys,threading,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from dock_twoo.brain.catalog import characters,keyword_id
from dock_twoo.brain.local_tts import get_local_tts
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.wake import WakeDetector
from dock_twoo.brain.audio_devices import MicrophoneConverter
engine=get_local_tts();assert engine.load(allow_download=False),engine.error
model=WakeDetector(BrainStore().data_dir/'models');model.configure_names([c['name'] for c in characters()]);assert model.load(allow_download=False),model.error
report=[]
for entry in characters():
 engine.voice='af_heart';clip=engine.clip('Hey '+entry['name']+', open my notes.',threading.Event())
 chunks=MicrophoneConverter(clip.rate).feed(np.frombuffer(clip.pcm,dtype='<i2').astype(np.float32)/32768)
 samples=np.concatenate((np.zeros(4800,dtype='<i2'),np.frombuffer(b''.join(chunks),dtype='<i2'),np.zeros(16000,dtype='<i2')))
 model.reset();found=[]
 for offset in range(0,len(samples),1600):
  word=model.feed(samples[offset:offset+1600].tobytes())
  if word:found.append(word)
 success=any(keyword_id(word)==entry['id'] for word in found)
 report.append({'name':entry['name'],'keywords':found,'detected':success})
 print(entry['name'],found,success,flush=True)
print(json.dumps({'characters':report,'detected':sum(r['detected'] for r in report),'total':len(report),'cloud_calls':0},indent=2))
