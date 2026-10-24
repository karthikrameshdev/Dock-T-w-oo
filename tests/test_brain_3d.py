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
    assert set(ACTIONS) <= {clip['name'] for clip in gltf['animations']}
    assert len(gltf['skins']) == 1 and len(gltf['skins'][0]['joints']) == 37
    names = [node.get('name') for node in gltf['nodes']]
    assert names.count('Helmet') == 1 and names.count('Antenna bulb') == 1
    assert 'Neck titanium spindle' in names
    assert 'Eye white.L' in names and 'Eye white.R' in names and 'Speaking smile' in names
    assert not any('bag' in (name or '').lower() for name in names)
    assert all(mat.get('alphaMode', 'OPAQUE') == 'OPAQUE' for mat in gltf['materials'])
    assert [mesh['weights'] for mesh in gltf['meshes'] if 'weights' in mesh] == [[0]]
    for clip in gltf['animations']:
        assert clip['channels'] and all(channel['target']['node'] < len(names) for channel in clip['channels'])


def test_saved_animation_clearance_audit_passes_for_every_clip():
    audit = json.loads((ROOT / 'character/animation-validation.json').read_text())
    assert audit['blend_sha256'] == hashlib.sha256((ROOT / 'character/MiniAssistant.blend').read_bytes()).hexdigest()
    assert audit['glb_sha256'] == hashlib.sha256((ROOT / 'dock_twoo/server/static/brain3d/brain.glb').read_bytes()).hexdigest()
    assert audit['success'] and audit['intersections'] == []
    assert audit['clips'] == len(ACTIONS) + 2
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
