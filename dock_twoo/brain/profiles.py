"""One external reasoning model; credentials encrypted separately from settings."""
from __future__ import annotations
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet
from dock_twoo.brain.cloud import PRESETS
from dock_twoo.brain.ecosystem.models import CLI_PROVIDERS, NETWORK_PROVIDERS, validate_agent_model as validate_config, configured

PRESETS={**PRESETS,**NETWORK_PROVIDERS,**{name:"" for name in CLI_PROVIDERS}}

PROVIDER_CATALOG={name:{'name':label,'kind':name,'default_base_url':PRESETS[name],'models':[],
                       'default_model':'','roles':['text_output','computer_use']}
    for name,label in [('gemini','Google Gemini'),('openrouter','OpenRouter'),('openai','OpenAI'),
                       ('anthropic','Anthropic Claude'),('deepseek','DeepSeek'),('xai','xAI'),
                       ('huggingface','Hugging Face'),('custom','Custom API provider'),('ollama','Ollama server'),('network','Network model server'),('gemini_cli','Gemini CLI'),('codex_cli','Codex CLI'),('claude_cli','Claude Code CLI'),('kilo_cli','Kilo CLI'),('custom_cli','Other CLI')]}

class ProfileManager:
    def __init__(self,store):
        self.store=store
        self._key_path=store.data_dir/'cloud-credentials.key'
        self._secrets_path=store.data_dir/'cloud-credentials.enc'
        with store.lock:
            if store.setting('cloud_profiles') is None:
                selected=store.setting('cloud_model')
                if selected is None:
                    active=store.setting('active_profile','local')
                    selected=next((p for p in store.setting('profiles',[]) if p.get('id')==active and p.get('provider') in PRESETS),{})
                provider=selected.get('provider') if selected.get('provider') in PRESETS else 'gemini'
                config={key:selected.get(key,'') for key in ('provider','model','base_url','protocol')}
                config.update(id='cloud',name='Default',provider=provider,base_url=config['base_url'] or PRESETS[provider])
                store.set_setting('cloud_profiles',[config]);store.set_setting('active_profile','cloud')
                keys=self._keys()
                keys.update({provider:key for provider,key in store.setting('cloud_keys',{}).items() if key})
                for provider in PRESETS:
                    if provider in keys:keys['profile:cloud:'+provider]=keys.pop(provider)
                if keys:self._save_keys(keys)
                store.set_setting('cloud_keys',{});store.set_setting('profiles',[])
            profiles=self._configs()
            active=store.setting('active_profile')
            if active not in {p['id'] for p in profiles}:store.set_setting('active_profile',profiles[0]['id'] if profiles else '')
            self._sync_compatibility()

    def _configs(self):return [dict(profile) for profile in self.store.setting('cloud_profiles',[])]

    def _sync_compatibility(self):
        active=self.store.setting('active_profile')
        config=next((p for p in self._configs() if p['id']==active),{})
        self.store.set_setting('cloud_model',{key:config.get(key,'') for key in ('provider','model','base_url','protocol')})

    def _cipher(self):
        from dock_twoo.brain.credential_key import cipher_key
        return Fernet(cipher_key(self._key_path))

    def _keys(self):
        if not self._secrets_path.exists():return {}
        return json.loads(self._cipher().decrypt(self._secrets_path.read_bytes()))

    def _save_keys(self,keys):
        data=self._cipher().encrypt(json.dumps(keys).encode())
        temporary=self._secrets_path.with_suffix('.tmp')
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'wb') as target:target.write(data)
        temporary.replace(self._secrets_path)

    def set_key(self,provider,key_value,profile_id=None):
        if provider not in PRESETS:raise ValueError('Choose a cloud provider.')
        with self.store.lock:
            ident=profile_id or self.store.setting('active_profile')
            if ident not in {p['id'] for p in self._configs()}:raise ValueError('Choose an existing cloud profile.')
            keys=self._keys();keys['profile:'+ident+':'+provider]=str(key_value).strip();self._save_keys(keys)

    def get_key(self,provider,profile_id=None):
        with self.store.lock:
            ident=profile_id if profile_id is not None else self.store.setting('active_profile')
            saved=self._keys().get('profile:'+str(ident)+':'+str(provider),'')
            if provider in CLI_PROVIDERS or provider in NETWORK_PROVIDERS:return saved
            return saved or os.environ.get({'gemini':'GEMINI_API_KEY','anthropic':'ANTHROPIC_API_KEY',
                'openai':'OPENAI_API_KEY','openrouter':'OPENROUTER_API_KEY','deepseek':'DEEPSEEK_API_KEY',
                'xai':'XAI_API_KEY','huggingface':'HF_TOKEN'}.get(provider,'BRAIN_CUSTOM_API_KEY'),'')

    def get_profile_status(self,profile):
        try:validate_config(profile)
        except ValueError:return 'not configured'
        if profile.get('provider') in CLI_PROVIDERS:return 'configured' if configured(profile) else 'not configured'
        if profile.get('provider') in NETWORK_PROVIDERS:return 'configured'
        return 'configured' if self.get_key(profile.get('provider'),profile.get('id')) else 'not configured'

    def _public(self,config):
        config=dict(config)
        config['kind']='cli' if config.get('provider') in CLI_PROVIDERS else 'network' if config.get('provider') in NETWORK_PROVIDERS else 'api'
        config['status']=self.get_profile_status(config)
        config['key_configured']=bool(self.get_key(config.get('provider'),config.get('id')))
        config['protocol']=config.get('protocol') or ('anthropic' if config.get('provider')=='anthropic' else 'openai')
        return config

    def get_active_profile(self):
        with self.store.lock:
            active=self.store.setting('active_profile')
            config=next((p for p in self._configs() if p['id']==active),
                        {'id':'','name':'No profile','provider':'gemini','base_url':PRESETS['gemini'],'model':''})
            return self._public(config)

    def _save_profile(self,data,create=False):
        import uuid
        with self.store.lock:
            profiles=self._configs();ident=data.get('id') or self.store.setting('active_profile')
            existing=next((p for p in profiles if p['id']==ident),None)
            if create or not profiles:
                ident=uuid.uuid4().hex;existing=None
            elif existing is None:raise ValueError('Cloud profile not found.')
            requested_name=data.get('name',(existing or {}).get('name','Default'))
            if not isinstance(requested_name,str):raise ValueError('Use a text profile name.')
            if 'api_key' in data and not isinstance(data['api_key'],str):raise ValueError('Use a text API key.')
            name=requested_name.strip()
            if not name or len(name)>80:raise ValueError('Use a profile name of 1 to 80 characters.')
            if any(p['id']!=ident and p['name'].casefold()==name.casefold() for p in profiles):raise ValueError('Choose a unique profile name.')
            clean=validate_config({k:data.get(k,[] if k=='arguments' else '') for k in ('provider','base_url','model','protocol','executable','arguments','cache_mode')})
            clean={k:clean[k] for k in ('provider','base_url','model','protocol','kind','executable','arguments','cache_mode') if k in clean};clean.update(id=ident,name=name)
            if existing:profiles=[clean if p['id']==ident else p for p in profiles]
            else:profiles.append(clean)
            self.store.set_setting('cloud_profiles',profiles)
            if not self.store.setting('active_profile'):self.store.set_setting('active_profile',ident)
            if data.get('api_key'):self.set_key(clean['provider'],data['api_key'],ident)
            self._sync_compatibility()
            return self._public(clean)

    def save_profile(self,data):return self._save_profile(data)
    def create_profile(self,data):return self._save_profile(data,create=True)
    def get_provider_catalog(self):return {'catalog':PROVIDER_CATALOG,'presets':PRESETS,'roles':['text_output','computer_use']}
    def get_profiles(self):
        with self.store.lock:return [self._public(p) for p in self._configs()]
    def character_profile(self, character_id):
        from dock_twoo.brain.catalog import character
        character(character_id)
        ident=self.store.setting('character_profiles',{}).get(character_id)
        config=next((p for p in self._configs() if p['id']==ident),None)
        return self._public(config) if config else self.get_active_profile()

    def bind_character(self, character_id, profile_id):
        from dock_twoo.brain.catalog import character
        character(character_id)
        if profile_id and profile_id not in {p['id'] for p in self._configs()}:
            raise ValueError('Choose an existing agent model profile.')
        with self.store.lock:
            bindings=dict(self.store.setting('character_profiles',{}))
            if profile_id:bindings[character_id]=profile_id
            else:bindings.pop(character_id,None)
            self.store.set_setting('character_profiles',bindings)
        return self.character_profile(character_id)

    def activate_profile(self,profile_id):
        with self.store.lock:
            if profile_id not in {p['id'] for p in self._configs()}:raise ValueError('Cloud profile not found.')
            self.store.set_setting('active_profile',profile_id);self._sync_compatibility();return True
    def delete_profile(self,profile_id):
        with self.store.lock:
            profiles=self._configs()
            if profile_id not in {p['id'] for p in profiles}:raise ValueError('Cloud profile not found.')
            remaining=[p for p in profiles if p['id']!=profile_id]
            keys={key:value for key,value in self._keys().items() if not key.startswith('profile:'+profile_id+':')}
            if self._secrets_path.exists():self._save_keys(keys)
            self.store.set_setting('cloud_profiles',remaining)
            if self.store.setting('active_profile')==profile_id:self.store.set_setting('active_profile',remaining[0]['id'] if remaining else '')
            self._sync_compatibility();return True
