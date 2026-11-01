"""Explicit assistant lifecycle, independent of the dock and saved wake preferences."""
from functools import wraps
import threading
from PySide6.QtCore import QThread


def lifecycle_locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._assistant_lock:
            return method(self, *args, **kwargs)
    return call


class AssistantLifecycle:
    @property
    def assistant_available(self):
        return not self.assistant_closed and not self._shutting_down

    @property
    def listening_mode(self):
        return self.store.setting('listening_mode', 'automatic')

    def set_listening_mode(self, mode):
        if mode not in ('automatic', 'manual', 'off'):
            raise ValueError('Listening mode must be automatic, manual or off.')
        if QThread.currentThread() != self.thread():
            self.run_on_main_thread(lambda: self.set_listening_mode(mode))
            return
        # Changing input policy invalidates old queued microphone/shortcut events,
        # but does not cancel model work or interrupt the current spoken answer.
        self._assistant_epoch += 1
        self.store.set_setting('listening_mode', mode)
        self.listener.listening_mode = mode
        self.listener.wake_detection_enabled = mode == 'automatic'
        self.listener.stop()
        self.shortcut_listener.stop()
        self.in_conversation_session = False
        self.session_timer.stop()
        self._listening_actor_id = self._listening_source = None
        self._pending_listener = self._pending_listener_source = None
        self._session_actor_id = self._session_source = None
        if self.assistant_available:
            if self._services_enabled and mode != 'off':self.shortcut_listener.start()
            if mode == 'automatic':
                # Preserve output echo suppression when automatic is enabled mid-answer.
                if self.reader.active:self.listener.suspend()
                self.listener.set_output_active(self.speech.playing or self._awaiting_reply or self.reader.active)
                if self._services_enabled:self.listener.start()
        self._refresh_actor_states()
        labels = {'automatic': 'Automatic wake-word listening', 'manual': 'Manual click or shortcut listening', 'off': 'Microphone off'}
        self.status_changed.emit(labels[mode])

    def _dispatch_assistant_callback(self, callback, *args):
        """Discard microphone/shortcut events queued before Close, even after reopen."""
        epoch = self._assistant_epoch
        def deliver():
            if self.assistant_available and epoch == self._assistant_epoch:
                callback(*args)
        self.run_on_main_thread(deliver)

    @lifecycle_locked
    def _open_assistant(self):
        """Only an explicit Show/Choose/Talk action may leave the closed state."""
        if self._shutting_down:
            return False
        if not self.assistant_closed:
            return True
        self._assistant_epoch += 1
        self.assistant_closed = False
        self._models_release_pending = False
        self.store.set_setting('assistant_closed', False)
        self.file_approvals.closed = False
        self.notifications.closed = False
        self.listener.closed = False
        self.listener.arm_wake()
        if self._services_enabled:
            if self.listening_mode != 'off':self.shortcut_listener.start()
            self.reader.remember_timer.start()
            self.ecology.timer.start()
            self.semantic_model.start()
            from dock_twoo.brain.local_tts import get_local_tts
            get_local_tts().start()
            if self.listening_mode == 'automatic':
                self.listener.start()
        self.status_changed.emit('Voice assistant opened.')
        return True

    @lifecycle_locked
    def close_assistant(self):
        """Cancel assistant work and release audio/presentation; leave the dock running."""
        if QThread.currentThread() != self.thread():
            self.run_on_main_thread(self.close_assistant)
            return
        self._assistant_epoch += 1
        self.assistant_closed = True
        self._models_release_pending = True
        self.store.update_settings({'assistant_closed': True, 'companion_visible': False})
        # Set the gate BEFORE cancelling: stop/finished callbacks cannot rearm input.
        self.listener.closed = True
        # Release OS devices first; cancelling jobs may need disk/grpc bookkeeping.
        self.audio_devices.close()
        self.stop_talking()
        self.listener.stop()
        self.shortcut_listener.stop()
        self.file_approvals.close()
        self.notifications.close()
        self.reader.remember_timer.stop()
        self.ecology.timer.stop()
        self.reminders.speech_queue.clear()
        for actor in self.companions.values():
            actor.stop_motion()
            actor.hide()
            if actor.model_view:
                actor.model_view.release_resources()
        self.visibility_changed.emit(False)
        self.status_changed.emit('Voice assistant closed. Microphone off. Open it from the dock to resume.')

    @lifecycle_locked
    def release_closed_resources(self):
        """Housekeeping thread: release idle ONNX sessions without waiting on inference.

        Close disables hardware immediately. In-flight native inference is allowed
        to return before its sessions are freed, and no result may reopen the UI.
        The lifecycle lock prevents a simultaneous explicit Open from racing unload.
        """
        if not self.assistant_closed or not self._models_release_pending:
            return
        if self._processing_turns or self.listener.decode_workers_active():return
        if self.listener.audio_workers_active():return
        if self.speech.worker and self.speech.worker.is_alive():return
        from dock_twoo.brain.local_tts import get_local_tts
        components = (self.listener.models, self.listener.wake_detector,
                      self.listener.stop_detector, self.listener.endpoint_vad, get_local_tts())
        released = [component.release_if_idle() for component in components]
        self.listener.echo_guard.clear()
        self._models_release_pending = not all(released)

    def _record_stopped_runs(self, runs):
        """One coalescing writer records exact cancelled IDs away from GUI locks."""
        if not runs:return
        with self._stop_trace_lock:
            self._stop_trace_pending.update(runs)
            if self._stop_trace_worker is not None:return
            self._stop_trace_worker = threading.Thread(
                target=self._write_stopped_runs, name='assistant-stop-trace', daemon=True)
            self._stop_trace_worker.start()

    def _write_stopped_runs(self):
        while True:
            with self._stop_trace_lock:
                if not self._stop_trace_pending:
                    self._stop_trace_worker = None
                    return
                run_id, reason = self._stop_trace_pending.popitem()
            try:self.activity.finish(run_id, 'stopped', reason=reason)
            except Exception as exc:self._stop_trace_error = str(exc)[:300]

    def _require_assistant(self):
        if self.assistant_available:
            return True
        self.status_changed.emit('Voice assistant is closed. Open it from the dock to resume.')
        return False
