"""Verify cached ONNX speech, enhancement and local OCR without a microphone."""
from pathlib import Path
import argparse
import json
import sys
import tempfile
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PySide6.QtWidgets import QApplication
app=QApplication.instance() or QApplication([])
from dock_twoo.brain.local_tts import LocalTts
from dock_twoo.brain.voice_models import LocalVoiceModels
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.local_vision import image_text

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--selected-pid',type=int,help='Verify an existing test selection without changing it.')
args=parser.parse_args()
models=LocalVoiceModels(BrainStore().data_dir/'models')
assert models.recognizer.load(allow_download=False),models.recognizer.error
assert models.denoiser.load(allow_download=False),models.denoiser.error
voice=LocalTts();assert voice.load(allow_download=False),voice.error
results=[]
for name in ('af_heart','am_adam'):
    voice.voice=name
    started=time.monotonic()
    clip=voice.clip('Today I completed the cloud agent and the task list.',threading.Event())
    elapsed=time.monotonic()-started
    assert clip.frames/clip.rate>1 and elapsed<clip.frames/clip.rate
    pcm=models._resample_pcm(clip.pcm,clip.rate,16000)
    samples=np.frombuffer(pcm,dtype='<i2').astype(float)*.3
    noisy=np.clip(samples+np.random.default_rng(42).normal(0,100,len(samples)),-32768,32767).astype('<i2').tobytes()
    started=time.monotonic();clean=models.enhance_pcm(noisy);enhancement=time.monotonic()-started
    assert len(clean)==len(pcm)
    transcript=models.recognizer.transcribe(clean).lower()
    assert 'cloud agent' in transcript and 'task list' in transcript,transcript
    results.append({'voice':name,'audio_seconds':round(clip.frames/clip.rate,3),'synthesis_seconds':round(elapsed,3),'enhancement_seconds':round(enhancement,3),'transcript':transcript})
with tempfile.TemporaryDirectory(prefix='brain-ocr-fixture-') as folder:
    from PIL import Image,ImageDraw,ImageFont
    image=Image.new('RGB',(1100,300),'white');draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',44)
    draw.text((40,80),'Brain work log: completed two tasks.',fill='black',font=font)
    path=Path(folder)/'fixture.png';image.save(path)
    outcome={}
    def ocr():
        try:outcome['text']=image_text(path)
        except Exception as exc:outcome['error']=str(exc)
    worker=threading.Thread(target=ocr,daemon=True);worker.start();deadline=time.monotonic()+25
    while worker.is_alive() and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert not worker.is_alive(),'Local OCR did not finish within 25 seconds.'
    assert 'error' not in outcome,outcome
    text=outcome['text']
    assert 'completed two tasks' in text.lower(),text
    results.append({'ocr':text,'pixels_uploaded':False})
if args.selected_pid:
    from dock_twoo.brain.desktop_driver import DesktopDriver
    selection=DesktopDriver().selected_text(args.selected_pid)
    assert selection['text']=='Brain selected text verification. Today I completed two tasks.'
    assert selection['selection_changed'] is False
    results.append({'native_existing_selection':'passed','selection_changed':False})
print(json.dumps({'success':True,'cases':results},indent=2))
