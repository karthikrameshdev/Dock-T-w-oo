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
        """Create renderers only; no additional speech, model or audio services."""
        from dock_twoo.brain.mascot import Companion
        self._display_entries = {entry['id']: entry for entry in chosen}
        self._all_display_entries = {entry['id']: entry for entry in (inventory or chosen)}
        if not chosen:
            return
        desired = [('brain-' + entry['id'], entry['id'], 'default') for entry in chosen]
        saved = []
        occupied = {(entry['id'], 'default') for entry in chosen}
        valid = {entry['id'] for entry in characters()}
        for item in self.store.setting('brain_instances', []):
            if not isinstance(item, dict) or not str(item.get('id', '')).startswith('extra-'):
                continue
            item = dict(item)
            screen_id = item.get('screen_id')
            char_id = item.get('character_id')
            # Migrate old duplicate Brains to distinct characters without losing the crowd.
            if char_id is None:
                char_id = next((c['id'] for c in characters() if (screen_id, c['id']) not in occupied), None)
            if char_id not in valid or (screen_id, char_id) in occupied:
                continue
            item['character_id'] = char_id
            occupied.add((screen_id, char_id))
            saved.append(item)
            if screen_id in self._display_entries:
                desired.append((item['id'], screen_id, char_id))
        self.store.set_setting('brain_instances', saved)
        # Reuse the startup renderer rather than flashing a second character.
        if 'default' in self.companions:
            actor = self.companions.pop('default')
            actor.actor_id = desired[0][0]
            self.companions[actor.actor_id] = actor
            self._remap_actor('default', actor.actor_id)
        wanted = {key for key, _, _ in desired}
        for key, display_id, char_id in desired:
            actor = self.companions.get(key)
            if actor is None:
                actor = Companion(self, character_id=char_id)
                actor.actor_id = key
                self.companions[key] = actor
            actor.home_display_id = display_id
            actor.assign_display(display_id, self._display_entries[display_id]['screen'])
            if self.store.setting('companion_visible', True):
                actor.show()
        fallback = desired[0][0]
        for key in list(self.companions):
            if key not in wanted:
                self._remap_actor(key, fallback)
                self.companions.pop(key).dispose()
        self._refresh_actor_states()
        if not hasattr(self, 'playground'):
            from dock_twoo.brain.playground import Playground
            self.playground = Playground(self)
        self.playground.arrange()

    def _remap_actor(self, old, new):
        turns=[*self._turn_queue, *(item['turn'] for item in self._processing_turns.values()), *(turn for turn,_ in self._reply_queue), *([self._active_turn] if self._active_turn else [])]
        actor=self.companions.get(old)
        target=self.companions.get(new)
        busy=any(turn.actor_id==old for turn in turns) or self._listening_actor_id==old
        if actor and target and actor.character_id!=target.character_id and busy:
            matching=next((item for key,item in self.companions.items() if key!=old and item.character_id==actor.character_id and item.screen_id in self._display_entries),None)
            new=(matching or self.add_brain(target.screen_id,actor.character_id)).actor_id
        if self._ui_actor_id == old:
            self._ui_actor_id = new
        if self._listening_actor_id == old:
            self._listening_actor_id = new
        if self._pending_listener == old:
            self._pending_listener = new
        if self._session_actor_id == old:
            self._session_actor_id = new
        for turn in turns:
            if turn.actor_id == old:
                turn.actor_id = new

    def character_on_screen(self, character_id, screen_id, *, exclude=None):
        return next((c for c in self.companions.values() if c is not exclude
                     and c.screen_id == screen_id and c.character_id == character_id), None)

    def add_brain(self, target=None, character_id=None):
        """Add a named assistant once per screen, reusing an existing hidden instance."""
        from dock_twoo.brain.mascot import Companion
        source = self.actor_for(target)
        display_id = target if target in self._all_display_entries else source.screen_id
        if character_id is None:
            character_id = next((c['id'] for c in characters()
                                 if not self.character_on_screen(c['id'], display_id)), source.character_id)
        character(character_id)  # Validate before saving or creating a window.
        existing = self.character_on_screen(character_id, display_id)
        if existing is None:
            existing = next((a for a in self.companions.values() if a.character_id==character_id and getattr(a,'home_display_id',a.screen_id)==display_id),None)
            if existing:
                home=self._all_display_entries.get(display_id)
                existing.assign_display(display_id,home['screen'] if home else source.assigned_screen)
        if existing:
            existing.show()
            return existing
        entry = self._all_display_entries.get(display_id)
        actor = Companion(self, character_id=character_id)
        actor.actor_id = 'extra-' + uuid.uuid4().hex
        actor.home_display_id = display_id
        self.companions[actor.actor_id] = actor
        actor.assign_display(display_id, entry['screen'] if entry else source.assigned_screen)
        instances = list(self.store.setting('brain_instances', []))
        instances.append({'id': actor.actor_id, 'screen_id': display_id, 'character_id': character_id})
        self.store.set_setting('brain_instances', instances)
        actor.show()
        if hasattr(self, 'playground'):
            self.playground.arrange()
        self.visibility_changed.emit(True)
        return actor

    def add_all_characters(self, target=None):
        screen_id = self.actor_for(target).screen_id
        for entry in characters():
            self.add_brain(screen_id, entry['id'])

    def voice_actor(self, character_id):
        """Summon on the pointer's selected screen; never choose a different identity."""
        point = QCursor.pos()
        entries = list(self._display_entries.values())
        entry = next((e for e in entries if e['screen'].geometry().contains(point)), None)
        screen_id = entry['id'] if entry else self.actor_for().screen_id
        actor = self.character_on_screen(character_id, screen_id)
        if actor is None:
            actor = self.add_brain(screen_id, character_id)
        actor.show()
        return actor.actor_id

    def set_roam_all_screens(self, enabled):
        self.store.set_setting('brain_roam_all_screens', bool(enabled))
        if not enabled:
            for actor in self.companions.values():
                entry = self._display_entries.get(getattr(actor, 'home_display_id', actor.screen_id))
                if entry:
                    actor.assign_display(entry['id'], entry['screen'])
            if hasattr(self, 'playground'):
                self.playground.arrange()

    def remove_brain(self, actor_id):
        self._remove_secondary_brains({actor_id})

    def remove_all_secondary_brains(self):
        """Remove extras on every display, including saved disconnected displays."""
        keys = set(self.companions)
        keys.update(item.get('id') for item in self.store.setting('brain_instances', [])
                    if isinstance(item, dict))
        self._remove_secondary_brains(keys)

    def actor_busy(self, actor):
        turns=[*self._turn_queue,*(item['turn'] for item in self._processing_turns.values()),*([self._active_turn] if self._active_turn else [])]
        if any(t.actor_id==actor.actor_id or t.character_id==actor.character_id for t in turns):return True
        if self._listening_actor_id==actor.actor_id and (self.listener.is_recording or self.listener._decode_token is not None):return True
        return hasattr(self,'coordinator') and self.coordinator.agent_states.get(actor.character_id) in ('processing','queued')

    def _remove_secondary_brains(self, keys):
        removed = {key for key in keys if isinstance(key, str) and key.startswith('extra-')}
        busy={key for key in removed if key in self.companions and self.actor_busy(self.companions[key])}
        removed-=busy
        if busy:self.status_changed.emit('Busy assistants keep their current task. Stop them before removing their character.')
        primaries = [c for key, c in self.companions.items() if not key.startswith('extra-')]
        if not removed or not primaries:
            return
        for key in removed:
            actor = self.companions.get(key)
            if actor:
                fallback = next((c for c in primaries if c.screen_id == actor.screen_id), primaries[0])
                self._remap_actor(key, fallback.actor_id)
                actor.stop_motion()
                self.companions.pop(key).dispose()
            self._histories.pop(key, None)
        self.store.set_setting('brain_instances', [item for item in self.store.setting('brain_instances', [])
                                                  if isinstance(item, dict) and item.get('id') not in removed])
        positions = self.store.setting('companion_positions', {})
        self.store.set_setting('companion_positions', {key: value for key, value in positions.items() if key not in removed})
        if self._listening_actor_id and (self.listener.is_recording or self.listener._decode_token is not None):
            self.actor_for(self._listening_actor_id).show()
        self._refresh_actor_states()
        if hasattr(self, 'playground'):
            for key in removed:
                self.playground._last_positions.pop(key, None)
                self.playground._groups.pop(key, None)
            self.playground.arrange()
        self.visibility_changed.emit(self.is_mini_agent_visible())

    def _choose_voice_actor(self):
        """A wake word belongs to one visible Brain nearest the pointer."""
        point = QCursor.pos()
        choices = [c for c in self.companions.values() if c.isVisible()]
        if choices:
            return min(choices, key=lambda c: (c.geometry().center() - point).manhattanLength()).actor_id
        return self._ui_actor_id

    def _queue_turn(self, text, source='voice', target=None, kind='request', profile_snapshot=None):
        if STOP.fullmatch(text):
            self._on_voice_stop(text)
            return
        actor = self.actor_for(target or self._listening_actor_id or self._ui_actor_id)
        if profile_snapshot is None:
            profile = dict(self.profile_mgr.character_profile(actor.character_id))
            key = self.profile_mgr.get_key(profile.get('provider'), profile.get('id'))
        else:
            profile, key = profile_snapshot
        transcript = text
        if source == 'voice':
            transcript = getattr(self.listener, 'last_completed_transcript', '') or text
            self.listener.last_completed_transcript = ''
        run_id = self.activity.start(transcript or '[Speech was not understood]', source)
        turn = Turn(text, source, actor.actor_id, profile, key, run_id, kind,
                    character_id=actor.character_id, character_name=actor.character_name)
        self._turn_queue.append(turn)
        self.activity.event(run_id, 'queued', {'position': len(self._turn_queue),
                            'actor_id': actor.actor_id, 'character_id': actor.character_id, 'character_name': actor.character_name, 'screen_id': actor.screen_id,
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
        if self._reply_queue:
            turn, reply = self._reply_queue.popleft()
            self._active_turn = turn
            self._ui_actor_id = turn.actor_id
            self._deliver_model_reply(turn, reply)
            return
        local = next((t for t in self._turn_queue if t.kind != 'request' or self._local_request(t.text)), None)
        if local:
            self._turn_queue.remove(local)
            self._active_turn = local
            self._ui_actor_id = local.actor_id
            if local.kind == 'greeting':
                self._greet_now(local.source, local.text)
            elif local.kind.startswith('read:'):
                self._start_reading_now(local.kind.split(':', 1)[1])
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
        pending = {turn.actor_id for turn in self._turn_queue}
        processing = {item['turn'].actor_id for item in self._processing_turns.values()}
        for key, actor in self.companions.items():
            if key == self._listening_actor_id and self.listener.is_recording:
                state = 'listening'
            elif key == self._listening_actor_id and self.listener._decode_token is not None:
                state = 'processing'
            elif self._active_turn and key == self._active_turn.actor_id:
                state = self._active_turn.phase
            elif key in processing or (hasattr(self,'coordinator') and self.coordinator.agent_states.get(actor.character_id)=='processing'):
                state='processing'
            elif key in pending or (hasattr(self,'coordinator') and self.coordinator.agent_states.get(actor.character_id)=='queued'):
                state='queued'
            else:
                state = 'idle'
            actor.set_activity(state)
            actor.setToolTip(f"{actor.character_name} · {state.title()} · {sum(t.actor_id == key for t in self._turn_queue)} queued")

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
