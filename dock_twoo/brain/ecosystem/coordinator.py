"""Brain-only delegation with distinct workers, exclusive leases and cancellation."""
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

    def client(self, character_id='default'):
        with self.lock:
            if character_id not in self.clients:self.clients[character_id]=self.bus.client(character_id)
            return self.clients[character_id]

    def start(self):self.client();return self

    def begin(self, character_id, prompt, profile, cancel, parent_id=''):
        while not cancel.is_set():
            result=self.client().call('Assign',{'character_id':character_id,'prompt':prompt,'profile_id':profile.get('id',''),'parent_id':parent_id})
            if result['accepted']:
                task_id=result['task_id']
                folder=tempfile.TemporaryDirectory(prefix='dock-'+character_id+'-')
                with self.lock:self.workspaces[task_id]=folder
                self.state(character_id,'processing')
                return task_id,Path(folder.name)
            self.state(character_id,'queued');cancel.wait(.1)
        if self.agent_states.get(character_id)=='queued':
            running=any(job['character_id']==character_id and job['state'] in ('running','cancelling') for job in self.snapshot()['jobs'])
            self.state(character_id,'processing' if running else 'idle')
        raise InterruptedError('Request stopped while waiting for an agent.')

    def state(self, character_id, state):
        with self.lock:self.agent_states[character_id]=state
        def apply():
            actors=[a for a in self.manager.companions.values() if a.character_id==character_id]
            if not actors and state in ('processing','queued'):
                self.manager.voice_actor(character_id)
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
        if folder:folder.cleanup()
        self.state(character_id,'idle')
        return paths

    def delegate(self, parent_character, parent_task, tasks, cancel):
        if parent_character!='default':raise PermissionError('Only Brain may delegate tasks.')
        if not isinstance(tasks,list) or not 1<=len(tasks)<=29:raise ValueError('Delegate between 1 and 29 independent tasks.')
        seen=set()
        for task in tasks:
            if not isinstance(task,dict) or set(task)-{'character_id','request'}:raise ValueError('A delegated task needs character_id and request.')
            identity=task.get('character_id');character(identity)
            if identity=='default' or identity in seen:raise ValueError('Assign each distinct worker at most once in a batch.')
            if not isinstance(task.get('request'),str) or not task['request'].strip() or len(task['request'])>20000:raise ValueError('Supply a bounded worker task.')
            seen.add(identity)
        futures=[self.pool.submit(self._run_child,task,parent_task,cancel) for task in tasks]
        results=[]
        for future in as_completed(futures):
            if cancel.is_set():
                for pending in futures:pending.cancel()
                raise InterruptedError('Delegation stopped.')
            results.append(future.result())
        budget=max(500,18000//len(results))
        for result in results:
            if len(result.get('summary',''))>budget:
                result['summary']=self.manager.memory.compact([{'role':'assistant','content':result['summary']}],next(t['request'] for t in tasks if t['character_id']==result['character_id']),budget)
                result['summary_compacted']=True
        return {'children':results,'instruction':'Read the result artifacts when more detail is needed. Synthesize the verified results into the final document. Failed workers must be repaired or reported explicitly.'}

    def _run_child(self, task, parent_task, cancel):
        from dock_twoo.brain.agent import BrainAgent
        identity=task['character_id'];entry=character(identity)
        profile=dict(self.manager.profile_mgr.character_profile(identity))
        key=self.manager.profile_mgr.get_key(profile.get('provider'),profile.get('id'))
        task_id,workspace=self.begin(identity,task['request'],profile,cancel,parent_task)
        proxy=WorkerManager(self.manager,identity,workspace,self.desktop_lock,cancel)
        agent=BrainAgent(self.manager.profile_mgr,proxy,tracker=self.manager.activity,client_factory=self.manager.agent.client_factory)
        agent.coordinator=self
        run=self.manager.activity.start(task['request'],'delegated')
        with self.lock:self.workers[task_id]=agent
        try:
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
            proxy.release_desktop()
            with self.lock:self.workers.pop(task_id,None)

    def review(self, character_id, task_id, prompt, evidence, cancel):
        """One targeted Brain review; workers never recursively spawn agents."""
        from dock_twoo.brain.ecosystem.models import model_client
        from dock_twoo.brain.agent_tools import TOOLS
        while not self.review_lock.acquire(timeout=.1):
            if cancel.is_set():raise InterruptedError('Review stopped.')
        client=None;review_task=None
        try:
            profile=dict(self.manager.profile_mgr.character_profile('default'))
            key=self.manager.profile_mgr.get_key(profile.get('provider'),profile.get('id'))
            if profile.get('status')=='not configured':return evidence['instruction']
            # Brain's active orchestrator already owns its lease. A worker's
            # standalone request obtains a temporary Brain review lease.
            existing_brain=next((job['id'] for job in self.snapshot()['jobs'] if job['character_id']=='default' and job['state']=='running'),None)
            if character_id!='default' and not existing_brain:review_task,_=self.begin('default','Review worker failure',profile,cancel,task_id)
            profile.update(_character_id='default',_character_name='Brain',_task_id=review_task or existing_brain or task_id,_parent_task_id=task_id if review_task else '')
            run=self.manager.activity.start('Review '+character(character_id)['name']+' failure','review')
            client=self.manager.agent.client_factory(profile,key);client.tracker=self.manager.activity;client.run_id=run;client.max_output_tokens=768
            response=client.turn([{'role':'system','content':'You are Brain, the agent supervisor. Review the supplied task failure DATA and return one specific recovery instruction via finish. Do not execute tools or claim the task completed.'},
                                  {'role':'user','content':json.dumps({'request':prompt[:4000],'review':evidence},ensure_ascii=False)}],[TOOLS[-1]],cancel)
            guidance=response.calls[0].get('arguments',{}).get('text','') if response.calls else response.text
            guidance=str(guidance or evidence['instruction'])[:4000]
            self.manager.activity.finish(run,'complete',guidance)
            if review_task:self.complete('default',review_task,guidance)
            self.publish(character_id,task_id,'recovery',{'brain_guidance':guidance})
            return guidance
        except Exception as exc:
            if review_task:self.complete('default',review_task,str(exc),'failed')
            if cancel.is_set():raise InterruptedError('Review stopped.') from exc
            return evidence['instruction']+' Brain review could not obtain more guidance: '+str(exc)[:300]
        finally:
            if client and hasattr(client,'close'):client.close()
            self.review_lock.release()

    @staticmethod
    def is_status_question(text):
        text = text.strip().rstrip('.!?').lower()
        return bool(re.fullmatch(r"(?:(?:please|can you|could you)\s+)?(?:give me (?:an? |the )?(?:update|status)(?: on .+)?|(?:what(?:'s| is)|tell me) (?:the |your )?(?:status|progress)(?: of .+| on .+)?|(?:how is|how's) (?:the |your )?(?:research|task|work|project)(?: going| progressing)?|(?:are you|is (?:the )?(?:research|task|work)) (?:done|finished|still working|still running)|status|progress|any update(?:s)?)", text))

    def describe_status(self, character_id):
        """Read worker-owned live reports through Brain's authenticated gRPC bus.

        This control request never acquires a second work lease or calls a model.
        Worker status is limited to that worker; Brain may describe its children.
        """
        snapshot = self.snapshot()
        jobs = snapshot['jobs']
        own = [job for job in jobs if job['character_id'] == character_id and not job['parent_id']]
        if not own:
            own = [job for job in jobs if job['character_id'] == character_id]
        active = [job for job in jobs if job['state'] in ('running','cancelling')]
        if character_id=='default' and active and not any(job['state']=='running' for job in own):
            return "I'm monitoring these tasks. " + ' '.join(character(job['character_id'])['name']+': '+' '.join(job['prompt'].split())[:160]+' — '+('in progress' if job['state']=='running' else 'stopping')+'.' for job in active) + ' Their results will be delivered when ready.'
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
        children = [child for child in jobs if child['parent_id'] == job['id']] if character_id == 'default' else []
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
                if not job['parent_id'] and job['state']=='running':self.client().call('Cancel',{'task_id':job['id']})
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
        if self.actor_id in self.base.companions:return self.base.companions[self.actor_id]
        return next(a for a in self.base.companions.values() if a.character_id==self.identity)

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
            raise ValueError('Delegated agents return documents to Brain; only the addressed agent can request speech.')
        actor = self.companion
        source = args['source']
        text = args.get('text', '') if source == 'text' else 'Read ' + source
        self.base._queue_turn(text, 'reader', actor.actor_id, 'read_text' if source == 'text' else 'read:' + source)
