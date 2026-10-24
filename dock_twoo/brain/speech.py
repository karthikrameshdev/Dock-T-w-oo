"""Speech playback coordinator with frame-by-frame mouth sync for robot mascot."""

from __future__ import annotations

import os
from pathlib import Path
import platform
import subprocess
import tempfile
import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot, QTimer
from dock_twoo.brain.audio import SpeechClip, synthesize, whistle_clip


class SpeechPlayback(QObject):
    """Coordinates text-to-speech synthesis and smooth mouth-synchronized audio playback."""

    activity = Signal(str)      # "thinking", "speaking", "idle", etc.
    mouth = Signal(float)       # 0.0 to 1.0 mouth aperture level
    failed = Signal(str)
    finished = Signal()
    _frame = Signal(int, float, float)  # token, level, deadline
    _done = Signal(int, str)            # token, error

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.generation: int = 0
        self.cancel_event: Optional[threading.Event] = None
        self.worker: Optional[threading.Thread] = None
        self.playing: bool = False
        self.last_error: str = ""
        self.voice_models = None

        self._frame.connect(self._schedule_frame)
        self._done.connect(self._finish)

    def start(self, text: str) -> None:
        """Start speech synthesis and playback of text."""
        self._start(text[:1000])

    def whistle(self) -> None:
        """Play robot whistle clip."""
        self._start(None)

    def _start(self, text: Optional[str]) -> None:
        self.stop()
        self.last_error = ""
        token = self.generation
        cancel = self.cancel_event = threading.Event()
        self.activity.emit("thinking")
        self.worker = threading.Thread(
            target=self._play_worker,
            args=(token, text, cancel),
            daemon=True,
            name="brain-speech",
        )
        self.worker.start()

    def stop(self) -> None:
        """Stop current speech immediately."""
        self.generation += 1
        if self.cancel_event:
            self.cancel_event.set()
        self.playing = False
        self.mouth.emit(0.0)
        self.activity.emit("idle")

    def _play_worker(self, token: int, text: Optional[str], cancel: threading.Event) -> None:
        error = ""
        try:
            with tempfile.TemporaryDirectory(prefix="dock-twoo-brain-speech-") as folder:
                wav_path = Path(folder) / "speech.wav"
                if text is None:
                    clip = whistle_clip()
                else:
                    clip = synthesize(text, wav_path, cancel, self.voice_models)

                if cancel.is_set():
                    raise InterruptedError("Speech cancelled.")

                self._play_clip(clip, wav_path, token, cancel)
        except InterruptedError:
            pass
        except Exception as exc:
            error = f"Speech output failed: {exc}"
        finally:
            self._done.emit(token, error)

    def _play_clip(self, clip: SpeechClip, wav_path: Path, token: int, cancel: threading.Event) -> None:
        # Try sounddevice if installed
        try:
            import sounddevice as sd
            cursor = 0
            finished = threading.Event()
            frame_bytes = 2 * clip.channels

            def output_cb(buffer, frames, clock, status):
                nonlocal cursor
                if cancel.is_set():
                    raise sd.CallbackAbort
                end = min(cursor + frames, clip.frames)
                data = clip.pcm[cursor * frame_bytes : end * frame_bytes]
                buffer[:] = data + bytes(frames * frame_bytes - len(data))
                delay = max(0.0, clock.outputBufferDacTime - clock.currentTime)
                self._frame.emit(token, clip.level_at(cursor), time.monotonic() + delay)
                cursor = end
                if cursor >= clip.frames:
                    raise sd.CallbackStop

            with sd.RawOutputStream(
                samplerate=clip.rate,
                channels=clip.channels,
                dtype="int16",
                blocksize=clip.window_frames,
                callback=output_cb,
                finished_callback=finished.set,
            ):
                deadline = time.monotonic() + clip.duration + 4.0
                while not finished.wait(0.04):
                    if cancel.is_set():
                        raise InterruptedError("Speech cancelled.")
                    if time.monotonic() > deadline:
                        break
            return
        except InterruptedError:
            raise
        except Exception as exc:
            playback_error = exc

        # Native macOS afplay fallback or subprocess fallback
        if platform.system().lower() == "darwin" and wav_path.exists():
            proc = subprocess.Popen(["afplay", str(wav_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            start_t = time.monotonic()
            while proc.poll() is None:
                if cancel.is_set():
                    proc.terminate()
                    raise InterruptedError("Speech cancelled.")
                elapsed = time.monotonic() - start_t
                curr_frame = int(elapsed * clip.rate)
                self._frame.emit(token, clip.level_at(curr_frame), time.monotonic() + 0.02)
                time.sleep(0.03)
            if proc.returncode != 0:
                raise RuntimeError(f"afplay exited with status {proc.returncode}")
            return

        raise RuntimeError(f"No working audio output device: {playback_error}")

    @Slot(int, float, float)
    def _schedule_frame(self, token: int, level: float, deadline: float) -> None:
        if token == self.generation:
            delay = max(0, min(2000, round((deadline - time.monotonic()) * 1000)))
            QTimer.singleShot(delay, self, lambda: self._publish(token, level))

    def _publish(self, token: int, level: float) -> None:
        if token != self.generation:
            return
        if not self.playing:
            self.playing = True
            self.activity.emit("speaking")
        self.mouth.emit(level)

    @Slot(int, str)
    def _finish(self, token: int, error: str) -> None:
        if token != self.generation:
            return
        self.generation += 1
        self.playing = False
        self.mouth.emit(0.0)
        self.activity.emit("idle")
        if error:
            self.failed.emit(error)
        self.finished.emit()
