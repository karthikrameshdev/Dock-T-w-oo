"""Offline neural stop and playback-echo regression using cached ONNX models.

Generated speech stays in memory. No cloud calls, recordings or hardware changes.
"""
from pathlib import Path
import sys,threading,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from dock_twoo.brain.local_tts import get_local_tts
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.wake import WakeDetector
from dock_twoo.brain.echo import PlaybackEchoGuard
from dock_twoo.brain.audio_devices import MicrophoneConverter
engine=get_local_tts();assert engine.load(allow_download=False),engine.error
model=WakeDetector(BrainStore().data_dir/'models',keywords=('STOP','BRAIN STOP'))
assert model.load(allow_download=False),model.error

def pcm(text,voice='am_adam'):
    engine.voice=voice
    clip=engine.clip(text,threading.Event())
    converter=MicrophoneConverter(clip.rate)
    chunks=converter.feed(np.frombuffer(clip.pcm,dtype='<i2').astype(np.float32)/32768)
    return np.frombuffer(b''.join(chunks),dtype='<i2').copy()

def detect(samples,guard=None):
    model.reset();found=[]
    for offset in range(0,len(samples),1600):
        frame=samples[offset:offset+1600].tobytes()
        if guard:frame=guard.filter(frame,100+offset/16000)
        word=model.feed(frame)
        if word:found.append({'word':word,'seconds':round(offset/16000,2)})
    for _ in range(10):
        word=model.feed(bytes(3200))
        if word:found.append({'word':word,'seconds':'tail'})
    return found

report={}
for phrase in ('Stop','Brain stop'):
    samples=np.concatenate((np.zeros(4800,dtype='<i2'),pcm(phrase),np.zeros(16000,dtype='<i2')))
    found=detect(samples);assert found,(phrase,model.status());report[phrase]=found
playback=pcm('You can say Brain stop whenever you want me to stop speaking.','af_heart')
guard=PlaybackEchoGuard();guard.begin(playback.tobytes(),16000,1,1,started=100.)
echo=(playback*.45).astype('<i2');echo_only=detect(echo,guard)
assert not echo_only,echo_only
near=pcm('Brain stop');offset=16000
mixed=echo.copy();size=min(len(near),len(mixed)-offset)
mixed[offset:offset+size]=np.clip(mixed[offset:offset+size].astype(np.int32)+near[:size],-32768,32767).astype('<i2')
guard.begin(playback.tobytes(),16000,1,2,started=100.)
double_talk=detect(mixed,guard);assert double_talk,model.status()
report.update(echo_only=echo_only,double_talk=double_talk,success=True,cloud_calls=0)
print(json.dumps(report,indent=2))
