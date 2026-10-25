"""One FIFO execution lane and one microphone owner for all Brain characters."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import re
import threading
import uuid

from PySide6.QtCore import QPoint, QThread, QTimer
from PySide6.QtGui import QCursor


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

    def public(self, companions):
        actor = companions.get(self.actor_id)
        return {'id': self.run_id, 'text': self.text, 'source': self.source,
                'actor_id': self.actor_id, 'screen_id': actor.screen_id if actor else '',
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
        self._worker_running = False
        self._awaiting_reply = False
        self._deferred_reply = None
        self._stopping = False
        self._histories = {}
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
        return self._histories.setdefault(self.active_actor_id, [])

    @conversation_history.setter
    def conversation_history(self, value):
        self._histories[self.active_actor_id] = value

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
        desired = [('brain-' + entry['id'], entry['id']) for entry in chosen]
        desired += [(item['id'], item['screen_id']) for item in self.store.setting('brain_instances', [])
                    if isinstance(item, dict) and item.get('id') and item.get('screen_id') in self._display_entries]
        # Reuse the startup renderer rather than flashing a second character.
        if 'default' in self.companions:
            actor = self.companions.pop('default')
            actor.actor_id = desired[0][0]
            self.companions[actor.actor_id] = actor
            self._remap_actor('default', actor.actor_id)
        wanted = {key for key, _ in desired}
        for key, display_id in desired:
            actor = self.companions.get(key)
            if actor is None:
                actor = Companion(self)
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
        if self._ui_actor_id == old:
            self._ui_actor_id = new
        if self._listening_actor_id == old:
            self._listening_actor_id = new
        if self._pending_listener == old:
            self._pending_listener = new
        if self._session_actor_id == old:
            self._session_actor_id = new
        for turn in [*self._turn_queue, *([self._active_turn] if self._active_turn else [])]:
            if turn.actor_id == old:
                turn.actor_id = new

    def add_brain(self, target=None):
        from dock_twoo.brain.mascot import Companion
        source = self.actor_for(target)
        display_id = target if target in self._display_entries else source.screen_id
        entry = self._all_display_entries.get(display_id)
        if entry is None:
            entry = next(iter(self._display_entries.values()), None)
        actor = Companion(self)
        actor.actor_id = 'extra-' + uuid.uuid4().hex
        actor.home_display_id = entry['id'] if entry else source.screen_id
        self.companions[actor.actor_id] = actor
        actor.assign_display(actor.home_display_id, entry['screen'] if entry else source.assigned_screen)
        instances = list(self.store.setting('brain_instances', []))
        instances.append({'id': actor.actor_id, 'screen_id': actor.home_display_id})
        self.store.set_setting('brain_instances', instances)
        actor.show()
        if hasattr(self, 'playground'):
            self.playground.arrange()
        self.visibility_changed.emit(True)
        return actor

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

    def _remove_secondary_brains(self, keys):
        removed = {key for key in keys if isinstance(key, str) and key.startswith('extra-')}
        primaries = [c for key, c in self.companions.items() if not key.startswith('extra-')]
        if not removed or not primaries:
            return
        for key in removed:
            actor = self.companions.get(key)
            if actor:
                fallback = next((c for c in primaries if c.screen_id == actor.screen_id), primaries[0])
                # Preserve accepted work and the single microphone on a primary.
                if key == self._session_actor_id or (self._active_turn and self._active_turn.actor_id == key):
                    if key in self._histories:
                        self._histories[fallback.actor_id] = self._histories[key]
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
            profile = dict(self.profile_mgr.get_active_profile())
            key = self.profile_mgr.get_key(profile.get('provider'), profile.get('id'))
        else:
            profile, key = profile_snapshot
        transcript = text
        if source == 'voice':
            transcript = getattr(self.listener, 'last_completed_transcript', '') or text
            self.listener.last_completed_transcript = ''
        run_id = self.activity.start(transcript or '[Speech was not understood]', source)
        turn = Turn(text, source, actor.actor_id, profile, key, run_id, kind)
        self._turn_queue.append(turn)
        self.activity.event(run_id, 'queued', {'position': len(self._turn_queue),
                            'actor_id': actor.actor_id, 'screen_id': actor.screen_id,
                            'profile_id': profile.get('id'), 'profile_name': profile.get('name')})
        self._refresh_actor_states()
        self._drain_turns()

    def _drain_turns(self):
        if self._stopping or self._active_turn or self._worker_running:
            return
        # A new capture must finish before any reply can take the shared speaker.
        if self.listener.is_recording or self.listener._decode_token is not None:
            return
        if not self._turn_queue:
            self._resume_session()
            return
        self._active_turn = self._turn_queue.popleft()
        turn = self._active_turn
        self._ui_actor_id = turn.actor_id
        self.activity.event(turn.run_id, 'dequeued', {'actor_id': turn.actor_id, 'screen_id': self.active_screen_id})
        self._refresh_actor_states()
        if turn.kind.startswith('read:'):
            self._start_reading_now(turn.kind.split(':', 1)[1])
        elif turn.kind == 'read_text':
            self._read_text_now(turn.text)
        else:
            self._process_turn(turn.text, turn.source)

    def _finish_turn(self):
        if self._worker_running or self.reader.active or self._awaiting_reply:
            return
        self._active_turn = None
        self._deferred_reply = None
        self._refresh_actor_states()
        if self._turn_queue:
            QTimer.singleShot(0, self, self._drain_turns)
        else:
            self._resume_session()

    def _resume_session(self):
        if self._stopping or self._active_turn or self._worker_running or self.listener.is_recording or self.listener._decode_token is not None:
            return
        self.listener.set_output_active(False)
        if self.in_conversation_session:
            self._listening_actor_id = self._session_actor_id or self._ui_actor_id
            self._listening_source = self._session_source
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
            if state == 'idle' and self._worker_running and not self._stopping:
                state = 'processing'
            self._active_turn.phase = state
            self._refresh_actor_states()
        else:
            self.companion.set_activity(state)

    def _refresh_actor_states(self):
        if not hasattr(self, 'listener'):
            return
        pending = {turn.actor_id for turn in self._turn_queue}
        for key, actor in self.companions.items():
            if key == self._listening_actor_id and self.listener.is_recording:
                state = 'listening'
            elif key == self._listening_actor_id and self.listener._decode_token is not None:
                state = 'processing'
            elif self._active_turn and key == self._active_turn.actor_id:
                state = self._active_turn.phase
            elif key in pending:
                state = 'queued'
            else:
                state = 'idle'
            actor.set_activity(state)
            actor.setToolTip(f"Brain · {state.title()} · {sum(t.actor_id == key for t in self._turn_queue)} queued")

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
            if self._active_turn:
                self.listener.set_output_active(True)
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
        self.listener.start_recording()
        self.visibility_changed.emit(True)
        self._refresh_actor_states()

    def queue_status(self):
        return {'active': self._active_turn.public(self.companions) if self._active_turn else None,
                'pending': [turn.public(self.companions) for turn in self._turn_queue],
                'listener_actor_id': self._listening_actor_id,
                'listener_screen_id': self.actor_for(self._listening_actor_id).screen_id if self._listening_actor_id else None,
                'worker_running': self._worker_running}
