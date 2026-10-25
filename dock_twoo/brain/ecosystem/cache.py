"""Provider-independent prompt templates with capability-specific prefix hints.

A local hit means a template was reused, never that a provider billed cached input.
Side effects and generated answers are deliberately not memoized by this cache.
"""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time

VERSION='agent-stages-v1'


class PromptCache:
    def __init__(self, root):
        self.path=Path(root)/'prompt-cache.sqlite3';self.path.parent.mkdir(parents=True,exist_ok=True);self.path.parent.chmod(0o700);self.lock=threading.Lock()
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS templates (key TEXT PRIMARY KEY,payload TEXT,hits INTEGER DEFAULT 0,at REAL)')
        self.path.chmod(0o600)

    def prepare(self, profile, character_id, credential, stable_messages, tools):
        # Digest scopes cache affinity without persisting credentials or user prompts.
        prefix=json.dumps({'version':VERSION,'messages':stable_messages,'tools':tools},sort_keys=True,separators=(',',':'))
        scope=json.dumps([profile.get('id'),profile.get('provider'),profile.get('base_url'),profile.get('model'),character_id,hashlib.sha256(credential.encode()).hexdigest(),hashlib.sha256(prefix.encode()).hexdigest()])
        key='dock-'+hashlib.sha256(scope.encode()).hexdigest()
        with self.lock, sqlite3.connect(self.path) as db:
            row=db.execute('SELECT payload,hits FROM templates WHERE key=?',(key,)).fetchone()
            if row:
                db.execute('UPDATE templates SET hits=hits+1,at=? WHERE key=?',(time.time(),key))
                cached=json.loads(row[0]);hit=True
            else:
                cached={'messages':copy.deepcopy(stable_messages),'tools':copy.deepcopy(tools)};hit=False
                db.execute('INSERT INTO templates VALUES(?,?,0,?)',(key,json.dumps(cached),time.time()))
            db.execute('DELETE FROM templates WHERE key NOT IN (SELECT key FROM templates ORDER BY at DESC LIMIT 256)')
        return cached,{'key':key,'local_template_hit':hit,'provider_cache_hit':'reported in model usage only','version':VERSION}


def native_cache_payload(config, payload, key=''):
    """Apply only documented capabilities; custom endpoints retain compatibility."""
    payload=copy.deepcopy(payload)
    mode=config.get('cache_mode','auto')
    if mode=='off':return payload
    if config.get('provider')=='openai' and key:
        payload['prompt_cache_key']=key
    if config.get('provider')=='openrouter':
        if key:payload['metadata']={**payload.get('metadata',{}),'session_id':key}
        if str(config.get('model','')).startswith('anthropic/'):
            payload['cache_control']={'type':'ephemeral'}
    if config.get('protocol')=='anthropic':
        # Stable system stages end before dates, memories, task state and results.
        system=payload.get('system','')
        stages=system.split('\n<runtime-context>\n',1)
        payload['system']=[{'type':'text','text':stages[0],'cache_control':{'type':'ephemeral'}}]
        if len(stages)>1:payload['system'].append({'type':'text','text':stages[1]})
        if payload.get('tools'):payload['tools'][-1]['cache_control']={'type':'ephemeral'}
    # Gemini's OpenAI-compatible endpoint and other providers use implicit prefix
    # caching when supported. Their documented usage, not a local guess, is counted.
    return payload
