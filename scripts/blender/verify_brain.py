"""Audit the saved rig at every frame and during idle/action blends.

Run Blender --background characters/default/default.blend --python this_file.
Uses the same conservative helmet/ear/arm envelopes as the builder. This catches
intersections between animation keys, not just the authored key poses.
"""
import ast
import json
import hashlib
import math
from pathlib import Path
import bpy

REPO = Path(__file__).resolve().parents[2]
rig = bpy.data.objects['Brain_Rig']
armature = rig.data
source = ast.parse((REPO / 'scripts/blender/rig_helpers.py').read_text())
function = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == 'limb_collisions')
exec(compile(ast.Module(body=[function], type_ignores=[]), '<clearance>', 'exec'))
HEAD_RISE = next(ast.literal_eval(node.value) for node in source.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'HEAD_RISE' for target in node.targets))
scene = bpy.context.scene
issues, frames, blends = [], 0, 0
for action in bpy.data.actions:
    rig.animation_data.action = action
    for frame in range(math.ceil(action.frame_range[0]), math.floor(action.frame_range[1]) + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        frames += 1
        for side in ('L', 'R'):
            if limb_collisions(side):
                issues.append({'clip': action.name, 'frame': frame, 'side': side})
    # Simulate the runtime's shortest-quaternion crossfade from a neutral pose.
    for fraction in (.25, .5, .75):
        scene.frame_set(round(action.frame_range[1] * fraction))
        poses = {bone.name: (bone.rotation_quaternion.copy(), bone.location.copy(), bone.scale.copy()) for bone in rig.pose.bones}
        rig.animation_data.action = None
        for blend in (.25, .5, .75):
            from mathutils import Quaternion, Vector
            for bone in rig.pose.bones:
                rotation, position, scale = poses[bone.name]
                bone.rotation_quaternion = Quaternion().slerp(rotation, blend)
                bone.location = position * blend
                bone.scale = Vector((1, 1, 1)).lerp(scale, blend)
            bpy.context.view_layer.update()
            blends += 1
            for side in ('L', 'R'):
                if limb_collisions(side):
                    issues.append({'clip': action.name, 'fraction': fraction, 'blend': blend, 'side': side})
        rig.animation_data.action = action
report = {'blend_sha256': hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),
          'glb_sha256': hashlib.sha256((REPO / 'dock_twoo/server/static/brain3d/brain.glb').read_bytes()).hexdigest(),
          'success': not issues, 'clips': len(bpy.data.actions), 'frames': frames,
          'transition_samples': blends, 'intersections': issues}
path = REPO / 'characters/default/animation-validation.json'
path.write_text(json.dumps(report, indent=2) + '\n')
print('BRAIN_ANIMATION_VALIDATION', json.dumps(report))
if issues:
    raise RuntimeError(f'{len(issues)} arm/helmet intersections found')
