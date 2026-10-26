"""Local outbound redaction with stable, request-scoped opaque references.

Patterns cover structured identifiers/secrets; a local quantized NER model adds
names, organisations and places. Detection is defence in depth, not a proof that
arbitrary text is anonymous. Scanner failures stop transmission.
"""
from functools import lru_cache
import json
import os
import re
import threading

MODEL='onnx-community/bert-base-NER-ONNX'
REVISION='9faa2f4a2d59b396888b318f596ff719cc893f1e'

class PrivacyUnavailable(RuntimeError):pass

class LocalEntities:
    def __init__(self):self.lock=threading.RLock();self.session=None
    def load(self):
        if self.session is not None:return
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
        import onnxruntime as ort
        def file(name):return hf_hub_download(MODEL,name,revision=REVISION)
        tokenizer=Tokenizer.from_file(file('tokenizer.json'))
        tokenizer.enable_truncation(max_length=512,stride=32)
        labels=json.loads(open(file('config.json')).read())['id2label']
        options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
        session=ort.InferenceSession(file('onnx/model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
        self.tokenizer,self.labels,self.session=tokenizer,labels,session
    @lru_cache(maxsize=256)
    def spans(self,text):
        import numpy as np
        with self.lock:
            try:
                self.load();encoded=self.tokenizer.encode(text);spans=[]
                for item in [encoded,*encoded.overflowing]:
                    values={'input_ids':[item.ids],'attention_mask':[item.attention_mask],'token_type_ids':[item.type_ids]}
                    output=self.session.run(None,{x.name:np.asarray(values[x.name],dtype=np.int64) for x in self.session.get_inputs()})[0][0]
                    for label,(start,end) in zip(output.argmax(axis=-1),item.offsets):
                        if end>start and self.labels[str(int(label))].split('-')[-1] in ('PER','LOC','ORG'):spans.append((start,end))
                spans.sort();merged=[]
                for start,end in spans:
                    if merged and start<=merged[-1][1]+1:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
                    else:merged.append((start,end))
                return tuple(merged)
            except Exception as exc:raise PrivacyUnavailable('The local privacy scanner is unavailable. No model request was sent. Check model download/connectivity and retry.') from exc

_entities=LocalEntities()
PATTERNS=[
 ('private_key',r'-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----'),
 ('email',r'\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b'),
 ('credential',r'\b(?:sk-(?:proj-|ant-)?[a-z0-9_\-]{12,}|(?:gh[pousr]_|github_pat_)[a-z0-9_]{15,}|AKIA[A-Z0-9]{16}|AIza[a-z0-9_\-]{30,})\b'),
 ('jwt',r'\beyJ[a-z0-9_\-]+\.[a-z0-9_\-]+\.[a-z0-9_\-]+\b'),
 ('secret',r'(?i)\b(?:password|passwd|pwd|api[_ -]?key|access[_ -]?key|access[_ -]?token|secret|authorization|pin|cvv|cvc)\s*["\']?\s*(?:[:=]|\bis\b)\s*["\']?([^\s,"\'<>;]+)'),
 ('bearer',r'\bBearer\s+[a-z0-9_.+/=\-]+'),
 ('identifier',r'(?<!\w)(?:\+?\d[\d ()\-]{7,22}\d)(?!\w)'),
 ('home',r'(?:/Users/|/home/|[A-Z]:[\\/]Users[\\/])[^/\\\s"\']+'),
 ('address',r'\b\d{1,6}\s+(?:[A-Z][\w.-]*\s+){1,6}(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr|Boulevard|Blvd)\b'),
]

class PrivacyFilter:
    def __init__(self,secrets=(),entities=None):
        self.secrets=set(s for s in secrets if s)
        self.secrets.update(v for k,v in os.environ.items() if len(v)>=4 and any(word in k.upper() for word in ('TOKEN','PASSWORD','SECRET','API_KEY','ACCESS_KEY')))
        self.entities=entities or _entities;self.values={};self.inverse={};self.lock=threading.RLock()
    def token(self,value):
        if value not in self.inverse:
            token=f'[PRIVATE_{len(self.values)+1}]';self.inverse[value]=token;self.values[token]=value
        return self.inverse[value]
    def text(self,text,ner=True):
        with self.lock:
            for value in sorted(self.secrets,key=len,reverse=True):text=text.replace(value,self.token(value))
            for kind,pattern in PATTERNS:
                def replace(match):
                    if kind=='secret':return match.group(0).replace(match.group(1),self.token(match.group(1)))
                    return self.token(match.group(0))
                text=re.sub(pattern,replace,text,flags=re.I)
            if ner and len(text)>2 and (' ' in text or '\n' in text):
                for start,end in reversed(self.entities.spans(text)):
                    # Do not re-scan opaque references or break their round trip.
                    if '[' in text[start:end] or ']' in text[start:end] or re.search(r'\[PRIVATE_\d*$',text[:start]):continue
                    value=text[start:end];text=text[:start]+self.token(value)+text[end:]
            return text
    def clean(self,value,*,ner=True):
        if isinstance(value,str):return self.text(value,ner)
        if isinstance(value,list):return [self.clean(v,ner=ner) for v in value]
        if isinstance(value,dict):
            result={}
            for key,item in value.items():
                sensitive=re.fullmatch(r'(?:password|passwd|pwd|api[_ -]?key|access[_ -]?(?:key|token)|secret|authorization|pin|cvv|cvc|card[_ -]?(?:number|security[_ -]?code))',str(key),re.I)
                if sensitive and isinstance(item,(str,int,float)) and str(item):
                    with self.lock:result[key]=self.token(str(item))
                else:result[key]=self.clean(item,ner=ner)
            return result
        return value
    def restore(self,value):
        if isinstance(value,str):
            return re.sub(r'\[PRIVATE_\d+\]',lambda m:self.values.get(m.group(0),m.group(0)),value)
        if isinstance(value,list):return [self.restore(v) for v in value]
        if isinstance(value,dict):return {k:self.restore(v) for k,v in value.items()}
        return value
    def messages(self,messages):
        # Roles, tool names and call ids are protocol metadata. Dynamic content,
        # including memory/review system messages and tool results, is scanned.
        return [{k:self.clean(v) if k in ('content','tool_calls') else v for k,v in message.items()} for message in messages]
