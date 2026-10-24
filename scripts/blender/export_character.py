"""Export the saved artist-authored project without rebuilding or saving over it.

Blender --background character/MiniAssistant.blend --python this_file -- --version 3.0.0
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import bpy

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--version', required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
if not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
    raise ValueError('Use a semantic character version, for example 3.0.0')
source = Path(bpy.data.filepath)
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
rig = bpy.data.objects.get('Brain_Rig')
if rig is None or rig.type != 'ARMATURE':
    raise RuntimeError('The saved project must contain the Brain_Rig armature')
meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH' and
          any(mod.type == 'ARMATURE' and mod.object == rig for mod in obj.modifiers)]
if not meshes or 'idle' not in bpy.data.actions:
    raise RuntimeError('The saved project has no skinned meshes or idle action')
bpy.ops.object.select_all(action='DESELECT')
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
for obj in meshes:
    obj.select_set(True)
rig.animation_data.action = bpy.data.actions['idle']
bpy.context.scene.frame_set(0)
bpy.context.view_layer.update()
folder = ROOT / 'dock_twoo/server/static/brain3d'
folder.mkdir(parents=True, exist_ok=True)
path = folder / 'brain.glb'
bpy.ops.preferences.addon_enable(module='io_scene_gltf2')
options = dict(filepath=str(path), export_format='GLB', use_selection=True,
               export_skins=True, export_animations=True, export_animation_mode='ACTIONS',
               export_force_sampling=True, export_anim_single_armature=True,
               export_morph=True, export_morph_animation=True, export_extras=True,
               export_yup=True, export_cameras=False, export_lights=False)
supported = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
bpy.ops.export_scene.gltf(**{key: value for key, value in options.items() if key in supported})
fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
release = {
    'version': args.version, 'name': 'Brain', 'design': 'Glossy Blue',
    'source': str(source.relative_to(ROOT)), 'source_sha256': source_hash,
    'asset': 'brain.glb', 'asset_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
    'bones': len(rig.data.bones), 'meshes': len(meshes),
    'actions': {action.name: {'duration': round(float(action.frame_range[1] - action.frame_range[0])/fps, 4),
                             'loop': bool(action.get('looping', False))}
                for action in bpy.data.actions},
}
(folder / 'character.json').write_text(json.dumps(release, indent=2) + '\n')
report = json.loads((ROOT / 'character/character-build.json').read_text())
report.update(version=args.version, source_sha256=source_hash, glb_sha256=release['asset_sha256'])
(ROOT / 'character/character-build.json').write_text(json.dumps(report, indent=2) + '\n')
assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash, 'The artist source was modified'
print('BRAIN_RELEASE', json.dumps(release))
