"""Small local GTCRN ONNX enhancer; downloads only from a background loader."""
from pathlib import Path
import hashlib
import threading
import urllib.request

MODEL_URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speech-enhancement-models/gtcrn_simple.onnx'
MODEL_SHA256 = 'e77603ac0c23dac3227dd2d7135b3a585cbee2679048aecfa886657d3ae1b534'


class LocalDenoiser:
    def __init__(self, model_dir):
        self.path = Path(model_dir) / 'gtcrn' / 'gtcrn_simple.onnx'
        self.engine = None
        self.state = 'not started'
        self.error = ''
        self.lock = threading.Lock()

    def cached(self):
        return self.path.is_file() and hashlib.sha256(self.path.read_bytes()).hexdigest() == MODEL_SHA256

    def load(self, allow_download=True):
        with self.lock:
            if self.engine is not None:
                return True
            try:
                self.state = 'preparing'
                if not self.cached():
                    if not allow_download:
                        raise RuntimeError('The local ONNX denoiser is not cached.')
                    self.state = 'downloading'
                    with urllib.request.urlopen(MODEL_URL, timeout=30) as response:
                        data = response.read(2 * 1024 * 1024)
                    if hashlib.sha256(data).hexdigest() != MODEL_SHA256:
                        raise RuntimeError('The denoiser download failed its integrity check.')
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = self.path.with_suffix('.tmp')
                    temporary.write_bytes(data)
                    temporary.replace(self.path)
                import sherpa_onnx as sherpa
                config = sherpa.OfflineSpeechDenoiserConfig(model=sherpa.OfflineSpeechDenoiserModelConfig(
                    gtcrn=sherpa.OfflineSpeechDenoiserGtcrnModelConfig(model=str(self.path)),
                    num_threads=1, provider='cpu'))
                if not config.validate():
                    raise RuntimeError('Invalid local denoiser model configuration.')
                self.engine = sherpa.OfflineSpeechDenoiser(config)
                self.state, self.error = 'ready', ''
                return True
            except Exception as exc:
                self.state, self.error = 'unavailable', str(exc)
                return False

    def enhance(self, pcm, rate):
        if self.engine is None:
            return pcm
        import numpy as np
        with self.lock:
            result = self.engine(np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768., rate)
        samples = np.asarray(result.samples)
        if not len(samples) or not np.isfinite(samples).all():
            raise RuntimeError('The denoiser returned invalid audio.')
        if result.sample_rate != rate:
            count = round(len(samples) * rate / result.sample_rate)
            samples = np.interp(np.linspace(0, len(samples)-1, count), np.arange(len(samples)), samples)
        cleaned = (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()
        return cleaned[:len(pcm)].ljust(len(pcm), b'\0')
