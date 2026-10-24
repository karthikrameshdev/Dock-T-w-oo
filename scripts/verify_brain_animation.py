"""Render a deterministic turn/walk/reverse/inspect/climb sequence without audio.

Writes a contact sheet, a transition report, and (when ffmpeg is installed) a
video under /tmp. No application windows or user settings are changed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
import dock_twoo.brain.mascot as mascot
from dock_twoo.brain.profiles import ProfileManager
from dock_twoo.brain.storage import BrainStore


def main() -> int:
    app = QApplication([])
    clock = [100.0]
    mascot.time = SimpleNamespace(monotonic=lambda: clock[0])
    output = Path('/tmp') if Path('/tmp').is_dir() else Path(tempfile.gettempdir())
    with tempfile.TemporaryDirectory(prefix='brain-animation-') as folder:
        root = Path(folder)
        store = BrainStore(root / 'store')
        robot = mascot.Companion(SimpleNamespace(store=store, profile_mgr=ProfileManager(store)))
        robot.show()
        for timer in (robot.activity_timer, robot.motion_timer, robot.blink_timer,
                      robot.roam_timer, robot.follow_timer):
            timer.stop()
        robot.move(100, 200)
        start = robot.pos()
        events, samples, frames = [], [], []
        done = [None]

        def event(name):
            events.append({'stage': name, 'seconds': round(clock[0] - 100, 2)})

        def finished():
            event('idle')
            done[0] = len(frames)

        def climb():
            event('climb')
            robot.play_action('climb', robot.pos() - QPoint(0, 40), duration=1.6)
            robot.arrival = lambda: robot.turn_to_user(on_turned=finished)

        def return_left():
            event('walk left')
            robot.play_action('walk_window', start, duration=1.6)
            robot.arrival = lambda: robot.turn_to_user(on_turned=climb)

        def inspect():
            event('inspect left')
            robot.play_action('inspect_window', duration=1.2, keep_orientation=True)
            robot.arrival = return_left

        def walk_right():
            event('walk right')
            robot.play_action('walk_window', start + QPoint(150, 0), duration=1.6)
            robot.arrival = lambda: robot.turn_to_side(-1, on_turned=inspect)

        previous = 0.0
        for index in range(600):
            clock[0] += 1 / 30
            if index == 15:
                event('turn right')
                robot.turn_to_side(1, on_turned=walk_right)
            robot._advance_motion()
            assert abs(robot._yaw - previous) <= 2.8 / 30 + .011
            previous = robot._yaw
            image = QImage(720, 340, QImage.Format.Format_RGB32)
            image.fill(QColor('#1c2230'))
            painter = QPainter(image)
            frame = QImage(robot.size(), QImage.Format.Format_ARGB32)
            frame.fill(0)
            robot.render(frame)
            delta = robot.pos() - start
            painter.drawImage(160 + delta.x(), 30 + delta.y(), frame)
            painter.setPen(QColor('#dbe5f3'))
            painter.drawText(20, 24, f"{events[-1]['stage'] if events else 'idle'}  ·  yaw {robot._yaw:.2f}")
            painter.end()
            image.save(str(root / f'frame-{index:04}.png'))
            frames.append(image)
            samples.append({'seconds': round(clock[0] - 100, 3), 'yaw': round(robot._yaw, 4),
                            'action': robot.action, 'x': robot.x(), 'y': robot.y()})
            if done[0] is not None and index - done[0] >= 20:
                break

        assert [entry['stage'] for entry in events] == [
            'turn right', 'walk right', 'inspect left', 'walk left', 'climb', 'idle']
        assert robot._yaw == 0 and robot.action is None
        sheet = QImage(720 * 3, 340 * 3, QImage.Format.Format_RGB32)
        painter = QPainter(sheet)
        for cell in range(9):
            chosen = round(cell / 8 * (len(frames) - 1))
            painter.drawImage((cell % 3) * 720, (cell // 3) * 340, frames[chosen])
        painter.end()
        sheet.save(str(output / 'dock-twoo-animation-contact-sheet.png'))
        report = {'success': True, 'frames': len(frames), 'events': events, 'samples': samples}
        (output / 'dock-twoo-animation-check.json').write_text(json.dumps(report, indent=2))
        if shutil.which('ffmpeg'):
            subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-framerate', '30',
                            '-i', str(root / 'frame-%04d.png'), '-c:v', 'libx264',
                            '-pix_fmt', 'yuv420p', str(output / 'dock-twoo-animation-flow.mp4')], check=True)
        robot.close()
        print(json.dumps({'success': True, 'frames': len(frames), 'events': events}, indent=2))
        print(f'Contact sheet and video: {output}/dock-twoo-animation-*')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
