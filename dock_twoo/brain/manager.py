"""BrainManager singleton coordinating the Mini Agent companion, speech, model routing, and context menus."""

from __future__ import annotations

import random
import threading
import time
import webbrowser
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QMetaObject, QObject, QPoint, QThread, Qt, Signal, Slot
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

    _instance: Optional[BrainManager] = None

    @classmethod
    def get_instance(cls) -> BrainManager:
        if cls._instance is None:
            cls._instance = BrainManager()
        return cls._instance

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.store = BrainStore()
        self.profile_mgr = ProfileManager(self.store)
        self.speech = SpeechPlayback(self)

        self.companion = Companion(self)
        self.speech.activity.connect(self.companion.set_activity)
        self.speech.mouth.connect(self.companion.set_mouth)

        self.activity_requested.connect(self.companion.set_activity)
        self.speech_start_requested.connect(self._do_speech_start)
        self.action_requested.connect(self._do_action)

        self._active_query_thread: Optional[threading.Thread] = None
        self._is_listening: bool = False

        # Real-time microphone listening and wake word ('Brain') detection
        self.listener = AudioListener(
            wake_word=self.store.setting("wake_word", "brain"),
            on_wake=self._on_wake_detected,
            on_turn_complete=self._on_turn_complete,
            parent=self,
        )
        # Push-to-talk shortcut listener (default: right Command key)
        self.shortcut_listener = GlobalShortcutListener(
            shortcut_key=self.store.setting("push_to_talk_shortcut", "cmd_r"),
            on_press=self._on_shortcut_press,
            on_release=self._on_shortcut_release,
        )
        if self.store.setting("wake_word_enabled", True):
            self.listener.start()
        self.shortcut_listener.start()

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
    def show_mini_agent(self) -> None:
        """Summon and display the robot mini agent on the desktop."""
        if QThread.currentThread() != self.thread():
            QMetaObject.invokeMethod(self, "show_mini_agent", Qt.ConnectionType.QueuedConnection)
            return
        self.store.set_setting("companion_visible", True)
        self.companion.show()
        self.companion.raise_()
        self.visibility_changed.emit(True)

    @Slot()
    def hide_mini_agent(self) -> None:
        """Hide the mini agent and stop active speech."""
        if QThread.currentThread() != self.thread():
            QMetaObject.invokeMethod(self, "hide_mini_agent", Qt.ConnectionType.QueuedConnection)
            return
        self.store.set_setting("companion_visible", False)
        self.stop_talking()
        self.companion.stop_motion()
        self.companion.hide()
        self.visibility_changed.emit(False)

    @Slot()
    def toggle_mini_agent(self) -> None:
        """Clicking Brain in the dock acts like an on/off toggle for the Mini Agent."""
        if QThread.currentThread() != self.thread():
            QMetaObject.invokeMethod(self, "toggle_mini_agent", Qt.ConnectionType.QueuedConnection)
            return
        if self.companion.isVisible():
            self.hide_mini_agent()
        else:
            self.show_mini_agent()

    @Slot()
    def _on_wake_detected(self) -> None:
        """Invoked when user says 'Brain' or 'Hey Brain'."""
        if QThread.currentThread() != self.thread():
            QMetaObject.invokeMethod(self, "_on_wake_detected", Qt.ConnectionType.QueuedConnection)
            return
        if not self.companion.isVisible():
            self.show_mini_agent()
        self.companion.turn_to_user()
        self.companion.set_activity("listening")
        # Greet user immediately and start listening for their statement!
        self.speech.start("Hey Karthik, I'm listening.")

        def wait_and_record():
            while self.speech.playing:
                time.sleep(0.04)
            self.listener.start_recording()

        threading.Thread(target=wait_and_record, daemon=True).start()

    @Slot()
    def _on_shortcut_press(self) -> None:
        """Push-to-talk pressed: immediately begin recording."""
        if QThread.currentThread() != self.thread():
            QMetaObject.invokeMethod(self, "_on_shortcut_press", Qt.ConnectionType.QueuedConnection)
            return
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

    @Slot(str)
    def _on_turn_complete(self, user_text: str) -> None:
        """Invoked when user finishes statement (via VAD or explicit shortcut)."""
        if not user_text:
            self.activity_requested.emit("idle")
            return

        # Top indicator rotates green with cycling hue while processing
        self.activity_requested.emit("processing")

        def run_turn():
            # 1. Check for dedicated voice command (movement, action, memory, CUA, research)
            cmd_reply = handle_voice_command(user_text, self)
            if cmd_reply:
                reply = cmd_reply
            else:
                self.activity_requested.emit("thinking")
                active_profile = self.profile_mgr.get_active_profile()
                provider = active_profile.get("provider", "local") if active_profile else "local"
                api_key = self.profile_mgr.get_key(provider) if active_profile else ""
                reply = query_llm(user_text, profile=active_profile, api_key=api_key)

            if self.store.setting("voice_reply", True):
                self.speech_start_requested.emit(reply)
            else:
                self.activity_requested.emit("idle")

        threading.Thread(target=run_turn, daemon=True).start()

    @Slot()
    def start_talking(self) -> None:
        """Activate voice listening state for the robot."""
        if QThread.currentThread() != self.thread():
            QMetaObject.invokeMethod(self, "start_talking", Qt.ConnectionType.QueuedConnection)
            return
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
        self._is_listening = False
        self.listener.stop_recording()
        self.speech.stop()
        self.companion.set_activity("idle")

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
            "active_profile": self.profile_mgr.get_active_profile(),
            "profiles": self.profile_mgr.get_profiles(),
            "settings": self.store.get_all(),
        }
