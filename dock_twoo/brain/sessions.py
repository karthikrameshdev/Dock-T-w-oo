"""Parallel character work, exclusive task leases, and one microphone/speaker lane."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import re
import threading
import uuid

from PySide6.QtCore import QPoint, QThread, QTimer
from PySide6.QtGui import QCursor
from dock_twoo.brain.catalog import characters, character, named_prefix


@dataclass
class Turn:
    text: str
    source: str
    actor_id: str
    profile: dict
    key: str = field(repr=False)
    run_id: str = ''
    kind: str = 'request'
    phase: str = 'processing'
    character_id: str = 'default'
    character_name: str = 'Brain'

    def public(self, companions):
        actor = companions.get(self.actor_id)
        return {'id': self.run_id, 'text': self.text, 'source': self.source,
                'actor_id': self.actor_id, 'character_id': self.character_id, 'character_name': self.character_name, 'screen_id': actor.screen_id if actor else '',
                'profile_id': self.profile.get('id', ''), 'profile_name': self.profile.get('name', ''),
                'phase': self.phase}


STOP = re.compile(r'\s*(?:(?:hey|okay|ok)[,\s]+)?(?:(?:brain|buddy)[,\s]+)?(?:please\s+)?stop(?:\s+(?:please|talking|speaking|reading))?[.!?\s]*', re.I)


class BrainSessions:
    """Mixed into BrainManager; every method mutates GUI state on its Qt thread."""
    def _init_sessions(self):
        self.companions = {}
        self._display_entries = {}
        self._all_display_entries = {}
        self._ui_actor_id = 'default'
        self._listening_actor_id = None
        self._listening_source = None
        self._pending_listener = None
        self._pending_listener_source = None
        self._active_turn = None
        self._turn_queue = deque()
        self._reply_queue = deque()
        self._processing_turns = {}
        self._character_agents = {}
        self._worker_running = False
        self._awaiting_reply = False
        self._deferred_reply = None
        self._stopping = False
        self._histories = {}
        self._character_histories = {}
        self._session_actor_id = None
        self._session_source = None
        from dock_twoo.brain.native_input import NativeInputRouter
        self.input_router = NativeInputRouter(self)

    @property
    def companion(self):
        return self.actor_for(self.active_actor_id)

    @property
    def active_actor_id(self):
        return (self._active_turn.actor_id if self._active_turn else
                self._listening_actor_id or self._ui_actor_id)

    @property
    def active_screen_id(self):
        return self.companion.screen_id

    @property
    def conversation_history(self):
        actor=self.actor_for(self.active_actor_id)
        history=self._character_histories.setdefault(actor.character_id,self._histories.get(actor.actor_id,[]))
        self._histories[actor.actor_id]=history
        return history

    @conversation_history.setter
    def conversation_history(self, value):
        actor=self.actor_for(self.active_actor_id)
        self._character_histories[actor.character_id]=value
        self._histories[actor.actor_id]=value

    def actor_for(self, target=None):
        if target in self.companions:
            return self.companions[target]
        if target:
            actor = next((c for c in self.companions.values() if c.screen_id == target), None)
            if actor:
                return actor
        return self.companions.get(self._ui_actor_id) or next(iter(self.companions.values()))

    def companion_for(self, screen_id=None):
        return self.actor_for(screen_id or self._ui_actor_id)

    def configure_displays(self, chosen, inventory=None):
        """One presentation window for the app, regardless of dock/display count."""
        self._display_entries = {entry['id']: entry for entry in chosen}
        self._all_display_entries = {entry['id']: entry for entry in (inventory or chosen)}
        if not chosen:
            return
        actor = self.actor_for()
        display_id = self.store.setting('assistant_display', '')
        entry = self._all_display_entries.get(display_id, chosen[0])
        actor.home_display_id = entry['id']
        actor.assign_display(entry['id'], entry['screen'])
        # Retire saved crowds; character profiles, memories and work survive.
        self.store.set_setting('brain_instances', [])
        if not display_id:self.store.set_setting('assistant_display', entry['id'])
        if self.store.setting('companion_visible', True):
            actor.show()
        self._refresh_actor_states()
        if not hasattr(self, 'playground'):
            from dock_twoo.brain.playground import Playground
            self.playground = Playground(self)

    def character_on_screen(self, character_id, screen_id, *, exclude=None):
        return next((c for c in self.companions.values() if c is not exclude
                     and c.screen_id == screen_id and c.character_id == character_id), None)

    def select_character(self, character_id, screen_id=None):
        """Replace the model in the sole renderer; never create a worker window."""
        character(character_id)
        actor = self.actor_for()
        actor.switch_character(character_id)
        self.store.set_setting('active_character', character_id)
        entry = self._all_display_entries.get(screen_id)
        if entry:
            actor.home_display_id = entry['id']
            actor.assign_display(entry['id'], entry['screen'])
            self.store.set_setting('assistant_display', entry['id'])
        self._ui_actor_id = actor.actor_id
        actor.show()
        self._refresh_actor_states()
        self.visibility_changed.emit(True)
        return actor

    def choose_assistant(self, character_id):
        """Manual selection ends the audio session, but leaves model jobs running."""
        if self.actor_for().character_id != character_id:
            self.in_conversation_session = False
            self.session_timer.stop()
            self.listener.cancel_recording()
            self._listening_actor_id = self._listening_source = None
            self._session_actor_id = self._session_source = None
            self._pending_listener = self._pending_listener_source = None
            self._active_turn = None
            self._awaiting_reply = False
            self._deferred_reply = None
            self.reader.stop()
            self.speech.stop()
            self.listener.set_output_active(False)
            self.listener.arm_wake()
        return self.select_character(character_id)

    def voice_actor(self, character_id):
        """A named wake replaces the presentation; the shared capture stays intact."""
        point = QCursor.pos()
        entry = next((e for e in self._display_entries.values()
                      if e['screen'].geometry().contains(point)), None)
        return self.select_character(character_id, entry['id'] if entry else None).actor_id

    def set_roam_all_screens(self, enabled):
        self.store.set_setting('brain_roam_all_screens', bool(enabled))
        if not enabled:
            for actor in self.companions.values():
                entry = self._display_entries.get(getattr(actor, 'home_display_id', actor.screen_id))
                if entry:
                    actor.assign_display(entry['id'], entry['screen'])
            if hasattr(self, 'playground'):
                self.playground.arrange()

    def actor_busy(self, actor):
        identity = actor.character_id
        turns = [*self._turn_queue, *(turn for turn, _ in self._reply_queue),
                 *(item['turn'] for item in self._processing_turns.values()),
                 *([self._active_turn] if self._active_turn else [])]
        return (any(t.character_id == identity for t in turns)
                or self.listener.is_recording or self.listener._decode_token is not None
                or self.coordinator.agent_states.get(identity) in ('processing', 'queued'))

    def _choose_voice_actor(self):
        """A wake word belongs to one visible Brain nearest the pointer."""
        point = QCursor.pos()
        choices = [c for c in self.companions.values() if c.isVisible()]
        if choices:
            return min(choices, key=lambda c: (c.geometry().center() - point).manhattanLength()).actor_id
        return self._ui_actor_id

    def _queue_turn(self, text, source='voice', target=None, kind='request', profile_snapshot=None, character_id=None):
        if STOP.fullmatch(text):
            self._on_voice_stop(text)
            return
        actor = self.actor_for(target or self._listening_actor_id or self._ui_actor_id)
        identity = character_id or actor.character_id
        entry = character(identity)
        if profile_snapshot is None:
            profile = dict(self.profile_mgr.character_profile(identity))
            key = self.profile_mgr.get_key(profile.get('provider'), profile.get('id'))
        else:
            profile, key = profile_snapshot
        transcript = text
        if source == 'voice':
            transcript = getattr(self.listener, 'last_completed_transcript', '') or text
            self.listener.last_completed_transcript = ''
        run_id = self.activity.start(transcript or '[Speech was not understood]', source)
        turn = Turn(text, source, actor.actor_id, profile, key, run_id, kind,
                    character_id=identity, character_name=entry['name'])
        self._turn_queue.append(turn)
        self.activity.event(run_id, 'queued', {'position': len(self._turn_queue),
                            'actor_id': actor.actor_id, 'character_id': identity, 'character_name': entry['name'], 'screen_id': actor.screen_id,
                            'profile_id': profile.get('id'), 'profile_name': profile.get('name')})
        self._refresh_actor_states()
        self._drain_turns()

    def _drain_turns(self):
        if self._stopping:
            return
        if self.listener.is_recording or self.listener._decode_token is not None:
            return
        # Start independent reasoning even while another character is speaking.
        # Preserve FIFO for requests addressed to the same logical character.
        waiting = deque()
        while self._turn_queue:
            turn = self._turn_queue.popleft()
            if turn.kind == 'request' and self.coordinator.is_status_question(turn.text):
                reply = self.coordinator.describe_status(turn.character_id)
                if reply:
                    self.activity.event(turn.run_id, 'live_status', {'character_id': turn.character_id, 'source': 'grpc'})
                    self.activity.finish(turn.run_id, 'complete', reply)
                    self._reply_queue.append((turn, reply))
                    continue
            if turn.kind != 'request' or self._local_request(turn.text):
                waiting.append(turn)
                continue
            busy = any(item['turn'].character_id == turn.character_id for item in self._processing_turns.values())
            if busy or self.coordinator.agent_states.get(turn.character_id) in ('processing', 'queued'):
                waiting.append(turn)
                continue
            self._launch_model_turn(turn)
        self._turn_queue = waiting
        self._refresh_actor_states()
        if self._active_turn or self._awaiting_reply or self.reader.active:
            return
        while self._reply_queue:
            turn, reply = self._reply_queue.popleft()
            if turn.character_id != self.companion.character_id:
                self.notifications.show(f"{turn.character_name} finished. Select {turn.character_name} and ask for its status.")
                continue
            self._active_turn = turn
            self._ui_actor_id = turn.actor_id
            self._deliver_model_reply(turn, reply)
            return
        local = next((t for t in self._turn_queue if t.kind != 'request' or self._local_request(t.text)), None)
        if local:
            self.select_character(local.character_id)
            self._turn_queue.remove(local)
            self._active_turn = local
            self._ui_actor_id = local.actor_id
            if local.kind == 'greeting':
                self._greet_now(local.source, local.text)
            elif local.kind.startswith('read:'):
                self._start_reading_now(local.kind.split(':', 1)[1])
            elif local.kind == 'reminder':
                self._awaiting_reply = True
                self._publish_response(local.text)
                self.activity.finish(local.run_id, 'complete', local.text)
                self._do_speech_start(local.text)
            elif local.kind == 'read_text':
                self._read_text_now(local.text)
            else:
                self._process_turn(local.text, local.source)
        else:
            self._resume_session()

    @staticmethod
    def _local_request(text):
        identity, command = named_prefix(text)
        return (not text.strip() or (identity is not None and not command) or bool(re.match(r"^(?:(?:okay|ok|alright|please)[,\s]+)?(?:read\b|stop\s+reading\b|bye\b|goodbye\b|that's all\b|dismiss\b|see you\b|exit\b|stop listening\b)", text.strip(), re.I)))

    def _finish_turn(self):
        if self.reader.active or self._awaiting_reply:
            return
        self._active_turn = None
        self._deferred_reply = None
        self._refresh_actor_states()
        if self._turn_queue or self._reply_queue:
            QTimer.singleShot(0, self, self._drain_turns)
        else:
            self._resume_session()

    def _resume_session(self):
        if self._stopping or self._active_turn or self.listener.is_recording or self.listener._decode_token is not None:
            return
        self.listener.set_output_active(False)
        if self.in_conversation_session and not self._processing_turns:
            self._listening_actor_id = self._session_actor_id or self._ui_actor_id
            self._listening_source = self._session_source
            self.listener.capture_character_id = self.actor_for(self._listening_actor_id).character_id
            self.listener.start_recording()
        else:
            self._listening_actor_id = None
            self._listening_source = None
            self.listener.arm_wake()
        self._refresh_actor_states()

    def _set_active_activity(self, state):
        if QThread.currentThread() != self.thread():
            self.run_on_main_thread(lambda: self._set_active_activity(state))
            return
        if self._active_turn:
            if state == 'idle' and self._active_turn.run_id in self._processing_turns and not self._stopping:
                state = 'processing'
            self._active_turn.phase = state
            self._refresh_actor_states()
        else:
            self.companion.set_activity(state)

    def _refresh_actor_states(self):
        if not hasattr(self, 'listener'):
            return
        pending = {turn.character_id for turn in self._turn_queue}
        processing = {item['turn'].character_id for item in self._processing_turns.values()}
        for key, actor in self.companions.items():
            if key == self._listening_actor_id and self.listener.is_recording:
                state = 'listening'
            elif key == self._listening_actor_id and self.listener._decode_token is not None:
                state = 'processing'
            elif self._active_turn and actor.character_id == self._active_turn.character_id:
                state = self._active_turn.phase
            elif actor.character_id in processing or (hasattr(self,'coordinator') and self.coordinator.agent_states.get(actor.character_id)=='processing'):
                state='processing'
            elif actor.character_id in pending or (hasattr(self,'coordinator') and self.coordinator.agent_states.get(actor.character_id)=='queued'):
                state='queued'
            else:
                state = 'idle'
            actor.set_activity(state)
            actor.setToolTip(f"{actor.character_name} · {state.title()} · {sum(t.character_id == actor.character_id for t in self._turn_queue)} queued")

    def _after_capture(self):
        self._listening_actor_id = None
        self._listening_source = None
        if self._pending_listener:
            target, self._pending_listener = self._pending_listener, None
            source, self._pending_listener_source = self._pending_listener_source, None
            self._start_capture(target, source or 'click')
        elif self._deferred_reply:
            deliver, self._deferred_reply = self._deferred_reply, None
            deliver()
        else:
            self._drain_turns()
        self._refresh_actor_states()

    def _start_capture(self, actor_id, source='click'):
        self._listening_actor_id = actor_id
        self._listening_source = source
        self._ui_actor_id = actor_id
        self._session_actor_id = actor_id
        self._session_source = source
        self.in_conversation_session = True
        self.session_timer.stop()
        self.listener.start()
        self.listener.set_output_active(False)
        actor = self.actor_for(actor_id)
        actor.show()
        actor.raise_()
        actor.stop_motion()
        actor.turn_to_user()
        self.listener.capture_character_id = actor.character_id
        self.listener.start_recording()
        self.visibility_changed.emit(True)
        self._refresh_actor_states()

    def queue_status(self):
        return {'active': self._active_turn.public(self.companions) if self._active_turn else None,
                'pending': [turn.public(self.companions) for turn in self._turn_queue],
                'listener_actor_id': self._listening_actor_id,
                'listener_screen_id': self.actor_for(self._listening_actor_id).screen_id if self._listening_actor_id else None,
                'worker_running': self._worker_running,
                'processing': [item['turn'].public(self.companions) for item in self._processing_turns.values()],
                'ready_replies': len(self._reply_queue)}
