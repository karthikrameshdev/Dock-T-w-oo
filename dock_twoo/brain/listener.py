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


def _patch_speech_recognition_flac() -> None:
    """Ensure SpeechRecognition uses native macOS afconvert instead of obsolete x86 flac-mac on ARM64."""
    try:
        import os, platform, subprocess, tempfile
        import speech_recognition as sr
        if platform.system() == "Darwin":
            def native_get_flac_data(self, convert_rate=None, convert_width=None):
                wav_data = self.get_wav_data(convert_rate, convert_width)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wf:
                    wf.write(wav_data)
                    wav_path = wf.name
                flac_path = wav_path + ".flac"
                try:
                    subprocess.run(
                        ["/usr/bin/afconvert", "-f", "flac", "-d", "flac", wav_path, flac_path],
                        check=True,
                        capture_output=True,
                    )
                    with open(flac_path, "rb") as ff:
                        flac_data = ff.read()
                    if flac_data.startswith(b"\x00\x00\x00\x00") and len(flac_data) >= 8:
                        flac_data = b"fLaC" + flac_data[4:]
                    return flac_data
                finally:
                    for p in (wav_path, flac_path):
                        if os.path.exists(p):
                            try:
                                os.unlink(p)
                            except Exception:
                                pass

            sr.AudioData.get_flac_data = native_get_flac_data
    except Exception:
        pass


_patch_speech_recognition_flac()


class AudioListener(QObject):
    """Monitors microphone stream for wake word ('Brain'), user speech, and fast VAD turn completion."""

    wake_detected = Signal()
    speech_started = Signal()
    speech_ended = Signal()
    processing_started = Signal()
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
        self.noise_floor = 30.0
        self.speech_frames = []
        self.ambient_speech_frames = []
        self.ambient_silence_count = 0
        self.silence_count = 0
        self.has_spoken = False
        self.stream = None
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.audio_queue = queue.Queue(maxsize=40)
        self._sf_recognizer = None
        self._init_native_speech()

        if on_wake:
            self.wake_detected.connect(on_wake)
        if on_turn_complete:
            self.turn_completed.connect(on_turn_complete)

    def _init_native_speech(self) -> None:
        """Initialize Apple Speech framework for instant offline on-device speech transcription if authorized."""
        try:
            import Speech
            from Foundation import NSLocale
            # Only use SFSpeechRecognizer if authorization has been explicitly granted (status == 3)
            # Otherwise it hangs waiting for permission or triggers TCC SIGABRT on unsigned Python binaries
            if hasattr(Speech.SFSpeechRecognizer, "authorizationStatus"):
                if Speech.SFSpeechRecognizer.authorizationStatus() != 3:
                    self._sf_recognizer = None
                    return
            loc = NSLocale.localeWithLocaleIdentifier_("en-US")
            rec = Speech.SFSpeechRecognizer.alloc().initWithLocale_(loc)
            if rec and rec.isAvailable():
                self._sf_recognizer = rec
        except Exception:
            self._sf_recognizer = None

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
        self.speech_ended.emit()
        self.processing_started.emit()
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
        norm_level = min(1.0, max(0.0, (rms - self.noise_floor) / 1000.0))
        self.audio_level.emit(norm_level)

        # Dynamic sensitivity: adapt to ambient room noise floor
        speech_threshold = max(35.0, self.noise_floor * 1.30)
        is_speech = rms > speech_threshold

        if not self.is_recording:
            # Ambient tracking / Wake word detection
            if not is_speech:
                self.noise_floor = 0.97 * self.noise_floor + 0.03 * min(rms, 180.0)
                if self.ambient_speech_frames:
                    self.ambient_silence_count += 1
                    # 3 consecutive 100ms silence chunks = 0.3s pause after speech for snappy response
                    if self.ambient_silence_count >= 3:
                        frames = list(self.ambient_speech_frames)
                        self.ambient_speech_frames = []
                        self.ambient_silence_count = 0
                        if len(frames) >= 2:
                            threading.Thread(target=self._check_wake_word, args=(frames,), daemon=True).start()
            else:
                self.ambient_silence_count = 0
                self.ambient_speech_frames.append(pcm)
                # Keep up to 80 frames (~8 seconds) to capture complete spoken commands without truncation
                if len(self.ambient_speech_frames) > 80:
                    self.ambient_speech_frames.pop(0)
        else:
            # Active turn recording
            self.speech_frames.append(pcm)
            if is_speech:
                self.has_spoken = True
                self.silence_count = 0
            else:
                if self.has_spoken:
                    self.silence_count += 1
                    # 5 consecutive 100ms silence chunks = 0.5s silence after speech -> turn complete!
                    if self.silence_count >= 5:
                        self.stop_recording()
                elif len(self.speech_frames) > 70:
                    # Recording started but user didn't speak within 7s -> timeout
                    self.stop_recording()

    def _check_wake_word(self, frames: list[bytes]) -> None:
        """Transcribe ambient utterance to detect wake word ('Brain') or full command."""
        raw_pcm = b"".join(frames)
        if len(raw_pcm) < 16000 * 2 * 0.18:
            return
        text = self._transcribe_pcm(raw_pcm).strip()
        if not text:
            return

        wake_match = re.search(r"\b(brain|hey\s+brain|brian|brin|rain|bran|drain|ray|rayne)\b", text, re.IGNORECASE)
        if wake_match:
            self.ambient_speech_frames = []
            self.ambient_silence_count = 0
            # Check if user spoke a full command or just called the wake name
            clean_cmd = re.sub(r"^(hey\s+brain|brain|brian|brin|rain|bran|drain|ray|rayne)[,\s]*", "", text, flags=re.IGNORECASE).strip()
            if not clean_cmd:
                # User said "Brain" and paused: wake up and greet!
                self.wake_detected.emit()
            else:
                # User spoke a full statement (e.g. "Brain, do this"): process directly without interrupting!
                self.turn_completed.emit(text)

    def _process_utterance(self, frames: list[bytes]) -> None:
        """Transcribe full user statement and emit turn_completed."""
        raw_pcm = b"".join(frames)
        # Skip trivial clicks/blips under 0.25s
        if len(raw_pcm) < 16000 * 2 * 0.25:
            return

        transcription = self._transcribe_pcm(raw_pcm)
        if transcription and len(transcription.strip()) > 1:
            self.turn_completed.emit(transcription.strip())

    def _transcribe_pcm(self, pcm_data: bytes) -> str:
        """Transcribe 16-bit 16kHz PCM audio buffer using local on-device recognizer with fallback."""
        if not pcm_data or len(pcm_data) < 1600:
            return ""

        # 1. On macOS: Native On-Device Speech Recognition (instant, zero network latency)
        if self._sf_recognizer:
            try:
                import Speech
                from Foundation import NSURL
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                    temp_wav = tf.name
                with wave.open(temp_wav, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(pcm_data)

                ns_url = NSURL.fileURLWithPath_(temp_wav)
                req = Speech.SFSpeechURLRecognitionRequest.alloc().initWithURL_(ns_url)
                if hasattr(req, "setRequiresOnDeviceRecognition_"):
                    req.setRequiresOnDeviceRecognition_(True)

                results = []
                done_ev = threading.Event()

                def handler(result, error):
                    if result:
                        text = str(result.bestTranscription().formattedString())
                        results.append(text)
                        if result.isFinal():
                            done_ev.set()
                    if error:
                        done_ev.set()

                task = self._sf_recognizer.recognitionTaskWithRequest_resultHandler_(req, handler)
                done_ev.wait(timeout=1.6)
                try:
                    os.unlink(temp_wav)
                except Exception:
                    pass
                if results and results[-1].strip():
                    return results[-1].strip()
            except Exception:
                pass

        # 2. Fallback: speech_recognition (Google endpoint / Sphinx)
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            recognizer.energy_threshold = 180
            recognizer.dynamic_energy_threshold = False

            wav_buf = io.BytesIO()
            with wave.open(wav_buf, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(pcm_data)
            wav_buf.seek(0)

            with sr.AudioFile(wav_buf) as source:
                audio = recognizer.record(source)

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
