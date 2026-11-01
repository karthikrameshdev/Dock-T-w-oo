"""Cached Kokoro PCM through production wake/VAD/Whisper turn handling.

Usage: .venv/bin/python scripts/verify_local_voice_turn.py --model-dir PATH
PATH is the existing assistant models directory containing huggingface/ and vad/.
No hardware audio, cloud requests, downloads, or user settings are touched. All
generated audio stays in memory; only synthetic diagnostic results are saved.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
# Unlike unit tests, this smoke must run the real production transcriber.
os.environ.pop('PYTEST_CURRENT_TEST', None)

import numpy as np
from PySide6.QtCore import QCoreApplication, QObject, Signal
from dock_twoo.brain.audio_devices import MicrophoneConverter
from dock_twoo.brain.listener import AudioListener
from dock_twoo.brain.local_tts import CACHE, LocalTts
from dock_twoo.brain.storage import BrainStore


class NoHardwareAudio(QObject):
    input_frame = Signal(bytes, float)
    input_state = Signal(bool, str)
    error = Signal(str)

    def start_input(self):
        raise AssertionError('This smoke must never open a microphone.')

    def stop_input(self):
        pass


class LocalOnlyListener(AudioListener):
    def _init_native_speech(self):
        # Exercise the common ONNX path, never OS-specific speech services.
        self._sf_recognizer = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path, default=Path('/tmp/dock-local-voice-turn.json'))
    args = parser.parse_args()
    source = args.model_dir.expanduser().resolve()
    assert (source / 'huggingface/hub').is_dir(), 'Cached recognition models are missing.'
    assert (source / 'vad/silero_vad.onnx').is_file(), 'Cached VAD is missing.'
    assert (CACHE / 'brain-kokoro-voices-v1.npz').is_file(), 'Prebuilt Kokoro voice cache is required.'
    app = QCoreApplication.instance() or QCoreApplication([])
    started = time.monotonic()
    report = {'success': False, 'cloud_calls': 0, 'hardware_audio': False,
              'settings_isolated': True, 'phrase': 'Brain, what time is it?'}
    engine = LocalTts()
    with tempfile.TemporaryDirectory(prefix='dock-local-voice-turn-') as directory:
        root = Path(directory)
        models = root / 'models'
        models.mkdir()
        # Checkpoints are read from cache; generated KWS lists stay in temp.
        (models / 'huggingface').symlink_to(source / 'huggingface', target_is_directory=True)
        (models / 'vad').symlink_to(source / 'vad', target_is_directory=True)
        listener = LocalOnlyListener(store=BrainStore(root / 'settings'),
                                     model_dir=models, audio_devices=NoHardwareAudio())
        listener.enable_character_names()
        wakes, turns, errors = [], [], []
        listener.named_wake_started.connect(wakes.append)
        listener.named_turn_completed.connect(lambda *turn: turns.append(turn))
        listener.error_occurred.connect(errors.append)
        try:
            assert engine.load(allow_download=False), engine.error
            assert listener.wake_detector.load(allow_download=False), listener.wake_detector.error
            assert listener.models.recognizer.load(allow_download=False), listener.models.recognizer.error
            assert listener.endpoint_vad.load(allow_download=False), listener.endpoint_vad.error
            clip = engine.clip(report['phrase'], threading.Event(), voice='af_heart')
            pcm = b''.join(MicrophoneConverter(clip.rate).feed(
                np.frombuffer(clip.pcm, dtype='<i2').astype(np.float32) / 32768))
            samples = np.concatenate((np.zeros(4800, dtype='<i2'),
                                      np.frombuffer(pcm, dtype='<i2'),
                                      np.zeros(64000, dtype='<i2')))
            listener.arm_wake()
            for offset in range(0, len(samples), 1600):
                listener._handle_pcm_frame(samples[offset:offset + 1600].tobytes())
                app.processEvents()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and (not turns or listener.decode_workers_active()):
                app.processEvents()
                time.sleep(.01)
            app.processEvents()
            report.update(wakes=wakes, turns=turns, errors=errors,
                          keyword=listener.wake_detector.last_keyword,
                          vad_windows=listener.endpoint_vad.windows,
                          voiced_windows=listener.endpoint_vad.voiced_windows,
                          decision=listener.last_wake_decision,
                          elapsed_seconds=round(time.monotonic() - started, 2))
            normalized = re.sub(r'[^a-z0-9 ]', '', turns[0][1].lower()).strip() if turns else ''
            report['success'] = (wakes == ['default'] and len(turns) == 1
                and turns[0][0] == 'default' and normalized == 'what time is it'
                and not turns[0][3] and not errors and listener.endpoint_vad.voiced_windows > 0)
        finally:
            listener.closed = True
            listener.stop()
            # Keep checkpoints alive until native inference workers finish.
            deadline = time.monotonic() + 30
            while listener.decode_workers_active() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.01)
            assert not listener.decode_workers_active(), 'A transcription worker did not retire.'
            assert listener.models.release_if_idle()
            assert listener.wake_detector.release_if_idle()
            assert listener.endpoint_vad.release_if_idle()
            assert engine.release_if_idle()
    args.report.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
