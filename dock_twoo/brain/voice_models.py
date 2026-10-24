"""Lazy, local Hugging Face speech models used by Brain.

The base runtime uses CPU ONNX Whisper for commands. On Apple Silicon the optional
MLX runtime adds MossFormer2 enhancement and Qwen3-TTS. WavLM speaker verification
is opt-in through voice enrollment.
"""

from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import platform
import tempfile
import threading
import wave
from typing import Optional, Sequence

from dock_twoo.brain.recognition import LocalRecognizer


class LocalVoiceModels:
    ENHANCER_MODEL = "starkdmi/MossFormer2-SE-8bit"
    ASR_MODEL = LocalRecognizer.MODEL_ID
    TTS_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"
    SPEAKER_MODEL = "microsoft/wavlm-base-plus-sv"
    OWNER_THRESHOLD = 0.86

    def __init__(self, model_dir: Path | str):
        self.model_dir = Path(model_dir).expanduser().resolve()
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._enhance_lock = threading.Lock()
        self._asr_lock = threading.Lock()
        self._tts_lock = threading.Lock()
        self._speaker_lock = threading.Lock()
        self._enhancer = None
        self._asr = None
        self.recognizer = LocalRecognizer(self.model_dir)
        self._tts = None
        self._speaker = None
        self._processor = None
        self.errors: dict[str, str] = {}
        self.download_state: dict[str, str] = {"recognizer": "not started", "denoiser": "not started", "tts": "not started"}
        self._download_lock = threading.Lock()
        self._download_threads: dict[str, threading.Thread] = {}
        self._setup_hf_cache()

    def _setup_hf_cache(self) -> None:
        # Hugging Face downloads must trust the system Keychain on managed Macs
        # where traffic is inspected by a corporate CA. This keeps TLS verification on.
        try:
            import truststore
            truststore.inject_into_ssl()
        except ImportError:
            pass
        cache = self.model_dir / "huggingface"
        cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(cache))
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(cache / "hub"))
        # Xet transfers are unreliable behind some managed-network TLS proxies.
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

    def start_model_downloads(self) -> None:
        """Fetch missing wake models in background; never download from the audio callback."""
        if "PYTEST_CURRENT_TEST" in os.environ:
            return
        for component, model_id in (("recognizer", self.ASR_MODEL), ("denoiser", self.ENHANCER_MODEL), ("tts", self.TTS_MODEL)):
            if component != "recognizer" and (platform.system() != "Darwin" or importlib.util.find_spec("mlx_audio") is None):
                continue
            if component == "recognizer" and self.recognizer.ready:
                continue
            if component == "denoiser" and self.model_weights_cached(model_id):
                self.download_state[component] = "ready"
                continue
            if component == "tts" and self._tts is not None:
                continue
            with self._download_lock:
                if component in self._download_threads and self._download_threads[component].is_alive():
                    continue
                thread = threading.Thread(
                    target=self._download_model,
                    args=(component, model_id),
                    name=f"brain-{component}-download",
                    daemon=True,
                )
                self._download_threads[component] = thread
                thread.start()

    def _download_model(self, component: str, model_id: str) -> None:
        self.download_state[component] = "loading" if component == "recognizer" else "queued"
        try:
            if component == "recognizer":
                if not self.recognizer.load():
                    raise RuntimeError(self.recognizer.error)
                self._asr = self.recognizer
            else:
                # Finish the small command recognizer before competing for bandwidth
                # with optional enhancement weights.
                primary = self._download_threads.get("recognizer")
                if primary and primary is not threading.current_thread():
                    primary.join()
                if component == "tts":
                    enhancement = self._download_threads.get("denoiser")
                    if enhancement:
                        enhancement.join()
                from huggingface_hub import snapshot_download
                self.download_state[component] = "downloading"
                folder = self.cached_snapshot(model_id) or Path(snapshot_download(repo_id=model_id, local_files_only=False))
                if component == "tts":
                    self.download_state[component] = "loading"
                    from mlx_audio.tts.utils import load_model
                    with self._lock:
                        self._tts = load_model(str(folder))
            if not self.model_weights_cached(model_id):
                raise RuntimeError("download completed without a model weight file")
            self.download_state[component] = "ready"
            self.errors.pop(component, None)
            if component == "recognizer":
                self.errors.pop("recognizer", None)
        except Exception as exc:
            self.download_state[component] = "failed"
            self.errors[component] = f"unavailable (model download failed: {type(exc).__name__}: {exc})"

    def status(self) -> dict[str, str]:
        def state(component: str, loaded: bool, package: str) -> str:
            if loaded:
                return "ready"
            if component in self.errors:
                return self.errors[component]
            try:
                available = importlib.util.find_spec(package) is not None
            except (ImportError, ValueError):
                available = False
            return "ready to load" if available else "install voice extra"

        return {
            "denoiser": self.download_state["denoiser"] if self.download_state["denoiser"] in ("downloading", "queued") else state("denoiser", self._enhancer is not None, "mlx_audio"),
            "recognizer": self.recognizer.state if self.recognizer.state in ("loading", "downloading") else state("recognizer", self.recognizer.ready, "sherpa_onnx"),
            "tts": self.download_state["tts"] if self.download_state["tts"] in ("downloading", "queued", "loading") else state("tts", self._tts is not None, "mlx_audio"),
            "speaker": state("speaker", self._speaker is not None, "transformers")
            if importlib.util.find_spec("torch") is not None
            else "install voice extra",
        }

    def checkpoint_cached(self, model_id: str, filename: str) -> bool:
        """Return whether a complete checkpoint file exists in the configured HF cache."""
        cache = Path(os.environ.get("HUGGINGFACE_HUB_CACHE", self.model_dir / "huggingface" / "hub"))
        repo_dir = cache / f"models--{model_id.replace('/', '--')}" / "snapshots"
        try:
            return any(path.is_file() and path.stat().st_size > 0 for path in repo_dir.glob(f"*/{filename}"))
        except OSError:
            return False

    def model_weights_cached(self, model_id: str) -> bool:
        """Avoid starting a network download from the real-time microphone thread."""
        if model_id == self.ASR_MODEL:
            return self.recognizer.cached()
        if model_id in (self.TTS_MODEL, self.ENHANCER_MODEL):
            return self.cached_snapshot(model_id) is not None
        cache = Path(os.environ.get("HUGGINGFACE_HUB_CACHE", self.model_dir / "huggingface" / "hub"))
        snapshots = cache / f"models--{model_id.replace('/', '--')}" / "snapshots"
        try:
            return any(
                path.is_file() and not path.name.endswith(".incomplete") and path.stat().st_size > 1024
                for pattern in ("*.safetensors", "*.npz", "*.pt", "*.bin")
                for path in snapshots.glob(f"*/{pattern}")
            )
        except OSError:
            return False

    def cached_snapshot(self, model_id: str) -> Optional[Path]:
        """Resolve a complete snapshot locally, including all TTS tokenizer shards."""
        try:
            from huggingface_hub import snapshot_download
            folder = Path(snapshot_download(
                model_id, local_files_only=True,
                cache_dir=os.environ.get("HUGGINGFACE_HUB_CACHE", str(self.model_dir / "huggingface" / "hub")),
            ))
            return folder
        except Exception:
            return None

    @staticmethod
    def _to_wav(pcm: bytes, rate: int, path: str) -> None:
        with wave.open(path, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            out.writeframes(pcm)

    @staticmethod
    def _resample_pcm(pcm: bytes, source_rate: int, target_rate: int) -> bytes:
        if source_rate == target_rate:
            return pcm
        import numpy as np

        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        if not len(samples):
            return b""
        target_size = max(1, round(len(samples) * target_rate / source_rate))
        old_x = np.arange(len(samples), dtype=np.float32)
        new_x = np.linspace(0, max(0, len(samples) - 1), target_size, dtype=np.float32)
        resampled = np.interp(new_x, old_x, samples)
        return np.clip(resampled, -32768, 32767).astype("<i2").tobytes()

    def _get_enhancer(self):
        if self._enhancer is None:
            with self._lock:
                if self._enhancer is None:
                    from mlx_audio.sts.models.mossformer2_se import MossFormer2SEModel
                    folder = self.cached_snapshot(self.ENHANCER_MODEL)
                    if folder is None:
                        raise RuntimeError("Enhancement checkpoint is not cached")
                    self._enhancer = MossFormer2SEModel.from_pretrained(str(folder))
        return self._enhancer

    def enhance_pcm(self, pcm: bytes, sample_rate: int = 16000) -> bytes:
        """Run MossFormer2 speech enhancement on a buffered utterance."""
        if platform.system() != "Darwin" or not pcm or "PYTEST_CURRENT_TEST" in os.environ:
            return pcm
        if "denoiser" in self.errors:
            return pcm
        # Never let a first-time model download block wake-word detection. Enhancement
        # is a best-effort stage; use the raw audio until the local checkpoint exists.
        if not self.model_weights_cached(self.ENHANCER_MODEL):
            return pcm
        try:
            model = self._get_enhancer()
            import numpy as np
            pcm48 = self._resample_pcm(pcm, sample_rate, 48000)
            with self._enhance_lock:
                enhanced = np.asarray(model.enhance(np.frombuffer(pcm48, dtype="<i2").astype(np.float32) / 32768.0)).reshape(-1)
            if not len(enhanced) or not np.isfinite(enhanced).all():
                raise RuntimeError("Enhancer returned invalid audio")
            clean_pcm = (np.clip(enhanced, -1.0, 1.0) * 32767).astype("<i2").tobytes()
            result = self._resample_pcm(clean_pcm, 48000, sample_rate)
            # STFT synthesis can omit the final partial hop. Preserve utterance
            # duration so capture boundaries and owner verification remain aligned.
            return result[:len(pcm)].ljust(len(pcm), b"\x00")
        except Exception as exc:
            self.errors["denoiser"] = f"unavailable ({exc})"
            return pcm

    def _get_asr(self):
        if self._asr is None:
            with self._lock:
                if self._asr is None:
                    if not self.recognizer.load(allow_download=False):
                        raise RuntimeError(self.recognizer.error)
                    self._asr = self.recognizer
        return self._asr

    def transcribe_pcm(self, pcm: bytes, sample_rate: int = 16000) -> str:
        """Transcribe locally with the quantized Whisper English command recognizer."""
        if not pcm or "PYTEST_CURRENT_TEST" in os.environ:
            return ""
        # Missing assets never start downloads from an utterance or wake worker.
        if not self.model_weights_cached(self.ASR_MODEL):
            self.errors["recognizer"] = "unavailable (speech checkpoint is not downloaded)"
            return ""
        if self.errors.get("recognizer") == "unavailable (speech checkpoint is not downloaded)":
            self.errors.pop("recognizer", None)
        try:
            asr = self._get_asr()
            with self._asr_lock:
                text = asr.transcribe(self._resample_pcm(pcm, sample_rate, 16000))
            self.errors.pop("recognizer", None)
            return text
        except Exception as exc:
            self.errors["recognizer"] = f"unavailable ({exc})"
            return ""

    def synthesize_wav(self, message: str, path: Path | str, speaker: str = "Ryan") -> bool:
        """Try expressive local Qwen3-TTS; caller can fall back to OS speech."""
        if "PYTEST_CURRENT_TEST" in os.environ:
            return False
        if "tts" in self.errors:
            return False
        # A first greeting must never wait for a multi-gigabyte TTS download.
        if self._tts is None:
            return False
        try:
            with self._tts_lock:
                results = self._tts.generate_custom_voice(
                    text=message,
                    speaker=speaker,
                    language="English",
                    instruct="Warm, natural, clear and conversational, with gentle expression.",
                    max_tokens=min(1200, max(120, len(message) * 2)),
                )
                result = next(iter(results), None)
            if result is None:
                raise RuntimeError("Qwen3-TTS returned no audio")
            import numpy as np
            audio = np.asarray(result.audio, dtype=np.float32).reshape(-1)
            sample_rate = int(getattr(result, "sample_rate", 24000))
            pcm = np.clip(audio, -1.0, 1.0)
            pcm = (pcm * 32767.0).astype("<i2").tobytes()
            self._to_wav(pcm, sample_rate, str(path))
            return True
        except Exception as exc:
            self.errors["tts"] = f"unavailable ({exc})"
            return False

    def speaker_embedding(self, pcm: bytes, sample_rate: int = 16000) -> Optional[list[float]]:
        """Extract a WavLM x-vector from a voice sample; audio never leaves this device."""
        if not pcm or "PYTEST_CURRENT_TEST" in os.environ:
            return None
        if "speaker" in self.errors:
            return None
        try:
            import numpy as np
            import torch
            from transformers import AutoModelForAudioXVector, AutoProcessor

            if self._speaker is None:
                with self._lock:
                    if self._speaker is None:
                        self._processor = AutoProcessor.from_pretrained(self.SPEAKER_MODEL)
                        self._speaker = AutoModelForAudioXVector.from_pretrained(self.SPEAKER_MODEL)
                        self._speaker.eval()
            signal = np.frombuffer(self._resample_pcm(pcm, sample_rate, 16000), dtype="<i2").astype(np.float32) / 32768.0
            # Wake names can be shorter than WavLM's useful speaker window; repeat the
            # observed crop only to reach one second. A borderline score remains "unknown".
            if 0 < len(signal) < 16000:
                repeats = int(np.ceil(16000 / len(signal)))
                signal = np.tile(signal, repeats)[:16000]
            # Enrollment is chunked so the template averages several phonetic contexts.
            chunk = 16000 * 3
            pieces = [signal[i : i + chunk] for i in range(0, len(signal), chunk) if len(signal[i : i + chunk]) >= 16000]
            if not pieces:
                return None
            embeddings = []
            with self._speaker_lock, torch.inference_mode():
                for piece in pieces:
                    inputs = self._processor(piece, sampling_rate=16000, return_tensors="pt", padding=True)
                    output = self._speaker(**inputs).embeddings
                    embeddings.append(torch.nn.functional.normalize(output, dim=-1)[0])
            mean = torch.stack(embeddings).mean(dim=0)
            return torch.nn.functional.normalize(mean, dim=0).cpu().tolist()
        except Exception as exc:
            self.errors["speaker"] = f"unavailable ({exc})"
            return None

    def verify_owner(self, pcm: bytes, template: Sequence[float], sample_rate: int = 16000) -> Optional[bool]:
        embedding = self.speaker_embedding(pcm, sample_rate)
        if embedding is None or not template or len(embedding) != len(template):
            return None
        similarity = sum(float(a) * float(b) for a, b in zip(embedding, template))
        return similarity >= self.OWNER_THRESHOLD


def save_embedding(path: Path | str, embedding: Sequence[float]) -> None:
    """Persist only the derived local speaker vector, never the enrollment recording."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps([float(value) for value in embedding]), encoding="utf-8")
    temporary.replace(target)
    try:
        target.chmod(0o600)
    except OSError:
        pass


def load_embedding(path: Path | str) -> Optional[list[float]]:
    try:
        values = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(values, list) and values and all(isinstance(x, (int, float)) for x in values):
            return [float(value) for value in values]
    except (OSError, ValueError, TypeError):
        pass
    return None
