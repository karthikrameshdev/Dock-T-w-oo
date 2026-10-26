"""Keep unit tests from emitting real speech into an already-running wake listener."""

import pytest


@pytest.fixture(autouse=True)
def isolate_brain_settings(tmp_path, monkeypatch):
    monkeypatch.setenv('DOCK_TWOO_BRAIN_DATA_DIR', str(tmp_path / 'brain'))
    from dock_twoo.brain.manager import BrainManager
    monkeypatch.setattr(BrainManager, '_instance', None)
    yield
    import shiboken6
    manager = BrainManager._instance
    if isinstance(manager, BrainManager) and shiboken6.isValid(manager) and shiboken6.isValid(manager.companion):
        manager.stop_talking()
        manager.companion.close()


@pytest.fixture(autouse=True)
def silence_unit_test_speech(monkeypatch):
    from dock_twoo.brain.speech import SpeechPlayback
    monkeypatch.setattr(SpeechPlayback, '_play_clip', lambda *_args, **_kwargs: None)


@pytest.fixture(autouse=True)
def offline_privacy_entities(monkeypatch):
    # Unit suites must not download a 100 MB model. Real ONNX verification is
    # exercised by scripts/verify_privacy_transport.py; regex guards remain real.
    from dock_twoo.brain.security.privacy import _entities
    monkeypatch.setattr(_entities,'spans',lambda text:())
