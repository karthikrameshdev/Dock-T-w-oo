"""A real on-device language model through the installed Ollama service."""
from __future__ import annotations
import json
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request


class LocalChat:
    PREFERRED = ('qwen3:4b-instruct', 'qwen3.5:0.8b', 'qwen3:0.6b')

    def __init__(self, base_url='http://127.0.0.1:11434', timeout=30):
        self.base_url = base_url.rstrip('/').removesuffix('/v1')
        self.timeout = timeout
        self.model = ''
        self.state = 'not started'
        self.error = ''
        self._startup_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._worker = None

    def _json(self, path, payload=None, timeout=None):
        request = urllib.request.Request(self.base_url+path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
            return json.load(response)

    def ensure_ready(self, requested='local', autostart=True):
        with self._startup_lock:
            try:
                try:
                    tags = self._json('/api/tags', timeout=2)
                except Exception:
                    address=urllib.parse.urlsplit(self.base_url)
                    binary=shutil.which('ollama')
                    if not autostart or not binary or address.hostname not in ('127.0.0.1','localhost') or address.port != 11434:
                        raise RuntimeError('The local model service is not running')
                    subprocess.Popen([binary,'serve'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True)
                    deadline=time.monotonic()+8
                    while True:
                        try:
                            tags=self._json('/api/tags',timeout=1)
                            break
                        except Exception:
                            if time.monotonic()>deadline:raise RuntimeError('Ollama did not start')
                            time.sleep(.2)
                available=[model['name'] for model in tags.get('models',[]) if model.get('name')]
                selected=requested if requested not in ('','local') else next((name for name in self.PREFERRED if name in available),available[0] if available else '')
                if not selected or selected not in available:
                    raise RuntimeError('No requested local language model is installed. Install one in Ollama or select an existing model.')
                self.model=selected
                self.state='ready'
                self.error=''
                return True
            except Exception as exc:
                self.state='unavailable';self.error=str(exc)
                return False

    def start(self):
        if self._worker and self._worker.is_alive():return
        def warm():
            self.state='starting'
            if self.ensure_ready():
                try:
                    self.state='loading'
                    self._json('/api/generate',{'model':self.model,'prompt':'','stream':False,'keep_alive':'15m','options':{'num_ctx':2048}})
                    self.state='ready'
                except Exception as exc:
                    self.state='unavailable';self.error=str(exc)
        self._worker=threading.Thread(target=warm,daemon=True,name='brain-local-language-model')
        self._worker.start()

    def chat(self, prompt, history=None, requested='local'):
        if not self.model or (requested not in ('','local') and requested != self.model):
            if not self.ensure_ready(requested):raise RuntimeError(self.error)
        messages=[{'role':'system','content':
            'You are Brain, a helpful desktop voice assistant. Answer the user directly in two or three short spoken sentences. '
            'Use plain language. Be useful and conversational. The app executes desktop commands separately; '
            'never claim you opened, typed, sent, changed or researched anything unless an execution result is supplied. '
            'If you cannot perform a requested action, explain the specific limitation instead of saying you did not understand. '
            'Built-in capabilities are opening installed apps, typing into an editor, singing a short original song, '
            'reading the active document, checking time and system status, following the cursor, and character gestures. '
            'Do not invent current information. Do not include thinking tags or markdown formatting.'}]
        messages.extend({'role':item['role'],'content':str(item['content'])[:2000]} for item in (history or [])[-8:] if item.get('role') in ('user','assistant'))
        if not messages or messages[-1]['role']!='user' or messages[-1]['content']!=prompt:
            messages.append({'role':'user','content':prompt})
        try:
            with self._request_lock:
                data=self._json('/api/chat',{'model':self.model,'messages':messages,'stream':False,'think':False,
                    'keep_alive':'15m','options':{'temperature':.5,'num_predict':256,'num_ctx':2048}})
            answer=str(data.get('message',{}).get('content','')).strip()
            if not answer:raise RuntimeError('The local model returned an empty answer')
            self.state='ready';self.error=''
            return answer
        except Exception as exc:
            self.error=str(exc);self.state='unavailable'
            raise RuntimeError('The local language model could not finish the response') from exc

    def status(self):
        return {'state':self.state,'model':self.model,'error':self.error}


_clients={}
_clients_lock=threading.Lock()
def get_local_chat(base_url='http://127.0.0.1:11434'):
    key=base_url.rstrip('/').removesuffix('/v1')
    with _clients_lock:
        if key not in _clients:_clients[key]=LocalChat(key)
        return _clients[key]
