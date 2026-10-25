"""Stochastic local-transformer animation policy with uninterrupted clip ownership."""
from concurrent.futures import ThreadPoolExecutor
import math
import random
import time
import numpy as np
from PySide6.QtCore import QObject,QPoint,QTimer

LOCOMOTION={'walk','run','dash','walk_window','chase_ball','fly','glide','soar'}


class EcologyDirector(QObject):
    def __init__(self,manager):
        super().__init__(manager);self.manager=manager;self.pending=set();self.next={};self.recent={}
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='animation-policy');self.closed=False;self.next_sound=time.monotonic()+20
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.tick);self.timer.start()

    def tick(self):
        model=self.manager.semantic_model
        if self.closed or not model.ready or not self.manager.store.setting('roaming',True):return
        now=time.monotonic()
        if now>self.next_sound:
            self.next_sound=now+random.uniform(18,40)
            idle=[a for a in self.manager.companions.values() if a.isVisible() and a.activity=='idle']
            if idle and self.manager.store.setting('character_sounds',True) and not self.manager._active_turn and not self.manager._turn_queue and not self.manager.listener.is_recording and not self.manager.in_conversation_session and not self.manager.speech.playing:
                actor=random.choice(idle);self.manager._ui_actor_id=actor.actor_id
                self.manager.speech.sound(actor.character_id)
        for actor in list(self.manager.companions.values()):
            actor.roam_timer.stop()
            if getattr(actor, 'resource_resting', False):continue
            if actor.actor_id in self.pending or now<self.next.get(actor.actor_id,0):continue
            if not actor.isVisible() or actor.activity!='idle' or actor.action or actor.on_turn_finished or actor.origin or actor.reduced_motion or actor.follow_cursor_enabled or now-actor.last_dragged<12:continue
            identity=actor.actor_id;self.pending.add(identity)
            # Each renderer keeps its own action clock. Policy evaluation never
            # interrupts a playing clip or a route to its current destination.
            candidates=[key for key,value in actor.character['actions'].items()
                        if key in LOCOMOTION or value.get('category') in ('species','acting')]
            if not candidates:candidates=['walk']
            context=f"A friendly {actor.character['species']} exploring the desktop, curious, playful, relaxed and moving naturally."
            future=self.pool.submit(self.choose,model,context,candidates,list(self.recent.get(identity,[])))
            future.add_done_callback(lambda result,a=actor,key=identity,char=actor.character_id:self.manager.run_on_main_thread(lambda:self.apply(a,key,result,char)))

    @staticmethod
    def choose(model,context,candidates,recent):
        query=model.embed(context)
        scores=np.array([float(model.embed('Perform '+key.replace('_',' ')+' naturally.')@query)-(.45 if key in recent else 0) for key in candidates])
        weights=np.exp((scores-scores.max())/.22);weights/=weights.sum()
        return str(np.random.default_rng().choice(candidates,p=weights))

    def apply(self,actor,identity,future,character_id=None):
        self.pending.discard(identity)
        if self.closed or actor not in self.manager.companions.values():return
        if character_id is not None and actor.character_id != character_id:return
        self.next[identity]=time.monotonic()+random.uniform(2,7)
        try:action=future.result()
        except Exception:return
        if getattr(actor,'resource_resting',False):return
        if actor.activity!='idle' or actor.action or actor.on_turn_finished or actor.origin or actor.reduced_motion or not actor.isVisible() or not self.manager.store.setting('roaming',True):return
        self.recent[identity]=[*self.recent.get(identity,[]),action][-5:]
        if action in LOCOMOTION and actor.assigned_screen:
            area=actor.assigned_screen.availableGeometry();bounds=actor.body_region().boundingRect()
            destination=QPoint(random.randint(area.left()-bounds.left(),max(area.left()-bounds.left(),area.right()-bounds.right())),
                               random.randint(area.top()-bounds.top(),max(area.top()-bounds.top(),area.bottom()-bounds.bottom())))
            distance=math.hypot(destination.x()-actor.x(),destination.y()-actor.y())
            actor.play_action(action,destination,max(2,distance/(180 if action in ('run','dash','fly') else 100)))
            actor.roam_action=True
        else:actor.play_action(action)

    def close(self):
        self.closed=True;self.timer.stop();self.pool.shutdown(wait=False,cancel_futures=True)
