"""Offline TTS→STT check of natural reading. No audio devices or cloud calls."""
import json, re, sys, threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from dock_twoo.brain.local_tts import get_local_tts
from dock_twoo.brain.recognition import LocalRecognizer
from dock_twoo.brain.storage import BrainStore
from dock_twoo.brain.audio_devices import MicrophoneConverter
from dock_twoo.brain.speech_text import spoken_text

tts = get_local_tts(); assert tts.load(allow_download=False), tts.error
stt = LocalRecognizer(BrainStore().data_dir/'models'); assert stt.load(allow_download=False), stt.error
source = '**The budget is $200.** The fee is $ 1.50. [Continue reading](https://example.com).'
expected = 'The budget is two hundred dollars. The fee is one dollar and fifty cents. Continue reading.'
assert spoken_text(source) == expected
clip = tts.clip(source, threading.Event())
converter = MicrophoneConverter(clip.rate)
pcm = b''.join(converter.feed(np.frombuffer(clip.pcm, dtype='<i2').astype(np.float32)/32768))
transcript = stt.transcribe(pcm)
# ASR may spell currency as either words or symbols. Verify the audible meaning.
normalized = re.sub(r'[^a-z0-9 ]', '', spoken_text(transcript).lower())
assert 'two hundred dollars' in normalized or '200 dollars' in normalized, transcript
assert 'fifty cents' in normalized or '50 cents' in normalized, transcript
assert not any(word in normalized for word in ('asterisk', 'dollar sign', 'https', 'exclamation')), transcript
assert 'continue reading' in normalized, transcript
print(json.dumps({'success':True,'spoken_text':expected,'transcript':transcript,'seconds':len(clip.pcm)/2/clip.rate,'cloud_calls':0,'hardware_audio':False}, indent=2))
