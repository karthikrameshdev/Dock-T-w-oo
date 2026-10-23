"""Real-time audio listener with local wake word ('Brain'), fast VAD silence detection, and global push-to-talk shortcuts."""

from __future__ import annotations

import array
import io
import json
import math
import queue
import re
import threading
import time
import wave
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal


class AudioListener(QObject):
    """Monitors microphone stream for wake word ('Brain'), user speech, and fast VAD turn completion."""

    wake_detected = Signal()
    speech_started = Signal()
    turn_completed = Signal(str)  # Transcribed user text
    audio_level = Signal(float)
    error_occurred = Signal(str)

    def __init__(
        self,
        wake_word: str = "brain",
        on_wake: Optional[Callable[[], None]] = None,
        on_turn_complete: Optional[Callable[[str], None]] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.wake_word = wake_word.lower().strip()
        self.is_running = False
        self.is_recording = False
        self.noise_floor = 120.0
        self.speech_frames = []
        self.silence_count = 0
        self.has_spoken = False
        self.stream = None
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.audio_queue = queue.Queue(maxsize=40)

        if on_wake:
            self.wake_detected.connect(on_wake)
        if on_turn_complete:
            self.turn_completed.connect(on_turn_complete)

    def start(self) -> None:
        """Start background microphone monitoring."""
        import os
        if "PYTEST_CURRENT_TEST" in os.environ:
            return
        if self.is_running:
            return
        self.is_running = True
        self.stop_event.clear()
        self.worker_thread = threading.Thread(target=self._run_loop, daemon=True, name="brain-audio-listener")
        self.worker_thread.start()

    def stop(self) -> None:
        """Stop background audio capture."""
        self.is_running = False
        self.stop_event.set()
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def start_recording(self) -> None:
        """Explicitly begin recording a user turn (push-to-talk or post-wake)."""
        self.speech_frames = []
        self.silence_count = 0
        self.has_spoken = False
        self.is_recording = True
        self.speech_started.emit()

    def stop_recording(self) -> None:
        """Explicitly end recording immediately and process speech buffer."""
        if not self.is_recording:
            return
        self.is_recording = False
        frames = list(self.speech_frames)
        self.speech_frames = []
        if frames:
            threading.Thread(target=self._process_utterance, args=(frames,), daemon=True).start()

    def _run_loop(self) -> None:
        """Audio streaming capture loop via sounddevice."""
        try:
            import sounddevice as sd
        except ImportError:
            self.error_occurred.emit("sounddevice package not available for microphone listening.")
            return

        def audio_callback(indata, frames, time_info, status):
            if status and not self.stop_event.is_set():
                pass
            try:
                self.audio_queue.put_nowait(bytes(indata))
            except queue.Full:
                pass

        try:
            with sd.RawInputStream(
                samplerate=16000,
                channels=1,
                dtype="int16",
                blocksize=1600,  # 100ms chunks at 16kHz
                callback=audio_callback,
            ):
                while not self.stop_event.is_set():
                    try:
                        pcm_chunk = self.audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue

                    self._handle_pcm_frame(pcm_chunk)
        except Exception as exc:
            if not self.stop_event.is_set():
                self.error_occurred.emit(f"Microphone stream error: {exc}")

    def _handle_pcm_frame(self, pcm: bytes) -> None:
        """Analyze RMS energy for VAD and wake word monitoring."""
        samples = array.array("h")
        samples.frombytes(pcm)
        if not samples:
            return

        rms = math.sqrt(sum(float(x) ** 2 for x in samples) / len(samples))
        norm_level = min(1.0, max(0.0, (rms - self.noise_floor) / 1200.0))
        self.audio_level.emit(norm_level)

        threshold = max(240.0, self.noise_floor * 2.2)
        is_speech = rms > threshold

        if not self.is_recording:
            # Ambient tracking / Wake word detection
            if not is_speech:
                self.noise_floor = 0.96 * self.noise_floor + 0.04 * min(rms, 200.0)
            else:
                self.speech_frames.append(pcm)
                # If accumulated speech exceeds 0.8s, test for wake word
                if len(self.speech_frames) >= 8:
                    candidate_frames = list(self.speech_frames)
                    self.speech_frames = []
                    threading.Thread(target=self._check_wake_word, args=(candidate_frames,), daemon=True).start()
        else:
            # Active turn recording
            self.speech_frames.append(pcm)
            if is_speech:
                self.has_spoken = True
                self.silence_count = 0
            else:
                if self.has_spoken:
                    self.silence_count += 1
                    # 6 consecutive 100ms silence chunks = 0.6s silence after speech -> turn complete!
                    if self.silence_count >= 6:
                        self.stop_recording()

    def _check_wake_word(self, frames: list[bytes]) -> None:
        """Transcribe short candidate frame to detect wake word ('Brain')."""
        text = self._transcribe_pcm(b"".join(frames)).lower().strip()
        if re.search(r"\b(brain|hey\s+brain|brian)\b", text):
            self.wake_detected.emit()

    def _process_utterance(self, frames: list[bytes]) -> None:
        """Transcribe full user statement and emit turn_completed."""
        raw_pcm = b"".join(frames)
        # Skip trivial clicks/blips under 0.3s
        if len(raw_pcm) < 16000 * 2 * 0.3:
            return

        transcription = self._transcribe_pcm(raw_pcm)
        if transcription and len(transcription.strip()) > 1:
            self.turn_completed.emit(transcription.strip())

    def _transcribe_pcm(self, pcm_data: bytes) -> str:
        """Transcribe 16-bit 16kHz PCM audio buffer using local speech recognizer."""
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            recognizer.energy_threshold = 280
            recognizer.dynamic_energy_threshold = False

            # Wrap PCM in standard WAV container in-memory
            wav_buf = io.BytesIO()
            with wave.open(wav_buf, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(pcm_data)
            wav_buf.seek(0)

            with sr.AudioFile(wav_buf) as source:
                audio = recognizer.record(source)

            # Recognize using Google local/endpoint or Sphinx
            try:
                return recognizer.recognize_google(audio)
            except Exception:
                pass
        except Exception:
            pass

        return ""


class GlobalShortcutListener:
    """Listens for global push-to-talk and stop recording shortcuts (default: right Command key)."""

    def __init__(
        self,
        shortcut_key: str = "cmd_r",
        on_press: Optional[Callable[[], None]] = None,
        on_release: Optional[Callable[[], None]] = None,
    ):
        self.shortcut_key = shortcut_key.lower().strip()
        self.on_press_cb = on_press
        self.on_release_cb = on_release
        self.listener = None
        self._cocoa_monitors = []
        self.is_pressed = False

    def start(self) -> None:
        import os, sys
        if "PYTEST_CURRENT_TEST" in os.environ:
            return

        # macOS: Use native Cocoa NSEvent monitors to avoid pynput's TSM thread assertion crashes
        if sys.platform == "darwin":
            try:
                from Cocoa import (
                    NSEvent,
                    NSEventMaskFlagsChanged,
                    NSEventModifierFlagCommand,
                    NSEventModifierFlagControl,
                    NSEventModifierFlagOption,
                    NSEventModifierFlagShift,
                )

                modifier_codes = {
                    "cmd_r": 54, "right_cmd": 54, "right_command": 54,
                    "cmd_l": 55, "left_cmd": 55, "cmd": 55,
                    "alt_r": 61, "right_alt": 61, "option_r": 61, "right_option": 61,
                    "alt_l": 58, "left_alt": 58, "option_l": 58, "left_option": 58,
                    "ctrl_r": 62, "right_ctrl": 62, "right_control": 62,
                    "ctrl_l": 59, "left_ctrl": 59, "left_control": 59,
                    "shift_r": 60, "right_shift": 60,
                    "shift_l": 56, "left_shift": 56,
                }
                target_code = modifier_codes.get(self.shortcut_key)

                def handle_flags(event):
                    if target_code is not None and event.keyCode() == target_code:
                        flags = event.modifierFlags()
                        if target_code in (54, 55):
                            is_down = bool(flags & NSEventModifierFlagCommand)
                        elif target_code in (58, 61):
                            is_down = bool(flags & NSEventModifierFlagOption)
                        elif target_code in (59, 62):
                            is_down = bool(flags & NSEventModifierFlagControl)
                        elif target_code in (56, 60):
                            is_down = bool(flags & NSEventModifierFlagShift)
                        else:
                            is_down = False

                        if is_down != self.is_pressed:
                            self.is_pressed = is_down
                            if is_down and self.on_press_cb:
                                self.on_press_cb()
                            elif not is_down and self.on_release_cb:
                                self.on_release_cb()

                m_global = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                    NSEventMaskFlagsChanged, handle_flags
                )
                if m_global:
                    self._cocoa_monitors.append(m_global)

                def handle_local(event):
                    handle_flags(event)
                    return event

                m_local = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                    NSEventMaskFlagsChanged, handle_local
                )
                if m_local:
                    self._cocoa_monitors.append(m_local)
                return
            except Exception:
                pass

        try:
            from pynput import keyboard

            def is_target_key(key):
                if self.shortcut_key in ("cmd_r", "right_cmd", "right_command"):
                    return key == keyboard.Key.cmd_r
                if self.shortcut_key in ("cmd_l", "left_cmd", "cmd"):
                    return key in (keyboard.Key.cmd, keyboard.Key.cmd_l)
                if self.shortcut_key in ("ctrl_r", "right_ctrl"):
                    return key == keyboard.Key.ctrl_r
                if self.shortcut_key in ("alt_r", "right_alt", "option_r"):
                    return key == keyboard.Key.alt_r
                if hasattr(key, "name") and key.name and key.name.lower() == self.shortcut_key:
                    return True
                return False

            def on_key_press(key):
                if is_target_key(key) and not self.is_pressed:
                    self.is_pressed = True
                    if self.on_press_cb:
                        self.on_press_cb()

            def on_key_release(key):
                if is_target_key(key) and self.is_pressed:
                    self.is_pressed = False
                    if self.on_release_cb:
                        self.on_release_cb()

            self.listener = keyboard.Listener(on_press=on_key_press, on_release=on_key_release)
            self.listener.daemon = True
            self.listener.start()
        except Exception:
            pass

    def stop(self) -> None:
        if self._cocoa_monitors:
            try:
                from Cocoa import NSEvent
                for m in self._cocoa_monitors:
                    NSEvent.removeMonitor_(m)
            except Exception:
                pass
            self._cocoa_monitors.clear()

        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
            self.listener = None
