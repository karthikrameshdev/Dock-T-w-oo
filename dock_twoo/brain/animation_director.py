"""Model-selected reactions, locally scheduled against the artist's skeleton."""
from __future__ import annotations
import time
from PySide6.QtCore import QObject,QTimer

REACTIONS={'handshake':'handshake','wave':'wave','nod':'nod','celebrate':'celebrate','think':'ponder','read':'read','whistle':'whistle'}
EMOTIONS={'excited':'celebrate','happy':'happy','curious':'ponder','concerned':'sad','calm':'nod','neutral':None}

class AnimationDirector(QObject):
    def __init__(self,manager):
        super().__init__(manager);self.manager=manager;self.last=0.;self.generation=0;self.last_decision={}

    def cancel(self):self.generation+=1

    def respond(self,reply):
        self.generation+=1;token=self.generation
        gesture=getattr(reply,'gesture','none');emotion=getattr(reply,'emotion','neutral')
        action=REACTIONS.get(gesture) or EMOTIONS.get(emotion)
        if gesture=='none' and time.monotonic()-self.last<4:action=None
        self.last_decision={'emotion':emotion,'gesture':gesture,'action':action or 'talk'}
        if not action or self.manager.store.setting('reduced_motion',False) or self.manager.reader.active:return
        from dock_twoo.brain.animation import ACTIONS
        if action not in self.manager.companion.actions:return
        self.last=time.monotonic()
        actor=self.manager.companion
        def play():
            if token!=self.generation or self.manager.reader.active:return
            if actor not in self.manager.companions.values():return
            actor.play_action(action)
        # A response gesture is applied after speech has begun, while live mouth
        # and eyes remain independent from the skeletal clip.
        QTimer.singleShot(180,self,play)
