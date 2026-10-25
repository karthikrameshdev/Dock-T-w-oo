"""System-default audio routing shared by Windows, macOS and Linux.

Qt owns device discovery and hotplug notifications. Hardware I/O stays on the Qt
thread; STT and synthesis stay on workers. A device change retains the capture
and resumes playback at its last played frame, without executing partial speech.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time

import numpy as np
from PySide6.QtCore import QBuffer, QIODevice, QObject, QTimer, Signal, Slot, Qt
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QAudioSource, QMediaDevices
try:
    from PySide6.QtMultimedia import QtAudio as QAudio
except ImportError:  # Qt 6.6–6.10
    from PySide6.QtMultimedia import QAudio


def decode_audio(data: bytes, fmt: QAudioFormat) -> np.ndarray:
    """Convert a native device format to normalized mono samples."""
    kind = fmt.sampleFormat()
    dtype, center, divisor = {
        QAudioFormat.SampleFormat.UInt8: (np.uint8, 128., 128.),
        QAudioFormat.SampleFormat.Int16: ('<i2', 0., 32768.),
        QAudioFormat.SampleFormat.Int32: ('<i4', 0., 2147483648.),
        QAudioFormat.SampleFormat.Float: ('<f4', 0., 1.),
    }[kind]
    samples = (np.frombuffer(data, dtype=dtype).astype(np.float32)-center)/divisor
    return samples.reshape(-1, fmt.channelCount()).mean(axis=1)


class MicrophoneConverter:
    """Stateful resampling: chunk boundaries cannot duplicate or lose samples."""
    def __init__(self, rate: int):
        self.step = rate/16000
        self.pending = np.empty(0, dtype=np.float32)
        self.position = 0.
        self.output = bytearray()

    def feed(self, samples: np.ndarray) -> list[bytes]:
        self.pending = np.concatenate((self.pending, samples))
        positions = np.arange(self.position, max(0, len(self.pending)-1), self.step)
        if len(positions):
            values = np.interp(positions, np.arange(len(self.pending)), self.pending)
            self.output.extend(np.clip(values*32768, -32768, 32767).astype('<i2').tobytes())
            self.position = float(positions[-1]+self.step)
        consumed = min(int(self.position), len(self.pending))
        self.pending = self.pending[consumed:]
        self.position -= consumed
        frames = []
        while len(self.output) >= 3200:
            frames.append(bytes(self.output[:3200]))
            del self.output[:3200]
        return frames


def encode_output(clip, fmt: QAudioFormat, start_frame: int = 0) -> bytes:
    """Resample TTS to the default device's supported rate/channels/sample type."""
    samples = np.frombuffer(clip.pcm, dtype='<i2').reshape(-1, clip.channels).astype(np.float32)/32768
    samples = samples[start_frame:]
    count = round(len(samples)*fmt.sampleRate()/clip.rate)
    positions = np.arange(count)*clip.rate/fmt.sampleRate()
    if not len(samples) or not count:
        return b''
    mono = samples.mean(axis=1)
    output = np.interp(positions, np.arange(len(mono)), mono)
    output = np.repeat(output[:, None], fmt.channelCount(), axis=1)
    kind = fmt.sampleFormat()
    if kind == QAudioFormat.SampleFormat.Float:
        return output.astype('<f4').tobytes()
    if kind == QAudioFormat.SampleFormat.Int16:
        return np.clip(output*32768, -32768, 32767).astype('<i2').tobytes()
    if kind == QAudioFormat.SampleFormat.Int32:
        return np.clip(output*2147483648, -2147483648, 2147483647).astype('<i4').tobytes()
    if kind == QAudioFormat.SampleFormat.UInt8:
        return np.clip(output*128+128, 0, 255).astype(np.uint8).tobytes()
    raise RuntimeError('The system default audio device has an unsupported sample format.')


@dataclass
class PlaybackRequest:
    clip: object
    cancel: threading.Event
    on_frame: object
    on_align: object
    done: threading.Event = field(default_factory=threading.Event)
    frame: int = 0
    error: str = ''
    base_frame: int = 0
    waiting_since: float = 0.
    aligned: bool = False
    last_progress: float = field(default_factory=time.monotonic)


class DefaultAudioDevices(QObject):
    """One input and one output, both following the OS default automatically."""
    input_frame = Signal(bytes, float)
    input_state = Signal(bool, str)
    error = Signal(str)
    _play = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.devices = QMediaDevices(self)
        self.devices.audioInputsChanged.connect(self._refresh)
        self.devices.audioOutputsChanged.connect(self._refresh)
        self.source = self.input_io = self.sink = self.output_buffer = None
        self._input_id = self._output_id = None
        self._input_name = self._output_name = ''
        self._want_input = False
        self._converter = None
        self._input_tail = b''
        self._request = None
        self._last_input_retry = 0.
        self._next_output_retry = 0.
        self._play.connect(self._start_playback, Qt.ConnectionType.QueuedConnection)
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._tick)
        self._refresh()

    @staticmethod
    def _identity(device):
        if device.isNull():
            return None
        fmt = device.preferredFormat()
        return (bytes(device.id()), fmt.sampleRate(), fmt.channelCount(), fmt.sampleFormat())

    def status(self):
        return {'routing': 'system default', 'input': self._input_name,
                'output': self._output_name, 'input_active': self.source is not None,
                'inputs': [d.description() for d in self.devices.audioInputs()],
                'outputs': [d.description() for d in self.devices.audioOutputs()]}

    @Slot()
    def _refresh(self):
        incoming = self.devices.defaultAudioInput()
        outgoing = self.devices.defaultAudioOutput()
        new_in, new_out = self._identity(incoming), self._identity(outgoing)
        input_changed, output_changed = new_in != self._input_id, new_out != self._output_id
        self._input_id, self._output_id = new_in, new_out
        self._input_name = incoming.description() if new_in is not None else ''
        self._output_name = outgoing.description() if new_out is not None else ''
        if input_changed and self._want_input:
            self._open_input()
        if output_changed and self._request:
            self._resume_output()

    def start_input(self):
        self.timer.start()
        self._want_input = True
        self._open_input()

    def stop_input(self):
        self._want_input = False
        self._close_input()

    def _close_input(self):
        source, self.source = self.source, None
        self.input_io = None
        if source:
            source.stop()
            source.deleteLater()
        self.input_state.emit(False, self._input_name)

    def _open_input(self):
        self._last_input_retry = time.monotonic()
        self._close_input()
        device = self.devices.defaultAudioInput()
        if device.isNull():
            self.error.emit('No system default microphone is available. Connect or enable a microphone.')
            return
        self._input_id = self._identity(device)
        self._input_name = device.description()
        fmt = device.preferredFormat()
        self._input_format = fmt
        self._converter = MicrophoneConverter(fmt.sampleRate())
        self._input_tail = b''
        self.source = source = QAudioSource(device, fmt, self)
        source.setBufferSize(max(fmt.bytesForDuration(200_000), 4096))
        source.stateChanged.connect(self._input_changed)
        self.input_io = source.start()
        if self.input_io is None or source.error() != QAudio.Error.NoError:
            self.error.emit('Cannot open the system default microphone. Check microphone permission and device availability.')
            self._close_input()
            return
        self.input_io.readyRead.connect(self._read_input)
        self.input_state.emit(True, self._input_name)

    @Slot()
    def _input_changed(self):
        source = self.source
        if source and source.state() == QAudio.State.StoppedState and source.error() != QAudio.Error.NoError:
            self.error.emit('The default microphone disconnected; waiting for the system audio device.')
            self._close_input()

    def _read_input(self):
        if self.input_io is None:
            return
        data = self._input_tail + bytes(self.input_io.readAll())
        width = self._input_format.bytesPerFrame()
        usable = len(data)//width*width
        self._input_tail = data[usable:]
        chunks = self._converter.feed(decode_audio(data[:usable], self._input_format))
        now = time.monotonic()
        for index, chunk in enumerate(chunks):
            self.input_frame.emit(chunk, now-(len(chunks)-index)*.1)

    def play(self, clip, cancel, on_frame, on_align):
        """Called by synthesis worker; queued Qt operation, cooperatively cancellable."""
        request = PlaybackRequest(clip, cancel, on_frame, on_align)
        self._play.emit(request)
        while not request.done.wait(.04):
            if cancel.is_set():
                raise InterruptedError('Speech cancelled.')
        if cancel.is_set():
            raise InterruptedError('Speech cancelled.')
        if request.error:
            raise RuntimeError(request.error)

    @Slot(object)
    def _start_playback(self, request):
        if request.cancel.is_set():
            request.done.set()
            return
        self._finish_output()
        self.timer.start()
        self._request = request
        self._open_output()

    def _close_output(self):
        sink, self.sink = self.sink, None
        if sink:
            sink.reset()  # Discard queued audio immediately on stop or device change.
            sink.deleteLater()
        if self.output_buffer:
            self.output_buffer.close()
            self.output_buffer.deleteLater()
            self.output_buffer = None

    def _finish_output(self, error=''):
        request, self._request = self._request, None
        self._close_output()
        if request:
            request.error = error
            request.done.set()

    def _open_output(self):
        request = self._request
        if not request:
            return
        device = self.devices.defaultAudioOutput()
        if device.isNull():
            request.waiting_since = request.waiting_since or time.monotonic()
            return
        self._output_id, self._output_name = self._identity(device), device.description()
        try:
            fmt = device.preferredFormat()
            data = encode_output(request.clip, fmt, request.frame)
            if not data:
                self._finish_output()
                return
            request.base_frame = request.frame
            request.aligned = False
            self.output_buffer = buffer = QBuffer(self)
            buffer.setData(data)
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            self.sink = sink = QAudioSink(device, fmt, self)
            sink.setBufferSize(max(fmt.bytesForDuration(80_000), 1024))
            sink.stateChanged.connect(self._output_changed)
            sink.start(buffer)
            if sink.error() != QAudio.Error.NoError:
                raise RuntimeError('Cannot open the system default speaker. Check audio settings.')
            request.waiting_since = 0.
            request.last_progress = time.monotonic()
        except Exception as exc:
            self._finish_output(str(exc))

    @Slot()
    def _output_changed(self):
        sink = self.sink
        if not sink or not self._request:
            return
        state = sink.state()
        if state == QAudio.State.IdleState:
            request = self._request
            request.frame = request.clip.frames
            request.on_frame(request.frame)
            self._finish_output()
        elif state == QAudio.State.StoppedState and sink.error() != QAudio.Error.NoError:
            self._advance_output()
            self._close_output()
            self._request.waiting_since = self._request.waiting_since or time.monotonic()
            self._next_output_retry = time.monotonic()+1

    def _advance_output(self):
        request = self._request
        if self.sink and request:
            played = self.sink.processedUSecs()/1e6
            frame = min(request.clip.frames, request.base_frame+round(played*request.clip.rate))
            if frame > request.frame:
                request.last_progress = time.monotonic()
            request.frame = frame
            if not request.aligned and played > 0:
                request.aligned = True
                request.on_align(time.monotonic()-played-request.base_frame/request.clip.rate)
            request.on_frame(request.frame)

    def _resume_output(self):
        self._advance_output()
        self._close_output()
        self._open_output()

    def _tick(self):
        if self._want_input and self.source is None and time.monotonic()-self._last_input_retry > 2:
            self._open_input()
        request = self._request
        if not request:
            return
        if request.cancel.is_set():
            self._finish_output()
        elif self.sink:
            self._advance_output()
            if time.monotonic()-request.last_progress > 5:
                self._finish_output('Audio playback stalled on the system default speaker. Check the output device.')
        elif request.waiting_since and time.monotonic()-request.waiting_since > 10:
            self._finish_output('No system default speaker is available. Connect or enable an output device.')
        elif not self.devices.defaultAudioOutput().isNull() and time.monotonic() >= self._next_output_retry:
            self._open_output()

    def close(self):
        self.timer.stop()
        self.stop_input()
        self._finish_output()
