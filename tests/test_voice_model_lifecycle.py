"""Closing speech releases idle models without interrupting native inference."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from dock_twoo.brain.denoiser import LocalDenoiser
from dock_twoo.brain.endpoint_vad import NeuralEndpointVad
from dock_twoo.brain.recognition import LocalRecognizer
from dock_twoo.brain.voice_models import LocalVoiceModels
from dock_twoo.brain.wake import WakeDetector


@contextmanager
def held_elsewhere(lock):
    entered, release = threading.Event(), threading.Event()

    def hold():
        with lock:
            entered.set()
            release.wait(5)

    worker = threading.Thread(target=hold)
    worker.start()
    assert entered.wait(1)
    try:yield
    finally:
        release.set()
        worker.join(2)
        assert not worker.is_alive()


@pytest.mark.parametrize('kind', ['recognizer', 'denoiser', 'wake', 'vad'])
def test_active_native_models_are_not_evicted(tmp_path, kind):
    if kind == 'recognizer':
        model = LocalRecognizer(tmp_path)
        model._recognizer = object()
        locks = [model._load_lock, model._inference_lock]
        loaded = lambda: model.ready
    elif kind == 'denoiser':
        model = LocalDenoiser(tmp_path)
        model.engine = object()
        locks = [model.lock]
        loaded = lambda: model.engine is not None
    elif kind == 'wake':
        model = WakeDetector(tmp_path)
        model._spotter = model._stream = model._bpe = object()
        model.state = 'ready'
        locks = [model._load_lock, model._lock]
        loaded = lambda: model.ready
    else:
        model = NeuralEndpointVad(tmp_path)
        model.model = object()
        model.pending = np.ones(10)
        locks = [model._load_lock, model._lock]
        loaded = lambda: model.ready
    for lock in locks:
        with held_elsewhere(lock):
            assert model.release_if_idle() is False
            assert loaded()
    assert model.release_if_idle() is True
    assert not loaded()
    assert model.release_if_idle() is True


@pytest.mark.parametrize('kind', ['wake', 'vad'])
def test_repeated_start_reuses_ready_or_inflight_models(tmp_path, monkeypatch, kind):
    model = WakeDetector(tmp_path) if kind == 'wake' else NeuralEndpointVad(tmp_path)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def load(_allow_download):
        calls.append(True)
        entered.set()
        assert release.wait(3)
        if kind == 'wake':
            model._spotter = object()
            model.state = 'ready'
        else:
            model.model = object()
        return True

    monkeypatch.setattr(model, '_load', load)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: model.start(), range(80)))
        assert entered.wait(1)
        assert calls == [True]
        assert not model.release_if_idle()
    finally:
        release.set()
        model._worker.join(2)
    original = model._worker
    for _ in range(80):model.start()
    assert model._worker is original and calls == [True]
    assert model.release_if_idle()
    model.start()
    model._worker.join(2)
    assert calls == [True, True] and model.ready


def test_model_bundle_preserves_inflight_loads_and_releases_resident_references(tmp_path):
    models = LocalVoiceModels(tmp_path)
    models.recognizer._recognizer = object()
    models.denoiser.engine = object()
    models._asr = models.recognizer
    models._enhancer = models.denoiser
    models._speaker = models._processor = object()
    models._download_threads['recognizer'] = SimpleNamespace(is_alive=lambda: True)
    assert not models.release_if_idle()
    assert models.recognizer.ready and models._speaker is not None
    models._download_threads.clear()
    with held_elsewhere(models._asr_lock):
        assert not models.release_if_idle()
        assert models.recognizer.ready
    assert models.release_if_idle()
    assert not models.recognizer.ready and models.denoiser.engine is None
    assert models._asr is models._enhancer is models._speaker is models._processor is None


@pytest.mark.parametrize('kind', ['recognizer', 'wake'])
def test_release_between_ready_check_and_inference_is_safe(tmp_path, monkeypatch, kind):
    model = LocalRecognizer(tmp_path) if kind == 'recognizer' else WakeDetector(tmp_path)
    if kind == 'recognizer':model._recognizer = object()
    else:
        model._spotter = model._stream = object()
        model.state = 'ready'
    original = np.frombuffer

    def release_then_convert(*args, **kwargs):
        assert model.release_if_idle()
        return original(*args, **kwargs)

    monkeypatch.setattr(np, 'frombuffer', release_then_convert)
    infer = model.transcribe if kind == 'recognizer' else model.feed
    assert infer(b'\0\0' * 320) == ''


def test_unloaded_vad_and_denoiser_do_not_process_audio(tmp_path):
    pcm = b'\0\0' * 320
    assert NeuralEndpointVad(tmp_path).feed(pcm) is False
    assert LocalDenoiser(tmp_path).enhance(pcm, 16000) == pcm
