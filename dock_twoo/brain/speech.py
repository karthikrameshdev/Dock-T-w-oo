"""Speech playback coordinator with frame-by-frame mouth sync for robot mascot."""

from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot, QTimer
from dock_twoo.brain.audio import SpeechClip, synthesize, synthesize_song, whistle_clip


class SpeechPlayback(QObject):
    """Coordinates text-to-speech synthesis and smooth mouth-synchronized audio playback."""

    activity = Signal(str)      # "thinking", "speaking", "idle", etc.
    mouth = Signal(float)       # 0.0 to 1.0 mouth aperture level
    failed = Signal(str)
    finished = Signal()
    progress = Signal(float)
    _frame = Signal(int, float, float)  # token, level, deadline
    _done = Signal(int, str)            # token, error

    def __init__(self, parent: Optional[QObject] = None, *, audio_devices=None):
        super().__init__(parent)
        self.generation: int = 0
        self.cancel_event: Optional[threading.Event] = None
        self.worker: Optional[threading.Thread] = None
        self.playing: bool = False
        self.last_error: str = ""
        from dock_twoo.brain.audio_devices import DefaultAudioDevices
        self.audio_devices = audio_devices or DefaultAudioDevices(self)
        self.voice_models = None
        self.echo_guard = None
        self.store = None
        self._progress_offset = 0.
        self._progress_scale = 1.

        self._frame.connect(self._schedule_frame)
        self._done.connect(self._finish)

    def start(self, text: str) -> None:
        """Start speech synthesis and playback of text."""
        self._start(text)

    def sing(self, lyrics: str) -> None:
        self._start(lyrics, song=True)

    def whistle(self) -> None:
        """Play robot whistle clip."""
        self._start(None)

    def sound(self, character_id):
        self._start(None,sound_id=character_id)

    def _start(self, text: Optional[str], *, song=False, sound_id=None) -> None:
        self.stop()
        self.last_error = ""
        token = self.generation
        cancel = self.cancel_event = threading.Event()
        self.activity.emit("thinking")
        from dock_twoo.brain.ecosystem.voices import tuning
        owner=getattr(self.parent(),'companion',None)
        character_id=sound_id or getattr(owner,'character_id','default')
        voice_settings=tuning(self.store,character_id) if self.store else None
        self.worker = threading.Thread(
            target=self._play_worker,
            args=(token, text, cancel, song, voice_settings, sound_id),
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
        self.progress.emit(0.0)
        self.activity.emit("idle")

    def _play_worker(self, token: int, text: Optional[str], cancel: threading.Event, song=False, voice_settings=None, sound_id=None) -> None:
        error = ""
        try:
            with tempfile.TemporaryDirectory(prefix="dock-twoo-brain-speech-") as folder:
                wav_path = Path(folder) / "speech.wav"
                if sound_id is not None:
                    from dock_twoo.brain.ecosystem.voices import species_sound
                    self._progress_offset,self._progress_scale=0.,1.
                    self._play_clip(species_sound(sound_id),wav_path,token,cancel)
                elif song or text is None:
                    clip = synthesize_song(text, wav_path, cancel, self.voice_models, voice_settings) if song else whistle_clip()
                    self._progress_offset,self._progress_scale=0.,1.
                    self._play_clip(clip, wav_path, token, cancel)
                else:
                    from concurrent.futures import ThreadPoolExecutor
                    from dock_twoo.brain.desktop_reader import speech_chunks
                    from dock_twoo.brain.local_tts import get_local_tts,VOICES
                    engine=get_local_tts()
                    if self.store:
                        requested=(voice_settings or {}).get('voice',self.store.setting('voice_name','af_heart'))
                        engine.voice=requested if requested in VOICES else 'af_heart'
                        engine.speed=float((voice_settings or {}).get('speed',self.store.setting('speech_rate',1)))/float((voice_settings or {}).get('pitch',1))
                    chunks=speech_chunks(text,limit=320)
                    total=max(1,sum(len(chunk) for chunk in chunks));offset=0
                    def render(index):
                        path=Path(folder)/f'phrase-{index}.wav'
                        clip=synthesize(chunks[index],path,cancel,self.voice_models,voice_settings)
                        pitch=float((voice_settings or {}).get('pitch',1))
                        if abs(pitch-1)>.001:
                            clip=SpeechClip.from_pcm(clip.pcm,round(clip.rate*pitch),clip.channels)
                        return clip,path
                    with ThreadPoolExecutor(max_workers=1,thread_name_prefix='brain-phrase-prefetch') as pool:
                        pending=pool.submit(render,0) if chunks else None
                        for index,chunk in enumerate(chunks):
                            if cancel.is_set():raise InterruptedError('Speech cancelled.')
                            clip,path=pending.result(timeout=35)
                            if index+1<len(chunks):pending=pool.submit(render,index+1)
                            self._progress_offset,self._progress_scale=offset/total,len(chunk)/total
                            self._play_clip(clip,path,token,cancel);offset+=len(chunk)

        except InterruptedError:
            pass
        except Exception as exc:
            error = f"Speech output failed: {exc}"
        finally:
            try:
                self._done.emit(token, error)
            except RuntimeError:
                pass  # The owner was closed while its cancelled worker finished.

    def _play_clip(self, clip: SpeechClip, wav_path: Path, token: int, cancel: threading.Event) -> None:
        if self.echo_guard and token == self.generation:
            self.echo_guard.begin(clip.pcm, clip.rate, clip.channels, token)
        def frame(cursor):
            if token == self.generation and not cancel.is_set():
                self._frame.emit(token, clip.level_at(cursor), time.monotonic())
                self.progress.emit(self._progress_offset+self._progress_scale*cursor/max(1, clip.frames))

        def align(started):
            if self.echo_guard and token == self.generation:
                self.echo_guard.align(token, started)

        self.audio_devices.play(clip, cancel, frame, align)

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
        self.last_error = error
        self.mouth.emit(0.0)
        self.activity.emit("idle")
        if error:
            self.failed.emit(error)
        self.finished.emit()
