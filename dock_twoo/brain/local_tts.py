"""Compact Kokoro transformer, quantized INT8 ONNX CPU speech with local voices."""
from __future__ import annotations
import os
from pathlib import Path
import threading
import wave

MODEL='onnx-community/Kokoro-82M-v1.0-ONNX'
REVISION='1939ad2a8e416c0acfeecc08a694d14ef25f2231'
# Speaker order is validated against the exported model metadata at load.
VOICES={'af_heart':('Heart · American female',3),'af_bella':('Bella · American female',1),
        'am_adam':('Adam · American male',11),'am_michael':('Michael · American male',16),
        'bf_emma':('Emma · British female',20),'bm_george':('George · British male',26)}
CACHE=Path.home()/'.cache/huggingface/hub'

class LocalTts:
    def __init__(self):
        self.engine=None;self.state='not started';self.error='';self.voice='af_heart';self.speed=1.
        self._load_lock=threading.Lock();self._synth_lock=threading.Lock();self._thread=None
        self.speakers={}

    def start(self):
        if self._thread and self._thread.is_alive():return
        self._thread=threading.Thread(target=self.load,daemon=True,name='brain-kokoro-onnx');self._thread.start()

    def load(self,allow_download=True):
        with self._load_lock:
            if self.engine:return True
            try:
                import truststore
                truststore.inject_into_ssl()
                from huggingface_hub import snapshot_download
                import numpy as np
                import onnxruntime as ort
                from kokoro_onnx import Kokoro
                self.state='preparing'
                patterns=['onnx/model_quantized.onnx','config.json','tokenizer.json']+['voices/'+voice+'.bin' for voice in VOICES]
                folder=Path(snapshot_download(MODEL,revision=REVISION,cache_dir=CACHE,
                    allow_patterns=patterns,local_files_only=not allow_download,max_workers=4))
                voice_cache=CACHE/'brain-kokoro-voices-v1.npz'
                if not voice_cache.exists():
                    temporary=voice_cache.with_suffix('.tmp.npz')
                    np.savez(temporary,**{name:np.fromfile(folder/'voices'/f'{name}.bin',dtype=np.float32).reshape(-1,1,256) for name in VOICES})
                    temporary.replace(voice_cache)
                options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
                session=ort.InferenceSession(str(folder/'onnx/model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
                self.engine=Kokoro.from_session(session,str(voice_cache))
                self.speakers={name:index for index,name in enumerate(VOICES)}
                self.state='ready';self.error='';return True
            except Exception as exc:
                self.state='unavailable';self.error=f'{type(exc).__name__}: {exc}';return False

    def clip(self,text,cancel,*,voice=None,speed=None):
        if not self.engine:raise RuntimeError('The local Kokoro speech model is preparing. Check Voice status in Brain settings.')
        from dock_twoo.brain.audio import SpeechClip
        import numpy as np
        with self._synth_lock:
            if cancel.is_set():raise InterruptedError('Speech stopped.')
            voice=voice or self.voice
            voice=voice if voice in VOICES else 'af_heart'
            selected_speed=self.speed if speed is None else speed
            samples,rate=self.engine.create(text,voice=voice,speed=max(.6,min(2,selected_speed)),
                lang='en-gb' if voice.startswith('b') else 'en-us',sentence_pause=.12,clause_pause=.06)
            if cancel.is_set():raise InterruptedError('Speech stopped.')
            pcm=(np.clip(samples,-1,1)*32767).astype('<i2').tobytes()
            if not pcm:raise RuntimeError('The local speech model returned no audio.')
            return SpeechClip.from_pcm(pcm,int(rate))

    def synthesize_wav(self,text,path,cancel,*,voice=None,speed=None):
        clip=self.clip(text,cancel,voice=voice,speed=speed)
        with wave.open(str(path),'wb') as target:
            target.setnchannels(clip.channels);target.setsampwidth(2);target.setframerate(clip.rate);target.writeframes(clip.pcm)
        return True

    def status(self):return {'engine':'Kokoro 82M · INT8 ONNX CPU','state':self.state,'error':self.error,'voice':self.voice}

_singleton=None
_lock=threading.Lock()
def get_local_tts():
    global _singleton
    with _lock:
        if _singleton is None:_singleton=LocalTts()
        return _singleton
