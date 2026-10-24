"""Render the actual transparent Qt/WebGL companion without opening the microphone.

Requires the local Dock console server. Writes six native overlay captures and a
runtime report to /tmp/dock-twoo-3d-check (or --output).
"""
import argparse
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget
from dock_twoo.brain.animation import ACTIONS
from dock_twoo.brain.model_view import CharacterView

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, default=Path('/tmp/dock-twoo-3d-check'))
args = parser.parse_args()
args.output.mkdir(exist_ok=True, parents=True)
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app = QApplication([])
widget = QWidget()
widget.setWindowTitle('Brain 3D verification')
widget.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus)
widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
widget.resize(264, 268)
widget.action, widget._yaw, widget.motion_started, widget.motion_duration = None, 0., time.monotonic(), 100
widget.gait_distance, widget.blink_amount, widget.mouth_level = 0., 0., 0.
widget.activity, widget._gaze_offset = 'idle', QPointF()
view = CharacterView(widget)
widget.show()
checks = [('front', 'idle', 0), ('quarter', 'idle', .55), ('side_walk', 'walk', 1),
          ('wave', 'wave', 0), ('climb', 'climb', -.65), ('pull', 'pull_scroll', .2)]
report = {'captures': [], 'errors': []}
started = time.monotonic()
index = -1
phase_start = started

def inspect_result(raw):
    global report
    try:
        runtime = json.loads(raw)
        report['runtime'] = runtime
        assert set(ACTIONS).issubset(runtime['clips'])
        assert runtime['meshes'] >= 60
        assert runtime['renderedFrames'] > 10
        assert not runtime['nonFinite'] and not runtime['translucent']
    except Exception as exc:
        report['errors'].append(str(exc))
    report['success'] = not report['errors']
    (args.output / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    widget.close()
    app.exit(0 if report['success'] else 1)

def tick():
    global index, phase_start
    now = time.monotonic()
    if now - started > 35:
        report['errors'].append(view.error or 'Qt WebGL load timed out')
        inspect_result('{}')
        return
    if not view.ready:
        return
    if index < 0:
        index, phase_start = 0, now
    label, action, yaw = checks[index]
    widget.action, widget._yaw = action, yaw
    widget.gait_distance += 1.6
    widget.motion_started = now - .5
    widget.motion_duration = 1.0
    if now - phase_start < .8:
        return
    capture = view.grab().toImage()
    assert not capture.isNull()
    path = args.output / (label + '.png')
    capture.save(str(path))
    report['captures'].append(str(path))
    index += 1
    phase_start = now
    if index == len(checks):
        timer.stop()
        view.page().runJavaScript('JSON.stringify(window.brainDiagnostics)', inspect_result)

timer = QTimer()
timer.timeout.connect(tick)
timer.start(33)
sys.exit(app.exec())
