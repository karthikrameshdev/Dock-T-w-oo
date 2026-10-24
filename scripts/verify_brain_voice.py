"""Exercise real local wake and ASR models using generated audio, without a microphone.

Run from the checkout: .venv/bin/python scripts/verify_brain_voice.py
Models must already be cached; this check never downloads models or records audio.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import QCoreApplication
from dock_twoo.brain.listener import AudioListener


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=Path('/tmp/dock-twoo-voice-check.json'))
    args = parser.parse_args()
    if platform.system() != 'Darwin':
        parser.error('This generated-speech check uses the macOS say command.')
    app = QCoreApplication.instance() or QCoreApplication([])
    listener = AudioListener()
    if not listener.wake_detector.load(allow_download=False):
        raise RuntimeError(listener.wake_detector.error)
    if not listener.models.recognizer.load(allow_download=False):
        raise RuntimeError(listener.models.recognizer.error)
    assert listener.endpoint_vad.load(allow_download=False), listener.endpoint_vad.error
    wakes, commands = [], []
    transcripts = []
    transcribe = listener._transcribe_pcm
    def trace_generated_audio(pcm):
        text = transcribe(pcm)
        transcripts.append(text)
        return text
    listener._transcribe_pcm = trace_generated_audio
    listener.wake_detected.connect(lambda: wakes.append(True))
    listener.turn_completed.connect(commands.append)
    phrases = ['Brain', 'Hey Brain', 'Hello Brain', 'Hey Buddy',
               'Hey Brain what time is it', 'Bring me a cup of tea',
               'The weather is beautiful today',
               'Hey Brain sing a song for me',
               'Hey Brain can you please sing a song for me',
               'Hey Brain open the Cursor application and type hello world']
    expected_commands = {4:'what time is it', 7:'sing a song for me',
                         8:'can you please sing a song for me',
                         9:'open the cursor application and type hello world'}
    report = []
    with tempfile.TemporaryDirectory(prefix='brain-voice-check-') as folder:
        for voice in ('Samantha', 'Daniel'):
            for index, phrase in enumerate(phrases):
                path = Path(folder) / 'sample.wav'
                subprocess.run(['say', '-v', voice, '-o', str(path), '--file-format=WAVE',
                                '--data-format=LEI16@16000', '--', phrase], check=True, capture_output=True)
                with wave.open(str(path), 'rb') as source:
                    assert source.getnchannels() == 1 and source.getframerate() == 16000
                    pcm = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2')
                for condition, gain, noise in (('normal', 1, 0), ('quiet', .04, 0), ('noise', .3, 200)):
                    listener.arm_wake()
                    import webrtcvad
                    listener._vad = webrtcvad.Vad(2)
                    wakes.clear()
                    commands.clear()
                    transcripts.clear()
                    samples = np.concatenate([np.zeros(6400), pcm.astype(float) * gain, np.zeros(80000)])
                    samples += np.random.default_rng(42).normal(0, noise, len(samples))
                    samples = np.clip(samples, -32768, 32767).astype('<i2')
                    for offset in range(0, len(samples), 1600):
                        listener._handle_pcm_frame(samples[offset:offset + 1600].tobytes())
                    deadline = time.monotonic() + 8
                    while time.monotonic() < deadline:
                        app.processEvents()
                        if wakes or commands:
                            break
                        if listener._wake_armed and not listener._wake_check_lock.locked():
                            break
                        time.sleep(.005)
                    normalized = [' '.join(text.lower().strip(' .?!').split()) for text in commands]
                    passed = (len(wakes) == 1 and not commands) if index < 4 else (
                        not wakes and normalized == [expected_commands[index]] if index in expected_commands else not wakes and not commands)
                    case = dict(voice=voice, phrase=phrase, condition=condition, passed=passed,
                                wakes=len(wakes), commands=list(commands), transcripts=list(transcripts), stage=listener.last_wake_decision)
                    report.append(case)
                    print(('PASS' if passed else 'FAIL'), voice, condition, repr(phrase), flush=True)
    listener.stop()
    # Finish any ambient backup decode before Python tears down ONNX Runtime.
    with listener._wake_check_lock:
        pass
    failures = sum(not case['passed'] for case in report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(dict(cases=report, passed=len(report) - failures, failed=failures), indent=2))
    print(f'{len(report) - failures}/{len(report)} passed. Report: {args.report}')
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
