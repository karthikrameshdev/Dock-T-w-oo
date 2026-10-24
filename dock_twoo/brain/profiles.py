"""One external reasoning model; credentials encrypted separately from settings."""
from __future__ import annotations
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet
from dock_twoo.brain.cloud import PRESETS, validate_config

PROVIDER_CATALOG={name:{'name':label,'kind':name,'default_base_url':PRESETS[name],'models':[],
                       'default_model':'','roles':['text_output','computer_use']}
    for name,label in [('gemini','Google Gemini'),('openrouter','OpenRouter'),('openai','OpenAI'),
                       ('anthropic','Anthropic Claude'),('deepseek','DeepSeek'),('xai','xAI'),
                       ('huggingface','Hugging Face'),('custom','Custom cloud provider')]}

class ProfileManager:
    def __init__(self,store):
        self.store=store
        self._key_path=store.data_dir/'cloud-credentials.key'
        self._secrets_path=store.data_dir/'cloud-credentials.enc'
        with store.lock:
            legacy=store.setting('cloud_keys',{})
            if legacy:
                for provider,key in legacy.items():
                    if key:self.set_key(provider,key)
                store.set_setting('cloud_keys',{})
            if store.setting('cloud_model') is None:
                active=store.setting('active_profile','local')
                selected=next((p for p in store.setting('profiles',[]) if p.get('id')==active and p.get('provider') in PRESETS),{})
                config={key:selected.get(key,'') for key in ('provider','model','base_url')}
                config['provider']=config['provider'] or 'gemini'
                config['base_url']=config['base_url'] or PRESETS[config['provider']]
                store.set_setting('cloud_model',config)
            # No local profile survives in the public configuration.
            store.set_setting('profiles',[])
            store.set_setting('active_profile','cloud')

    def _cipher(self):
        if not self._key_path.exists():
            fd=os.open(self._key_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as target:target.write(Fernet.generate_key())
        return Fernet(self._key_path.read_bytes())

    def _keys(self):
        if not self._secrets_path.exists():return {}
        return json.loads(self._cipher().decrypt(self._secrets_path.read_bytes()))

    def set_key(self,provider,key_value):
        if provider not in PRESETS:raise ValueError('Choose a cloud provider.')
        with self.store.lock:
            keys=self._keys();keys[provider]=str(key_value).strip()
            data=self._cipher().encrypt(json.dumps(keys).encode())
            temporary=self._secrets_path.with_suffix('.tmp')
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
            with os.fdopen(fd,'wb') as target:target.write(data)
            temporary.replace(self._secrets_path)

    def get_key(self,provider):
        with self.store.lock:
            return self._keys().get(provider,'') or os.environ.get({'gemini':'GEMINI_API_KEY','anthropic':'ANTHROPIC_API_KEY',
                'openai':'OPENAI_API_KEY','openrouter':'OPENROUTER_API_KEY','deepseek':'DEEPSEEK_API_KEY',
                'xai':'XAI_API_KEY','huggingface':'HF_TOKEN'}.get(provider,'BRAIN_CUSTOM_API_KEY'),'')

    def get_profile_status(self,profile):
        try:validate_config(profile)
        except ValueError:return 'not configured'
        return 'configured' if self.get_key(profile.get('provider')) else 'not configured'

    def get_active_profile(self):
        config=dict(self.store.setting('cloud_model',{}))
        config.update(id='cloud',name=PROVIDER_CATALOG.get(config.get('provider'),{}).get('name','Cloud model'))
        config['status']=self.get_profile_status(config)
        config['key_configured']=bool(self.get_key(config.get('provider')))
        config['protocol']=config.get('protocol') or ('anthropic' if config.get('provider')=='anthropic' else 'openai')
        return config

    def save_profile(self,data):
        clean=validate_config({k:data.get(k,'') for k in ('provider','base_url','model','protocol')})
        self.store.set_setting('cloud_model',{k:clean[k] for k in ('provider','base_url','model','protocol')})
        if data.get('api_key'):self.set_key(clean['provider'],data['api_key'])
        return self.get_active_profile()

    def get_provider_catalog(self):return {'catalog':PROVIDER_CATALOG,'presets':PRESETS,'roles':['text_output','computer_use']}
    def get_profiles(self):return [self.get_active_profile()]
    def activate_profile(self,profile_id):return profile_id=='cloud'
    def delete_profile(self,profile_id):raise ValueError('Brain uses one cloud model. Edit its configuration instead.')
