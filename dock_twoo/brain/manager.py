"""BrainManager singleton coordinating the Mini Agent companion, speech, model routing, and context menus."""

from __future__ import annotations

import random
import re
import threading
import time
import webbrowser
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QMetaObject, QObject, QPoint, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import QMenu, QApplication

from dock_twoo.brain.animation import ACTIONS
from dock_twoo.brain.commands import handle_voice_command
from dock_twoo.brain.listener import AudioListener, GlobalShortcutListener
from dock_twoo.brain.mascot import Companion
from dock_twoo.brain.profiles import ProfileManager
from dock_twoo.brain.providers import query_llm
from dock_twoo.brain.speech import SpeechPlayback
from dock_twoo.brain.storage import BrainStore


class BrainManager(QObject):
    """Central controller for the Brain voice-assisted system."""

    status_changed = Signal(str)
    reply_received = Signal(str)
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
        self.store = store or BrainStore()
        self.profile_mgr = ProfileManager(self.store)
        self.speech = SpeechPlayback(self)

        self.companion = Companion(self)
        self.speech.activity.connect(self.companion.set_activity)
        self.speech.mouth.connect(self.companion.set_mouth)

        self.activity_requested.connect(self.companion.set_activity)
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

        self.session_timer = QTimer(self)
        self.session_timer.setSingleShot(True)
        self.session_timer.timeout.connect(self._on_session_timeout)

        self.speech.finished.connect(self._on_speech_finished)

        # Real-time microphone listening and wake word ('Brain') detection
        self.listener = AudioListener(
            wake_word=self.store.setting("wake_word", "brain"),
            on_wake=self._on_wake_detected,
            on_turn_complete=self._on_turn_complete,
            parent=self,
            store=self.store,
            model_dir=voice_model_dir,
        )
        self.speech.voice_models = self.listener.models
        self.audio_listener_error = ""
        self.listener.error_occurred.connect(self._on_audio_listener_error)
        self.listener.speech_started.connect(self._on_speech_started)
        self.listener.speech_ended.connect(self._on_speech_ended)
        self.listener.processing_started.connect(self._on_processing_started)
        self.listener.wake_started.connect(self._on_keyword_started)
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
        self.reader.failed.connect(self._on_reading_failed)
        self.reader.finished.connect(lambda: self.status_changed.emit("Finished reading the document."))
        self.speech.progress.connect(self.companion.reading_progress)
        if start_services and self.store.setting("wake_word_enabled", True):
            self.listener.start()
        if start_services:
            self.shortcut_listener.start()

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
        return self.companion.isVisible()

    @Slot()
    def _do_show_mini_agent(self) -> None:
        self.store.set_setting("companion_visible", True)
        self.companion.show()
        self.companion.raise_()
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
        self.companion.stop_motion()
        self.companion.hide()
        self.visibility_changed.emit(False)

    def hide_mini_agent(self) -> None:
        """Hide the mini agent and stop active speech safely across threads."""
        if QThread.currentThread() == self.thread():
            self._do_hide_mini_agent()
        else:
            self.hide_mini_agent_requested.emit()

    @Slot()
    def _do_toggle_mini_agent(self) -> None:
        if self.companion.isVisible():
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
    def _on_speech_started(self) -> None:
        self.session_timer.stop()
        self.activity_requested.emit("listening")

    @Slot()
    def _on_speech_ended(self) -> None:
        self.activity_requested.emit("processing")

    @Slot()
    def _on_processing_started(self) -> None:
        self.activity_requested.emit("processing")

    @Slot()
    def _on_speech_finished(self) -> None:
        """Invoked when text-to-speech audio playback completes."""
        if self.reader.active:
            self.reader.speech_finished()
            return
        if self.in_conversation_session:
            # Hands-free multi-turn continuation: immediately resume listening for follow-ups!
            self.activity_requested.emit("listening")
            self.listener.start_recording()
            # The listener owns the idle timeout and never times out active speech.
        else:
            self.listener.arm_wake()
            self.activity_requested.emit("idle")

    @Slot(str)
    def _on_speech_activity(self, activity: str) -> None:
        active = activity in ("thinking", "speaking")
        if active:
            self.listener.cancel_recording()
        self.listener.set_output_active(active)

    @Slot()
    def _on_keyword_started(self) -> None:
        self._query_generation += 1
        self.in_conversation_session = True
        self.conversation_history.clear()
        self.session_timer.stop()
        self._do_show_mini_agent()
        self.companion.turn_to_user()
        self.companion.set_activity("listening")

    @Slot()
    def _on_session_timeout(self) -> None:
        """End multi-turn conversational session after trailing inactivity."""
        self.in_conversation_session = False
        self._query_generation += 1
        self.conversation_history.clear()
        self.listener.arm_wake()
        self.activity_requested.emit("idle")

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
    def _do_wake_detected(self) -> None:
        self._query_generation += 1
        self.in_conversation_session = True
        self.conversation_history.clear()
        self.session_timer.stop()

        if not self.companion.isVisible():
            self._do_show_mini_agent()
        self.companion.turn_to_user()
        # Wake is a silent acknowledgement. A spoken greeting here can mask
        # the command the user is about to continue in the same statement.
        self.listener.start_recording()
        self.companion.set_activity("listening")

    def _on_wake_detected(self) -> None:
        """Invoked when user says 'Brain' or 'Hey Brain'."""
        if QThread.currentThread() == self.thread():
            self._do_wake_detected()
        else:
            self.wake_detected_requested.emit()

    @Slot()
    def _on_shortcut_press(self) -> None:
        """Push-to-talk pressed: immediately begin recording."""
        if QThread.currentThread() != self.thread():
            QMetaObject.invokeMethod(self, "_on_shortcut_press", Qt.ConnectionType.QueuedConnection)
            return
        self.reader.stop()
        self.in_conversation_session = True
        self.session_timer.stop()
        self.listener.start()
        if not self.companion.isVisible():
            self.show_mini_agent()
        self.speech.stop()
        self.companion.turn_to_user()
        self.companion.set_activity("listening")
        self.listener.start_recording()

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

    @Slot(str)
    def _do_turn_complete(self, user_text: str) -> None:
        if user_text and not self.companion.isVisible():
            # Ambient wake-prefixed commands arrive here without a separate wake event.
            self._do_show_mini_agent()

        if re.fullmatch(r"\s*(?:(?:hey|hello|hi)\s+)?(?:brain|buddy)[.!?,\s]*", user_text, re.I):
            self._do_wake_detected()
            return

        if re.fullmatch(r"\s*(?:hey\s+)?(?:brain[,\s]+)?read\s+(?:the\s+)?(?:desktop|(?:active\s+)?window)[.!?\s]*", user_text, re.I):
            self.start_reading("window")
            return
        if re.fullmatch(r"\s*(?:brain[,\s]+)?stop\s+reading[.!?\s]*", user_text, re.I):
            self.stop_reading()
            return
        if not user_text:
            # Real speech with no usable transcript gets a clarification only
            # after endpointing; idle silence never reaches this path.
            if self.in_conversation_session:
                if self.store.setting("voice_reply", True):
                    self.speech.start("Hey Buddy, I'm sorry, I couldn't understand that. Could you repeat or rephrase it?")
                else:
                    self.listener.start_recording()
                    self.activity_requested.emit("listening")
            else:
                self.listener.arm_wake()
                self.activity_requested.emit("idle")
            return

        self.session_timer.stop()
        self.activity_requested.emit("processing")
        self._query_generation += 1
        generation = self._query_generation
        self.conversation_history.append({"role": "user", "content": user_text})
        history = list(self.conversation_history)

        # Check for conversational session exit phrases ("bye", "goodbye", "that's all", "dismiss")
        clean = user_text.strip().lower()
        if re.search(r"^(bye|goodbye|that\'?s\s+all|dismiss|dismissed|see\s+you|thank\s+you\s+bye|thanks\s+bye|exit|stop\s+listening)\b", clean):
            self.in_conversation_session = False
            self.conversation_history.clear()
            reply = "Goodbye! Standing by on your desktop whenever you need me."
            if self.store.setting("voice_reply", True):
                self.speech_start_requested.emit(reply)
            else:
                self.listener.arm_wake()
                self.activity_requested.emit("idle")
            return

        def run_turn():
            # 1. Check for dedicated voice command (movement, window walk, ball play, action, memory, CUA, research)
            try:
                cmd_reply = handle_voice_command(user_text, self, history=history)
                if cmd_reply:
                    reply = cmd_reply
                else:
                    self.activity_requested.emit("thinking")
                    active_profile = self.profile_mgr.get_active_profile()
                    provider = active_profile.get("provider", "local") if active_profile else "local"
                    api_key = self.profile_mgr.get_key(provider) if active_profile else ""
                    reply = query_llm(user_text, profile=active_profile, api_key=api_key, history=history)
            except Exception as exc:
                self.status_changed.emit(f"Brain request failed: {type(exc).__name__}")
                reply = "Hey Buddy, I'm sorry, I couldn't process that request. Could you try again?"

            def deliver_reply():
                if generation != self._query_generation:
                    return
                self.conversation_history.append({"role": "assistant", "content": reply})
                if self.store.setting("voice_reply", True):
                    self.speech.start(reply)
                elif self.in_conversation_session:
                    self.activity_requested.emit("listening")
                    self.listener.start_recording()
                else:
                    self.activity_requested.emit("idle")

            self.run_on_main_thread(deliver_reply)

        threading.Thread(target=run_turn, daemon=True).start()

    def _on_turn_complete(self, user_text: str) -> None:
        """Invoked when user finishes statement (via VAD or explicit shortcut)."""
        if QThread.currentThread() == self.thread():
            self._do_turn_complete(user_text)
        else:
            self.turn_complete_requested.emit(user_text)

    @Slot()
    def start_talking(self) -> None:
        """Activate voice listening state for the robot."""
        if QThread.currentThread() != self.thread():
            QMetaObject.invokeMethod(self, "start_talking", Qt.ConnectionType.QueuedConnection)
            return
        self.reader.stop()
        self.in_conversation_session = True
        self.listener.start()
        self.conversation_history.clear()
        self.session_timer.stop()
        self.companion.show()
        self.companion.raise_()
        self.visibility_changed.emit(True)
        self.companion.turn_to_user()
        self.companion.set_activity("listening")
        self.listener.start_recording()

    @Slot()
    def stop_talking(self) -> None:
        """Cancel active listening or speech immediately."""
        if QThread.currentThread() != self.thread():
            QMetaObject.invokeMethod(self, "stop_talking", Qt.ConnectionType.QueuedConnection)
            return
        self.reader.stop()
        self._is_listening = False
        self._query_generation += 1
        self.in_conversation_session = False
        self.conversation_history.clear()
        self.session_timer.stop()
        self.listener.arm_wake()
        self.speech.stop()
        self.companion.set_activity("idle")

    def start_reading(self, mode: str = "window") -> None:
        if QThread.currentThread() != self.thread():
            self.run_on_main_thread(lambda: self.start_reading(mode))
            return
        self._query_generation += 1
        self.reader.start(mode)

    @Slot(str)
    def _on_reading_failed(self, message: str) -> None:
        self.status_changed.emit(message)
        if self.store.setting('voice_reply', True):
            self.speech.start(f"I'm sorry, I couldn't read that window. {message}")

    def stop_reading(self) -> None:
        if QThread.currentThread() != self.thread():
            self.run_on_main_thread(self.stop_reading)
            return
        self.reader.stop()

    def show_context_menu(self, global_pos: QPoint) -> None:
        """Render the complete Brain properties and functionality context menu.
        
        Invoked both by right-clicking on the Brain dock icon and right-clicking on the mini agent.
        """
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
        act_talk = menu.addAction("🎤 Talk to Brain", self.start_talking)
        act_talk.setEnabled(True)
        menu.addAction("Read Desktop", lambda: self.start_reading("desktop"))
        menu.addAction("Read Active Window", lambda: self.start_reading("window"))
        stop_read = menu.addAction("Stop Reading", self.stop_reading)
        stop_read.setEnabled(self.reader.active)

        menu.addSeparator()

        # 2. Model Profiles Submenu
        profile_menu = menu.addMenu("🧠 Model Profile")
        profiles = self.profile_mgr.get_profiles()
        active_id = self.store.setting("active_profile")

        for p in profiles:
            p_id = p.get("id")
            p_name = p.get("name", p_id)
            p_status = p.get("status", "active")
            display_label = f"{p_name} ({p_status.title()})"
            act = profile_menu.addAction(display_label)
            act.setCheckable(True)
            act.setChecked(p_id == active_id)
            act.triggered.connect(lambda checked=False, pid=p_id: self._activate_and_notify(pid))

        # 3. Animations Submenu
        anim_menu = menu.addMenu("🎭 Animations")
        act_loop = anim_menu.addAction("▶ Play All (Loop)", self.companion.start_animation_loop)
        act_loop.setEnabled(not self.companion.reduced_motion)

        act_stop = anim_menu.addAction("⏹ Stop Animations", self.companion.stop_motion)
        act_stop.setEnabled(bool(self.companion.action or self.companion.animation_loop))

        anim_menu.addSeparator()
        for action_key, (action_lbl, _) in ACTIONS.items():
            a_act = anim_menu.addAction(
                action_lbl, lambda checked=False, k=action_key: self.companion.play_action(k)
            )
            a_act.setEnabled(not self.companion.reduced_motion)

        menu.addSeparator()

        # 4. Roaming Toggle
        roam_act = menu.addAction("🚶 Roaming on Desktop")
        roam_act.setCheckable(True)
        roam_act.setChecked(bool(self.store.setting("roaming", True)))
        roam_act.toggled.connect(lambda v: self.store.set_setting("roaming", v))
        follow_act = menu.addAction("Follow Cursor")
        follow_act.setCheckable(True)
        follow_act.setChecked(self.companion.follow_cursor_enabled)
        follow_act.toggled.connect(self.companion.set_follow_cursor)

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
        menu.addAction("⚙️ Brain Settings & Models…", self.open_console_settings)

        # 8. Close / Hide Mini Agent Option
        if self.companion.isVisible():
            menu.addSeparator()
            menu.addAction("✕ Close Mini Agent", self.hide_mini_agent)
        else:
            menu.addSeparator()
            menu.addAction("👁️ Show Mini Agent", self.show_mini_agent)

        menu.exec(global_pos)

    def _activate_and_notify(self, profile_id: str) -> None:
        self.profile_mgr.activate_profile(profile_id)
        self.companion.update()
        if self.store.setting("voice_reply", True):
            active = self.profile_mgr.get_active_profile()
            self.speech.start(f"Switched profile to {active.get('name')}.")
        else:
            self.speech.whistle()

    def open_console_settings(self) -> None:
        webbrowser.open("http://127.0.0.1:28842/#brain")

    def get_status(self) -> Dict[str, Any]:
        """Return runtime status for Web Console."""
        return {
            "name": "Brain",
            "is_mini_agent_visible": self.companion.isVisible(),
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
            "character": {
                "renderer": "3d" if self.companion.model_view and self.companion.model_view.ready else "artwork",
                "error": self.companion.model_view.error if self.companion.model_view else "",
            },
            "active_profile": self.profile_mgr.get_active_profile(),
            "profiles": self.profile_mgr.get_profiles(),
            "settings": self.store.get_all(),
        }

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
