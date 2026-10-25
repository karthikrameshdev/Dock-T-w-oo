"""Bounded playback-reference echo reduction for local spoken stop controls.

The reference is the PCM actually sent to the speaker. Microphone audio and
reference samples stay in memory; neither is recorded or sent to a provider.
This is an echo suppressor, not a guarantee of acoustic isolation in every room.
"""
from __future__ import annotations

import threading
import time
import numpy as np


class PlaybackEchoGuard:
    def __init__(self):
        self._lock = threading.Lock()
        self._samples = np.zeros(0, dtype=np.float32)
        self._started = 0.0
        self._token = None
        self.last_similarity = 0.0
        self.suppressed_frames = 0

    def begin(self, pcm, rate, channels, token, started=None):
        samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32)
        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1)
        if rate != 16000 and len(samples):
            samples = np.interp(np.arange(round(len(samples)*16000/rate))*rate/16000,
                                np.arange(len(samples)), samples).astype(np.float32)
        with self._lock:
            self._samples, self._token = samples, token
            self._started = time.monotonic() if started is None else started

    def align(self, token, started):
        with self._lock:
            if token == self._token:
                self._started = started

    def clear(self):
        with self._lock:
            self._samples = np.zeros(0, dtype=np.float32)
            self._token = None

    def filter(self, pcm, captured_at=None):
        samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32)
        if not len(samples):
            return pcm
        captured_at = time.monotonic()-len(samples)/16000 if captured_at is None else captured_at
        with self._lock:
            reference, started = self._samples, self._started
        cursor = round((captured_at-started)*16000)
        lo, hi = max(0, cursor-6400), min(len(reference), cursor+1280+len(samples))
        self.last_similarity = 0.0
        if hi-lo < len(samples) or float(samples @ samples) < len(samples)*16:
            return pcm
        window = reference[lo:hi].astype(np.float64)
        mic = samples.astype(np.float64)
        mic -= mic.mean()
        energy = np.concatenate(([0.0], np.cumsum(window*window)))
        powers = energy[len(mic):]-energy[:-len(mic)]
        correlations = np.correlate(window, mic, mode='valid')
        scores = correlations**2 / np.maximum(1, powers*float(mic @ mic))
        offset = int(np.argmax(scores))
        self.last_similarity = float(np.sqrt(max(0, scores[offset])))
        if self.last_similarity < .35 or correlations[offset] <= 0:
            return pcm
        matched = window[offset:offset+len(mic)]
        gain = float(correlations[offset]/max(1, powers[offset]))
        if not .005 < gain < 4:
            return pcm
        residual = mic-gain*matched
        # A nearly identical delayed playback frame is echo, not a new command.
        # During double talk, retain the residual containing the user's voice.
        if self.last_similarity > .985:
            residual *= 0
            self.suppressed_frames += 1
        return np.clip(residual, -32768, 32767).astype('<i2').tobytes()

    def status(self):
        return {'reference_loaded': bool(len(self._samples)),
                'similarity': round(self.last_similarity, 3), 'suppressed_frames': self.suppressed_frames}
