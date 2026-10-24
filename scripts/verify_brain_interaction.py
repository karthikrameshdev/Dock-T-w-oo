"""Verify wake -> Mini Agent -> audible greeting -> spoken command -> audible reply.

Uses cached models and generated PCM, a temporary Brain store, and real audio
output. It never opens an input stream or changes the user's Brain settings.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.os_integration.screen_manager import ScreenManager


def main() -> int:
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    ScreenManager.configure_macos_accessory()
    model_dir = BrainStore().data_dir / 'models'
    with tempfile.TemporaryDirectory(prefix='brain-interaction-check-') as folder:
        manager = BrainManager(store=BrainStore(Path(folder) / 'store'), start_services=False,
                               voice_model_dir=model_dir)
        manager.companion.hide()
        assert manager.listener.wake_detector.load(allow_download=False), manager.listener.wake_detector.error
        assert manager.listener.models.recognizer.load(allow_download=False), manager.listener.models.recognizer.error
        manager.listener.arm_wake()
        clips = []
        for index, text in enumerate(('Brain', 'What time is it?')):
            path = Path(folder) / f'{index}.wav'
            subprocess.run(['say', '-v', 'Samantha', '-o', str(path), '--file-format=WAVE',
                            '--data-format=LEI16@16000', '--', text], check=True, capture_output=True)
            with wave.open(str(path), 'rb') as source:
                clips.append(bytes(12800) + source.readframes(source.getnframes()) + bytes(64000))
        result = {'success': False, 'speech_completions': 0}
        current = [clips[0], 0]
        timer = QTimer()
        timer.setInterval(100)

        def feed():
            pcm, offset = current
            if offset >= len(pcm):
                timer.stop()
                return
            manager.listener._handle_pcm_frame(pcm[offset:offset + 3200])
            current[1] += 3200

        def command():
            current[:] = [clips[1], 0]
            timer.start()

        def finished():
            result['speech_completions'] += 1
            if result['speech_completions'] == 1:
                QTimer.singleShot(400, command)
            else:
                result.update(
                    success=(manager.companion.isVisible() and manager.listener.is_recording and not manager.speech.last_error
                             and len(manager.conversation_history) == 2
                             and 'time' in manager.conversation_history[0]['content'].lower()
                             and manager.conversation_history[1]['role'] == 'assistant'),
                    companion_visible=manager.companion.isVisible(),
                    resumed_listening=manager.listener.is_recording,
                    microphone_opened=manager.listener.stream is not None,
                    output_error=manager.speech.last_error,
                    wake_matches=manager.listener.last_wake_matches,
                    turns=[dict(turn) for turn in manager.conversation_history],
                )
                app.quit()

        def timeout():
            result['error'] = 'The interaction did not complete within 30 seconds.'
            result['stage'] = manager.listener.last_wake_decision
            app.quit()

        timer.timeout.connect(feed)
        manager.speech.finished.connect(finished)
        QTimer.singleShot(30000, timeout)
        timer.start()
        app.exec()
        timer.stop()
        manager.stop_talking()
        manager.companion.close()
        report = Path('/tmp/dock-twoo-interaction-check.json')
        report.write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        print(f'Report: {report}')
        return int(not result['success'])


if __name__ == '__main__':
    raise SystemExit(main())
