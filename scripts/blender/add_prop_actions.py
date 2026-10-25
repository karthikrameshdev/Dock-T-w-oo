"""Add contact-based toy performances to the saved Brain, preserving its design.

blender --background character/Brain.blend --python scripts/blender/add_prop_actions.py
Run export_character.py afterward to publish the saved source to the application.
"""
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import shutil

import bpy
from mathutils import Vector, Quaternion
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[2]
source_path = Path(bpy.data.filepath)
assert source_path.name == 'Brain.blend', 'Open the renamed saved project first.'
backup_dir = Path(os.environ.get('BRAIN_CHARACTER_BACKUP_DIR', str(Path.home()/'.dock-twoo/character-backups')))
backup_dir.mkdir(parents=True, exist_ok=True)
backup = backup_dir/('Brain-'+hashlib.sha256(source_path.read_bytes()).hexdigest()[:12]+'.blend')
if not backup.exists():
    shutil.copy2(source_path, backup)
scene = bpy.context.scene
rig = bpy.data.objects['Brain_Rig']
armature = rig.data
HEAD_RISE = .34
objects, bindings = [], {}

# Reuse mesh and IK helpers, without executing the destructive design builder.
builder = ast.parse((ROOT/'scripts/blender/rig_helpers.py').read_text())
helpers = {'finish', 'sphere', 'rounded_box', 'cylinder', 'torus', 'curve',
           'rotation', 'leg', 'limb_collisions', 'clear_arms', 'arm_target'}
exec(compile(ast.Module(body=[node for node in builder.body if isinstance(node, ast.FunctionDef)
                             and node.name in helpers], type_ignores=[]), '<prop helpers>', 'exec'))


for obj in list(bpy.data.objects):
    if obj.name.startswith('Brain toy '):
        bpy.data.objects.remove(obj, do_unlink=True)
old_meshes = [obj for obj in scene.objects if obj.type == 'MESH']
def geometry_hash(meshes):
    digest = hashlib.sha256()
    for obj in sorted(meshes, key=lambda item: item.name):
        digest.update(obj.name.encode())
        for vertex in obj.data.vertices:
            digest.update(str(tuple(vertex.co)).encode())
    return digest.hexdigest()
original_geometry = geometry_hash(old_meshes)

bpy.ops.object.select_all(action='DESELECT')
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='EDIT')
specs = [('prop.ball', (0, 0, 0), 'root'),
         ('prop.hammer', (1.14, -.055, 1.33), 'hand.L'),
         ('prop.anvil', (1.25, -.45, 0), 'root'),
         ('prop.tether', (1.14, -.055, 1.33), 'hand.L'),
         ('prop.balloon', (1.65, -.055, 2.71), 'prop.tether'),
         ('prop.parachute', (0, 0, 0), 'root')]
for name, origin, parent in specs:
    bone = armature.edit_bones.get(name) or armature.edit_bones.new(name)
    bone.head, bone.tail = origin, Vector(origin)+Vector((0, 0, .1))
    bone.parent = armature.edit_bones[parent]
bpy.ops.object.mode_set(mode='OBJECT')

blue = bpy.data.materials.get('Brain toy cobalt') or bpy.data.materials.new('Brain toy cobalt')
blue.use_nodes = True
shader = blue.node_tree.nodes.get('Principled BSDF')
shader.inputs['Base Color'].default_value = (.015, .27, .48, 1)
shader.inputs['Metallic'].default_value = .35
shader.inputs['Roughness'].default_value = .23
blue.diffuse_color = (.015, .27, .48, 1)
silver = bpy.data.materials['Pearl silver ceramic']
metal = bpy.data.materials['Brushed titanium']
rubber = bpy.data.materials['Rubber joint seals']
light = bpy.data.materials['Electric cyan light']
ball = sphere('Brain toy ball', (0, 0, 0), (.23,)*3, silver, 'prop.ball', 40)
for index, angles in enumerate(((0, 0, 0), (math.pi/2, 0, 0), (0, math.pi/2, 0))):
    torus('Brain toy ball seam '+str(index), (0, 0, 0), .229, .012, blue, 'prop.ball', angles)
sphere('Brain toy ball center badge', (0, -.229, 0), (.07, .012, .07), blue, 'prop.ball')

cylinder('Brain toy hammer handle', (1.14, -.055, 1.10), (1.14, -.055, 1.89), .047, metal, 'prop.hammer')
cylinder('Brain toy hammer grip', (1.14, -.055, 1.16), (1.14, -.055, 1.49), .064, rubber, 'prop.hammer')
for index in range(5):
    torus('Brain toy hammer grip ring '+str(index), (1.14, -.055, 1.18+index*.065), .064, .009, blue, 'prop.hammer')
hammer = rounded_box('Brain toy hammer head', (1.14, -.055, 1.89), (.60, .24, .20), .035, metal, 'prop.hammer')
for sign in (-1, 1):
    rounded_box('Brain toy hammer striking face '+str(sign), (1.14+sign*.29, -.055, 1.89), (.06, .25, .21), .02, silver, 'prop.hammer')
cylinder('Brain toy stand base', (1.25, -.45, .04), (1.25, -.45, .14), .30, rubber, 'prop.anvil')
cylinder('Brain toy stand column', (1.25, -.45, .14), (1.25, -.45, 1.05), .11, blue, 'prop.anvil')
stand = rounded_box('Brain toy stand contact pad', (1.25, -.45, 1.12), (.68, .48, .24), .035, silver, 'prop.anvil')

sphere('Brain toy balloon', (1.65, -.055, 3.13), (.31, .29, .42), blue, 'prop.balloon', 40)
cylinder('Brain toy balloon knot', (1.65, -.055, 2.69), (1.65, -.055, 2.75), .035, rubber, 'prop.balloon', .015)
tether = curve('Brain toy balloon tether', [(1.14, -.055, 1.33), (1.36, -.055, 1.96), (1.65, -.055, 2.71)], .012, silver, 'prop.tether')

# A curved, opaque fabric canopy and suspension lines share one moving rig.
verts, faces = [], []
for ring in range(13):
    radius = 1.65*ring/12
    for segment in range(48):
        angle = math.tau*segment/48
        verts.append((radius*math.cos(angle), radius*.62*math.sin(angle),
                      4.90+.55*math.sqrt(max(0, 1-(radius/1.65)**2))))
for ring in range(12):
    for segment in range(48):
        a = ring*48+segment; b = ring*48+(segment+1)%48
        faces.append((a, b, b+48, a+48))
mesh = bpy.data.meshes.new('Brain toy canopy fabric'); mesh.from_pydata(verts, [], faces); mesh.update()
canopy = bpy.data.objects.new('Brain toy parachute canopy', mesh); scene.collection.objects.link(canopy)
finish(canopy, canopy.name, blue, 'prop.parachute'); canopy.data.materials.append(silver)
for index, polygon in enumerate(canopy.data.polygons):
    polygon.material_index = (index % 48)//6 % 2
for sign, side in ((1, 'L'), (-1, 'R')):
    for depth in (-.55, .55):
        curve('Brain toy suspension '+side+str(depth), [(sign*1.17, -.35, 2.30),
              (sign*1.32, depth*.7, 3.6), (sign*1.48, math.copysign(.452, depth), 4.90)], .013, silver, 'prop.parachute')

for obj in objects:
    bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True); bpy.context.view_layer.objects.active = obj
    for modifier in list(obj.modifiers): bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    group = obj.vertex_groups.new(name=bindings[obj.name])
    group.add(list(range(len(obj.data.vertices))), 1, 'REPLACE')
    modifier = obj.modifiers.new('Brain skeleton', 'ARMATURE'); modifier.object = rig; obj.parent = rig
    if obj is tether:
        top = obj.vertex_groups.new(name='prop.balloon')
        for vertex in obj.data.vertices:
            fraction = max(0, min(1, (vertex.co.z-1.33)/1.38))
            group.add([vertex.index], 1-fraction, 'REPLACE'); top.add([vertex.index], fraction, 'REPLACE')

new_bones = [name for name, _origin, _parent in specs]
# Explicit hidden tracks prevent a previous toy leaking into another action.
for action in list(bpy.data.actions):
    if action.name in ('kick_ball', 'hammer', 'balloon', 'parachute'):
        bpy.data.actions.remove(action)
        continue
    rig.animation_data.action = action
    for name in new_bones:
        joint = rig.pose.bones[name]
        joint.location = (0, 0, 0); joint.rotation_mode = 'QUATERNION'; joint.rotation_quaternion = Quaternion()
        for frame in (0, int(action.frame_range[1])):
            joint.scale = (.001,)*3
            for prop in ('location', 'rotation_quaternion', 'scale'): joint.keyframe_insert(prop, frame=frame, group=name)

def reset():
    for joint in rig.pose.bones:
        joint.rotation_mode = 'QUATERNION'; joint.rotation_quaternion = Quaternion(); joint.location = (0, 0, 0)
        joint.scale = (.001,)*3 if joint.name.startswith(('prop.', 'jet.')) else (1, 1, 1)

def smooth(value):
    value = max(0, min(1, value)); return value*value*(3-2*value)

def curve_value(points, p):
    if p <= points[0][0]: return points[0][1:]
    for first, last in zip(points, points[1:]):
        if p <= last[0]:
            weight = smooth((p-first[0])/(last[0]-first[0]))
            return tuple(a+(b-a)*weight for a, b in zip(first[1:], last[1:]))
    return points[-1][1:]

def orient_world(name, desired):
    joint = rig.pose.bones[name]; bpy.context.view_layer.update()
    parent = joint.parent.matrix @ joint.parent.bone.matrix_local.inverted()
    rest = joint.bone.matrix_local.to_quaternion()
    joint.rotation_quaternion = rest.inverted() @ parent.to_quaternion().inverted() @ desired @ rest

def grip(side, point, desired):
    origin = Vector((1.14 if side == 'L' else -1.14, -.055, 1.33))
    wrist = armature.bones['hand.'+side].head_local
    target = Vector(point)-desired@(origin-wrist)
    arm_target(side, target, (1.55 if side == 'L' else -1.55, -.2, 1.85))
    orient_world('hand.'+side, desired)
    for index in range(4):
        rotation(f'digit{index}.'+side, (1, 0, 0), -.85)
        rotation(f'digit_tip{index}.'+side, (1, 0, 0), -.75)
    rotation('thumb.'+side, (1, 0, 0), -.45)
    rotation('thumb_tip.'+side, (1, 0, 0), -.55)

def show(name, amount): rig.pose.bones[name].scale = (max(.001, amount),)*3

def body(name, p):
    reset(); envelope = smooth(min(p*10, (1-p)*10))
    rotation('antenna', (1, 0, 0), .055*math.sin(p*math.tau*2-.3)*envelope)
    if name == 'kick_ball':
        y, z = curve_value([(0, 0, .30), (.12, 0, .30), (.23, .27, .43),
                           (.35, -.30, .30), (.41, -.60, .48), (.58, -.12, .40), (.76, 0, .30), (1, 0, .30)], p)
        leg('L', 0, .30); leg('R', y, z)
        rotation('torso', (1, 0, 0), -.065*envelope)
        rotation('head', (1, 0, 0), .11*envelope)
        rotation('upper_arm.L', (1, 0, 0), -.40*envelope)
        rotation('upper_arm.R', (1, 0, 0), .35*envelope)
    elif name == 'hammer':
        angle, height = curve_value([(0, 0, 1.33), (.12, 1.1, 2.20), (.26, 1.4, 2.22),
             (45/132, math.pi, 1.88526), (.41, 2.70, 2.02), (.53, 1.3, 2.22),
             (86/132, math.pi, 1.88526), (.72, 2.75, 2.02), (.88, 1.0, 1.80), (1, 0, 1.33)], p)
        grip('L', (1.14+.11*envelope, -.055-.395*envelope, height), Quaternion(Vector((1, 0, 0)), angle))
        show('prop.hammer', envelope); show('prop.anvil', envelope)
        rotation('torso', (1, 0, 0), -.04*envelope)
        rotation('head', (1, 0, 0), .10*envelope)
        rotation('upper_arm.R', (0, 1, 0), .18*envelope)
    elif name == 'balloon':
        grip('L', (1.14+.11*envelope, -.055-.17*envelope, 1.33+.36*envelope), Quaternion())
        show('prop.tether', envelope); show('prop.balloon', 1)
        orient_world('prop.tether', Quaternion())
        sway = .10*math.sin(p*math.tau*1.4)*envelope
        rig.pose.bones['prop.balloon'].location.x = sway
        rig.pose.bones['prop.balloon'].location.y = -.5*sway*sway/1.38
        rotation('head', (0, 1, 0), -.06*envelope)
        rotation('head', (1, 0, 0), -.09*envelope)
    else:
        sway = .025*math.sin(p*math.tau*2)*envelope
        rotation('prop.parachute', (0, 1, 0), sway); show('prop.parachute', envelope)
        # Solve both hands to the actual moving suspension endpoints.
        bpy.context.view_layer.update()
        transform = rig.pose.bones['prop.parachute'].matrix @ armature.bones['prop.parachute'].matrix_local.inverted()
        for side, sign in (('L', 1), ('R', -1)):
            resting = Vector((sign*1.14, -.055, 1.33))
            target = resting.lerp(Vector((sign*1.17, -.35, 2.30)), envelope)
            if envelope > .99: target = transform @ Vector((sign*1.17, -.35, 2.30))
            grip(side, target, Quaternion())
            leg(side, -.12*envelope, .30+.14*envelope)
        rotation('torso', (0, 1, 0), -sway*.7)
    clear_arms()

def bake(name, frames):
    action = bpy.data.actions.new(name); action.use_fake_user = True; action['looping'] = False
    rig.animation_data.action = action
    for frame in range(frames+1):
        body(name, frame/frames)
        for joint in rig.pose.bones:
            for prop in ('location', 'rotation_quaternion', 'scale'): joint.keyframe_insert(prop, frame=frame, group=joint.name)
    return action

kick = bake('kick_ball', 120)
rig.animation_data.action = kick; scene.frame_set(42); bpy.context.view_layer.update()

def foot_tree():
    vertices, polygons = [], []
    for obj in old_meshes:
        if 'foot.R' not in obj.vertex_groups: continue
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()); mesh = evaluated.to_mesh()
        offset = len(vertices); vertices.extend(obj.matrix_world @ vertex.co for vertex in mesh.vertices)
        polygons.extend(tuple(offset+v for v in face.vertices) for face in mesh.polygons)
        evaluated.to_mesh_clear()
    return BVHTree.FromPolygons(vertices, polygons)

tree = foot_tree(); radius = .23
lo, hi = -1.8, -.65
for _ in range(45):
    middle = (lo+hi)/2
    distance = tree.find_nearest(Vector((-.38, middle, radius)))[3]
    if distance > radius: lo = middle
    else: hi = middle
start = Vector((-.38, (lo+hi)/2, radius))
position = start.copy(); velocity = Vector((0, -1.4, 1.6)); bounces = []
for frame in range(121):
    if frame > 42:
        velocity.z -= 5/30; position += velocity/30
        if position.z < radius:
            position.z = radius
            if velocity.z < -.35: bounces.append(frame); velocity.z *= -.48
            else: velocity.z = 0
            velocity.y *= .86
    joint = rig.pose.bones['prop.ball']
    envelope = smooth(min(frame/8, (120-frame)/8))
    joint.location = joint.bone.matrix_local.to_quaternion().inverted() @ position
    joint.rotation_quaternion = Quaternion(Vector((1, 0, 0)), (start.y-position.y)/radius)
    joint.scale = (max(.001, envelope),)*3
    for prop in ('location', 'rotation_quaternion', 'scale'): joint.keyframe_insert(prop, frame=frame, group=joint.name)
kick['contact_frame'] = 42; kick['ball_launch_frame'] = 43; kick['bounce_frames'] = json.dumps(bounces)
kick['ball_start'] = list(start); kick.pose_markers.new('FOOT CONTACT').frame = 42
for name, frames in (('hammer', 132), ('balloon', 150), ('parachute', 150)):
    action = bake(name, frames)
    if name == 'hammer':
        action['contact_frames'] = json.dumps([45, 86])
        for frame in (45, 86): action.pose_markers.new('HAMMER CONTACT '+str(frame)).frame = frame

# Dense authored keys use linear interpolation so subframes cannot move the ball
# before contact or overshoot a striking surface between baked frames.
for action in bpy.data.actions:
    if action.name not in ('kick_ball', 'hammer', 'balloon', 'parachute'):
        continue
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fcurve in bag.fcurves:
                    for key in fcurve.keyframe_points:
                        key.interpolation = 'LINEAR'

assert geometry_hash(old_meshes) == original_geometry, 'The saved character geometry changed.'
rig.animation_data.action = bpy.data.actions['idle']; scene.frame_set(0)
scene['brain_prop_contact_version'] = '3.1.0'
scene['brain_original_geometry_sha256'] = original_geometry
bpy.ops.object.select_all(action='DESELECT'); rig.select_set(True); bpy.context.view_layer.objects.active = rig
bpy.ops.wm.save_as_mainfile(filepath=str(source_path))
report = {'preserved_character_meshes': len(old_meshes), 'preserved_geometry_sha256': original_geometry,
          'bones': len(armature.bones), 'actions': len(bpy.data.actions),
          'ball_contact_frame': 42, 'ball_launch_frame': 43, 'ball_bounce_frames': bounces,
          'hammer_contact_frames': [45, 86], 'source': str(source_path.relative_to(ROOT))}
(ROOT/'character/prop-animation-build.json').write_text(json.dumps(report, indent=2)+'\n')
print('BRAIN_PROP_ACTIONS', json.dumps(report))
