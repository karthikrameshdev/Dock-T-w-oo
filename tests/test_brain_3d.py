"""Validate the shipped rig contract rather than a second procedural character."""
import json
import hashlib
from pathlib import Path
import struct
from dock_twoo.brain.animation import ACTIONS

ROOT = Path(__file__).resolve().parents[1]


def test_exported_rig_covers_actions_and_uses_one_opaque_character():
    data = (ROOT / 'dock_twoo/server/static/brain3d/brain.glb').read_bytes()
    magic, version, length = struct.unpack_from('<4sII', data)
    assert magic == b'glTF' and version == 2 and length == len(data)
    size, kind = struct.unpack_from('<II', data, 12)
    assert kind == 0x4E4F534A
    gltf = json.loads(data[20:20 + size])
    assert set(ACTIONS)-{'handshake'} <= {clip['name'] for clip in gltf['animations']}
    assert len(gltf['skins']) == 1 and len(gltf['skins'][0]['joints']) == 58
    names = [node.get('name') for node in gltf['nodes']]
    assert names.count('Helmet') == 1 and names.count('Antenna bulb') == 1
    assert 'Neck titanium spindle' in names
    assert 'Eye white.L' in names and 'Eye white.R' in names and 'Speaking smile' in names
    assert not any('bag' in (name or '').lower() for name in names)
    assert all(mat.get('alphaMode', 'OPAQUE') == 'OPAQUE' for mat in gltf['materials'])
    morphs = [mesh for mesh in gltf['meshes'] if 'weights' in mesh]
    assert len(morphs) == 4
    assert all(all(weight == 0 for weight in mesh['weights']) for mesh in morphs)
    assert 'Tongue' in names and 'Upper teeth' in names and 'Mouth cavity' in names
    assert {'Magnifier handle', 'Camera blue body', 'Reading tablet screen'} <= set(names)
    talk = next(clip for clip in gltf['animations'] if clip['name'] == 'talk')
    assert sum(channel['target']['path'] == 'weights' for channel in talk['channels']) == 4
    for clip in gltf['animations']:
        assert clip['channels'] and all(channel['target']['node'] < len(names) for channel in clip['channels'])


def test_saved_animation_clearance_audit_passes_for_every_clip():
    audit = json.loads((ROOT / 'character/animation-validation.json').read_text())
    assert audit['blend_sha256'] == hashlib.sha256((ROOT / 'character/Brain.blend').read_bytes()).hexdigest()
    assert audit['glb_sha256'] == hashlib.sha256((ROOT / 'dock_twoo/server/static/brain3d/brain.glb').read_bytes()).hexdigest()
    assert audit['success'] and audit['intersections'] == []
    assert audit['clips'] == len(ACTIONS)  # handshake is a separately verified runtime clip
    assert audit['frames'] > 1500 and audit['transition_samples'] > 300


def test_repeated_blinks_reopen_eyes_with_the_real_three_animation_mixer():
    import shutil
    import subprocess
    import pytest
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is needed for the Three.js animation regression')
    result = subprocess.run([node, str(ROOT / 'scripts/verify_brain_face.mjs')], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_character_release_identifies_the_exact_saved_source_and_runtime():
    release = json.loads((ROOT / 'dock_twoo/server/static/brain3d/character.json').read_text())
    assert release['version'] == '3.1.0'
    assert release['source_sha256'] == hashlib.sha256((ROOT / release['source']).read_bytes()).hexdigest()
    assert release['asset_sha256'] == hashlib.sha256((ROOT / 'dock_twoo/server/static/brain3d' / release['asset']).read_bytes()).hexdigest()
    assert set(ACTIONS)-{'handshake'} <= release['actions'].keys()
    assert len(release['actions']) == 50 and release['bones'] == 58
    assert all(clip['duration'] > 0 for clip in release['actions'].values())


def test_every_named_animation_can_be_requested_without_triggering_ball_play():
    from types import SimpleNamespace
    from dock_twoo.brain.commands import handle_voice_command
    calls = []
    manager = SimpleNamespace(companion=SimpleNamespace(play_action=calls.append))
    for action in ACTIONS:
        assert handle_voice_command('Brain, play the ' + action.replace('_',' ') + ' animation', manager)
    assert calls == list(ACTIONS)


def test_demo_playlist_includes_every_current_character_action_once():
    from dock_twoo.brain.animation import PLAYLIST
    assert set(PLAYLIST) == set(ACTIONS)
    assert len(PLAYLIST) == len(set(PLAYLIST))


def test_saved_toy_contacts_match_this_source_and_export():
    audit=json.loads((ROOT/'character/prop-animation-validation.json').read_text())
    assert audit['success'] and not audit['issues']
    assert audit['blend_sha256']==hashlib.sha256((ROOT/'character/Brain.blend').read_bytes()).hexdigest()
    assert audit['glb_sha256']==hashlib.sha256((ROOT/'dock_twoo/server/static/brain3d/brain.glb').read_bytes()).hexdigest()
    assert audit['ball_contact_frame']<audit['ball_launch_frame']
    assert abs(audit['ball_contact_gap'])<.002
    assert all(abs(hit['gap'])<.025 for hit in audit['hammer_contacts'])
    assert audit['maximum_grip_error']<.01 and audit['samples']>500


def test_real_three_mixer_preserves_ball_contact_and_retracts_toys():
    import shutil,subprocess,pytest
    node=shutil.which('node')
    if node is None:pytest.skip('Node is needed for Three.js export validation')
    result=subprocess.run([node,str(ROOT/'scripts/verify_brain_props.mjs')],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def test_loading_and_renderer_failure_cannot_draw_an_older_character(qtbot,tmp_path):
    from types import SimpleNamespace
    from PySide6.QtGui import QImage
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget
    from dock_twoo.brain.mascot import Companion
    from dock_twoo.brain.storage import BrainStore
    companion=Companion(SimpleNamespace(store=BrainStore(tmp_path)))
    qtbot.addWidget(companion)
    companion.set_renderer_status('')
    for ready,error in ((False,''),(False,'WebGL failed'),(True,'')):
        companion.model_view=SimpleNamespace(ready=ready,error=error)
        image=QImage(companion.size(),QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
        companion.render(image)
        assert all(image.pixelColor(x,y).alpha()==0 for x in range(image.width()) for y in range(image.height()))
    assert not hasattr(companion,'art_front') and not hasattr(companion,'_paint_robot')
    assert not list((ROOT/'dock_twoo/assets').rglob('robot-*.png'))
