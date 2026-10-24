"""Render the actual transparent Qt/WebGL companion without opening the microphone.

Requires the local Dock console server. Writes nine native overlay captures and a
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
parser.add_argument('--all-actions', action='store_true', help='Exercise every exported action in the actual renderer')
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
widget.reduced_motion = False
view = CharacterView(widget)
widget.show()
checks = [('front', 'idle', 0), ('blink_closed', 'idle', 0), ('eyes_reopened', 'idle', 0),
          ('speech', 'idle', 0), ('quarter', 'idle', .55), ('side_walk', 'walk', 1),
          ('wave', 'wave', 0), ('climb', 'climb', -.65), ('pull', 'pull_scroll', .2), ('magnifier', 'magnifier', 0),
          ('camera', 'camera', 0), ('read', 'read', 0), ('scan_code', 'scan_code', 0), ('fly', 'fly', .5)]
release=json.loads((Path(__file__).resolve().parents[1] / 'dock_twoo/server/static/brain3d/character.json').read_text())
if args.all_actions:
    covered={action for _label, action, _yaw in checks}
    checks += [('library_'+action,action,0) for action in release['actions'] if action not in covered]
checks += [('online','idle',0),('offline','idle',0),('listening','idle',0),('thinking','idle',0),('reduced_motion','dance',0)]
report = {'captures': [], 'errors': [], 'animation_probes': [], 'eye_pixels': {}}
phase_probe = None
probe_requested = False
ready_since = None
started = time.monotonic()
index = -1
phase_start = started

def inspect_result(raw):
    global report
    try:
        runtime = json.loads(raw)
        report['runtime'] = {key:value for key,value in runtime.items() if key != 'poseSignature'}
        report['average_render_fps'] = round(runtime['renderedFrames']/max(.01,time.monotonic()-ready_since),1)
        assert runtime['version'] == release['version'] and runtime['assetHash'] == release['asset_sha256']
        assert set(release['actions']) == set(runtime['clips'])
        assert view.version == release['version']
        assert set(ACTIONS).issubset(runtime['clips'])
        assert runtime['meshes'] >= 60
        assert runtime['speechMeshes'] == 4
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
    global index, phase_start, phase_probe, probe_requested, ready_since
    now = time.monotonic()
    if now - started > 90:
        report['errors'].append(view.error or 'Qt WebGL load timed out')
        inspect_result('{}')
        return
    if not view.ready:
        if view.error:
            timer.stop()
            report["errors"].append(view.error)
            inspect_result("{}")
        return
    if ready_since is None:
        ready_since = now
    if now-ready_since < 2:
        return
    if index < 0:
        index, phase_start = 0, now
    label, action, yaw = checks[index]
    widget.action, widget._yaw = action, yaw
    widget.gait_distance += 1.6
    widget.motion_started = phase_start
    widget.motion_duration = 1.6
    widget.blink_amount = 1.0 if label == 'blink_closed' else 0.0
    widget.activity = {'speech':'speaking','listening':'listening','thinking':'thinking'}.get(label,'idle')
    view.connectivity.online = label != 'offline'
    widget.reduced_motion = label == 'reduced_motion'
    widget.mouth_level = .7 if label == 'speech' else 0.0
    if now-phase_start > .3 and not probe_requested:
        probe_requested = True
        def first_probe(raw):
            global phase_probe
            phase_probe = json.loads(raw)
        view.page().runJavaScript('JSON.stringify(window.brainDiagnostics)', first_probe)
    if now - phase_start < .8:
        return
    capture = view.grab().toImage()
    assert not capture.isNull()
    path = args.output / (label + '.png')
    capture.save(str(path))
    if label in ('front', 'blink_closed', 'eyes_reopened'):
        logical = capture.scaled(264, 268)
        white_pixels = 0
        for y in range(65, 92):
            for x in range(104, 160):
                color = logical.pixelColor(x, y)
                white_pixels += color.green()>color.red()+25 and color.blue()>color.red()+25 and color.green()>140 and color.alpha()>200
        report['eye_pixels'][label] = white_pixels
        if (label == 'blink_closed' and white_pixels > 35) or (label != 'blink_closed' and white_pixels < 90):
            report['errors'].append(f'{label}: rendered eye pixels do not match the intended blink state')
    report['captures'].append(str(path))
    expected_label, expected_action, first = label, action, phase_probe
    def check_motion(raw):
        runtime = json.loads(raw)
        try:
            assert runtime['action'] == {'speech':'talk','listening':'listen','thinking':'ponder'}.get(expected_label,expected_action), f'{expected_label}: controller action did not reach renderer'
            if expected_label in ('online','offline','listening','thinking'):
                expected_colors={'online':0x22c55e,'offline':0xef4444,'listening':0xfacc15,'thinking':0xa855f7}
                assert runtime['indicator']['name']==expected_label
                assert runtime['indicator']['color']==expected_colors[expected_label], f'{expected_label}: incorrect antenna color'
            if expected_label in ('front', 'eyes_reopened'):
                assert min(runtime['eyeScales']) > .98, f'{expected_label}: eyes did not open'
            if expected_label == 'blink_closed':
                assert max(runtime['eyeScales']) < .04
            if expected_label == 'speech':
                assert runtime['mouth'] > .6, 'Speaking mouth morph did not reach renderer'
            expected_prop={'magnifier':'propmagnifier','camera':'propcamera','read':'proptablet','scan_code':'propscan','fly':'jetL'}.get(expected_label)
            if expected_prop:
                assert runtime['propScales'][expected_prop] > .2, f'{expected_label}: prop did not deploy'
            if expected_label in ('front','eyes_reopened'):
                assert max(runtime['propScales'].values()) < .002, 'Inactive props did not retract'
            if expected_label == 'reduced_motion':
                assert runtime['actionTime'] == 0, 'Reduced motion did not freeze the pose'
            elif expected_label.startswith('library_'):
                displacement=sum((x-y)**2 for x,y in zip(first['poseSignature'],runtime['poseSignature']))**.5
                assert displacement > .0001, f'{expected_label}: exported clip remained static'
                report['animation_probes'].append({'action':expected_action,'pose_change':round(displacement,4)})
            if expected_action in ('walk','wave','climb','pull_scroll'):

                a = sum(first['handPositions'], [])
                b = sum(runtime['handPositions'], [])
                displacement = sum((x-y)**2 for x,y in zip(a,b)) ** .5
                assert displacement > .01, f'{expected_label}: skeleton remained static'
                report['animation_probes'].append({'action':expected_action, 'hand_displacement':round(displacement,4)})
        except Exception as exc:
            report['errors'].append(str(exc))
    view.page().runJavaScript('JSON.stringify(window.brainDiagnostics)', check_motion)
    phase_probe, probe_requested = None, False
    index += 1
    phase_start = now
    if index == len(checks):
        timer.stop()
        view.page().runJavaScript('JSON.stringify(window.brainDiagnostics)', inspect_result)

timer = QTimer()
timer.timeout.connect(tick)
timer.start(33)
sys.exit(app.exec())
