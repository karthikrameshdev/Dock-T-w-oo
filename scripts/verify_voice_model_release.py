"""Offline real-model load, TTS→STT, release and reload verification.

Uses already-cached checkpoints only. Does not open microphones/speakers, call
cloud providers, download assets, or modify the user's assistant configuration.
RSS counters are observations, not allocator-dependent pass/fail assertions.
"""
import gc
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import psutil
from dock_twoo.brain.audio_devices import MicrophoneConverter
from dock_twoo.brain.local_tts import LocalTts
from dock_twoo.brain.recognition import LocalRecognizer
from dock_twoo.brain.storage import BrainStore


def main():
    process = psutil.Process()
    tts = LocalTts()
    stt = LocalRecognizer(BrainStore().data_dir / 'models')
    samples = []
    def sample(stage):
        samples.append({'stage': stage, 'rss_bytes': process.memory_info().rss,
                        'threads': process.num_threads()})
    sample('before_models')
    for cycle in range(2):
        assert tts.load(allow_download=False), tts.error
        assert stt.load(allow_download=False), stt.error
        clip = tts.clip('The assistant can close and open again.', threading.Event())
        converter = MicrophoneConverter(clip.rate)
        pcm = b''.join(converter.feed(np.frombuffer(clip.pcm, dtype='<i2').astype(np.float32) / 32768))
        transcript = stt.transcribe(pcm)
        assert 'close' in transcript.lower() and 'open' in transcript.lower(), transcript
        sample(f'loaded_and_inferred_{cycle + 1}')
        assert tts.release_if_idle() and stt.release_if_idle()
        assert tts.engine is None and not stt.ready
        del clip, converter, pcm
        gc.collect()
        sample(f'released_{cycle + 1}')
    report = {'success': True, 'cycles': 2, 'transcript': transcript,
              'cloud_calls': 0, 'hardware_audio': False, 'samples': samples}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
