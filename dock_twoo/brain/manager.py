"""BrainManager singleton coordinating the Mini Agent companion, speech, model routing, and context menus."""

from __future__ import annotations

import json
from pathlib import Path
import random
import os
import re
import threading
import time
import webbrowser
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QMetaObject, QObject, QPoint, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import QMenu, QApplication

from dock_twoo.brain.animation import ACTIONS
from dock_twoo.brain.listener import AudioListener, GlobalShortcutListener
from dock_twoo.brain.mascot import Companion
from dock_twoo.brain.profiles import ProfileManager
from dock_twoo.brain.providers import query_llm
from dock_twoo.brain.speech import SpeechPlayback
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.agent import BrainAgent
from dock_twoo.brain.cloud import NOT_CONFIGURED
from dock_twoo.brain.local_tts import get_local_tts
from dock_twoo.brain.animation_director import AnimationDirector
from dock_twoo.brain.sessions import BrainSessions


class BrainManager(QObject, BrainSessions):
    """Central controller for the Brain voice-assisted system."""

    status_changed = Signal(str)
    reply_received = Signal(str)
    app_open_requested = Signal(str)
    app_data_changed = Signal(str)
    tasks_view_requested = Signal(object)
    visibility_changed = Signal(bool)

    # Thread-safe dispatch signals for mascot updates from worker threads
    action_requested = Signal(str)
    activity_requested = Signal(str)
    speech_start_requested = Signal(str)
    show_mini_agent_requested = Signal()
    hide_mini_agent_requested = Signal()
    toggle_mini_agent_requested = Signal()
    wake_detected_requested = Signal()
    turn_complete_requested = Signal(str)
    main_thread_action_requested = Signal(object)

    _instance: Optional[BrainManager] = None

    @classmethod
    def get_instance(cls) -> BrainManager:
        try:
            import shiboken6
            if cls._instance is not None and not shiboken6.isValid(cls._instance):
                cls._instance = None
        except Exception:
            pass

        if cls._instance is None:
            cls._instance = BrainManager()
        return cls._instance

    def __init__(self, parent: Optional[QObject] = None, *, store=None, start_services: bool = True, voice_model_dir=None):
        super().__init__(parent)
        if "PYTEST_CURRENT_TEST" in os.environ:
            start_services = False
        self.store = store or BrainStore()
        self.profile_mgr = ProfileManager(self.store)
        from dock_twoo.brain.activity import ActivityStore
        self.activity = ActivityStore(self.store.data_dir/'activity')
        if start_services:self.activity.recover_interrupted()
        self.activity_cleanup = QTimer(self)
        self.activity_cleanup.setInterval(60*60*1000)
        self.activity_cleanup.timeout.connect(self.activity.prune)
        if start_services:self.activity_cleanup.start()
        from dock_twoo.brain.audio_devices import DefaultAudioDevices
        self.audio_devices = DefaultAudioDevices(self)
        self.speech = SpeechPlayback(self, audio_devices=self.audio_devices)
        self.speech.store = self.store

        self._init_sessions()
        actor = Companion(self)
        actor.actor_id = 'default'
        self.companions['default'] = actor
        self.speech.activity.connect(self._set_active_activity)
        self.speech.mouth.connect(lambda value: self.companion.set_mouth(value))

        self.activity_requested.connect(self._set_active_activity)
        self.speech_start_requested.connect(self._do_speech_start)
        self.action_requested.connect(self._do_action)
        self.show_mini_agent_requested.connect(self._do_show_mini_agent, Qt.ConnectionType.QueuedConnection)
        self.hide_mini_agent_requested.connect(self._do_hide_mini_agent, Qt.ConnectionType.QueuedConnection)
        self.toggle_mini_agent_requested.connect(self._do_toggle_mini_agent, Qt.ConnectionType.QueuedConnection)
        self.wake_detected_requested.connect(self._do_wake_detected, Qt.ConnectionType.QueuedConnection)
        self.turn_complete_requested.connect(self._do_turn_complete, Qt.ConnectionType.QueuedConnection)
        self.main_thread_action_requested.connect(self._do_run_main_action, Qt.ConnectionType.QueuedConnection)

        self._active_query_thread: Optional[threading.Thread] = None
        self._is_listening: bool = False
        self.in_conversation_session: bool = False
        self.conversation_history: List[Dict[str, str]] = []
        self.wake_count: int = 0
        self.last_wake_time: float = 0.0
        self._last_wake_reply: str = ""
        self._query_generation = 0
        self.last_response = {'generation':0, 'text':''}
        self._response_generation = 0
        self._agent_cancel = threading.Event()

        self.session_timer = QTimer(self)
        self.session_timer.setSingleShot(True)
        self.session_timer.timeout.connect(self._on_session_timeout)

        self.speech.finished.connect(self._on_speech_finished)
        self.speech.failed.connect(self.status_changed)

        # Real-time microphone listening and wake word ('Brain') detection
        self.listener = AudioListener(
            wake_word=self.store.setting("wake_word", "brain"),
            on_wake=None,
            on_turn_complete=None,
            parent=self,
            store=self.store,
            model_dir=voice_model_dir,
            audio_devices=self.audio_devices,
        )
        self.speech.voice_models = self.listener.models
        self.speech.echo_guard = self.listener.echo_guard
        self.listener.stop_requested.connect(self._on_voice_stop)
        self.audio_listener_error = ""
        self.listener.error_occurred.connect(self._on_audio_listener_error)
        self.listener.speech_started.connect(self._on_speech_started)
        self.listener.speech_ended.connect(self._on_speech_ended)
        self.listener.processing_started.connect(self._on_processing_started)
        self.listener.enable_character_names()
        self.listener.named_wake_started.connect(self._on_named_keyword_started)
        self.listener.named_turn_completed.connect(self._on_named_turn_completed)
        self.listener.turn_timed_out.connect(self._on_session_timeout)
        self.speech.activity.connect(self._on_speech_activity)
        self.listener.wake_detection_enabled = bool(self.store.setting("wake_word_enabled", True))

        # Push-to-talk shortcut listener (default: right Command key)
        self.shortcut_listener = GlobalShortcutListener(
            shortcut_key=self.store.setting("push_to_talk_shortcut", "cmd_r"),
            on_press=self._on_shortcut_press,
            on_release=self._on_shortcut_release,
        )
        from dock_twoo.brain.desktop_reader import DesktopReader
        self.reader = DesktopReader(self)
        if not start_services:
            self.reader.remember_timer.stop()
        from dock_twoo.brain.ecosystem.semantic import SemanticModel
        from dock_twoo.brain.ecosystem.memory import AdaptiveMemory
        from dock_twoo.brain.ecosystem.cache import PromptCache
        self.semantic_model=SemanticModel(voice_model_dir or self.store.data_dir/'models')
        self.memory=AdaptiveMemory(self.store.data_dir/'memory',self.semantic_model)
        self.prompt_cache=PromptCache(self.store.data_dir/'cache')
        if start_services:self.semantic_model.start()
        self.agent = BrainAgent(self.profile_mgr, self, tracker=self.activity)
        from dock_twoo.brain.ecosystem.coordinator import Coordinator
        self.coordinator=Coordinator(self)
        self.agent.coordinator=self.coordinator
        if start_services:self.coordinator.start()
        self.animation_director = AnimationDirector(self)
        from dock_twoo.brain.ecosystem.animation import EcologyDirector
        self.ecology=EcologyDirector(self)
        if not start_services:self.ecology.timer.stop()
        self.reader.failed.connect(self._on_reading_failed)
        self.reader.finished.connect(self._on_reading_finished)
        self.speech.progress.connect(lambda value: self.companion.reading_progress(value))
        if start_services and self.store.setting("wake_word_enabled", True):
            self.listener.start()
        if start_services:
            self.shortcut_listener.start()
            get_local_tts().start()

        if self.store.setting("companion_visible", True):
            self.show_mini_agent()

    @Slot(str)
    def _on_audio_listener_error(self, message: str) -> None:
        """Keep microphone startup failures available to the settings console."""
        self.audio_listener_error = message
        self.status_changed.emit(message)

    @Slot(str)
    def _do_speech_start(self, reply: str) -> None:
        self.speech.start(reply)

    @Slot(str)
    def _do_action(self, action_name: str) -> None:
        if action_name == "loop":
            self.companion.start_animation_loop()
        else:
            self.companion.play_action(action_name)

    def is_mini_agent_visible(self) -> bool:
        return any(actor.isVisible() for actor in self.companions.values())

    @Slot()
    def _do_show_mini_agent(self) -> None:
        self.store.set_setting("companion_visible", True)
        for actor in self.companions.values():
            actor.show()
            actor.raise_()
        if hasattr(self, 'playground'):
            self.playground.arrange()
        self.visibility_changed.emit(True)

    def show_mini_agent(self) -> None:
        """Summon and display the robot mini agent on the desktop safely across threads."""
        if QThread.currentThread() == self.thread():
            self._do_show_mini_agent()
        else:
            self.show_mini_agent_requested.emit()

    @Slot()
    def _do_hide_mini_agent(self) -> None:
        self.store.set_setting("companion_visible", False)
        self.stop_talking()
        for actor in self.companions.values():
            actor.stop_motion()
            actor.hide()
        self.visibility_changed.emit(False)

    def hide_mini_agent(self) -> None:
        """Hide the mini agent and stop active speech safely across threads."""
        if QThread.currentThread() == self.thread():
            self._do_hide_mini_agent()
        else:
            self.hide_mini_agent_requested.emit()

    @Slot()
    def _do_toggle_mini_agent(self) -> None:
        if self.is_mini_agent_visible():
            self._do_hide_mini_agent()
        else:
            self._do_show_mini_agent()

    def toggle_mini_agent(self) -> None:
        """Clicking Brain in the dock acts like an on/off toggle for the Mini Agent."""
        if QThread.currentThread() == self.thread():
            self._do_toggle_mini_agent()
        else:
            self.toggle_mini_agent_requested.emit()

    @Slot()
    def _on_speech_started(self):
        self.session_timer.stop()
        self._refresh_actor_states()

    @Slot()
    def _on_speech_ended(self):
        self._refresh_actor_states()

    @Slot()
    def _on_processing_started(self):
        self._refresh_actor_states()

    @Slot()
    def _on_speech_finished(self):
        self._awaiting_reply = False
        if self.reader.active:
            self.reader.speech_finished()
            return
        if self.speech.last_error:
            self.in_conversation_session = False
            self.status_changed.emit(self.speech.last_error)
        self.listener.set_output_active(False)
        if self._active_turn:
            self._finish_turn()
        else:
            self._resume_session()

    @Slot(str)
    def _on_speech_activity(self, activity):
        active = activity in ('thinking', 'speaking')
        if active:
            self.listener.start()
        # Explicit listening can coexist with an agent worker, never playback.
        self.listener.set_output_active(active and not self.listener.is_recording)

    @Slot(str)
    def _on_named_keyword_started(self, character_id):
        owner = self.voice_actor(character_id)
        # A wake can interrupt playback, while the single model worker continues.
        self._listening_actor_id = owner
        self._listening_source = self._session_source = 'voice'
        self._session_actor_id = self._ui_actor_id = owner
        self.in_conversation_session = True
        self.session_timer.stop()
        if self.reader.active:
            self.reader.stop()
        self._awaiting_reply = False
        self.speech.stop()
        if self._active_turn and not self._deferred_reply:
            self._active_turn = None
        actor = self.actor_for(owner)
        actor.stop_motion()
        actor.turn_to_user()
        self._refresh_actor_states()

    @Slot(str, str, str, bool)
    def _on_named_turn_completed(self, character_id, command, transcript, bare):
        owner = self.voice_actor(character_id)
        self.listener.cancel_recording()
        self._session_actor_id = owner
        self._session_source = 'voice'
        self._listening_actor_id = None
        self.listener.last_completed_transcript = transcript
        self._queue_turn(command or transcript, 'voice', owner, kind='greeting' if bare else 'request')
        self._after_capture()

    @Slot()
    def _on_keyword_started(self):
        if self._listening_actor_id is None:
            self._listening_actor_id = self._choose_voice_actor()
        self._session_actor_id = self._listening_actor_id
        self._listening_source = self._session_source = 'voice'
        self.in_conversation_session = True
        self.session_timer.stop()
        actor = self.actor_for(self._listening_actor_id)
        actor.show()
        actor.stop_motion()
        actor.turn_to_user()
        self._refresh_actor_states()

    @Slot()
    def _on_session_timeout(self):
        self.in_conversation_session = False
        self.listener.arm_wake()
        self._after_capture()


    def get_wake_greeting(self, owner_verified: Optional[bool] = True) -> str:
        """Generate a natural, realistic spoken response when activated by the wake word 'Brain'."""
        owner_name = str(self.store.setting("owner_first_name", "Karthik")).strip() or "Karthik"
        if owner_verified is not True:
            return "Hey Buddy, what can I do for you?"

        now = time.monotonic()
        # Initial welcoming greeting if first call or after extended inactivity (> 25 minutes)
        is_first = (self.wake_count == 0) or (self.last_wake_time > 0 and (now - self.last_wake_time > 1500))
        self.wake_count += 1
        self.last_wake_time = now

        if is_first:
            initial_options = [
                f"Hey {owner_name}, what would you like to do?",
                f"Hey {owner_name}! How can I help you today?",
                f"Hey {owner_name}, what are we working on today?",
            ]
            reply = random.choice(initial_options)
            self._last_wake_reply = reply
            return reply

        # Subsequent responses: realistic, active, conversational, and concise
        subsequent_options = [
            "Yeah, I'm here. Tell me.",
            f"I'm listening, {owner_name}.",
            "Right here. What's on your mind?",
            "Yeah, what's up?",
            "All ears, tell me.",
            f"I'm here, {owner_name}. What do you need?",
            "Yeah, go ahead.",
            "Right here with you. Tell me.",
            f"Listening, {owner_name}. Go ahead.",
        ]
        # Avoid repeating the same greeting twice consecutively
        choices = [opt for opt in subsequent_options if opt != self._last_wake_reply]
        reply = random.choice(choices if choices else subsequent_options)
        self._last_wake_reply = reply
        return reply

    @Slot()
    def _do_wake_detected(self, source='voice', transcript=None):
        text = transcript or getattr(self.listener, 'last_completed_transcript', '') or 'Brain'
        owner = self._listening_actor_id or self._choose_voice_actor()
        self._listening_actor_id = None
        self._queue_turn(text, source, owner)
        self._after_capture()

    def _greet_now(self, source='voice', transcript=None) -> None:
        self.in_conversation_session = True
        self._session_actor_id = self.active_actor_id
        self.conversation_history.clear()
        self.session_timer.stop()

        if not self.companion.isVisible():
            self._do_show_mini_agent()
        self.companion.turn_to_user()
        # This signal is delivered only after the entire wake statement ends.
        # Inline commands go directly to _do_turn_complete without a greeting.
        profile = self._active_turn.profile if self._active_turn else self.profile_mgr.get_active_profile()
        reply = NOT_CONFIGURED if profile['status']=='not configured' else self.get_wake_greeting(self.listener.last_wake_owner_verified)
        self._publish_response(reply)
        if self._active_turn:
            self.activity.finish(self._active_turn.run_id, 'complete', reply)
        if self.store.setting("voice_reply", True):
            self._awaiting_reply = True
            self.speech.start(reply)
        else:
            self._finish_turn()

    def _on_wake_detected(self) -> None:
        """Invoked when user says 'Brain' or 'Hey Brain'."""
        if QThread.currentThread() == self.thread():
            self._do_wake_detected()
        else:
            self.wake_detected_requested.emit()

    @Slot()
    def _on_shortcut_press(self):
        self.run_on_main_thread(lambda: self.start_talking(self._choose_voice_actor(), source='shortcut'))

    @Slot()
    def _on_shortcut_release(self) -> None:
        """Push-to-talk released: finish recording immediately and process speech."""
        if QThread.currentThread() != self.thread():
            QMetaObject.invokeMethod(self, "_on_shortcut_release", Qt.ConnectionType.QueuedConnection)
            return
        self.listener.stop_recording()

    @Slot(object)
    def _do_run_main_action(self, fn: Any) -> None:
        try:
            fn()
        except Exception:
            pass

    def run_on_main_thread(self, fn: Any) -> None:
        """Safely execute a function or lambda on the main Qt GUI thread."""
        if QThread.currentThread() == self.thread():
            fn()
        else:
            self.main_thread_action_requested.emit(fn)

    def forget_character_memory(self, character_id):
        from dock_twoo.brain.catalog import character
        character(character_id)
        if any(self.actor_busy(actor) for actor in self.companions.values() if actor.character_id==character_id):
            raise ValueError('Finish or stop this character’s task and listening before clearing its memory.')
        self.memory.forget_character(character_id)
        self._character_histories.pop(character_id,None)
        for key,actor in self.companions.items():
            if actor.character_id==character_id:self._histories.pop(key,None)
        for agent in {self.agent, *self._character_agents.values()}:
            for key in list(agent._last_memory_runs):
                if json.loads(key)[0]==character_id:agent._last_memory_runs.pop(key,None)
            for key in list(agent._last_task_families):
                if key[0]==character_id:agent._last_task_families.pop(key,None)

    def submit_request(self, text, source='console', screen_id=None):
        from dock_twoo.brain.catalog import named_prefix
        character_id, command=named_prefix(text)
        identity=character_id or self.actor_for(screen_id).character_id
        profile = dict(self.profile_mgr.character_profile(identity))
        key = self.profile_mgr.get_key(profile.get('provider'), profile.get('id'))
        def accept():
            target = screen_id
            if character_id is not None:
                display_id = self.actor_for(screen_id).screen_id
                target = self.add_brain(display_id, character_id).actor_id
            self._queue_turn(command if character_id is not None and command else text, source, target,
                             kind='greeting' if character_id is not None and not command else 'request',
                             profile_snapshot=(profile, key))
        self.run_on_main_thread(accept)

    def _do_turn_complete(self, user_text: str, source='voice', screen_id=None) -> None:
        self._queue_turn(user_text, source, screen_id)

    def _process_turn(self, user_text: str, source='voice') -> None:
        if re.fullmatch(r'\s*(?:(?:hey|okay|ok)[,\s]+)?(?:(?:brain|buddy)[,\s]+)?(?:please\s+)?stop(?:\s+(?:please|talking|speaking|reading))?[.!?\s]*',user_text,re.I):
            self._on_voice_stop(user_text)
            return
        if user_text and not self.companion.isVisible():
            # Ambient wake-prefixed commands arrive here without a separate wake event.
            self._do_show_mini_agent()

        if re.fullmatch(r"\s*(?:(?:hey|hello|hi)\s+)?(?:brain|buddy)[.!?,\s]*", user_text, re.I):
            self._greet_now(source,user_text)
            return

        run_id = self._active_turn.run_id
        def local_done(message):
            self.activity.finish(run_id, 'complete', message)
            if not self.reader.active and not self._awaiting_reply:
                self._finish_turn()

        from dock_twoo.brain.computer_actions import normalize_request
        reading_text = re.sub(r'^(?:okay|ok|alright)[,\s]+','',normalize_request(user_text),flags=re.I).strip(' .!?')
        if re.fullmatch(r'read\s+(?:(?:this|the|current)\s+)?(?:text|page|screen|document)', reading_text, re.I):
            self._start_reading_now('window')
            local_done('Reading the active window locally.')
            return
        literal = re.fullmatch(r'read\s+(?:this\s+text|aloud)\s*:\s*(.+)',reading_text,re.I|re.S)
        if literal:
            self._read_text_now(literal.group(1))
            local_done('Reading supplied text locally.')
            return
        if re.fullmatch(r"\s*(?:hey\s+)?(?:brain[,\s]+)?read\s+(?:the\s+)?(?:desktop|(?:active\s+)?window)[.!?\s]*", user_text, re.I):
            self._start_reading_now("window")
            local_done("Reading the active window locally.")
            return
        if re.fullmatch(r"\s*(?:(?:hey\s+)?brain[,\s]+)?(?:please\s+)?read\s+(?:the\s+)?selected\s+text[.!?\s]*", user_text, re.I):
            self._start_reading_now("selected")
            local_done("Reading selected text locally.")
            return
        if re.fullmatch(r"\s*(?:brain[,\s]+)?stop\s+reading[.!?\s]*", user_text, re.I):
            self.stop_reading()
            local_done("Reading stopped.")
            return
        if not user_text:
            self.activity.finish(run_id,"error",reason="Speech could not be transcribed.")
            # Real speech with no usable transcript gets a clarification only
            # after endpointing; idle silence never reaches this path.
            if self.in_conversation_session:
                if self.store.setting("voice_reply", True):
                    self._awaiting_reply = True
                    self.speech.start("Hey Buddy, I'm sorry, I couldn't understand that. Could you repeat or rephrase it?")
                else:
                    self._finish_turn()
            else:
                self._finish_turn()
            return

        # Local session exit; model requests are launched independently by the scheduler.
        self.in_conversation_session = False
        self.conversation_history.clear()
        reply = "Goodbye! Standing by whenever you need me."
        self.activity.finish(run_id, 'complete', reply)
        self._deliver_model_reply(self._active_turn, reply)

    def _launch_model_turn(self, turn):
        from dock_twoo.brain.ecosystem.coordinator import WorkerManager
        self.session_timer.stop()
        cancel = threading.Event()
        identity = turn.character_id
        agent = self._character_agents.get(identity)
        if agent is None:
            agent = self.agent if identity == 'default' else BrainAgent(self.profile_mgr, self, tracker=self.activity, client_factory=self.agent.client_factory)
            self._character_agents[identity] = agent
        proxy = WorkerManager(self, identity, None, self.coordinator.desktop_lock, cancel, foreground=True, actor_id=turn.actor_id)
        agent.manager = proxy
        agent.tools.manager = proxy
        agent.coordinator = self.coordinator
        history = self._character_histories.setdefault(identity, [])
        history.append({'role': 'user', 'content': turn.text})
        del history[:-12]
        snapshot = list(history)
        self._processing_turns[turn.run_id] = {'turn': turn, 'agent': agent, 'cancel': cancel}
        self._worker_running = True
        self.activity.event(turn.run_id, 'dequeued', {'actor_id': turn.actor_id, 'character_id': identity})
        def run_turn():
            reply = None
            try:
                reply = agent.run(turn.text, history=snapshot, cancel=cancel, source=turn.source,
                                  run_id=turn.run_id, profile=turn.profile, api_key=turn.key,
                                  character_name=turn.character_name, character_id=identity)
            except InterruptedError:
                pass
            except Exception as exc:
                reply = 'I could not complete the request. ' + str(exc)
                self.activity.finish(turn.run_id, 'error', reply)
            finally:
                proxy.release_desktop()
            def completed():
                self._processing_turns.pop(turn.run_id, None)
                self._worker_running = bool(self._processing_turns)
                if not cancel.is_set() and reply is not None:
                    history = self._character_histories.setdefault(identity, [])
                    history.append({'role': 'assistant', 'content': str(reply)})
                    del history[:-12]
                    self._reply_queue.append((turn, reply))
                self._drain_turns()
            self.run_on_main_thread(completed)
        self._active_query_thread = threading.Thread(target=run_turn, daemon=True, name='agent-' + identity)
        self._active_query_thread.start()

    def _deliver_model_reply(self, turn, reply):
        self._publish_response(reply)
        if getattr(reply, 'tasks_query', None) is not None:
            self.tasks_view_requested.emit({'filters': reply.tasks_query, 'summary': str(reply)})
        self.animation_director.respond(reply)
        if self.reader.active:
            return
        if not self.store.setting('voice_reply', True):
            self.listener.set_output_active(False)
            self._finish_turn()
            return
        self._awaiting_reply = True
        turn.phase = 'speaking'
        self._refresh_actor_states()
        if getattr(reply, 'gesture', None) == 'whistle':
            self.speech.whistle()
        elif getattr(reply, 'delivery', None) == 'sing' or hasattr(reply, 'lyrics'):
            self.speech.sing(getattr(reply, 'lyrics', str(reply)))
        else:
            spoken = str(reply)
            documents = [Path(path) for path in getattr(reply, 'artifacts', []) if Path(path).suffix.lower() in ('.md', '.txt') and Path(path).is_file()]
            if documents:
                document = max(documents, key=lambda path: (bool(re.search(r'final|report|document', path.stem, re.I)), path.stat().st_size))
                if document.stat().st_size <= 500000:
                    content = document.read_text(encoding='utf-8', errors='replace')
                    content = re.sub(r'^#{1,6}\s+', '', content, flags=re.M)
                    content = re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', content).replace('```', '').replace('`', '')
                    spoken += '\n\n' + content
            self.speech.start(spoken)

    def _on_turn_complete(self, user_text):
        def accept():
            owner = self._listening_actor_id or self._choose_voice_actor()
            self.listener.cancel_recording()
            self._session_actor_id = owner
            self._listening_actor_id = None
            self._queue_turn(user_text, 'voice', owner)
            self._after_capture()
        self.run_on_main_thread(accept)

    def toggle_talking(self, target=None):
        if QThread.currentThread() != self.thread():
            self.run_on_main_thread(lambda: self.toggle_talking(target))
            return
        actor = self.actor_for(target)
        if self._listening_actor_id == actor.actor_id:
            if self.listener.is_recording:
                self.listener.stop_recording()
                return
            if self.listener._decode_token is not None:
                return  # Rapid clicks cannot reset an in-flight decoder.
        self.start_talking(actor.actor_id)

    @Slot(str)
    def _on_voice_stop(self, command='Stop') -> None:
        """Stop speech, reading, and pending cloud actions locally and silently."""
        self.stop_talking()
        self.companion.stop_motion()
        self._publish_response('Stopped.')
        self.status_changed.emit('Stopped.')
        run = self.activity.start(command, 'voice')
        self.activity.finish(run, 'complete', 'Stopped locally.')

    def start_talking(self, target=None, source='click'):
        if QThread.currentThread() != self.thread():
            self.run_on_main_thread(lambda: self.start_talking(target, source))
            return
        actor = self.actor_for(target)
        if self.listener.is_recording or self.listener._decode_token is not None:
            if actor.actor_id != self._listening_actor_id:
                self._pending_listener = actor.actor_id
                self._pending_listener_source = source
                self.listener.stop_recording()
            return
        # The user can barge into an answer without cancelling a running agent.
        if self.reader.active:
            self.reader.stop()
        self.speech.stop()
        self._awaiting_reply = False
        self._histories.setdefault(actor.actor_id, [])
        self._start_capture(actor.actor_id, source)
        if self._active_turn and not self._deferred_reply:
            self._finish_turn()

    @Slot()
    def stop_talking(self) -> None:
        """Cancel active listening or speech immediately."""
        if QThread.currentThread() != self.thread():
            QMetaObject.invokeMethod(self, "stop_talking", Qt.ConnectionType.QueuedConnection)
            return
        self._stopping = True
        for turn in self._turn_queue:
            self.activity.finish(turn.run_id, 'stopped', reason='Removed from the queue by Stop.')
        self._turn_queue.clear()
        self._reply_queue.clear()
        for item in self._processing_turns.values():
            item['cancel'].set()
            item['agent'].stop()
        if self._active_turn:
            self.activity.finish(self._active_turn.run_id, 'stopped', reason='Stopped by the user.')
        self._pending_listener = None
        self._pending_listener_source = None
        self._listening_actor_id = None
        self._listening_source = None
        self._session_source = None
        self._deferred_reply = None
        self._awaiting_reply = False
        self._agent_cancel.set()
        if hasattr(self,"coordinator"):self.coordinator.stop()
        self.agent.stop()
        self.animation_director.cancel()
        self.reader.stop()
        self._is_listening = False
        self._query_generation += 1
        self.in_conversation_session = False
        self.conversation_history.clear()
        self.session_timer.stop()
        self.listener.arm_wake()
        self.speech.stop()
        self._active_turn = None
        self._stopping = False
        self._refresh_actor_states()

    def shutdown(self):
        self.stop_talking()
        self.input_router.close()
        self.ecology.close()
        self.coordinator.close()
        self._stopping = True
        self.reader.remember_timer.stop()
        self.activity_cleanup.stop()
        self.listener.stop()
        self.audio_devices.close()
        self.shortcut_listener.stop()
        if hasattr(self, 'playground'):
            self.playground.timer.stop()
        for actor in self.companions.values():
            for timer in actor.findChildren(QTimer):
                timer.stop()
            actor.close()

    def _publish_response(self, text: str) -> None:
        self._response_generation += 1
        self.last_response = {'generation':self._response_generation, 'text':str(text), 'artifacts':list(getattr(text,'artifacts',[]))}
        self.reply_received.emit(str(text))

    def read_text(self, text: str) -> None:
        self.run_on_main_thread(lambda: self._queue_turn(text, 'reader', self._ui_actor_id, 'read_text'))

    def _read_text_now(self, text: str) -> None:
        if QThread.currentThread() != self.thread():
            self.run_on_main_thread(lambda:self._read_text_now(text))
            return
        self._publish_response('Reading supplied text.')
        self.listener.start()
        self.reader.start_text(text)

    def start_reading(self, mode: str = "window", target=None) -> None:
        self.run_on_main_thread(lambda: self._queue_turn('Read '+mode, 'reader', target or self._ui_actor_id, 'read:'+mode))

    def _start_reading_now(self, mode: str = "window") -> None:
        if QThread.currentThread() != self.thread():
            self.run_on_main_thread(lambda: self._start_reading_now(mode))
            return
        self._publish_response('Reading selected text.' if mode == 'selected' else 'Reading the active window.')
        self.listener.start()
        self.reader.start(mode)

    @Slot()
    def _on_reading_finished(self) -> None:
        if self._active_turn:
            self.activity.finish(self._active_turn.run_id, 'complete', 'Finished reading locally.')
        self._publish_response('Finished reading.')
        self.status_changed.emit('Finished reading.')
        self._awaiting_reply = False
        self._finish_turn()

    @Slot(str)
    def _on_reading_failed(self, message: str) -> None:
        if self._active_turn:
            self.activity.finish(self._active_turn.run_id, 'error', reason=message)
        self.status_changed.emit(message)
        self._publish_response(message)
        if self.store.setting('voice_reply', True):
            self._awaiting_reply = True
            self.speech.start(f"I'm sorry, I couldn't read that window. {message}")
        else:
            self._finish_turn()

    def stop_reading(self) -> None:
        if QThread.currentThread() != self.thread():
            self.run_on_main_thread(self.stop_reading)
            return
        self.reader.stop()
        self._publish_response('Reading stopped.')
        self._awaiting_reply = False
        self._finish_turn()

    def show_context_menu(self, global_pos: QPoint, target=None) -> None:
        """Open Brain's dock context menu without losing the active document."""
        self.reader._remember()
        menu=self._build_context_menu(target)
        menu.exec(global_pos)

    def _build_context_menu(self, target=None) -> QMenu:
        """Create the current profile and action choices on the GUI thread."""
        actor = self.actor_for(target)
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background: rgba(24, 24, 27, 0.96);
                color: #f4f4f5;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 5px;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 20px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #3b82f6;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 4px 6px;
            }
        """)

        # 1. Talk Action
        talk_label = "Finish speaking" if self.listener.is_recording else f"🎤 Talk to {actor.character_name}"
        act_talk = menu.addAction(talk_label, lambda: self.toggle_talking(actor.actor_id))
        act_talk.setEnabled(True)
        menu.addAction("Read Desktop", lambda: self.start_reading("desktop", actor.actor_id))
        menu.addAction("Read Active Window", lambda: self.start_reading("window", actor.actor_id))
        menu.addAction("Read Selected Text", lambda: self.start_reading("selected", actor.actor_id))
        stop_read = menu.addAction("Stop Reading", self.stop_reading)
        stop_read.setEnabled(self.reader.active)

        menu.addSeparator()

        # 2. Model Profiles Submenu
        profile_menu = menu.addMenu(f"Agent model for {actor.character_name}")
        profile_menu.addAction("Use default agent model",lambda:self.profile_mgr.bind_character(actor.character_id,""))
        profiles = self.profile_mgr.get_profiles()
        active_id = self.store.setting("active_profile")

        for p in profiles:
            p_id = p.get("id")
            p_name = p.get("name", p_id).replace("&", "&&")
            p_status = p.get("status", "active")
            display_label = f"{p_name} ({p_status.title()})"
            act = profile_menu.addAction(display_label)
            act.setCheckable(True)
            act.setChecked(p_id == self.profile_mgr.character_profile(actor.character_id)['id'])
            act.triggered.connect(lambda checked=False, pid=p_id: self.profile_mgr.bind_character(actor.character_id,pid))

        # 3. Animations Submenu
        anim_menu = menu.addMenu("🎭 Animations")
        act_loop = anim_menu.addAction("▶ Play All (Loop)", actor.start_animation_loop)
        act_loop.setEnabled(not actor.reduced_motion)

        act_stop = anim_menu.addAction("⏹ Stop Animations", actor.stop_motion)
        act_stop.setEnabled(bool(actor.action or actor.animation_loop))

        anim_menu.addSeparator()
        for action_key, (action_lbl, _) in actor.actions.items():
            a_act = anim_menu.addAction(
                action_lbl, lambda checked=False, k=action_key: actor.play_action(k)
            )
            a_act.setEnabled(not actor.reduced_motion)

        menu.addSeparator()

        # 4. Roaming Toggle
        roam_act = menu.addAction("🚶 Roaming on Desktop")
        roam_act.setCheckable(True)
        roam_act.setChecked(bool(self.store.setting("roaming", True)))
        roam_act.toggled.connect(lambda v: self.store.set_setting("roaming", v))
        follow_act = menu.addAction("Follow Cursor")
        follow_act.setCheckable(True)
        follow_act.setChecked(actor.follow_cursor_enabled)
        follow_act.toggled.connect(actor.set_follow_cursor)

        all_screens = menu.addAction("Roam across all screens")
        all_screens.setCheckable(True)
        all_screens.setChecked(bool(self.store.setting('brain_roam_all_screens', False)))
        all_screens.toggled.connect(self.set_roam_all_screens)
        from dock_twoo.brain.catalog import characters as character_catalog
        add_menu = menu.addMenu('Add assistant')
        for entry in character_catalog():
            existing = self.character_on_screen(entry['id'], actor.screen_id)
            choice = add_menu.addAction(entry['name'] + (' · on this screen' if existing else ''),
                lambda checked=False, key=entry['id']: self.add_brain(actor.screen_id, key))
            choice.setEnabled(existing is None)
        add_menu.addSeparator()
        add_menu.addAction('Add all missing characters', lambda: self.add_all_characters(actor.actor_id))
        on_screen = menu.addMenu('Assistants on this screen')
        for other in self.companions.values():
            if other.screen_id != actor.screen_id:
                continue
            on_screen.addAction(f'Talk to {other.character_name}', lambda checked=False, key=other.actor_id: self.toggle_talking(key))
            if other.actor_id.startswith('extra-'):
                remove=on_screen.addAction(f'Remove {other.character_name}', lambda checked=False, key=other.actor_id: self.remove_brain(key))
                remove.setEnabled(not self.actor_busy(other))
        if actor.actor_id.startswith('extra-'):
            remove=menu.addAction(f'Remove {actor.character_name}', lambda: self.remove_brain(actor.actor_id))
            remove.setEnabled(not self.actor_busy(actor))
        remove_extras = menu.addAction('Remove all secondary assistants', self.remove_all_secondary_brains)
        remove_extras.setEnabled(any(key.startswith('extra-') for key in self.companions) or
                                 bool(self.store.setting('brain_instances', [])))
        together = menu.addMenu("Play together")
        from dock_twoo.brain.playground import GROUP_ACTIVITIES
        for key, label in GROUP_ACTIVITIES.items():
            choice = together.addAction(label, lambda checked=False, kind=key: self.playground.play(kind, actor.actor_id))
            choice.setEnabled(hasattr(self, 'playground') and len(self.companions) > 1)

        # 5. Speak Replies Toggle
        voice_act = menu.addAction("🔊 Speak Replies")
        voice_act.setCheckable(True)
        voice_act.setChecked(bool(self.store.setting("voice_reply", True)))
        voice_act.toggled.connect(lambda v: self.store.set_setting("voice_reply", v))

        # 6. Reduce Motion Toggle
        motion_act = menu.addAction("♿ Reduce Motion")
        motion_act.setCheckable(True)
        motion_act.setChecked(bool(self.store.setting("reduced_motion", False)))
        motion_act.toggled.connect(lambda v: self.store.set_setting("reduced_motion", v))

        menu.addSeparator()

        # 7. Configure in Web Console
        menu.addAction("⚙️ Voice Assistant Settings & Models…", self.open_console_settings)

        # 8. Close / Hide Mini Agent Option
        menu.addSeparator()
        show_all = menu.addAction("Show all assistants", self.show_mini_agent)
        show_all.setEnabled(any(not c.isVisible() for c in self.companions.values()))
        hide_all = menu.addAction("✕ Hide all assistants and stop requests", self.hide_mini_agent)
        hide_all.setEnabled(self.is_mini_agent_visible())

        return menu

    def _activate_and_notify(self, profile_id: str) -> None:
        self.profile_mgr.activate_profile(profile_id)
        self.companion.update()
        active=self.profile_mgr.get_active_profile()
        self.status_changed.emit(f"Cloud profile: {active['name']}")
        if self._active_turn or self._worker_running or self.reader.active or self.listener.is_recording or self.listener._decode_token is not None:
            return  # The running request keeps its captured model and credential.
        if self.store.setting("voice_reply", True):
            active = self.profile_mgr.get_active_profile()
            self.speech.start(f"Switched profile to {active.get('name')}.")
        else:
            self.speech.whistle()

    def open_console_settings(self) -> None:
        webbrowser.open("http://127.0.0.1:28842/#brain")

    def get_status(self) -> Dict[str, Any]:
        """Read GUI state on its owning thread, not the HTTP server worker."""
        if QThread.currentThread()!=self.thread():
            import copy
            ready=threading.Event();outcome={}
            def snapshot():
                try:outcome['status']=self.get_status()
                finally:ready.set()
            self.run_on_main_thread(snapshot)
            if ready.wait(3) and 'status' in outcome:return outcome['status']
            return copy.deepcopy(getattr(self,'_status_cache',{'name':'Brain','activity':'busy','error':'The desktop UI is busy.'}))
        status = {
            "name": "Voice Assistant",
            "queue": self.queue_status(),
            "characters": [{'id': actor.actor_id, 'character_id': actor.character_id, 'name': actor.character_name, 'screen_id': actor.screen_id,
                            'visible': actor.isVisible(), 'activity': actor.activity}
                           for actor in self.companions.values()],
            "is_mini_agent_visible": self.is_mini_agent_visible(),
            "activity": self.companion.activity,
            "voice_input": {
                "enabled": bool(self.store.setting("wake_word_enabled", True)),
                "listening": self.listener.is_running and self.listener.stream_active,
                "error": self.audio_listener_error or self.listener.last_error,
                "owner_enrolled": self.listener._load_speaker_embedding(self.listener.owner_embedding_path) is not None,
                "models": self.listener.models.status(),
                "wake_ready": self.listener.wake_detector.ready,
                "recognizer_ready": self.listener.models.recognizer.ready,
                "wake_diagnostics": self.listener.diagnostics(),
            },
            "voice_output": {"playing": self.speech.playing, "error": self.speech.last_error},
            "reading": self.reader.status(),
            "language_model": {"state": self.profile_mgr.get_active_profile()["status"],
                               "name": self.profile_mgr.get_active_profile().get("name", ""),
                               "profile_id": self.profile_mgr.get_active_profile().get("id", ""),
                               "model": self.profile_mgr.get_active_profile().get("model", ""), "kind":"cloud"},
            "agent": self.agent.status(),
            "local_speech": get_local_tts().status(),
            "local_policy": self.semantic_model.status(),
            "ecosystem": {"agents":30,"grpc_ready":self.coordinator.bus.port is not None,"agent_states":dict(self.coordinator.agent_states)},
            "animation": dict(self.animation_director.last_decision),
            "last_response": dict(self.last_response),
            "character": {
                "version": self.companion.model_view.version if self.companion.model_view else "",
                "asset_hash": self.companion.model_view.asset_hash if self.companion.model_view else "",
                "renderer": "3d" if self.companion.model_view and self.companion.model_view.ready else "loading" if not self.companion.model_view or not self.companion.model_view.error else "unavailable",
                "error": self.companion.model_view.error if self.companion.model_view else "",
            },
            "active_profile": self.profile_mgr.get_active_profile(),
            "profiles": self.profile_mgr.get_profiles(),
            "settings": self.store.get_all(),
        }
        import copy
        self._status_cache=copy.deepcopy(status)
        return status

    def apply_voice_settings(self, changes: Dict[str, Any]) -> None:
        """Apply saved voice controls to the live listener on the GUI thread."""
        if "follow_cursor" in changes:
            self.companion.set_follow_cursor(bool(changes["follow_cursor"]))
        if "wake_word" in changes:
            self.listener.set_wake_word(str(changes["wake_word"]))
        if "wake_word_enabled" in changes:
            enabled = bool(changes["wake_word_enabled"])
            self.listener.wake_detection_enabled = enabled
            if enabled:
                self.listener.arm_wake()
                self.listener.start()
            elif not self.listener.is_recording:
                self.listener.stop()
        if "push_to_talk_shortcut" in changes:
            self.shortcut_listener.stop()
            self.shortcut_listener.shortcut_key = str(changes["push_to_talk_shortcut"])
            self.shortcut_listener.start()

    def enroll_owner_voice(self) -> None:
        """Capture an enrollment phrase and store only the local WavLM speaker vector."""
        from dock_twoo.brain.voice_models import save_embedding
        sample = self.listener.capture_owner_enrollment()
        sample = self.listener.models.enhance_pcm(sample)
        embedding = self.listener.models.speaker_embedding(sample)
        if embedding is None:
            detail = self.listener.models.status().get("speaker", "Speaker model unavailable")
            raise RuntimeError(f"Could not enroll voice: {detail}. Install the voice-id extra and try again.")
        save_embedding(self.listener.owner_embedding_path, embedding)
        self.store.set_setting("voice_enrolled", True)
