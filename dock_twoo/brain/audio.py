"""Local speech synthesis, WAV audio parsing, and PCM level envelopes for robot mouth sync."""

from __future__ import annotations

from array import array
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading
import time
import wave
from typing import Optional


@dataclass(frozen=True)
class SpeechClip:
    pcm: bytes
    rate: int
    channels: int
    levels: tuple[float, ...]
    window_frames: int

    @property
    def frames(self) -> int:
        return len(self.pcm) // (2 * self.channels)

    @property
    def duration(self) -> float:
        return self.frames / self.rate

    def level_at(self, frame: int) -> float:
        if frame < 0 or frame >= self.frames or not self.levels:
            return 0.0
        idx = min(frame // self.window_frames, len(self.levels) - 1)
        return self.levels[idx]

    @classmethod
    def read(cls, path: Path | str) -> SpeechClip:
        with wave.open(str(path), "rb") as source:
            rate = source.getframerate()
            channels = source.getnchannels()
            if (
                source.getsampwidth() != 2
                or channels not in (1, 2)
                or not 8000 <= rate <= 96000
                or source.getcomptype() != "NONE"
            ):
                raise ValueError("Speech must be 16-bit PCM, mono or stereo.")
            pcm = source.readframes(source.getnframes())
        return cls.from_pcm(pcm, rate, channels)

    @classmethod
    def from_pcm(cls, pcm: bytes, rate: int, channels: int = 1) -> SpeechClip:
        if channels not in (1, 2) or not 8000 <= rate <= 96000 or len(pcm) % (2 * channels):
            raise ValueError("Invalid 16-bit PCM audio payload.")
        samples = array("h")
        samples.frombytes(pcm)
        if sys.byteorder != "little":
            samples.byteswap()

        window = max(1, round(rate * 0.02))
        energies = []
        for offset in range(0, len(samples), window * channels):
            values = samples[offset : offset + window * channels]
            if values:
                rms = math.sqrt(sum(float(x) ** 2 for x in values) / len(values)) / 32768.0
                energies.append(rms)
            else:
                energies.append(0.0)

        peak = max(max(energies, default=0.02), 0.02)
        levels = tuple(0.0 if x < 0.003 else min(1.0, x / peak) for x in energies)
        return cls(pcm, rate, channels, levels, window)


def whistle_clip() -> SpeechClip:
    """A gentle robot whistle for quick sound feedback."""
    import struct

    rate = 22050
    values = []
    for frequency in (1000, 1250):
        frames = round(rate * 0.25)
        for i in range(frames):
            fade = min(1.0, i / (rate * 0.03), (frames - i - 1) / (rate * 0.03))
            values.append(
                round(2800 * fade * math.sin(math.tau * frequency * i / rate))
            )
        values.extend([0] * round(rate * 0.06))
    return SpeechClip.from_pcm(struct.pack("<" + "h" * len(values), *values), rate)


def synthesize(
    message: str,
    path: Path | str,
    cancel: Optional[threading.Event] = None,
    voice_models=None,
) -> SpeechClip:
    """Synthesize text to speech into a WAV file using native platform capabilities."""
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Speech message cannot be empty.")
    clean_msg = message.strip()[:1000]
    cancel = cancel or threading.Event()
    if cancel.is_set():
        raise InterruptedError("Speech cancelled.")

    system = platform.system().lower()
    path_obj = Path(path).resolve()
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    if voice_models is not None and system_is_macos():
        if voice_models.synthesize_wav(clean_msg, path_obj, cancel=cancel):
            if cancel.is_set():
                raise InterruptedError("Speech cancelled.")
            return SpeechClip.read(path_obj)

    if system == "darwin":
        args = [
            "say",
            "-o",
            str(path_obj),
            "--file-format=WAVE",
            "--data-format=LEI16@22050",
            "--",
            clean_msg,
        ]
        payload = None
    elif system == "windows":
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$d=[Console]::In.ReadToEnd()|ConvertFrom-Json; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "try{$s.SetOutputToWaveFile($d.path);$s.Speak($d.text)}finally{$s.Dispose()}"
        )
        args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
        payload = json.dumps({"path": str(path_obj), "text": clean_msg}).encode("ascii")
    else:
        # Linux fallback
        engine = shutil.which("espeak-ng") or shutil.which("espeak")
        if engine:
            args = [engine, "-w", str(path_obj), "--", clean_msg]
            payload = None
        else:
            raise RuntimeError("Local speech engine unavailable on this Linux system.")

    process = subprocess.Popen(
        args,
        stdin=subprocess.PIPE if payload else subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    deadline = time.monotonic() + 30.0
    while True:
        if cancel.is_set():
            process.terminate()
            raise InterruptedError("Speech cancelled.")
        if time.monotonic() > deadline:
            process.terminate()
            raise RuntimeError("Speech synthesis timed out.")
        try:
            _, stderr = process.communicate(input=payload, timeout=0.1)
            break
        except subprocess.TimeoutExpired:
            payload = None

    if cancel.is_set():
        raise InterruptedError("Speech cancelled.")

    if not path_obj.exists() or path_obj.stat().st_size == 0:
        raise RuntimeError("Failed to generate speech audio output.")

    return SpeechClip.read(path_obj)


def system_is_macos() -> bool:
    return platform.system().lower() == "darwin"


def synthesize_song(lyrics: str, path: Path | str, cancel: threading.Event) -> SpeechClip:
    """Sing original lyrics with the installed macOS melodic novelty voice."""
    if platform.system().lower() != 'darwin':
        raise RuntimeError('The local singing voice is currently available on macOS only.')
    path = Path(path)
    process = subprocess.Popen(['say','-v','Good News','-o',str(path),
        '--file-format=WAVE','--data-format=LEI16@22050','--',lyrics],
        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    deadline=time.monotonic()+20
    while process.poll() is None:
        if cancel.is_set() or time.monotonic()>deadline:
            process.terminate()
            raise InterruptedError('Song cancelled or timed out')
        time.sleep(.025)
    if process.returncode:
        raise RuntimeError('The macOS singing voice is not available on this computer.')
    return SpeechClip.read(path)
