"""Small CPU speech recognizer for local assistant commands on every supported OS."""

from __future__ import annotations

import threading
import re
from pathlib import Path


class LocalRecognizer:
    MODEL_ID = "csukuangfj/sherpa-onnx-whisper-tiny.en"
    REVISION = "d026532c022fa99fd789d6b32446a1df7b6bfc43"
    ENCODER = "tiny.en-encoder.int8.onnx"
    DECODER = "tiny.en-decoder.int8.onnx"
    TOKENS = "tiny.en-tokens.txt"
    FILES = (ENCODER, DECODER, TOKENS)

    def __init__(self, model_dir: Path | str):
        self.cache_dir = Path(model_dir) / "huggingface" / "hub"
        self.state = "not started"
        self.error = ""
        self._recognizer = None
        self._load_lock = threading.Lock()
        self._inference_lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self._recognizer is not None

    def cached(self) -> bool:
        folder = self.cache_dir / f"models--{self.MODEL_ID.replace('/', '--')}" / "snapshots" / self.REVISION
        return all((folder / name).is_file() and (folder / name).stat().st_size > 0 for name in self.FILES)

    def load(self, allow_download: bool = True) -> bool:
        with self._load_lock:
            if self.ready:
                return True
            try:
                import sherpa_onnx
                from huggingface_hub import snapshot_download
                cached = self.cached()
                self.state = "loading" if cached else "downloading"
                if cached:
                    folder = self.cache_dir / f"models--{self.MODEL_ID.replace('/', '--')}" / "snapshots" / self.REVISION
                else:
                    folder = Path(snapshot_download(
                        self.MODEL_ID, revision=self.REVISION, allow_patterns=list(self.FILES),
                        cache_dir=self.cache_dir, local_files_only=not allow_download, max_workers=3,
                    ))
                self._recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
                    tokens=str(folder / self.TOKENS), encoder=str(folder / self.ENCODER),
                    decoder=str(folder / self.DECODER), language="en", task="transcribe",
                    num_threads=2, decoding_method="greedy_search", provider="cpu",
                )
                self.state, self.error = "ready", ""
                return True
            except Exception as exc:
                self.state, self.error = "error", f"{type(exc).__name__}: {exc}"
                return False

    def transcribe(self, pcm: bytes) -> str:
        if not self.ready or not pcm:
            return ""
        import numpy as np
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        samples -= samples.mean()
        rms = float(np.sqrt(np.mean(samples * samples)))
        samples = np.clip(samples * min(12.0, max(1.0, 0.035 / max(rms, 0.001))), -1.0, 1.0)
        with self._inference_lock:
            # Whisper has a finite context. Decode long statements in overlapping
            # windows, retaining the full statement instead of its first 30 sec.
            transcripts = []
            for offset in range(0, len(samples), 24 * 16000):
                stream = self._recognizer.create_stream()
                stream.accept_waveform(16000, samples[offset:offset + 26 * 16000])
                self._recognizer.decode_stream(stream)
                text = stream.result.text.strip()
                if not text:
                    continue
                words = text.split()
                previous = ' '.join(transcripts).split()
                normalize = lambda word: re.sub(r'\W+', '', word).lower()
                overlap = 0
                for count in range(1, min(40, len(words), len(previous)) + 1):
                    if list(map(normalize, previous[-count:])) == list(map(normalize, words[:count])):
                        overlap = count
                transcripts.append(' '.join(words[overlap:]))
                if offset + 26 * 16000 >= len(samples):
                    break
            return ' '.join(part for part in transcripts if part).strip()
