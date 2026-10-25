"""One small local transformer shared by memory, review and animation policy."""
from functools import lru_cache
from pathlib import Path
import threading
import numpy as np


class SemanticModel:
    MODEL = 'Xenova/all-MiniLM-L6-v2'
    REVISION = '751bff37182d3f1213fa05d7196b954e230abad9'
    FILES = ('tokenizer.json','onnx/model_quantized.onnx')

    def __init__(self, root):
        self.root=Path(root); self.state='not started'; self.error=''
        self.session=None; self.tokenizer=None; self.lock=threading.RLock(); self.worker=None

    @property
    def ready(self):return self.session is not None

    def start(self):
        if self.ready or (self.worker and self.worker.is_alive()):return
        self.worker=threading.Thread(target=self.load,name='local-semantic-transformer',daemon=True);self.worker.start()

    def load(self, allow_download=True):
        with self.lock:
            if self.ready:return True
            try:
                import onnxruntime as ort
                from tokenizers import Tokenizer
                from huggingface_hub import snapshot_download
                self.state='loading'
                folder=Path(snapshot_download(self.MODEL,revision=self.REVISION,cache_dir=self.root/'huggingface'/'hub',allow_patterns=list(self.FILES),local_files_only=not allow_download))
                tokenizer=Tokenizer.from_file(str(folder/'tokenizer.json'))
                tokenizer.enable_truncation(max_length=256);tokenizer.enable_padding()
                options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
                session=ort.InferenceSession(str(folder/'onnx/model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
                self.tokenizer=tokenizer;self.session=session;self.state='ready';self.error='';return True
            except Exception as exc:self.state='unavailable';self.error=f'{type(exc).__name__}: {exc}';return False

    @lru_cache(maxsize=2048)
    def embed(self, text):
        if not self.ready:raise RuntimeError('Local semantic model is not ready.')
        with self.lock:
            token=self.tokenizer.encode(str(text)[:6000])
            data={'input_ids':np.array([token.ids],dtype=np.int64),'attention_mask':np.array([token.attention_mask],dtype=np.int64),'token_type_ids':np.array([token.type_ids],dtype=np.int64)}
            outputs=self.session.run(None,{v.name:data[v.name] for v in self.session.get_inputs()})
        value=outputs[0]
        if value.ndim==3:
            mask=data['attention_mask'][...,None];value=(value*mask).sum(axis=1)/np.maximum(1,mask.sum(axis=1))
        value=np.asarray(value[0],dtype=np.float32);value=value/max(1e-9,float(np.linalg.norm(value)));value.setflags(write=False)
        return value

    def similarity(self, a, b):return float(self.embed(a) @ self.embed(b))

    def status(self):return {'model':self.MODEL,'revision':self.REVISION,'state':self.state,'error':self.error,'ready':self.ready,'roles':['memory retrieval','extractive compaction','progress review','animation ranking']}
