"""Real-time audio listener with local wake word ('Brain'), fast VAD silence detection, and global push-to-talk shortcuts."""

from __future__ import annotations

import array
from collections import deque
from functools import wraps
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

from dock_twoo.brain.endpoint import TurnEndpoint


def capture_locked(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._capture_lock:
            return method(self, *args, **kwargs)
    return wrapped


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


def command_after_keyword(text: str, wake_word: str = "brain", *, strict=False) -> tuple[bool, str]:
    """Interpret dictation only after the dedicated keyword model has fired.

    A tiny dictation model often spells a one-word 'Brain' as 'plane' or 'green'.
    It must not veto the keyword model for those short calls. Longer transcripts
    can reject a close negative ('bring me ...') and preserve an inline command.
    """
    words = re.findall(r"[\w']+", text.lower())
    if words and words[0] == "bring" and len(words) > 1:
        return False, ""
    configured = wake_word.lower().strip() or "brain"
    aliases = {"brain", "brian", "buddy", "bobby", "body", "grain", "green", "plane", "spring", configured, configured.split()[-1]}
    if strict and configured not in {"brain","buddy","brian"}:aliases={configured}
    matches = list(re.finditer(r"[\w']+", text))
    for index, word in enumerate(words):
        if strict and not (index==0 or (index==1 and words[0] in {"hey","hello","hi","okay","ok","a","may"})):continue
        if word in ({configured} if strict and configured not in {"brain","buddy","brian"} else {"brain", "brian", "buddy", configured, configured.split()[-1]}):
            command = text[matches[index].end():].strip(" \t,.:;!?…-–—")
            remaining = re.findall(r"[\w']+", command.lower())
            if remaining and all(part in aliases | {"hey", "hello", "hi"} for part in remaining):
                command = ""
            return True, command
    for index, word in enumerate(words[:3]):
        if strict and not (index==0 or (index==1 and words[0] in {"hey","hello","hi","okay","ok","a","may"})):continue
        if word in aliases:
            command = text[matches[index].end():].strip(" \t,.:;!?…-–—")
            remaining = re.findall(r"[\w']+", command.lower())
            if remaining and all(word in aliases | {"hey", "hello", "hi"} for word in remaining):
                command = ""
            return True, command
    if words and words[0] in {"what", "when", "where", "how", "can", "open", "launch", "type", "sing", "hum", "show", "take", "walk", "dance", "climb", "stop", "tell", "set", "find", "search", "read", "write", "move", "turn", "give", "go", "do", "research", "please", "help"}:
        return True, text.strip()
    if not strict and len(words) <= 3:
        return True, ""
    return False, ""


class AudioListener(QObject):
    """Monitors microphone stream for wake word ('Brain'), user speech, and fast VAD turn completion."""

    named_wake_started = Signal(str)
    named_turn_completed = Signal(str, str, str, bool)  # id, command, raw transcript, bare wake
    wake_detected = Signal()
    wake_started = Signal()  # A verified keyword was heard; show the companion immediately.
    speech_started = Signal()
    speech_ended = Signal()
    processing_started = Signal()
    turn_completed = Signal(str)  # Transcribed user text
    turn_timed_out = Signal()
    audio_level = Signal(float)
    error_occurred = Signal(str)
    stop_requested = Signal(str)

    def __init__(
        self,
        wake_word: str = "brain",
        on_wake: Optional[Callable[[], None]] = None,
        on_turn_complete: Optional[Callable[[str], None]] = None,
        parent: Optional[QObject] = None,
        *,
        store=None,
        model_dir=None,
        audio_devices=None,
    ):
        super().__init__(parent)
        from dock_twoo.brain.audio_devices import DefaultAudioDevices
        self.audio_devices = audio_devices or DefaultAudioDevices(self)
        self.audio_devices.input_frame.connect(self._enqueue_audio)
        self.audio_devices.input_state.connect(self._input_state)
        self.audio_devices.error.connect(self.error_occurred)
        self._capture_lock = threading.RLock()
        self.named_characters = False
        self.capture_character_id = "default"
        self._keyword_character_id = None
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
        self.stream_active = False
        self.last_error = ""
        self.audio_frames_seen = 0
        self.speech_frames_seen = 0
        self.ambient_segments_seen = 0
        self.last_frame_rms = 0.0
        self.last_wake_decision = "waiting-for-audio"
        self.last_wake_checks = 0
        self.last_wake_matches = 0
        self.backup_wake_checks = 0
        self.backup_wake_matches = 0
        self._diagnostic_lock = threading.Lock()
        self._diagnostic_started = self._diagnostic_until = 0.0
        self._diagnostic_entries = deque(maxlen=20)
        self._diagnostic_peak = 0.0
        self._wake_check_lock = threading.Lock()
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.audio_queue = queue.Queue(maxsize=40)
        self._sf_recognizer = None
        from dock_twoo.brain.voice_models import LocalVoiceModels, load_embedding
        from dock_twoo.brain.storage import BrainStore
        self.store = store or BrainStore()
        self.models = LocalVoiceModels(model_dir or self.store.data_dir / "models")
        from dock_twoo.brain.wake import WakeDetector
        self.wake_detector = WakeDetector(self.models.model_dir, self.wake_word)
        self.stop_detector = WakeDetector(self.models.model_dir, keywords=('STOP', 'BRAIN STOP'))
        from dock_twoo.brain.echo import PlaybackEchoGuard
        self.echo_guard = PlaybackEchoGuard()
        self._passive_stop = False
        self._stop_latched = False
        self.stop_matches = 0
        from dock_twoo.brain.endpoint_vad import NeuralEndpointVad
        self.endpoint_vad = NeuralEndpointVad(self.models.model_dir)
        self._wake_preroll = deque(maxlen=20)
        self._backup_ring = deque(maxlen=40)
        self._backup_voice_ring = deque(maxlen=40)
        self._backup_ticks = 0
        self._backup_checked = False
        self._backup_silence = 0.0
        self._endpoint = TurnEndpoint()
        self._wake_capture = False
        self._capture_revision = 0
        self._decode_token = None
        self._capture_forced = False
        self._audio_timeline = deque(maxlen=160)
        self._wake_armed = True
        self.wake_detection_enabled = True
        self._output_active = False
        self._ignore_audio_until = 0.0
        self._capture_generation = 0
        self.input_device = ""
        self.input_overflows = 0
        self.dropped_frames = 0
        self._load_speaker_embedding = load_embedding
        self.owner_embedding_path = self.store.data_dir / "owner_voice_embedding.json"
        self.last_wake_owner_verified: Optional[bool] = None
        self._enrollment_lock = threading.Lock()
        self._enrollment_frames: Optional[list[bytes]] = None
        self._enrollment_complete = threading.Event()
        self._enrollment_result: Optional[bytes] = None
        try:
            import webrtcvad
            # Wake spotting bypasses VAD entirely. Mode 2 bounds assistant turns in
            # background noise instead of treating every energetic frame as speech.
            self._vad = webrtcvad.Vad(2)
        except ImportError:
            self._vad = None
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
        self.last_error = ""
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        self.wake_detector.start()
        self.stop_detector.start()
        self.endpoint_vad.start()
        self.models.start_model_downloads()
        self.is_running = True
        self.stop_event.clear()
        self.worker_thread = threading.Thread(target=self._run_loop, daemon=True, name="brain-audio-listener")
        self.worker_thread.start()
        self.audio_devices.start_input()

    def stop(self) -> None:
        """Stop background audio capture."""
        self.is_running = False
        self.stop_event.set()
        self.audio_devices.stop_input()
        if self.worker_thread and self.worker_thread is not threading.current_thread():
            self.worker_thread.join(timeout=1.0)
        self.cancel_recording()

    @capture_locked
    def start_recording(self) -> None:
        """Listen for a complete turn; silence timeout starts before speech only."""
        self._capture_generation += 1
        self._capture_revision = 0
        self._decode_token = None
        self._capture_forced = False
        self._passive_stop = False
        self._stop_latched = False
        self._wake_capture = False
        self._keyword_character_id = None
        self.wake_detector.reset()
        self._endpoint = TurnEndpoint()
        self.speech_frames = []
        self.silence_count = 0
        self.has_spoken = False
        self.is_recording = True
        self._wake_armed = False
        self.speech_started.emit()

    @capture_locked
    def _begin_wake_capture(self, frames: list[bytes], character_id=None) -> None:
        if character_id is not None:
            self.capture_character_id = character_id
        self._output_active = False
        self._ignore_audio_until = 0
        self.start_recording()
        self._keyword_character_id = character_id
        self.speech_frames = list(frames)
        self._wake_capture = True
        self.has_spoken = True
        self._endpoint.speech = .2  # A verified name is already speech.
        self.last_wake_decision = "capturing-wake-statement"
        self.wake_started.emit()  # Visual acknowledgement only, never speech.
        if self.named_characters:
            self.named_wake_started.emit(self.capture_character_id)

    @capture_locked
    def stop_recording(self) -> None:
        """Finish explicitly on push-to-talk release; automatic capture uses VAD."""
        if self.is_recording:
            self._capture_forced = True
            self.is_recording = False
            self._passive_stop = True
            self.speech_ended.emit()
            self.processing_started.emit()
            self._dispatch_capture()

    def _dispatch_capture(self) -> None:
        if self._decode_token is not None:
            return
        if self._endpoint.overlong or not self.has_spoken or self._endpoint.speech < .18:
            if self._endpoint.overlong:
                self.last_error = "The statement exceeded two minutes; no partial command was executed."
                self.error_occurred.emit(self.last_error)
            self.cancel_recording()
            self.turn_timed_out.emit()
            return
        token = (self._capture_generation, self._capture_revision)
        self._decode_token = token
        target = self._complete_keyword_wake if self._wake_capture else self._process_utterance
        threading.Thread(target=target, args=(list(self.speech_frames), *token), daemon=True).start()

    @capture_locked
    def _accept_capture(self, generation, revision) -> bool:
        if generation is not None and generation != self._capture_generation:
            return False
        if revision is not None:
            if self._decode_token != (generation, revision):
                return False
            self._decode_token = None
            if revision != self._capture_revision:
                self.last_wake_decision = "speech-resumed-before-reply"
                if self._capture_forced:
                    self._dispatch_capture()
                return False
            was_recording = self.is_recording
            self.is_recording = False
            self._passive_stop = True
            self.speech_frames = []
            self._wake_capture = False
            if was_recording:
                self.speech_ended.emit()
                self.processing_started.emit()
        return True

    @capture_locked
    def cancel_recording(self) -> None:
        """Invalidate every pending capture/decode without processing partial speech."""
        self.is_recording = False
        self._capture_generation += 1
        self._capture_revision = 0
        self._decode_token = None
        self.speech_frames = []
        self.has_spoken = False
        self._wake_capture = False

    @capture_locked
    def arm_wake(self) -> None:
        self.cancel_recording()
        self._passive_stop = False
        self._stop_latched = False
        self._wake_armed = self.wake_detection_enabled
        self._wake_preroll.clear()
        self._backup_ring.clear()
        self._backup_voice_ring.clear()
        self._backup_ticks = 0
        self._backup_checked = False
        self._backup_silence = 0.0
        self.ambient_speech_frames = []
        self.ambient_silence_count = 0
        self._audio_timeline.clear()
        self.wake_detector.reset()
        self.endpoint_vad.reset()

    @capture_locked
    def suspend(self) -> None:
        """Suspend capture during an explicit document-reading session."""
        self.cancel_recording()
        self._wake_armed = False
        self._passive_stop = True

    @capture_locked
    def set_output_active(self, active: bool) -> None:
        """Use playback time for stop-only monitoring, never ambient wake routing."""
        was_active = self._output_active
        self._output_active = active
        if active:
            self._passive_stop = True
            if not was_active:
                self._stop_latched = False
                self.stop_detector.reset()
        if active or was_active:
            self._ignore_audio_until = time.monotonic() + 0.3
            self._wake_preroll.clear()
            self._backup_ring.clear()
            self._backup_voice_ring.clear()
            self._backup_ticks = 0
            self._backup_checked = False
            self._backup_silence = 0.0
            self.wake_detector.reset()
            self.endpoint_vad.reset()

    @capture_locked
    def enable_character_names(self):
        from dock_twoo.brain.catalog import characters
        self.named_characters = True
        self.wake_detector.configure_names([entry['name'] for entry in characters()])

    def _emit_statement(self, text, command=None, bare=False, character_id=None):
        if self.named_characters:
            from dock_twoo.brain.catalog import named_prefix
            found, rest = named_prefix(text, acoustic=True)
            target = found or character_id or self.capture_character_id
            value = rest if found else (command if command is not None else text.strip())
            self.named_turn_completed.emit(target, value, text, bare or (found is not None and not rest))
        elif bare:
            self.wake_detected.emit()
        else:
            self.turn_completed.emit(text.strip() if command is None else command)

    def set_wake_word(self, value: str) -> None:
        self.wake_word = value.lower().strip() or "brain"
        self.wake_detector.configure(self.wake_word)

    def capture_owner_enrollment(self, timeout: float = 10.0) -> bytes:
        """Capture a short owner sample from the existing microphone stream."""
        if not self.is_running or not self.stream_active:
            raise RuntimeError("Start Brain's microphone listener before enrolling your voice.")
        with self._enrollment_lock:
            if self._enrollment_frames is not None:
                raise RuntimeError("Voice enrollment is already in progress.")
            self._enrollment_result = None
            self._enrollment_complete.clear()
            self._enrollment_frames = []
        if not self._enrollment_complete.wait(timeout):
            with self._enrollment_lock:
                self._enrollment_frames = None
            raise TimeoutError("Timed out waiting for the voice sample. Please try again.")
        if self._enrollment_result is None:
            raise RuntimeError("No voice sample was captured. Please try again.")
        return self._enrollment_result

    def _input_state(self, active: bool, name: str) -> None:
        self.stream_active = active
        self.input_device = name
        if active:
            self.last_error = ''

    def _enqueue_audio(self, pcm: bytes, captured_at: float) -> None:
        if not self.is_running:
            return
        try:
            self.audio_queue.put_nowait((pcm, captured_at))
        except queue.Full:
            self.dropped_frames += 1

    def _run_loop(self) -> None:
        """Analyze normalized audio independently of the native audio device."""
        try:
            while not self.stop_event.is_set():
                try:
                    pcm, captured_at = self.audio_queue.get(timeout=.2)
                except queue.Empty:
                    continue
                self._handle_pcm_frame(pcm, captured_at=captured_at)
        except Exception as exc:
            self.last_error = f'Microphone processing error: {exc}'
            self.error_occurred.emit(self.last_error)
        finally:
            self.is_running = False

    @capture_locked
    def _handle_pcm_frame(self, pcm: bytes, *, captured_at=None) -> None:
        """Analyze RMS energy for VAD and wake word monitoring."""
        samples = array.array("h")
        samples.frombytes(pcm)
        if not samples:
            return
        self.audio_frames_seen += 1

        if self._output_active or (self._passive_stop and not self.is_recording):
            self.last_wake_decision = "monitoring-spoken-stop"
            clean = self.echo_guard.filter(pcm, captured_at)
            if not self._stop_latched and self.stop_detector.ready:
                keyword = self.stop_detector.feed(clean)
                if keyword in ('STOP', 'BRAIN_STOP'):
                    self._stop_latched = True
                    self.stop_matches += 1
                    self.cancel_recording()
                    self.last_wake_decision = 'spoken-stop'
                    self.stop_requested.emit(keyword.replace('_', ' ').title())
                    return
            if not self.named_characters or not self.wake_detection_enabled:
                return
            # Shared output permits a named handoff on echo-cleaned audio.
            pcm = clean
            samples = array.array('h'); samples.frombytes(pcm)
        if time.monotonic() < self._ignore_audio_until and not self.named_characters:
            self.last_wake_decision = "suppressing-playback-echo"
            return

        with self._enrollment_lock:
            if self._enrollment_frames is not None:
                self._enrollment_frames.append(pcm)
                # Five seconds gives WavLM several phonetic contexts for a stable template.
                if len(self._enrollment_frames) >= 50:
                    self._enrollment_result = b"".join(self._enrollment_frames)
                    self._enrollment_frames = None
                    self._enrollment_complete.set()
                return

        rms = math.sqrt(sum(float(x) ** 2 for x in samples) / len(samples))
        self.last_frame_rms = round(rms, 1)
        if time.monotonic() < self._diagnostic_until:
            self._diagnostic_peak = max(self._diagnostic_peak, rms)
        norm_level = min(1.0, max(0.0, (rms - self.noise_floor) / 1000.0))
        self.audio_level.emit(norm_level)

        # Dynamic sensitivity: adapt to ambient room noise floor
        speech_threshold = max(12.0, self.noise_floor * 0.50)
        is_speech = self._is_speech_frame(pcm, rms, speech_threshold)
        if is_speech:
            self.speech_frames_seen += 1

        self._audio_timeline.append((self.audio_frames_seen, pcm, is_speech))
        if self.is_recording:
            if self.named_characters and not self._wake_capture and self._endpoint.speech < 1.5:
                from dock_twoo.brain.catalog import keyword_id
                keyword = self.wake_detector.feed(pcm) if self.wake_detector.ready else ''
                target = keyword_id(keyword) if keyword else None
                if target is not None:
                    self.capture_character_id = target
                    self._keyword_character_id = target
                    self._wake_capture = True
                    self.named_wake_started.emit(target)
            # Continue listening while a candidate transcript is being decoded.
            # Speech resuming during ASR invalidates that candidate and extends it.
            if is_speech and self._decode_token is not None and not self._capture_forced:
                self._capture_revision += 1
            if not self._capture_forced:
                self._endpoint.feed(len(pcm) / 32000, is_speech)
                self.has_spoken = self._endpoint.speech > 0
                if not self._endpoint.overlong:
                    self.speech_frames.append(pcm)
            if self._endpoint.complete or self._endpoint.idle_expired or self._endpoint.overlong:
                self._dispatch_capture()
            return
        if not self.wake_detection_enabled or (not self._wake_armed and not (self.named_characters and (self._output_active or self._passive_stop))):
            return
        self._wake_preroll.append(pcm)
        if self.wake_detector.ready:
            self.last_wake_checks += 1
            keyword = self.wake_detector.feed(pcm)
            self.last_wake_decision = "waiting-for-keyword"
            if keyword:
                self.last_wake_matches += 1
                from dock_twoo.brain.catalog import keyword_id
                self._begin_wake_capture(list(self._wake_preroll), keyword_id(keyword) if self.named_characters else None)
                return
        elif not self.models.recognizer.ready and self._sf_recognizer is None:
            self.last_wake_decision = "wake-model-" + self.wake_detector.state
            return
        # One backup per utterance, not full Whisper every two seconds during
        # background conversations/music. The streaming keyword detector above
        # remains active on every frame, including quiet speech and long audio.
        self._backup_ring.append(pcm)
        self._backup_voice_ring.append(is_speech)
        self._backup_silence = 0.0 if is_speech else self._backup_silence+len(pcm)/32000
        if is_speech or self._backup_ticks:self._backup_ticks += 1
        voiced = sum(self._backup_voice_ring)
        retry_without_kws = not self.wake_detector.ready and self._backup_ticks > 0 and self._backup_ticks % 20 == 0
        if (not self._backup_checked or retry_without_kws) and voiced >= 2 and (self._backup_ticks >= 20 or self._backup_silence >= .4):
            self._backup_checked = True
            # A partial backup only activates capture; it never executes text.
            self._dispatch_wake_check(list(self._backup_ring))
        if self._backup_silence >= .8:
            self._backup_ring.clear();self._backup_voice_ring.clear()
            self._backup_ticks = 0;self._backup_checked = False

    def _dispatch_wake_check(self, frames: list[bytes]) -> None:
        if not frames:
            return
        self.ambient_segments_seen += 1
        self.last_wake_decision = "transcribing-ambient-audio"
        threading.Thread(target=self._check_wake_word, args=(frames, self._capture_generation, self.audio_frames_seen), daemon=True).start()

    def begin_voice_check(self, seconds: float = 30.0) -> None:
        """Expose a short, explicit local diagnostic; no microphone audio is saved."""
        if not self.is_running or not self.stream_active:
            raise RuntimeError("The microphone listener is not running.")
        with self._diagnostic_lock:
            self._diagnostic_started = time.monotonic()
            self._diagnostic_until = self._diagnostic_started + seconds
            self._diagnostic_entries.clear()
            self._diagnostic_peak = 0.0

    def _record_voice_check(self, text: str, engine: str) -> None:
        now = time.monotonic()
        if now < self._diagnostic_until and text:
            with self._diagnostic_lock:
                self._diagnostic_entries.append({"seconds": round(now - self._diagnostic_started, 1),
                                                 "engine": engine, "heard": text[:100]})

    def voice_check_status(self) -> dict[str, object]:
        now = time.monotonic()
        with self._diagnostic_lock:
            if now > self._diagnostic_until + 90:
                self._diagnostic_entries.clear()
            return {"active": now < self._diagnostic_until,
                    "seconds_remaining": max(0, round(self._diagnostic_until - now)),
                    "peak_rms": round(self._diagnostic_peak, 1), "heard": list(self._diagnostic_entries)}

    def diagnostics(self) -> dict[str, object]:
        """Expose counters and decision stage without retaining recognized user speech."""
        speech_authorization = "unavailable"
        if self._sf_recognizer is not None:
            speech_authorization = "authorized"
        else:
            try:
                import Speech
                speech_authorization = str(Speech.SFSpeechRecognizer.authorizationStatus())
            except Exception:
                pass
        return {
            "audio_frames": self.audio_frames_seen,
            "speech_frames": self.speech_frames_seen,
            "ambient_segments": self.ambient_segments_seen,
            "wake_checks": self.last_wake_checks,
            "wake_matches": self.last_wake_matches,
            "last_rms": self.last_frame_rms,
            "last_decision": self.last_wake_decision,
            "apple_speech_authorization": speech_authorization,
            "speech_checkpoint_cached": self.models.model_weights_cached(self.models.ASR_MODEL),
            "denoiser_checkpoint_cached": self.models.model_weights_cached(self.models.ENHANCER_MODEL),
            "wake_model": self.wake_detector.status(),
            "recognizer_engine": "Whisper small.en INT8",
            "recognizer_ready": self.models.recognizer.ready,
            "input_device": self.input_device,
            "audio_devices": self.audio_devices.status(),
            "input_overflows": self.input_overflows,
            "dropped_frames": self.dropped_frames,
            "wake_armed": self._wake_armed,
            "output_active": self._output_active,
            "passive_stop": self._passive_stop,
            "stop_model": self.stop_detector.status(),
            "stop_matches": self.stop_matches,
            "playback_echo": self.echo_guard.status(),
            "recording": self.is_recording,
            "capture_kind": "wake statement" if self._wake_capture else "command",
            "capture_seconds": round(self._endpoint.elapsed, 2),
            "trailing_silence_seconds": round(self._endpoint.silence, 2),
            "endpoint_silence_seconds": self._endpoint.silence_required,
            "speech_boundary_model": self.endpoint_vad.status(),
            "decoding": self._decode_token is not None,
            "backup_wake_checks": self.backup_wake_checks,
            "backup_wake_matches": self.backup_wake_matches,
            "voice_check": self.voice_check_status(),
        }

    def _is_speech_frame(self, pcm: bytes, rms: float, threshold: float) -> bool:
        """Use WebRTC's noise-robust VAD when installed, with a low-volume energy fallback."""
        if self.endpoint_vad.ready:
            return self.endpoint_vad.feed(pcm)
        if self._vad is not None:
            try:
                if rms < 2.0:
                    return False
                if rms < 250:
                    import numpy as np
                    pcm = np.clip(np.frombuffer(pcm, dtype="<i2").astype(np.float32) * min(8.0, 250 / rms), -32768, 32767).astype("<i2").tobytes()
                # RawInputStream blocks are 100ms. WebRTC VAD accepts 10/20/30ms frames.
                frames = [pcm[offset:offset + 640] for offset in range(0, len(pcm) - 639, 640)]
                return sum(self._vad.is_speech(frame, 16000) for frame in frames) >= max(1, len(frames) // 2 + 1)
            except Exception:
                pass
        return rms > threshold

    def _complete_keyword_wake(self, frames: list[bytes], generation: Optional[int] = None, revision: Optional[int] = None) -> None:
        """Confirm a detected name and preserve any following command locally."""
        pcm = b"".join(frames)
        try:
            text = self._transcribe_pcm(pcm).strip()
            self._record_voice_check(text, "keyword confirmation")
        except Exception as exc:
            self.last_error = f"Wake confirmation failed: {exc}"
            self.error_occurred.emit(self.last_error)
            text = ""
        if not self._accept_capture(generation, revision):
            return
        if not text:
            self.last_wake_decision = "wake-statement-not-understood"
            self._emit_statement("")
            return
        if self.named_characters:
            from dock_twoo.brain.catalog import named_prefix
            found, command = named_prefix(text, acoustic=True)
            accepted = found is not None
            # KWS can finish after the name, leaving only the complete command.
            if not accepted and self._keyword_character_id is not None:
                from dock_twoo.brain.catalog import character
                accepted, command = command_after_keyword(text, character(self._keyword_character_id)['name'],strict=True)
        else:
            accepted, command = command_after_keyword(text, self.wake_word)
        if not accepted:
            self.last_wake_decision = "keyword-rejected-by-transcript"
            self.arm_wake()
            return
        template = self._load_speaker_embedding(self.owner_embedding_path)
        self.last_wake_owner_verified = (
            self.models.verify_owner(pcm, template)
            if template and self.models.model_weights_cached(self.models.SPEAKER_MODEL) else False
        )
        if generation is not None and generation != self._capture_generation:
            return
        self.last_completed_transcript = text
        if command:
            self.last_wake_decision = "wake-command-detected"
            self._emit_statement(text, command=command)
        else:
            self.last_wake_decision = "wake-detected"
            self._emit_statement(text, command='', bare=True)

    def _check_wake_word(self, frames: list[bytes], generation: Optional[int] = None, frame_end: Optional[int] = None) -> None:
        """Transcribe ambient utterance to detect wake word ('Brain') or full command."""
        if not self._wake_check_lock.acquire(blocking=False):
            return
        self.last_wake_checks += 1
        self.backup_wake_checks += 1
        try:
            self._check_wake_word_locked(frames, generation, frame_end)
        except Exception as exc:
            self.last_wake_decision = f"wake-check-error: {type(exc).__name__}"
            self.last_error = f"Wake recognition failed: {exc}"
            self.error_occurred.emit(self.last_error)
        finally:
            self._wake_check_lock.release()

    def _check_wake_word_locked(self, frames: list[bytes], generation: Optional[int] = None, frame_end: Optional[int] = None) -> None:
        raw_pcm = b"".join(frames)
        if len(raw_pcm) < 16000 * 2 * 0.18:
            self.last_wake_decision = "segment-too-short"
            return
        clean_pcm = raw_pcm
        text = self._transcribe_pcm(raw_pcm).strip()
        if not text:
            clean_pcm = self.models.enhance_pcm(raw_pcm)
            if clean_pcm != raw_pcm:
                text = self._transcribe_pcm(clean_pcm).strip()
        self._record_voice_check(text, "utterance backup")
        if generation is not None and (generation != self._capture_generation or (not self._wake_armed and not (self.named_characters and not self.is_recording and self._decode_token is None))):
            return
        if not text:
            self.last_wake_decision = "no-transcript"
            return

        from dock_twoo.brain.catalog import named_prefix
        detected_id, _ = named_prefix(text, acoustic=True) if self.named_characters else (None, '')
        wake_phrases = {"brain", "brian", "buddy"}
        if self.named_characters:
            from dock_twoo.brain.catalog import characters
            wake_phrases.update(c['name'].lower() for c in characters())
        configured_wake_word = self.wake_word.strip()
        if configured_wake_word:
            wake_phrases.add(configured_wake_word)
            wake_phrases.add(configured_wake_word.split()[-1])
        phrase_pattern = "|".join(
            re.escape(phrase).replace(r"\ ", r"\s+")
            for phrase in sorted(wake_phrases, key=len, reverse=True)
            if phrase
        )
        greeting_pattern = r"(?:hey|hello|hi|okay|ok|yo|a|eh)(?:\s+there)?[\s,.:;!?…\-–—]+"
        wake_prefix = re.compile(
            rf"(?:^\s*|[.!?]\s+)(?:{greeting_pattern})?(?:{phrase_pattern})\b|\b{greeting_pattern}(?:{phrase_pattern})\b",
            re.IGNORECASE,
        )
        prefix_match = (detected_id is not None) if self.named_characters else wake_prefix.search(text)
        if not prefix_match and not self.named_characters:
            # A greeted wake name is sometimes spelled "grain" by Whisper in
            # noise. Require both the greeting and an actionable following verb
            # for this backup; an arbitrary "green" in ambient speech cannot wake.
            prefix_match = re.search(
                r"^\s*(?:hey|hello|hi)[\s,]+(?:grain|green|plane)[\s,]+(?=(?:open|sing|hum|can|could|what|go|walk|read|please)\b)",
                text, re.I)
        if not prefix_match or (self.named_characters and detected_id is None):
            self.last_wake_decision = "transcript-without-wake-prefix"
            return

        with self._capture_lock:
            if generation is not None and (generation != self._capture_generation or (not self._wake_armed and not (self.named_characters and not self.is_recording and self._decode_token is None))):
                return
            # Preserve the audio that arrived while the backup ASR was decoding.
            following = [(pcm, voiced) for seq, pcm, voiced in self._audio_timeline
                         if frame_end is not None and seq > frame_end]
            self.backup_wake_matches += 1
            self.last_wake_matches += 1
            self._begin_wake_capture(list(frames) + [pcm for pcm, _voiced in following], detected_id)
            # Replay boundaries as well as PCM. The user may have completed the
            # sentence while backup ASR was running; do not wait for them to
            # speak again just to finish an already-buffered statement.
            for pcm, voiced in following:
                self._endpoint.feed(len(pcm) / 32000, voiced)
            if self._endpoint.complete:
                self._dispatch_capture()

    def _process_utterance(self, frames: list[bytes], generation: Optional[int] = None, revision: Optional[int] = None) -> None:
        """Decode the whole statement and reject stale results if speech resumed."""
        raw_pcm = b"".join(frames)
        if generation is not None and generation != self._capture_generation:
            return
        try:
            transcription = self._transcribe_pcm(raw_pcm) if len(raw_pcm) >= 8000 else ""
            if not transcription and len(raw_pcm) >= 8000:
                enhanced = self.models.enhance_pcm(raw_pcm)
                if enhanced != raw_pcm:
                    transcription = self._transcribe_pcm(enhanced)
            if self._accept_capture(generation, revision):
                self.last_completed_transcript = transcription or ""
                self._record_voice_check(transcription, "complete statement")
                self._emit_statement(transcription or "")
        except Exception as exc:
            if self._accept_capture(generation, revision):
                self.last_error = f"Speech recognition failed: {exc}"
                self.error_occurred.emit(self.last_error)
                self.turn_completed.emit("")

    def _transcribe_pcm(self, pcm_data: bytes) -> str:
        """Transcribe 16-bit 16kHz PCM audio buffer using local on-device recognizer with fallback."""
        if not pcm_data or len(pcm_data) < 1600:
            return ""

        # If Whisper's several-hundred-megabyte checkpoint is absent, use authorized
        # macOS on-device recognition immediately instead of waiting on a network fetch.
        if self._sf_recognizer and not self.models.model_weights_cached(self.models.ASR_MODEL):
            recognized = self._transcribe_native_pcm(pcm_data)
            if recognized:
                return recognized

        # The compact transformer runs locally on CPU across supported platforms.
        recognized = self.models.transcribe_pcm(pcm_data)
        if recognized and re.fullmatch(r"\s*\[(?:inaudible|blank_audio|silence|music|noise)\]\s*", recognized, re.I):
            return ""
        if recognized:
            return recognized

        # Native on-device recognition is a fallback if local Whisper is installed.
        if self._sf_recognizer:
            recognized = self._transcribe_native_pcm(pcm_data)
            if recognized:
                return recognized

        # An empty result from the loaded recognizer is not permission to invent
        # a different transcript through a less reliable fallback recognizer.
        if self.models.recognizer.ready:
            return ""

        # 2. Offline fallback: PocketSphinx if installed. Do not send microphone audio
        # to a hosted recognizer when the user selected the local Brain voice pipeline.
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
                return recognizer.recognize_sphinx(audio)
            except Exception:
                pass
        except Exception:
            pass

        return ""

    def _transcribe_native_pcm(self, pcm_data: bytes) -> str:
        """Run the authorized macOS recognizer on-device and clean up its temporary WAV."""
        temp_wav = None
        task = None
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

            request = Speech.SFSpeechURLRecognitionRequest.alloc().initWithURL_(NSURL.fileURLWithPath_(temp_wav))
            if hasattr(request, "setRequiresOnDeviceRecognition_"):
                request.setRequiresOnDeviceRecognition_(True)
            results: list[str] = []
            done = threading.Event()

            def handler(result, error):
                if result:
                    results.append(str(result.bestTranscription().formattedString()))
                    if result.isFinal():
                        done.set()
                if error:
                    done.set()

            task = self._sf_recognizer.recognitionTaskWithRequest_resultHandler_(request, handler)
            done.wait(timeout=3.5)
            if results and results[-1].strip():
                return results[-1].strip()
        except Exception as exc:
            self.last_wake_decision = f"native-speech-error: {type(exc).__name__}"
        finally:
            if task is not None:
                try:
                    task.cancel()
                except Exception:
                    pass
            if temp_wav:
                try:
                    import os
                    os.unlink(temp_wav)
                except OSError:
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
