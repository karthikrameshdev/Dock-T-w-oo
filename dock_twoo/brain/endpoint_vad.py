"""Streaming neural speech boundaries; no audio is saved or sent to a service."""
from __future__ import annotations

import hashlib
from pathlib import Path
import threading
import urllib.request


class NeuralEndpointVad:
    URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx'
    SHA256 = '9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6'

    def __init__(self, model_dir):
        self.path = Path(model_dir) / 'vad/silero_vad.onnx'
        self.model = None
        self.error = ''
        self.pending = None
        self.voiced_windows = 0
        self.windows = 0
        self._lock = threading.RLock()

    @property
    def ready(self):
        return self.model is not None

    def start(self):
        threading.Thread(target=self.load, daemon=True, name='brain-endpoint-vad').start()

    def load(self, allow_download=True):
        try:
            if not self.path.exists():
                if not allow_download:
                    return False
                import truststore
                truststore.inject_into_ssl()
                with urllib.request.urlopen(self.URL, timeout=20) as response:
                    data = response.read(4 * 1024 * 1024)
                if hashlib.sha256(data).hexdigest() != self.SHA256:
                    raise RuntimeError('Speech boundary model checksum does not match')
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix('.download')
                temporary.write_bytes(data)
                temporary.replace(self.path)
            if hashlib.sha256(self.path.read_bytes()).hexdigest() != self.SHA256:
                raise RuntimeError('Speech boundary checkpoint is corrupted')
            import sherpa_onnx
            config = sherpa_onnx.VadModelConfig()
            config.silero_vad.model = str(self.path)
            config.silero_vad.threshold = .5
            config.silero_vad.window_size = 512
            config.sample_rate = 16000
            config.num_threads = 1
            config.provider = 'cpu'
            model = sherpa_onnx.VadModel.create(config)
            with self._lock:
                self.model = model
                self.error = ''
                self.pending = None
            return True
        except Exception as exc:
            self.error = str(exc)
            return False

    def reset(self):
        with self._lock:
            self.pending = None
            if self.model:
                self.model.reset()

    def feed(self, pcm):
        import numpy as np
        with self._lock:
            samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768
            samples -= samples.mean() if len(samples) else 0
            rms = float(np.sqrt(np.mean(samples*samples))) if len(samples) else 0
            # Quiet speech is amplified for the classifier only. The original
            # PCM remains intact for ASR; neural classification rejects hiss.
            samples *= min(8., .025 / max(rms, .00001))
            self.pending = samples if self.pending is None else np.concatenate((self.pending, samples))
            votes = []
            while len(self.pending) >= 512:
                voiced = bool(self.model.is_speech(self.pending[:512]))
                votes.append(voiced)
                self.windows += 1
                self.voiced_windows += voiced
                self.pending = self.pending[512:]
            return any(votes)

    def status(self):
        return {'engine': 'Silero VAD (local CPU)', 'ready': self.ready,
                'error': self.error, 'windows': self.windows, 'speech_windows': self.voiced_windows}
