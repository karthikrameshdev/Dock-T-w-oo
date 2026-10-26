"""Capture completion, local barge-in, echo rejection and default-device routing."""
import threading
from types import SimpleNamespace
import numpy as np
import pytest
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtMultimedia import QAudio, QAudioFormat
from dock_twoo.brain.audio import SpeechClip
from dock_twoo.brain.audio_devices import DefaultAudioDevices, MicrophoneConverter, decode_audio, encode_output, PlaybackRequest
from dock_twoo.brain.echo import PlaybackEchoGuard
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from tests.test_voice_turns import listener_for_test,feed,SPEECH,SILENCE


def test_second_click_processes_entire_capture_once(qtbot,tmp_path,monkeypatch):
    manager=BrainManager(store=BrainStore(tmp_path),start_services=False)
    listener=manager.listener
    listener._is_speech_frame=lambda pcm,*_:pcm!=SILENCE
    captured=[];entered=threading.Event();release=threading.Event();results=[]
    def transcribe(pcm):
        captured.append(pcm);entered.set();release.wait(2)
        return 'Open Cursor and type hello world'
    monkeypatch.setattr(listener,'_transcribe_pcm',transcribe)
    listener.named_turn_completed.disconnect()
    listener.named_turn_completed.connect(lambda ident,command,raw,bare:results.append(command))
    manager.toggle_talking();feed(listener,SPEECH,12)
    manager.toggle_talking()
    assert not listener.is_recording and entered.wait(1)
    generation=listener._capture_generation
    manager.toggle_talking()  # A rapid third click cannot restart a pending decode.
    assert listener._capture_generation==generation
    release.set();qtbot.waitUntil(lambda:bool(results))
    assert results==['Open Cursor and type hello world'] and captured==[SPEECH*12]
    manager.shutdown()


def test_second_click_during_outdated_decode_reprocesses_complete_statement(qtbot,tmp_path):
    listener=listener_for_test(tmp_path);entered=threading.Event();release=threading.Event();sizes=[];results=[]
    def transcribe(pcm):
        sizes.append(len(pcm))
        if len(sizes)==1:entered.set();release.wait(2);return 'Brain, open'
        return 'Brain, open Cursor and type hello world'
    listener._transcribe_pcm=transcribe;listener.turn_completed.connect(results.append)
    feed(listener,SPEECH,5);feed(listener,SILENCE,15);assert entered.wait(1)
    feed(listener,SPEECH,8);listener.stop_recording();release.set()
    qtbot.waitUntil(lambda:bool(results))
    assert results==['open Cursor and type hello world'] and sizes[1]>sizes[0]


def test_silent_second_click_does_not_execute_a_request(tmp_path):
    listener=listener_for_test(tmp_path);timed=[];results=[]
    listener.turn_timed_out.connect(lambda:timed.append(True));listener.turn_completed.connect(results.append)
    listener.start_recording();listener.stop_recording()
    assert timed==[True] and results==[] and not listener.is_recording


@pytest.mark.parametrize('mode',['output','thinking','reading'])
def test_stop_only_monitoring_during_busy_states(tmp_path,mode):
    listener=listener_for_test(tmp_path);stops=[];commands=[];wakes=[]
    listener.stop_detector=SimpleNamespace(ready=True,reset=lambda:None,feed=lambda _: 'BRAIN_STOP')
    listener.stop_requested.connect(stops.append);listener.turn_completed.connect(commands.append)
    listener.wake_detected.connect(lambda:wakes.append(True))
    if mode=='reading':listener.suspend()
    elif mode=='thinking':listener._passive_stop=True
    else:listener.set_output_active(True)
    feed(listener,SPEECH,3)
    assert stops==['Brain Stop'] and not commands and not wakes and listener.stop_matches==1


def test_spoken_stop_cancels_agent_and_reading_without_calling_cloud(qapp,tmp_path,monkeypatch):
    manager=BrainManager(store=BrainStore(tmp_path),start_services=False)
    calls=[]
    monkeypatch.setattr(manager.agent,'stop',lambda:calls.append('stop'))
    monkeypatch.setattr(manager.agent,'execute',lambda *_:pytest.fail('Stop must not call a model'),raising=False)
    manager.in_conversation_session=True;manager.listener.start_recording()
    before=manager.speech.generation
    manager._do_turn_complete('Brain stop')
    assert calls and manager.speech.generation>before
    assert not manager.in_conversation_session and not manager.listener.is_recording
    assert not manager.reader.active and manager.last_response['text']=='Stopped.'
    manager.shutdown()


def test_echo_rejection_preserves_double_talk():
    rng=np.random.default_rng(7)
    reference=rng.normal(0,2200,32000).astype('<i2');guard=PlaybackEchoGuard()
    guard.begin(reference.tobytes(),16000,1,1,started=10.)
    echo=(reference[8000:9600]*.4).astype('<i2')
    assert not any(guard.filter(echo.tobytes(),captured_at=10.56))
    near=rng.normal(0,1300,1600).astype('<i2')
    residual=np.frombuffer(guard.filter((echo+near).astype('<i2').tobytes(),10.56),dtype='<i2')
    assert np.corrcoef(residual,near)[0,1]>.98


def audio_format(rate=48000,channels=2,kind=QAudioFormat.SampleFormat.Float):
    fmt=QAudioFormat();fmt.setSampleRate(rate);fmt.setChannelCount(channels);fmt.setSampleFormat(kind);return fmt


@pytest.mark.parametrize('rate',[16000,22050,44100,48000])
def test_native_microphone_rates_resample_without_chunk_drift(rate):
    converter=MicrophoneConverter(rate);t=np.arange(rate*2)/rate
    values=np.sin(2*np.pi*240*t).astype(np.float32)*.2
    frames=[]
    for chunk in np.array_split(values,71):frames.extend(converter.feed(chunk))
    result=np.frombuffer(b''.join(frames),dtype='<i2')
    assert 19*1600 <= len(result) <= 20*1600
    assert len(result)+len(converter.output)//2 in (31999,32000)
    expected=np.sin(2*np.pi*240*np.arange(len(result))/16000)*.2*32768
    assert np.sqrt(np.mean((result-expected)**2))<15


@pytest.mark.parametrize('kind',[QAudioFormat.SampleFormat.UInt8,QAudioFormat.SampleFormat.Int16,QAudioFormat.SampleFormat.Int32,QAudioFormat.SampleFormat.Float])
def test_speaker_format_conversion_retains_resume_offset(kind):
    values=np.linspace(-10000,10000,24000).astype('<i2')
    clip=SpeechClip.from_pcm(values.tobytes(),24000)
    fmt=audio_format(kind=kind)
    data=encode_output(clip,fmt,start_frame=12000)
    result=decode_audio(data,fmt)
    assert len(result)==24000
    assert abs(result[0])<.01 and result[-1]>.29


class Device:
    def __init__(self,name):self.name=name
    def id(self):return self.name.encode()
    def description(self):return self.name
    def isNull(self):return False
    def preferredFormat(self):return audio_format()


class Devices:
    def __init__(self):self.input=Device('Built-in mic');self.output=Device('Built-in speaker')
    def defaultAudioInput(self):return self.input
    def defaultAudioOutput(self):return self.output
    def audioInputs(self):return [self.input]
    def audioOutputs(self):return [self.output]


def test_default_device_changes_reopen_only_changed_route_and_keep_progress(qapp,monkeypatch):
    route=DefaultAudioDevices();route.devices=Devices();route._refresh();route._want_input=True
    calls=[];route._request=PlaybackRequest(SpeechClip.from_pcm(bytes(32000),16000),threading.Event(),lambda _:None,lambda _:None)
    route._request.frame=5300
    monkeypatch.setattr(route,'_open_input',lambda:calls.append('input'))
    monkeypatch.setattr(route,'_resume_output',lambda:calls.append(('output',route._request.frame)))
    route.devices.input=Device('Bluetooth mic');route._refresh()
    assert calls==['input']
    route.devices.output=Device('Bluetooth speaker');route._refresh()
    assert calls==['input',('output',5300)]
    route._refresh();assert len(calls)==2
    route.close()


def test_device_handover_restarts_at_frames_actually_played(qapp,monkeypatch):
    route=DefaultAudioDevices();frames=[];clip=SpeechClip.from_pcm(bytes(96000),24000)
    request=PlaybackRequest(clip,threading.Event(),frames.append,lambda _:None,frame=1200,base_frame=1200)
    route._request=request;route.sink=SimpleNamespace(processedUSecs=lambda:250000)
    calls=[]
    monkeypatch.setattr(route,'_close_output',lambda:calls.append('closed'))
    monkeypatch.setattr(route,'_open_output',lambda:calls.append(request.frame))
    route._resume_output()
    assert calls==['closed',7200] and frames==[7200]
    route.sink=None;route.close()


def test_cancel_discards_queued_audio_and_releases_worker(qapp):
    route=DefaultAudioDevices();request=PlaybackRequest(SpeechClip.from_pcm(bytes(32000),16000),threading.Event(),lambda _:None,lambda _:None)
    calls=[];route.sink=SimpleNamespace(reset=lambda:calls.append('discard'),deleteLater=lambda:None)
    route._request=request;request.cancel.set();route._tick()
    assert request.done.is_set() and route.sink is None and calls==['discard']
    route.close()


def test_stalled_speaker_is_bounded_instead_of_waiting_forever(qapp,monkeypatch):
    route=DefaultAudioDevices();request=PlaybackRequest(SpeechClip.from_pcm(bytes(32000),16000),threading.Event(),lambda _:None,lambda _:None,last_progress=0)
    route._request=request;calls=[]
    route.sink=SimpleNamespace(processedUSecs=lambda:0,reset=lambda:calls.append('discard'),deleteLater=lambda:None)
    route._tick()
    assert request.done.is_set() and 'stalled' in request.error and calls==['discard']
    route.close()


def test_bluetooth_format_change_on_same_device_reopens_route(qapp,monkeypatch):
    route=DefaultAudioDevices();route.devices=Devices();route._refresh();route._want_input=True
    calls=[];monkeypatch.setattr(route,'_open_input',lambda:calls.append('input'))
    route.devices.input.preferredFormat=lambda:audio_format(rate=16000,channels=1)
    route._refresh();assert calls==['input']
    route.close()


def test_spoken_stop_remains_available_when_automatic_wake_is_disabled(qapp,tmp_path,monkeypatch):
    store=BrainStore(tmp_path);store.set_setting('wake_word_enabled',False)
    manager=BrainManager(store=store,start_services=False);started=[]
    monkeypatch.setattr(manager.listener,'start',lambda:started.append(True))
    manager._on_speech_activity('speaking')
    assert started==[True] and manager.listener._passive_stop
    assert not manager.listener.wake_detection_enabled
    manager.shutdown()
