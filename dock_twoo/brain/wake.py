"""Streaming, local keyword spotting independent of dictation and speech output models."""

from __future__ import annotations

import re
import threading
from pathlib import Path


class WakeDetector:
    """Run the 3.3M parameter Zipformer on every audio frame, before any VAD gate.

    Model layout and API follow k2-fsa's sherpa-onnx keyword spotting examples.
    The Hugging Face mirror is pinned so a future repository update cannot change
    the model loaded by an existing installation.
    """

    MODEL_ID = "mobilebytesensei/sherpa-onnx-kws-zipformer-gigaspeech-3.3M"
    REVISION = "e8ca74a794ce66e38a100e7c60c0214189ff4100"
    ENCODER = "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"
    DECODER = "decoder-epoch-12-avg-2-chunk-16-left-64.onnx"
    JOINER = "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"
    FILES = (ENCODER, DECODER, JOINER, "tokens.txt", "bpe.model")

    def __init__(self, model_dir: Path | str, wake_word: str = "brain", *, keywords=None):
        self.model_dir = Path(model_dir)
        self.cache_dir = self.model_dir / "huggingface" / "hub"
        self.wake_word = wake_word
        self.keywords = tuple(keywords) if keywords else None
        self.names = ()
        self.state = "not started"
        self.error = ""
        self.frames = 0
        self.last_keyword = ""
        self._spotter = None
        self._stream = None
        self._bpe = None
        self._gain = 1.0
        self._lock = threading.RLock()
        self._worker: threading.Thread | None = None

    @property
    def ready(self) -> bool:
        return self.state == "ready" and self._spotter is not None

    def start(self) -> None:
        if self.ready or (self._worker and self._worker.is_alive()):
            return
        self.state = "loading"
        self._worker = threading.Thread(target=self.load, name="brain-wake-model", daemon=True)
        self._worker.start()

    def load(self, allow_download: bool = True) -> bool:
        """Initialize outside the audio thread. Offline verification can forbid downloads."""
        self.error = ""
        try:
            import sentencepiece
            import sherpa_onnx
            from huggingface_hub import snapshot_download

            self.state = "loading"
            try:
                folder = Path(snapshot_download(
                    self.MODEL_ID, revision=self.REVISION, cache_dir=self.cache_dir,
                    local_files_only=True, allow_patterns=list(self.FILES),
                ))
                if not all((folder / name).is_file() for name in self.FILES):
                    raise FileNotFoundError("Wake checkpoint is incomplete")
            except (FileNotFoundError, OSError):
                if not allow_download:
                    raise
                self.state = "downloading"
                folder = Path(snapshot_download(
                    self.MODEL_ID, revision=self.REVISION, cache_dir=self.cache_dir,
                    allow_patterns=list(self.FILES), max_workers=3,
                ))
            bpe = sentencepiece.SentencePieceProcessor(model_file=str(folder / "bpe.model"))
            # The required base list is never empty. Stream-specific custom names
            # are added with create_stream(), without reloading the neural network.
            keywords_path = self.model_dir / ("stop-keywords.txt" if self.keywords else "wake-keywords.txt")
            keywords_path.parent.mkdir(parents=True, exist_ok=True)
            keywords_path.write_text("\n".join(
                " ".join(bpe.encode(word, out_type=str)) + " @" + word.replace(' ', '_')
                for word in (self.keywords or ("BRAIN", "BUDDY"))
            ) + "\n", encoding="utf-8")
            spotter = sherpa_onnx.KeywordSpotter(
                tokens=str(folder / "tokens.txt"), encoder=str(folder / self.ENCODER),
                decoder=str(folder / self.DECODER), joiner=str(folder / self.JOINER),
                keywords_file=str(keywords_path), num_threads=1, provider="cpu",
                keywords_score=1.0, keywords_threshold=.45 if self.keywords else .25, num_trailing_blanks=1,
            )
            with self._lock:
                self._spotter, self._bpe = spotter, bpe
                self._new_stream()
                self.state = "ready"
            return True
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.state = "error"
            return False

    def _new_stream(self) -> None:
        phrase = re.sub(r"^(?:hey|hello|hi|okay|ok|yo)\s+", "", self.wake_word.strip(), flags=re.I).upper()
        if self.names and not self.keywords:
            # sherpa's stream API separates multiple inline keywords with '/'.
            entries = []
            for name in self.names:
                if name.upper() in ('BRAIN', 'BUDDY'):
                    continue
                variants = {'MOCHI': ('MO CHI','MO CHAI','MO CHEE'), 'ZURI': ('ZOO REE','SURI')}
                for phrase in (name.upper(), *variants.get(name.upper(), ())):
                    entries.append(" ".join(self._bpe.encode(phrase, out_type=str)) + " :2.0 #0.15 @" + name.upper().replace(' ', '_'))
            self._stream = self._spotter.create_stream('/'.join(entries))
        elif not self.keywords and phrase and phrase not in ("BRAIN", "BUDDY"):
            tokens = " ".join(self._bpe.encode(phrase, out_type=str))
            self._stream = self._spotter.create_stream(f"{tokens} @{phrase.replace(' ', '_')}")
        else:
            self._stream = self._spotter.create_stream()
        self._gain = 1.0

    def configure(self, wake_word: str) -> None:
        with self._lock:
            self.wake_word = wake_word
            if self.ready:
                self._new_stream()

    def configure_names(self, names):
        with self._lock:
            self.names = tuple(dict.fromkeys(names))
            if self.ready:
                self._new_stream()

    def reset(self) -> None:
        with self._lock:
            if self.ready:
                self._new_stream()

    def feed(self, pcm: bytes) -> str:
        """Consume 16 kHz mono int16 audio. This method performs no I/O or downloads."""
        if not self.ready or not pcm:
            return ""
        import numpy as np

        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        samples -= samples.mean()
        rms = float(np.sqrt(np.mean(samples * samples)))
        # Bounded, smoothed gain keeps a quiet call audible without clipping normal
        # speech. Noise still has to match the neural keyword probability threshold.
        target_gain = min(12.0, max(1.0, 0.035 / max(rms, 0.001)))
        self._gain = 0.7 * self._gain + 0.3 * target_gain
        samples = np.clip(samples * self._gain, -1.0, 1.0)
        with self._lock:
            self._stream.accept_waveform(16000, samples)
            self.frames += 1
            while self._spotter.is_ready(self._stream):
                self._spotter.decode_stream(self._stream)
                keyword = self._spotter.get_result(self._stream)
                if keyword:
                    self.last_keyword = keyword
                    self._spotter.reset_stream(self._stream)
                    return keyword
        return ""

    def status(self) -> dict[str, object]:
        return {"engine": "Zipformer", "state": self.state, "ready": self.ready,
                "error": self.error, "audio_frames": self.frames, "last_keyword": self.last_keyword}
