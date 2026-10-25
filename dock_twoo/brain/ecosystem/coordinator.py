"""Peer delegation with exclusive leases, bounded workers and cancellation."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
from pathlib import Path
import shutil
import tempfile
import threading
import time
from types import SimpleNamespace

from dock_twoo.brain.catalog import character,characters
from dock_twoo.brain.ecosystem.bus import AgentBus

DESKTOP_TOOLS={'open_app','open_url','observe_desktop','click','type_text','press_key','scroll','drag','get_selected_text','describe_active_window'}


class Coordinator:
    def __init__(self, manager):
        self.manager=manager;self.bus=AgentBus(manager.store.data_dir/'ecosystem')
        self.clients={};self.lock=threading.RLock();self.desktop_lock=threading.Lock()
        self.pool=ThreadPoolExecutor(max_workers=29,thread_name_prefix='character-agent')
        self.review_lock=threading.Lock()
        self.agent_states={};self.workspaces={};self.workers={};self.closed=False
        self.cleanup_pending={};self.current_tasks={}

    def client(self, character_id='default'):
        with self.lock:
            if character_id not in self.clients:self.clients[character_id]=self.bus.client(character_id)
            return self.clients[character_id]

    def start(self):self.client();return self

    def begin(self, character_id, prompt, profile, cancel, parent_id='', *, assigning_identity=None):
        while not cancel.is_set():
            result=self.client(assigning_identity or character_id).call('Assign',{'character_id':character_id,'prompt':prompt,'profile_id':profile.get('id',''),'parent_id':parent_id})
            if result['accepted']:
                task_id=result['task_id']
                try:
                    folder=tempfile.TemporaryDirectory(prefix='dock-'+character_id+'-')
                except OSError as exc:
                    self.client(character_id).call('Report',{'task_id':task_id,'state':'failed','error':str(exc)[:4000]})
                    raise
                with self.lock:
                    self.workspaces[task_id]=folder
                    self.current_tasks[character_id]=task_id
                    self.state(character_id,'processing')
                if parent_id:
                    self.manager.run_on_main_thread(lambda: self.manager.notifications.task_started(character(assigning_identity)['name'], character(character_id)['name'], prompt))
                return task_id,Path(folder.name)
            if parent_id:
                raise ValueError(f'{character(character_id)["name"]} is busy. Choose an available peer or finish another subtask first.')
            cancel.wait(.1)
        if self.agent_states.get(character_id)=='queued':
            running=any(job['character_id']==character_id and job['state'] in ('running','cancelling') for job in self.snapshot()['jobs'])
            self.state(character_id,'processing' if running else 'idle')
        raise InterruptedError('Request stopped while waiting for an agent.')

    def state(self, character_id, state):
        with self.lock:self.agent_states[character_id]=state
        def apply():
            self.manager._refresh_actor_states()
        self.manager.run_on_main_thread(apply)

    def publish(self, character_id, task_id, kind, payload):
        return self.client(character_id).call('Publish',{'task_id':task_id,'kind':kind,'payload':payload})

    def complete(self, character_id, task_id, result, state='complete', artifacts=None):
        paths=[]
        with self.lock:folder=self.workspaces.get(task_id)
        destination=self.manager.store.data_dir/'documents'/task_id
        if folder:
            root=Path(folder.name).resolve();used=0
            for source in root.rglob('*'):
                relative=source.relative_to(root)
                if source.is_symlink() or not source.is_file() or source.name in ('task.json','last-message.txt') or any(part.startswith('.') or part in ('node_modules','__pycache__') for part in relative.parts):continue
                used+=source.stat().st_size
                if used>50_000_000:break
                target=destination/source.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target);paths.append(str(target))
        for path in artifacts or []:
            if Path(path).is_file() and (not folder or not Path(path).resolve().is_relative_to(Path(folder.name).resolve())) and path not in paths:paths.append(path)
        self.client(character_id).call('Report',{'task_id':task_id,'state':state,'result':str(result)[:200_000],'artifacts':paths})
        with self.lock:
            folder=self.workspaces.pop(task_id,None)
        if folder:
            try:folder.cleanup()
            except OSError:
                # Windows scanners/CLI children may briefly retain file handles.
                # Cleanup must not turn a completed task back into a failed lease.
                with self.lock:self.cleanup_pending[task_id]=(folder,time.monotonic()+30)
        with self.lock:
            if self.current_tasks.get(character_id)==task_id:
                self.current_tasks.pop(character_id,None)
                self.state(character_id,'idle')
        jobs = self.snapshot()['jobs']
        job = next((job for job in jobs if job['id'] == task_id), None)
        if job and job['parent_id']:
            parent = next((item for item in jobs if item['id'] == job['parent_id']), None)
            if parent:
                self.manager.run_on_main_thread(lambda: self.manager.notifications.task_finished(character(parent['character_id'])['name'], character(character_id)['name'], state))
        return paths

    def cleanup_finished_workspaces(self):
        """Retry only completed, app-owned projects, away from the GUI thread."""
        now=time.monotonic()
        with self.lock:pending=list(self.cleanup_pending.items())
        for task_id,(folder,due) in pending:
            if now<due:continue
            try:folder.cleanup()
            except OSError:
                with self.lock:self.cleanup_pending[task_id]=(folder,now+30)
            else:
                with self.lock:self.cleanup_pending.pop(task_id,None)
        with self.lock:return len(self.cleanup_pending)

    def delegate(self, parent_character, parent_task, tasks, cancel):
        if not isinstance(tasks,list) or not 1<=len(tasks)<=29:raise ValueError('Delegate between 1 and 29 independent tasks.')
        seen=set()
        for task in tasks:
            if not isinstance(task,dict) or set(task)-{'character_id','request'}:raise ValueError('A delegated task needs character_id and request.')
            identity=task.get('character_id');character(identity)
            if identity==parent_character or identity in seen:raise ValueError('Assign each distinct worker at most once in a batch.')
            if not isinstance(task.get('request'),str) or not task['request'].strip() or len(task['request'])>20000:raise ValueError('Supply a bounded worker task.')
            seen.add(identity)
        # Reserve before occupying a pool thread. Busy/ancestor targets fail
        # immediately, so nested delegations cannot fill the pool with waiters.
        futures=[];results=[]
        for task in tasks:
            identity=task['character_id']
            try:
                profile=dict(self.manager.profile_mgr.character_profile(identity))
                key=self.manager.profile_mgr.get_key(profile.get('provider'),profile.get('id'))
                task_id,workspace=self.begin(identity,task['request'],profile,cancel,parent_task,assigning_identity=parent_character)
            except InterruptedError:
                break
            except Exception as exc:
                results.append({'character_id':identity,'name':character(identity)['name'],'state':'unavailable','error':str(exc)[:1000]})
                continue
            futures.append(self.pool.submit(self._run_child,task,parent_task,cancel,profile,key,task_id,workspace))
        for future in as_completed(futures):
            try:results.append(future.result())
            except InterruptedError:pass
        if cancel.is_set():raise InterruptedError('Delegation stopped.')
        budget=max(500,18000//len(results))
        for result in results:
            if len(result.get('summary',''))>budget:
                result['summary']=self.manager.memory.compact([{'role':'assistant','content':result['summary']}],next(t['request'] for t in tasks if t['character_id']==result['character_id']),budget)
                result['summary_compacted']=True
        return {'children':results,'instruction':'Read the result artifacts when more detail is needed. Synthesize the verified results into the final document. Failed workers must be repaired or reported explicitly.'}

    def _run_child(self, task, parent_task, cancel, profile, key, task_id, workspace):
        from dock_twoo.brain.agent import BrainAgent
        identity=task['character_id'];entry=character(identity)
        proxy=None
        try:
            if cancel.is_set():raise InterruptedError('Delegation stopped.')
            proxy=WorkerManager(self.manager,identity,workspace,self.desktop_lock,cancel)
            agent=BrainAgent(self.manager.profile_mgr,proxy,tracker=self.manager.activity,client_factory=self.manager.agent.client_factory)
            agent.coordinator=self
            run=self.manager.activity.start(task['request'],'delegated')
            with self.lock:self.workers[task_id]=agent
            reply=agent.run(task['request'],cancel=cancel,source='delegated',run_id=run,profile=profile,api_key=key,
                            character_id=identity,character_name=entry['name'],task_id=task_id,parent_task_id=parent_task,workspace=workspace)
            state='complete' if agent.status()['state']=='complete' else 'failed'
            artifacts=self.complete(identity,task_id,reply,state,getattr(reply,'artifacts',[]))
            return {'character_id':identity,'name':entry['name'],'task_id':task_id,'state':state,'summary':str(reply)[:6000],'artifacts':artifacts}
        except InterruptedError:
            self.complete(identity,task_id,'Stopped.','cancelled');raise
        except Exception as exc:
            self.publish(identity,task_id,'review_required',{'error':str(exc)[:2000]})
            self.complete(identity,task_id,str(exc),'failed')
            return {'character_id':identity,'name':entry['name'],'task_id':task_id,'state':'failed','error':str(exc)[:2000]}
        finally:
            if proxy:proxy.release_desktop()
            with self.lock:self.workers.pop(task_id,None)

    def review(self, character_id, task_id, prompt, evidence, cancel):
        """A targeted recovery review uses the failing agent's own model profile."""
        from dock_twoo.brain.ecosystem.models import model_client
        from dock_twoo.brain.agent_tools import TOOLS
        while not self.review_lock.acquire(timeout=.1):
            if cancel.is_set():raise InterruptedError('Review stopped.')
        client=None
        try:
            profile=dict(self.manager.profile_mgr.character_profile(character_id))
            key=self.manager.profile_mgr.get_key(profile.get('provider'),profile.get('id'))
            if profile.get('status')=='not configured':return evidence['instruction']
            profile.update(_character_id=character_id,_character_name=character(character_id)['name'],_task_id=task_id)
            run=self.manager.activity.start('Review '+character(character_id)['name']+' failure','review')
            client=self.manager.agent.client_factory(profile,key);client.tracker=self.manager.activity;client.run_id=run;client.max_output_tokens=768
            response=client.turn([{'role':'system','content':'You are the recovery reviewer for this agent. Review the supplied task failure DATA and return one specific recovery instruction via finish. Do not execute tools or claim the task completed.'},
                                  {'role':'user','content':json.dumps({'request':prompt[:4000],'review':evidence},ensure_ascii=False)}],[TOOLS[-1]],cancel)
            guidance=response.calls[0].get('arguments',{}).get('text','') if response.calls else response.text
            guidance=str(guidance or evidence['instruction'])[:4000]
            self.manager.activity.finish(run,'complete',guidance)
            self.publish(character_id,task_id,'recovery',{'guidance':guidance})
            return guidance
        except Exception as exc:
            if cancel.is_set():raise InterruptedError('Review stopped.') from exc
            return evidence['instruction']+' Recovery review could not obtain more guidance: '+str(exc)[:300]
        finally:
            if client and hasattr(client,'close'):client.close()
            self.review_lock.release()

    @staticmethod
    def is_status_question(text):
        text = text.strip().rstrip('.!?').lower()
        return bool(re.fullmatch(r"(?:(?:please|can you|could you)\s+)?(?:give me (?:an? |the )?(?:update|status)(?: on .+)?|(?:what(?:'s| is)|tell me) (?:the |your )?(?:status|progress)(?: of .+| on .+)?|(?:how is|how's) (?:the |your )?(?:research|task|work|project)(?: going| progressing)?|(?:are you|is (?:the )?(?:research|task|work)) (?:done|finished|still working|still running)|status|progress|any update(?:s)?)", text))

    def describe_status(self, character_id):
        """Report the addressed peer's own work and its delegated subtasks."""
        snapshot = self.snapshot()
        jobs = snapshot['jobs']
        own = [job for job in jobs if job['character_id'] == character_id]
        if not own:
            return ''
        job = next((job for job in own if job['state'] in ('running', 'cancelling')), own[0])
        name = character(character_id)['name']
        if job['state'] not in ('running', 'cancelling'):
            if job['state'] == 'complete':
                return f"{name}'s latest task is complete. " + job.get('result', '')[:1200]
            return f"{name}'s latest task is {job['state']}. " + (job.get('error') or job.get('result', ''))[:600]
        if job['state'] == 'cancelling':
            return "I'm stopping this task and waiting for the running work to close."
        children = [child for child in jobs if child['parent_id'] == job['id']]
        parts = []
        for child in sorted(children, key=lambda row: row['started']):
            worker = character(child['character_id'])['name']
            description = ' '.join(child['prompt'].split())[:180]
            progress = child['state']
            if progress == 'running':
                progress = 'in progress'
                if child.get('progress'):
                    detail = child['progress'].get('message') or child['progress'].get('tool')
                    if detail:
                        progress += ' — ' + str(detail).replace('_', ' ')[:120]
            parts.append(f"{worker}: {description} — {progress}.")
        if parts:
            active = any(child['state'] == 'running' for child in children)
            lead = "I've assigned parts of your research to these agents. "
            end = " We're still working. I'll bring you the combined result when it is ready." if active else " I'm reviewing their results and preparing the final response."
            return lead + ' '.join(parts) + end
        detail = job.get('progress', {}).get('message') or job.get('progress', {}).get('tool')
        return "I'm still working on your request" + (': ' + str(detail).replace('_', ' ')[:200] if detail else '') + ". I'll respond when it is ready."

    def snapshot(self):return self.client().call('Snapshot')

    def stop(self):
        if self.bus.port:
            for job in self.snapshot()['jobs']:
                if not job['parent_id'] and job['state']=='running':self.client(job['character_id']).call('Cancel',{'task_id':job['id']})
        with self.lock:workers=list(self.workers.values())
        for worker in workers:worker.stop()

    def close(self):
        if self.closed:return
        self.closed=True;self.stop();self.pool.shutdown(wait=True,cancel_futures=True)
        with self.lock:clients=list(self.clients.values())
        for client in clients:client.close()
        self.bus.close()


class WorkerManager:
    """Child UI context and an exclusive desktop lease; no independent mic/TTS."""
    def __init__(self, manager, identity, workspace, desktop_lock, cancel, *, foreground=False, actor_id=None):
        self.base=manager;self.identity=identity;self.workspace=workspace
        self.foreground=foreground;self.actor_id=actor_id
        self.desktop_lock=desktop_lock;self.cancel=cancel;self.owns_desktop=False
        for key in ('store','profile_mgr','memory','prompt_cache','semantic_model','reader'):
            setattr(self,key,getattr(manager,key))

    @property
    def companion(self):
        actor = next((a for a in self.base.companions.values() if a.character_id==self.identity), None)
        if actor is None:raise ValueError('This agent is working in the background without a character view.')
        return actor

    def __getattr__(self,name):return getattr(self.base,name)

    def run_on_main_thread(self,callback):self.base.run_on_main_thread(callback)

    def acquire_desktop(self):
        if self.owns_desktop:return
        while not self.desktop_lock.acquire(timeout=.1):
            if self.cancel.is_set():raise InterruptedError('Stopped waiting for desktop access.')
        self.owns_desktop=True

    def release_desktop(self):
        if self.owns_desktop:self.desktop_lock.release();self.owns_desktop=False

    def request_read(self, args):
        if not self.foreground:
            raise ValueError('Delegated agents return documents to their parent; only the addressed agent can request speech.')
        source = args['source']
        text = args.get('text', '') if source == 'text' else 'Read ' + source
        self.base._queue_turn(text, 'reader', kind='read_text' if source == 'text' else 'read:' + source, character_id=self.identity)
