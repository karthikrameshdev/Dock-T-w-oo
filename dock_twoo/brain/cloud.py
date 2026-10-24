"""Text-only cloud transport; native tool loops, with no local LLM fallback."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

NOT_CONFIGURED = 'Model is not configured. Open Brain settings and set a cloud provider URL, model ID, and API key.'
PRESETS = {
    'gemini':'https://generativelanguage.googleapis.com/v1beta/openai',
    'openai':'https://api.openai.com/v1', 'anthropic':'https://api.anthropic.com/v1',
    'openrouter':'https://openrouter.ai/api/v1', 'deepseek':'https://api.deepseek.com/v1',
    'xai':'https://api.x.ai/v1', 'huggingface':'https://router.huggingface.co/v1', 'custom':''}

class CloudError(RuntimeError): pass
class ModelNotConfigured(CloudError): pass

@dataclass
class ModelTurn:
    message: dict
    calls: list[dict]
    text: str
    truncated: bool = False
    usage: dict = field(default_factory=dict)


def validate_config(config, *, allow_test_endpoint=False):
    provider=config.get('provider','custom')
    if provider not in PRESETS:raise ValueError('Choose an external cloud provider.')
    url=str(config.get('base_url') or PRESETS[provider]).rstrip('/')
    address=urllib.parse.urlsplit(url)
    if address.username or address.password or address.query or address.fragment:
        raise ValueError('Use a provider base URL without credentials, query parameters or fragments.')
    if not address.hostname or (address.scheme!='https' and not (allow_test_endpoint and address.hostname in ('localhost','127.0.0.1') and address.scheme=='http')):
        raise ValueError('The cloud provider URL must use HTTPS.')
    if address.hostname in ('localhost','127.0.0.1','::1') and not allow_test_endpoint:
        raise ValueError('Local reasoning model endpoints are not supported.')
    model=str(config.get('model','')).strip()
    if not model:raise ValueError('Enter the cloud model ID.')
    protocol=config.get('protocol') or ('anthropic' if provider=='anthropic' else 'openai')
    if protocol not in ('openai','anthropic'):raise ValueError('Choose OpenAI-compatible or Anthropic Messages protocol.')
    return {**config,'provider':provider,'base_url':url,'model':model,'protocol':protocol}


class CloudClient:
    def __init__(self, config, key, *, timeout=45, allow_test_endpoint=False):
        if not key or not str(config.get('model','')).strip():raise ModelNotConfigured(NOT_CONFIGURED)
        self.config=validate_config(config,allow_test_endpoint=allow_test_endpoint)
        self.key=key.strip();self.timeout=timeout

    def payload(self, messages, tools):
        maximum = max(128, min(2048, int(getattr(self, 'max_output_tokens', 1024))))
        if self.config['protocol'] == 'anthropic':
            return {'model':self.config['model'],'max_tokens':maximum,
                    'system':'\n'.join(m['content'] for m in messages if m['role']=='system'),
                    'messages':[m for m in messages if m['role']!='system'],
                    'tools':[{'name':t['function']['name'],'description':t['function']['description'],
                              'input_schema':t['function']['parameters']} for t in tools]}
        limit_key='max_completion_tokens' if self.config['provider']=='openai' else 'max_tokens'
        return {'model':self.config['model'],'messages':messages,'tools':tools,
                'tool_choice':'auto','stream':False,limit_key:maximum}

    def turn(self, messages, tools, cancel=None):
        from dock_twoo.brain.activity import ActivityStore, provider_usage
        cancel=cancel or threading.Event()
        if cancel.is_set():raise InterruptedError('Request stopped.')
        anthropic=self.config['protocol']=='anthropic'
        payload=self.payload(messages,tools)
        headers=({'Content-Type':'application/json','x-api-key':self.key,'anthropic-version':'2023-06-01'} if anthropic
                 else {'Content-Type':'application/json','Authorization':'Bearer '+self.key})
        endpoint='/messages' if anthropic else '/chat/completions'
        tracker=getattr(self,'tracker',None)
        if tracker is None:
            from dock_twoo.brain.storage import BrainStore
            tracker=ActivityStore(BrainStore().data_dir/'activity')
        run_id=getattr(self,'run_id',None)
        own_run=not run_id
        if own_run:run_id=tracker.start('Cloud connection / direct model request',source='connection_test')
        step=getattr(self,'step',1)
        call_id=tracker.begin_call(run_id,self.config,payload,step,getattr(self,'retry',False),self.key)
        started=time.monotonic();data={};status='error';error=''
        try:
            request=urllib.request.Request(self.config['base_url']+endpoint,data=json.dumps(payload).encode(),headers=headers)
            try:
                with urllib.request.urlopen(request,timeout=self.timeout) as response:
                    data=json.loads(response.read(4*1024*1024))
            except urllib.error.HTTPError as exc:
                try:data={'http_status':exc.code,'error_body':exc.read(4000).decode(errors='replace')}
                except OSError:data={'http_status':exc.code}
                labels={401:'The provider rejected the API key.',403:'The provider denied access to this model.',
                        404:'The provider URL or model ID was not found.',429:'The provider rate or credit limit was reached.'}
                raise CloudError(labels.get(exc.code,f'The cloud provider returned HTTP {exc.code}. Check its model and tool-calling support.')) from None
            except (OSError,ValueError):
                raise CloudError('The cloud provider did not return a valid response. Check connectivity and the provider URL.') from None
            usage=provider_usage(data,self.config['protocol'])
            if cancel.is_set():
                status='cancelled'
                raise InterruptedError('Request stopped.')
            try:
                if anthropic:
                    blocks=data['content']
                    calls=[{'id':block['id'],'name':block['name'],'arguments':block['input']} for block in blocks if block['type']=='tool_use']
                    text='\n'.join(block['text'] for block in blocks if block['type']=='text')
                    result=ModelTurn({'role':'assistant','content':blocks},calls,text,data.get('stop_reason')=='max_tokens',usage)
                else:
                    choice=data['choices'][0];message=choice['message'];calls=[]
                    for call in message.get('tool_calls') or []:
                        args=call['function']['arguments']
                        try:args=json.loads(args) if isinstance(args,str) else args
                        except ValueError:args={'__invalid_json__':True}
                        calls.append({'id':call['id'],'name':call['function']['name'],'arguments':args})
                    result=ModelTurn(message,calls,message.get('content') or '',choice.get('finish_reason')=='length',usage)
            except (KeyError,IndexError,TypeError):
                raise CloudError('The provider response did not match the selected API protocol.') from None
            status='success'
            return result
        except Exception as exc:
            error=str(exc)
            raise
        finally:
            tracker.end_call(call_id,data,self.config['protocol'],status=status,error=error,
                             latency_ms=round((time.monotonic()-started)*1000),secret=self.key)
            if own_run:tracker.finish(run_id,'complete' if status=='success' else status,reason=error)

    def append_results(self,messages,results):
        if self.config['protocol']=='anthropic':
            messages.append({'role':'user','content':[{'type':'tool_result','tool_use_id':ident,
                'content':json.dumps(result,ensure_ascii=False),'is_error':not result.get('ok',False)} for ident,result in results]})
        else:
            messages.extend({'role':'tool','tool_call_id':ident,'content':json.dumps(result,ensure_ascii=False)} for ident,result in results)
