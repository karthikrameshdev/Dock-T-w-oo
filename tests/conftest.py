"""Keep unit tests from emitting real speech into an already-running wake listener."""

import pytest


@pytest.fixture(autouse=True)
def silence_unit_test_speech(monkeypatch):
    from dock_twoo.brain.speech import SpeechPlayback
    monkeypatch.setattr(SpeechPlayback, '_play_clip', lambda *_args, **_kwargs: None)
