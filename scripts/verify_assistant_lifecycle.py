"""Isolated resident lifecycle stress; no microphone, speakers, models or network.

Exercises actual manager, Qt dock controls, ASR capture generations and queued
worker completions. The fake recognizer/provider deliberately ignore cancellation
until released, reproducing results arriving after Close and a fast Open.
Use --cycles 500 for repeated lifecycle and Python/process memory measurements.
Native WebEngine/GPU resources are covered by verify_resident_stability.py.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import tracemalloc
from types import SimpleNamespace

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['PYTEST_CURRENT_TEST'] = 'assistant-lifecycle-soak'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from dock_twoo.brain.agent import BrainAgent
from dock_twoo.brain.local_tts import get_local_tts
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.config import ConfigManager
import dock_twoo.config as config_module
from dock_twoo.displays import display_inventory
from dock_twoo.os_integration.margin_manager import DesktopMarginManager
from dock_twoo.ui.dock_window import DockWindow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycles', type=int, default=200)
    parser.add_argument('--output', type=Path, default=Path(tempfile.gettempdir()) / 'dock-assistant-lifecycle.json')
    args = parser.parse_args()
    if args.cycles < 30:
        parser.error('--cycles must be at least 30 (20 warm-up cycles)')
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    counts = {'input_opened': 0, 'input_closed': 0, 'provider_calls': 0, 'asr_calls': 0,
              'stale_callbacks': 0, 'dock_clicks': 0}
    samples = []
    process = psutil.Process()
    started = time.monotonic()
    manager = dock = None
    signals = []
    old_run = BrainAgent.run

    def pump_until(predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                raise AssertionError('Timed out waiting for an isolated worker/Qt completion')
            app.processEvents()
            time.sleep(.001)
        app.processEvents()

    try:
        with tempfile.TemporaryDirectory(prefix='dock-lifecycle-') as directory:
            root = Path(directory)
            os.environ['DOCK_TWOO_BRAIN_DATA_DIR'] = str(root / 'storage' / 'voice')
            config = ConfigManager(root / 'config.json')
            config.config.storage_path = str(root / 'storage')
            config.config.reserve_screen_space = False
            config_module.ConfigManager = lambda: config
            DesktopMarginManager.start = lambda self: None
            manager = BrainManager(store=BrainStore(root / 'storage' / 'voice'), start_services=False)
            BrainManager._instance = manager
            manager.store.update_settings({'roaming': False, 'voice_reply': False, 'character_sounds': False})
            entries = display_inventory()
            manager.configure_displays(entries[:1], entries)
            manager.semantic_model.start = lambda: None
            manager.shortcut_listener.start = lambda: None
            get_local_tts().start = lambda: None
            # The real lifecycle runs, but the input hardware is a disposable
            # route with no device or inference process behind it.
            def close_source():
                counts['input_closed'] += 1
            def open_source():
                counts['input_opened'] += 1
                manager.audio_devices.source = SimpleNamespace(stop=close_source, deleteLater=lambda: None)
                manager.audio_devices.input_io = object()
            manager.audio_devices._open_input = open_source
            def start_listener():
                if manager.listener.closed or manager.listener.is_running:
                    return
                manager.listener.is_running = True
                manager.audio_devices.start_input()
            manager.listener.start = start_listener
            manager._services_enabled = True
            # Never probe actual foreground windows from a timer.
            manager.reader.backend.remember_frontmost = lambda: None
            manager.listener.start()
            dock = DockWindow(config, screen_id=entries[0]['id'])
            dock.show()
            app.processEvents()
            pending = {}

            def provider(_self, _text, **kwargs):
                counts['provider_calls'] += 1
                pending['cancel'] = kwargs['cancel']
                pending['model_entered'].set()
                pending['release'].wait(5)
                return 'Stale response that must never be spoken.'
            BrainAgent.run = provider

            def transcribe(_pcm):
                counts['asr_calls'] += 1
                pending['asr_entered'].set()
                pending['release'].wait(5)
                pending['asr_done'].set()
                return 'Brain, execute this stale statement.'
            manager.listener._transcribe_pcm = transcribe
            tracemalloc.start(5)

            for cycle in range(args.cycles):
                pending = {name: threading.Event() for name in ('model_entered', 'asr_entered', 'asr_done', 'release')}
                signals.append(pending['release'])
                manager.show_mini_agent()
                assert manager.assistant_available and manager.is_mini_agent_visible()
                manager.hide_mini_agent()
                assert not manager.assistant_closed and manager.listener._wake_armed
                assert manager.audio_devices._want_input
                manager.show_mini_agent()
                manager._queue_turn('Analyze the lifecycle fixture', source='console')
                assert pending['model_entered'].wait(1)
                manager.start_talking()
                manager.listener.speech_frames = [bytes(3200)] * 3
                manager.listener.has_spoken = True
                manager.listener._endpoint.speech = .3
                manager.listener.stop_recording()
                assert pending['asr_entered'].wait(1)
                # Queue on a worker without giving Qt a chance to dispatch it.
                worker = threading.Thread(target=lambda: manager._dispatch_assistant_callback(
                    lambda: counts.__setitem__('stale_callbacks', counts['stale_callbacks'] + 1)))
                worker.start()
                worker.join(1)
                generation = manager.last_response['generation']
                manager.close_assistant()
                assert pending['cancel'].is_set()
                assert not manager.is_mini_agent_visible() and not manager.assistant_available
                assert not manager.listener.is_recording and not manager.listener.is_running
                assert not manager.audio_devices._want_input and manager.audio_devices.source is None
                assert not manager.audio_devices.timer.isActive()
                manager._on_named_turn_completed('default', 'stale', 'Brain stale', False)
                manager.speech.start('Late speech should be ignored')
                assert not manager._turn_queue and manager.speech._pending_speech is None
                # Real Qt dock app selection/close remains responsive with the
                # entire assistant/audio lane unavailable.
                QTest.mouseClick(dock._icon_buttons['notes'], Qt.MouseButton.LeftButton)
                assert dock.attached_window.is_showing_app('notes')
                dock.attached_window.hide_window()
                counts['dock_clicks'] += 1
                manager.show_mini_agent()
                assert manager.assistant_available and manager.audio_devices._want_input
                pending['release'].set()
                pump_until(lambda: not manager._processing_turns and pending['asr_done'].is_set())
                assert manager.last_response['generation'] == generation
                assert not manager._reply_queue and counts['stale_callbacks'] == 0
                assert len(manager.companions) == 1
                signals.clear()
                if cycle == 19 or (cycle + 1) % 25 == 0 or cycle == args.cycles - 1:
                    gc.collect()  # GUI-thread collection measures retained objects.
                    current, peak = tracemalloc.get_traced_memory()
                    samples.append({'cycle': cycle + 1, 'python_bytes': current, 'python_peak': peak,
                                    'rss_bytes': process.memory_info().rss, 'threads': threading.active_count()})
                    print(json.dumps(samples[-1]), flush=True)

            manager.close_assistant()
            report = {'success': True, 'cycles': args.cycles, 'seconds': round(time.monotonic() - started, 2),
                      **counts, 'samples': samples, 'python_retained_growth_bytes': samples[-1]['python_bytes'] - samples[0]['python_bytes'],
                      'rss_growth_bytes': samples[-1]['rss_bytes'] - samples[0]['rss_bytes'],
                      'real_microphone_opened': False, 'real_speaker_opened': False, 'external_model_calls': 0,
                      'limits': 'Offscreen Qt lifecycle stress; excludes native GPU rendering and long real-model inference.'}
            assert report['python_retained_growth_bytes'] < 8 * 1024 * 1024, report
            assert samples[-1]['threads'] <= samples[0]['threads'] + 2, report
            args.output.write_text(json.dumps(report, indent=2))
            print(json.dumps({key: value for key, value in report.items() if key != 'samples'}), flush=True)
            dock.close()
            manager.shutdown()
            dock = manager = None
    finally:
        for release in signals:
            release.set()
        BrainAgent.run = old_run
        if dock:
            dock.close()
        if manager:
            manager.shutdown()
        tracemalloc.stop()


if __name__ == '__main__':
    main()
