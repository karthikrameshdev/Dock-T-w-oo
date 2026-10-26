"""Cancellable headless CLI transport. Task JSON goes over stdin, never a shell."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
import uuid

from dock_twoo.brain.cloud import CloudClient,ModelTurn,CloudError
from dock_twoo.brain.ecosystem.models import validate_agent_model


class CLIClient:
    def __init__(self, config, key='', *, timeout=600):
        self.config=validate_agent_model(config);self.key=key;self.timeout=timeout
        from dock_twoo.brain.security.privacy import PrivacyFilter
        self.privacy=PrivacyFilter([key])
        self._folder=tempfile.TemporaryDirectory(prefix='dock-agent-')
        self.workspace=Path(self._folder.name);self.closed=False

    def payload(self,messages,tools):
        messages=self.privacy.messages(messages)
        return {'model':self.config['model'],'protocol':'dock-agent-json-v1','system_and_conversation':messages,'tools':tools,
                'response_contract':{'text':'User-facing answer, or empty while making tool calls','calls':[{'name':'tool name','arguments':{}}]},
                'instructions':'Read the conversation and act on the final user request. Return one JSON object matching response_contract. Tool calls are executed by Dock. Do not execute tools or read local files. Return Dock tool requests for execution by its permission layer. Never claim an unverified action.'}

    def command(self):
        c=self.config;provider=c['provider'];model=c['model'];exe=c['executable']
        if provider!='claude_cli':raise CloudError('This CLI adapter is disabled by the file/privacy guard: it cannot guarantee all reads and writes pass through Dock. Use an API/network profile or Claude CLI with an explicit API key.')
        if not self.key:raise CloudError('Guarded Claude CLI requires a profile API key; home-directory authentication and configuration are not inherited.')
        return [exe,'-p','--output-format','json','--model',model,'--tools','',
                '--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--disable-slash-commands',
                '--setting-sources','','--settings','{"disableAllHooks":true}','--no-session-persistence']

    @staticmethod
    def _terminate(process):
        if os.name=='nt':
            if process.poll() is not None:return
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=5)
        else:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:return
            try:process.wait(timeout=.6)
            except subprocess.TimeoutExpired:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass

    def turn(self,messages,tools,cancel=None):
        cancel=cancel or threading.Event()
        if cancel.is_set():raise InterruptedError('Request stopped.')
        command=self.command()
        payload=self.payload(messages,tools)
        (self.workspace/'task.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
        tracker=getattr(self,'tracker',None)
        call_id=tracker.begin_call(self.run_id,self.config,payload,getattr(self,'step',1),getattr(self,'retry',False),self.key) if tracker else None
        started=time.monotonic();status='success';error='';reported={};process=None
        try:
            environment={k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT','WINDIR','LANG','LC_ALL','TMP','TEMP')}
            # Hidden runtime state is excluded from task artifacts and reports.
            private_home=self.workspace/'.cli-home';private_home.mkdir(exist_ok=True)
            environment.update(HOME=str(private_home),USERPROFILE=str(private_home),XDG_CONFIG_HOME=str(private_home/'config'),CLAUDE_CONFIG_DIR=str(private_home/'claude'))
            # Do not forward unrelated provider keys to a CLI task process.
            selected_keys={'gemini_cli':{'GEMINI_API_KEY','GOOGLE_API_KEY'},'codex_cli':{'OPENAI_API_KEY'},'claude_cli':{'ANTHROPIC_API_KEY','CLAUDE_CODE_OAUTH_TOKEN'},'kilo_cli':{'KILO_API_KEY'}}.get(self.config['provider'],set())
            for name in list(environment):
                upper=name.upper()
                sensitive=upper.endswith(('_API_KEY','_TOKEN','_SECRET','_PASSWORD')) or upper in {'HF_TOKEN','GH_TOKEN','BRAIN_CUSTOM_API_KEY','AGENT_MODEL_API_KEY'}
                if sensitive and name not in selected_keys:environment.pop(name,None)
            secrets = {value for name,value in environment.items() if name in selected_keys and value}
            if self.key:secrets.add(self.key)
            def redacted(value):
                for secret in sorted(secrets,key=len,reverse=True):value=value.replace(secret,'[redacted]')
                return value
            key_name={'gemini_cli':'GEMINI_API_KEY','codex_cli':'OPENAI_API_KEY','claude_cli':'ANTHROPIC_API_KEY','kilo_cli':'KILO_API_KEY'}.get(self.config['provider'],'AGENT_MODEL_API_KEY')
            if self.key and key_name:environment[key_name]=self.key
            environment['AGENT_MODEL_ID']=self.config['model']
            kwargs={'start_new_session':True} if os.name!='nt' else {'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP}
            process=subprocess.Popen(command,cwd=self.workspace,env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
            buffers=[bytearray(),bytearray()];overflow=threading.Event()
            def read(pipe,buffer):
                while True:
                    block=pipe.read(8192)
                    if not block:break
                    if len(buffer)+len(block)>2_000_000:overflow.set()
                    elif not overflow.is_set():buffer.extend(block)
            readers=[threading.Thread(target=read,args=(pipe,buffer),daemon=True) for pipe,buffer in zip((process.stdout,process.stderr),buffers)]
            for worker in readers:worker.start()
            def write():
                try:process.stdin.write(json.dumps(payload,ensure_ascii=False).encode());process.stdin.close()
                except (BrokenPipeError,OSError):pass
            writer=threading.Thread(target=write,daemon=True);writer.start()
            while process.poll() is None:
                if cancel.wait(.05):raise InterruptedError('Request stopped.')
                if overflow.is_set():raise CloudError('CLI output exceeded the task output limit.')
                if time.monotonic()-started>self.timeout:raise CloudError('CLI model timed out.')
            for worker in readers:worker.join(2)
            if overflow.is_set():raise CloudError('CLI output exceeded the task output limit.')
            if process.returncode:
                detail=redacted(buffers[1].decode(errors='replace'))[-1000:]
                raise CloudError(f'CLI exited with code {process.returncode}: {detail}')
            raw_output=redacted(buffers[0].decode(errors='replace'))
            text,reported=self.parse_output(raw_output)
            reported.update(model=self.config['model'],response_text=text,native_output=raw_output[:900000])
            if reported.get('error'):raise CloudError('CLI reported a failure: '+str(reported['error'])[:1000])
            answer=self.workspace/'last-message.txt'
            if self.config['provider']=='codex_cli' and answer.is_file():text=answer.read_text(encoding='utf-8')[:200_000]
            try:
                result=json.loads(text.strip().removeprefix('```json').removesuffix('```').strip())
            except (ValueError,AttributeError):result={'text':text,'calls':[]}
            if not isinstance(result,dict):raise CloudError('CLI returned an invalid agent result.')
            calls=[]
            for item in result.get('calls',[])[:8]:
                if isinstance(item,dict) and isinstance(item.get('name'),str) and isinstance(item.get('arguments'),dict):calls.append({'id':'cli_'+uuid.uuid4().hex,'name':item['name'],'arguments':item['arguments']})
            reply=str(result.get('text',''))
            message={'role':'assistant','content':reply or None}
            if calls:message['tool_calls']=[{'id':c['id'],'type':'function','function':{'name':c['name'],'arguments':json.dumps(c['arguments'])}} for c in calls]
            artifacts=[str(p) for p in self.workspace.rglob('*') if p.is_file() and not p.is_symlink() and p.name not in ('last-message.txt','task.json') and not any(part.startswith('.') or part in ('node_modules','__pycache__') for part in p.relative_to(self.workspace).parts)][:100]
            if tracker and artifacts:tracker.event(self.run_id,'cli_artifacts',{'paths':artifacts})
            return ModelTurn(self.privacy.restore(message),self.privacy.restore(calls),self.privacy.restore(reply),usage=reported.get('usage',{}))
        except InterruptedError as exc:status='cancelled';error=str(exc);raise
        except Exception as exc:status='error';error=str(exc);raise
        finally:
            if process:self._terminate(process)
            if tracker and call_id:tracker.end_call(call_id,reported,'openai',status=status,error=error,latency_ms=round((time.monotonic()-started)*1000),secret=self.key)

    @staticmethod
    def parse_output(text):
        values=[]
        try:values=[json.loads(text)]
        except ValueError:
            for line in text.splitlines():
                try:values.append(json.loads(line))
                except ValueError:pass
        answer='';usage={};error=None
        for data in values:
            if not isinstance(data,dict):continue
            if data.get('error') or data.get('is_error'):error=data.get('error') or data.get('result') or 'CLI could not complete the request.'
            answer=data.get('response') or data.get('result') or answer
            item=data.get('item',{})
            if item.get('type')=='agent_message':answer=item.get('text',answer)
            if data.get('type')=='text':answer+=str(data.get('part',{}).get('text',''))
            raw=data.get('usage')
            if isinstance(raw,dict):
                incoming=raw.get('input_tokens');outgoing=raw.get('output_tokens')
                if incoming is not None:
                    cached=raw.get('cache_read_input_tokens',raw.get('cached_input_tokens',0))
                    created=raw.get('cache_creation_input_tokens',0)
                    # Claude reports base + cache separately; Codex input includes cache.
                    if 'cache_read_input_tokens' in raw:incoming+=cached+created
                    usage={'input_tokens':incoming,'output_tokens':outgoing,'input_tokens_details':{'cached_tokens':cached}}
            models=(data.get('stats') or {}).get('models',{})
            if models:
                tokens=[m.get('tokens',{}) for m in models.values()]
                usage={'input_tokens':sum(t.get('prompt',t.get('input',0)) for t in tokens),'output_tokens':sum(t.get('candidates',t.get('output',0))+t.get('thoughts',0) for t in tokens),'total_tokens':sum(t.get('total',0) for t in tokens),'input_tokens_details':{'cached_tokens':sum(t.get('cached',0) for t in tokens)}}
        result={'usage':usage} if usage else {}
        if error:result['error']=error
        return (json.dumps(answer,ensure_ascii=False) if isinstance(answer,(dict,list)) else str(answer) if answer else text),result

    append_results=CloudClient.append_results

    def close(self):
        if not self.closed:
            if self._folder:self._folder.cleanup()
            self.closed=True
