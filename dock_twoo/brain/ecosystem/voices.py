"""Per-character Kokoro speaker tuning and quiet, local species entrance sounds."""
import math
import numpy as np
from dock_twoo.brain.catalog import character
from dock_twoo.brain.local_tts import VOICES
from dock_twoo.brain.audio import SpeechClip


def tuning(store, character_id):
    entry=character(character_id);index=entry['index'];speakers=list(VOICES)
    if character_id=='default':
        default={'voice':store.setting('voice_name','af_heart'),'speed':float(store.setting('speech_rate',1)),'pitch':1.}
    else:
        default={'voice':speakers[index%len(speakers)],'speed':.94+(index%7)*.025,'pitch':.97+(index%5)*.015}
    return {**default,**store.setting('character_voices',{}).get(character_id,{})}


def validate_tuning(value):
    if not isinstance(value,dict) or set(value)-{'voice','speed','pitch'}:raise ValueError('Supply voice, speed and pitch settings.')
    if value.get('voice') not in VOICES:raise ValueError('Choose an available local voice.')
    for key,lower,upper in (('speed',.75,1.4),('pitch',.85,1.2)):
        if type(value.get(key)) not in (float,int) or not math.isfinite(value[key]) or not lower<=value[key]<=upper:raise ValueError('Invalid character '+key+'.')
    return dict(value)


def species_sound(character_id):
    """Short procedural cues, original PCM; no recorded animal or provider audio."""
    entry=character(character_id);species=entry['species'];rate=24000
    duration=.65 if species=='owl' else .38
    t=np.arange(int(duration*rate),dtype=float)/rate
    envelope=np.sin(np.pi*t/duration)**2
    if species=='owl':
        phase=2*np.pi*(330*t+8*np.sin(2*np.pi*3*t));wave=(np.sin(phase)+.2*np.sin(2*phase))*.22
    elif species in ('corgi','beagle','husky'):
        noise=np.random.default_rng(entry['index']).normal(0,1,len(t))
        pulse=(np.sin(2*np.pi*160*t)+.25*noise)*np.exp(-t*6)
        wave=np.tanh(1.8*pulse)*.22
    elif species in ('tuxedo','calico','siamese'):
        phase=2*np.pi*(700*t-400*t*t);wave=(np.sin(phase)+.15*np.sin(3*phase))*.16
    elif entry['family']=='bird':
        phase=2*np.pi*(1200*t+140*t*t+12*np.sin(2*np.pi*12*t));wave=np.sin(phase)*.12
    else:
        frequency=440+entry['index']*23;wave=(np.sin(2*np.pi*frequency*t)+.25*np.sin(2*np.pi*frequency*1.5*t))*.10
    pcm=(np.clip(wave*envelope,-1,1)*32767).astype('<i2').tobytes()
    return SpeechClip.from_pcm(pcm,rate)
