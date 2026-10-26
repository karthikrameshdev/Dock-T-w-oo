import threading
from types import SimpleNamespace

import pytest
from dock_twoo.brain.speech_text import spoken_text


@pytest.mark.parametrize('source,expected', [
    ('**Hello**, Rio! The budget is $200.', 'Hello, Rio! The budget is two hundred dollars.'),
    ('$ 200', 'two hundred dollars'),
    ('$1.50; $.50; -$20', 'one dollar and fifty cents; fifty cents; minus twenty dollars'),
    ('$1.00 and $0', 'one dollar and zero dollars'),
    ('£1.01 and €2.50', 'one pound and one penny and two euros and fifty cents'),
    ('₹1,23,456', 'one hundred twenty three thousand four hundred fifty six rupees'),
    ('$2.5 million', 'two million five hundred thousand dollars'),
    ('***\n!!!\n…', ''),
    ("Wait... Hello, world! Why? It's fine.", "Wait... Hello, world! Why? It's fine."),
    ('**bold** *italic* _words_ `code` ~~old~~', 'bold italic words code old'),
    ('# Summary\n* **Budget:** $200\n* Rate: 12.5%\n---\n[Read this](https://example.com)',
     'Summary\nBudget: two hundred dollars\nRate: 12.5 percent\nRead this'),
    ('<p>Research &amp; development</p>', 'Research and development'),
    ('6 * 7 = 42; C++ & C#', '6 times 7 equals 42; C plus plus and C sharp'),
    ('```python\nprint("Hello")\n```', 'print, Hello'),
])
def test_formatting_is_silent_and_semantic_symbols_are_spoken(source, expected):
    assert spoken_text(source) == expected
    assert spoken_text(expected) == expected


def test_local_model_receives_narration_and_original_response_stays_intact():
    from dock_twoo.brain.local_tts import LocalTts
    import numpy as np
    calls = []; tts = LocalTts()
    def create(text, **options):calls.append(text); return np.zeros(240), 24000
    tts.engine = SimpleNamespace(create=create)
    original = '**Rio** costs $200.'
    clip = tts.clip(original, threading.Event())
    assert calls == ['Rio costs two hundred dollars.'] and clip.frames == 240
    assert original == '**Rio** costs $200.'


def test_platform_fallback_receives_the_same_clean_narration(tmp_path, monkeypatch):
    from dock_twoo.brain import audio
    from pathlib import Path
    calls = []
    class Process:
        def communicate(self, **kwargs):return None, b''
    def launch(args, **kwargs):
        calls.append(args); Path(args[args.index('-o') + 1]).write_bytes(b'fixture')
        return Process()
    monkeypatch.setattr(audio.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(audio.subprocess, 'Popen', launch)
    monkeypatch.setattr(audio.SpeechClip, 'read', lambda _: 'clip')
    assert audio.synthesize('**Rio** costs $200.', tmp_path / 'clip.wav') == 'clip'
    assert calls[0][-1] == 'Rio costs two hundred dollars.'


def test_full_formatting_is_normalized_before_tts_phrase_chunking(qtbot, monkeypatch):
    from dock_twoo.brain.speech import SpeechPlayback
    playback = SpeechPlayback(); calls = []
    monkeypatch.setattr(playback, '_play_worker', lambda _, text, *args: calls.append(text))
    try:
        playback.start('**Rio** costs $ 200.\n```text\nRead this.\n```')
        qtbot.waitUntil(lambda: bool(calls))
        assert calls == ['Rio costs two hundred dollars.\nRead this.']
    finally:playback.stop(); playback.audio_devices.close()
