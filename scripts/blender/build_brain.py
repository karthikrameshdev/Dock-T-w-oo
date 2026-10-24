"""Build the native Brain character, rig and action library inside Blender.

Run with Blender --background --python this_file -- --project FILE --export FILE.
The editable .blend is the source; the assistant loads the exported rigged GLB.
"""

import argparse
import ast
import json
import math
from pathlib import Path
import shutil
import sys

import bpy
from mathutils import Vector, Quaternion


parser = argparse.ArgumentParser()
parser.add_argument('--project', type=Path, required=True)
parser.add_argument('--export', type=Path, required=True)
parser.add_argument('--preview', action='store_true')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
REPO = Path(__file__).resolve().parents[2]
if args.project.exists() and not args.project.with_suffix('.pre-codex.blend').exists():
    shutil.copy2(args.project, args.project.with_suffix('.pre-codex.blend'))

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for block in list(bpy.data.actions):
    bpy.data.actions.remove(block)

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = scene.render.resolution_y = 768
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
scene.render.fps = 30
scene.view_settings.view_transform = 'AgX'


def linear(value):
    return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4


def material(name, color, roughness=.28, metallic=.12, emission=0):
    rgb = tuple(linear(int(color[index:index + 2], 16) / 255) for index in (1, 3, 5))
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    shader = result.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*rgb, 1)
    shader.inputs['Roughness'].default_value = roughness
    shader.inputs['Metallic'].default_value = metallic
    shader.inputs['Coat Weight'].default_value = .35
    shader.inputs['Coat Roughness'].default_value = .18
    if emission:
        shader.inputs['Emission Color'].default_value = (*rgb, 1)
        shader.inputs['Emission Strength'].default_value = emission
    result.diffuse_color = (*rgb, 1)
    return result


HEAD_RISE = .34
objects = []
bindings = {}


def finish(obj, name, mat, bone):
    obj.name = name
    obj.data.materials.append(mat)
    if obj.type == 'MESH':
        for face in obj.data.polygons:
            face.use_smooth = True
    objects.append(obj)
    bindings[obj.name] = bone
    return obj


def sphere(name, location, size, mat, bone, segments=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=16, location=location)
    obj = bpy.context.object
    obj.scale = size
    return finish(obj, name, mat, bone)


def rounded_box(name, location, size, radius, mat, bone):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel = obj.modifiers.new('Soft manufactured corners', 'BEVEL')
    bevel.width, bevel.segments = radius, 4
    bevel.affect = 'EDGES'
    weighted = obj.modifiers.new('Polished surface normals', 'WEIGHTED_NORMAL')
    weighted.keep_sharp = True
    return finish(obj, name, mat, bone)


def armor(name, start, end, width, depth, mat, bone):
    direction = Vector(end) - Vector(start)
    obj = rounded_box(name, (Vector(start) + Vector(end)) / 2,
                      (width, depth, direction.length), min(width, depth) * .25, mat, bone)
    obj.rotation_euler = direction.to_track_quat('Z', 'Y').to_euler()
    return obj


def cylinder(name, start, end, radius, mat, bone, radius_end=None):
    direction = Vector(end) - Vector(start)
    midpoint = (Vector(start) + Vector(end)) / 2
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=radius,
                                  radius2=radius_end if radius_end is not None else radius,
                                  depth=direction.length, location=midpoint)
    obj = bpy.context.object
    obj.rotation_euler = direction.to_track_quat('Z', 'Y').to_euler()
    bevel = obj.modifiers.new('Rounded cylinder ends', 'BEVEL')
    bevel.width, bevel.segments = .035, 3
    return finish(obj, name, mat, bone)


def torus(name, location, major, minor, mat, bone, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_segments=32, minor_segments=8,
                                   location=location, major_radius=major, minor_radius=minor,
                                   rotation=rotation)
    return finish(bpy.context.object, name, mat, bone)


def rounded_panel(name, location, width, height, depth, radius, mat, bone, conform=False):
    surface = conform if callable(conform) else helmet_front
    outline = []
    for center, begin in (((width / 2 - radius, height / 2 - radius), 0),
                          ((-width / 2 + radius, height / 2 - radius), 90),
                          ((-width / 2 + radius, -height / 2 + radius), 180),
                          ((width / 2 - radius, -height / 2 + radius), 270)):
        for step in range(9):
            angle = math.radians(begin + step * 90 / 8)
            outline.append((center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle)))
    count = len(outline)
    vertices = [(location[0] + x, location[1] + y, location[2] + z)
                for y in (-depth / 2, depth / 2) for x, z in outline]
    if conform:
        # Curved, flush visor follows the actual helmet instead of a projecting TV screen.
        vertices = [(x, surface(x, z) + y, z)
                    for x, y, z in vertices]
    faces = [tuple(range(count - 1, -1, -1)), tuple(range(count, count * 2))]
    faces += [(index, (index + 1) % count, (index + 1) % count + count, index + count) for index in range(count)]
    if conform:
        # Tessellate the curved face; a single ngon would cut through the shell.
        vertices = [(location[0], surface(location[0], location[2]) + location[1] - depth / 2, location[2])]
        radial_steps = 16
        for ring in range(1, radial_steps + 1):
            for x, z in outline:
                px, pz = location[0] + x * ring / radial_steps, location[2] + z * ring / radial_steps
                vertices.append((px, surface(px, pz) + location[1] - depth / 2, pz))
        faces = [(0, 1 + i, 1 + (i + 1) % count) for i in range(count)]
        for ring in range(radial_steps - 1):
            for i in range(count):
                a, b = 1 + ring * count + i, 1 + ring * count + (i + 1) % count
                faces.append((a, a + count, b + count, b))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    bevel = obj.modifiers.new('Soft panel rim', 'BEVEL')
    bevel.width, bevel.segments = .025, 3
    return finish(obj, name, mat, bone)


def curve(name, points, radius, mat, bone):
    data = bpy.data.curves.new(name, 'CURVE')
    data.dimensions = '3D'
    data.bevel_depth, data.bevel_resolution = radius, 2
    spline = data.splines.new('BEZIER')
    spline.bezier_points.add(len(points) - 1)
    for handle, point in zip(spline.bezier_points, points):
        handle.co = point
        handle.handle_left_type = handle.handle_right_type = 'AUTO'
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target='MESH')
    obj.select_set(False)
    return finish(obj, name, mat, bone)


# Native geometry: silver ceramic and smooth blue gradient accents.
exec(compile((Path(__file__).parent / 'fluffy_design.py').read_text(), 'fluffy_design.py', 'exec'))

# Leave a real neck gap. Shape-key meshes must move every target together.
for obj in objects:
    if bindings[obj.name] in ('head', 'antenna', 'brow.L', 'brow.R', 'eye.L', 'eye.R', 'pupil.L', 'pupil.R') and not obj.name.startswith('Upper neck'):
        if obj.data.shape_keys:
            for shape in obj.data.shape_keys.key_blocks:
                for vertex in shape.data:
                    vertex.co.z += HEAD_RISE
        else:
            obj.location.z += HEAD_RISE

# Rigid mechanical pieces share one real skeleton and one set of materials.
armature = bpy.data.armatures.new('Brain mechanical skeleton')
rig = bpy.data.objects.new('Brain_Rig', armature)
scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')


def bone(name, head, tail, parent=None):
    result = armature.edit_bones.new(name)
    result.head, result.tail = head, tail
    if parent:
        result.parent = armature.edit_bones[parent]
    return result


bone('root', (0, 0, 0), (0, 0, .3))
bone('torso', (0, 0, 1.42), (0, 0, 2.48), 'root')
bone('head', (0, 0, 2.80), (0, 0, 4.04), 'torso')
for sign, side in ((1, 'L'), (-1, 'R')):
    bone('upper_arm.' + side, (sign * .77, 0, 2.35), (sign * 1., 0, 1.88), 'torso')
    bone('forearm.' + side, (sign * 1., 0, 1.88), (sign * 1.12, -.025, 1.49), 'upper_arm.' + side)
    bone('hand.' + side, (sign * 1.12, -.025, 1.49), (sign * 1.14, -.055, 1.25), 'forearm.' + side)
    bone('fingers.' + side, (sign * 1.14, -.055, 1.34), (sign * 1.14, -.055, 1.18), 'hand.' + side)
    for finger in range(4):
        x = sign * (.995 + finger * .092)
        length = .22 if finger in (1, 2) else .18
        bone(f'digit{finger}.' + side, (x, -.055, 1.245), (x, -.075, 1.15), 'fingers.' + side)
        bone(f'digit_tip{finger}.' + side, (x, -.075, 1.15), (x, -.12, 1.245 - length), f'digit{finger}.' + side)
    bone('thumb.' + side, (sign * 1.29, -.055, 1.40), (sign * 1.34, -.10, 1.32), 'hand.' + side)
    bone('thumb_tip.' + side, (sign * 1.34, -.10, 1.32), (sign * 1.30, -.15, 1.26), 'thumb.' + side)
    bone('thigh.' + side, (sign * .38, 0, 1.42), (sign * .38, 0, .87), 'root')
    bone('shin.' + side, (sign * .38, 0, .87), (sign * .38, 0, .30), 'thigh.' + side)
    bone('foot.' + side, (sign * .38, 0, .30), (sign * .38, -.35, .16), 'shin.' + side)
    bone('eye.' + side, (sign * .38, helmet_front(sign * .38, 3.49) - .072, 3.49 + HEAD_RISE), (sign * .38, helmet_front(sign * .38, 3.49) - .072, 3.59 + HEAD_RISE), 'head')
    bone('pupil.' + side, (sign * .38, helmet_front(sign * .38, 3.49) - .134, 3.48 + HEAD_RISE), (sign * .38, helmet_front(sign * .38, 3.49) - .134, 3.53 + HEAD_RISE), 'eye.' + side)
bone('speech',(0,0,3),(0,0,3.1),'head')
bone('antenna', (.52,.08,4.20+HEAD_RISE), (.92,.08,4.78+HEAD_RISE), 'head')
for sign, side in ((1,'L'),(-1,'R')):
    bone('brow.'+side, (sign*.40,-.8,3.86+HEAD_RISE), (sign*.40,-.8,3.96+HEAD_RISE), 'head')
    bone('jet.'+side, (sign*.43,.39,1.72), (sign*.43,.39,1.45), 'torso')
for name, origin, parent in (('prop.magnifier',(1.14,-.055,1.33),'hand.L'),
                            ('prop.camera',(1.14,-.055,1.33),'hand.L'),
                            ('prop.tablet',(-1.14,-.055,1.33),'hand.R'),
                            ('prop.scan',(0,-1.05,2),'torso'),
                            ('prop.scanline',(0,-1.05,2),'prop.scan')):
    bone(name,origin, (origin[0],origin[1],origin[2]+.1),parent)
bpy.ops.object.mode_set(mode='OBJECT')
rig.show_in_front = True
for obj in objects:
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    # Apply the manufactured bevels before adding skeletal deformation.
    for modifier in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    if obj.data.shape_keys is None:
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    paint_accent_gradient(obj)
    group = obj.vertex_groups.new(name=bindings[obj.name])
    group.add(list(range(len(obj.data.vertices))), 1., 'REPLACE')
    modifier = obj.modifiers.new('Brain skeleton', 'ARMATURE')
    modifier.object = rig
    obj.parent = rig

# Speech shapes share one skeletal control, so every Blender Action previews
# its facial performance and glTF can bake the same morph channels.
for obj in objects:
    if obj.data.shape_keys:
        for key in list(obj.data.shape_keys.key_blocks)[1:]:
            key.value=0
            driver=key.driver_add('value').driver
            var=driver.variables.new();var.name='v';var.type='SINGLE_PROP'
            var.targets[0].id=rig
            axis={'mouth_open':1,'mouth_round':0,'tongue_curl':2}[key.name]
            var.targets[0].data_path=f'pose.bones["speech"].scale[{axis}]'
            driver.expression='max(0,min(1,v-1))'

rig['design'] = 'Smooth redesign: silver ceramic and glossy cobalt-to-cyan gradient enamel; cyan digital eyes, tongue, expressive brows and spring antenna.'
rig['actions'] = 'All native assistant actions; walking feet are solved with two-bone inverse kinematics.'


def rotation(name, axis, angle):
    pose = rig.pose.bones[name]
    # Convert a world-axis rotation into this manufactured joint's local frame.
    rest = armature.bones[name].matrix_local.to_quaternion()
    world = Quaternion(Vector(axis), angle)
    pose.rotation_quaternion = rest.inverted() @ world @ rest


def leg(side, y, ankle_z, root_z=0, pitch=0):
    upper, lower = .55, .57
    height = 1.42 + root_z - ankle_z
    reach = min(upper + lower - .001, max(.03, math.hypot(y, height)))
    line = math.atan2(y, height)
    hip = line - math.acos(max(-1, min(1, (upper * upper + reach * reach - lower * lower) / (2 * upper * reach))))
    knee = math.pi - math.acos(max(-1, min(1, (upper * upper + lower * lower - reach * reach) / (2 * upper * lower))))
    rotation('thigh.' + side, (1, 0, 0), hip)
    rotation('shin.' + side, (1, 0, 0), knee)
    rotation('foot.' + side, (1, 0, 0), -hip - knee + pitch)


def gait(phase, running=False):
    support = .45 if running else .6
    if phase < support:
        return -.5 + phase / support, 0
    swing = (phase - support) / (1 - support)
    eased = swing * swing * (3 - 2 * swing)
    return .5 - eased, (.38 if running else .22) * math.sin(math.pi * swing)


def pose(name, p):
    for joint in rig.pose.bones:
        joint.rotation_mode = 'QUATERNION'
        joint.location = (0, 0, 0)
        joint.rotation_quaternion = (1, 0, 0, 0)
        joint.scale = (1, 1, 1)
    arc = math.sin(math.pi * p)
    cycle = math.sin(math.tau * p)
    fade = min(1, p * 6, (1 - p) * 6)
    if name in ('walk', 'walk_window', 'chase_ball', 'run', 'explore'):
        running = name in ('run', 'chase_ball')
        root_z = -.16 + .025 * abs(math.sin(p * math.tau))
        rig.pose.bones['root'].location.y = root_z
        for side, offset in (('L', 0), ('R', .5)):
            phase = (p + offset) % 1
            y, lift = gait(phase, running)
            leg(side, y, .30 + lift, root_z)
            rotation('upper_arm.' + side, (1, 0, 0), (-1 if side == 'L' else 1) * (.65 if running else .38) * cycle)
            rotation('forearm.' + side, (1, 0, 0), -.2 if running else -.08)
    elif name in ('climb', 'climb_dock'):
        rig.pose.bones['torso'].location.y = .025 * cycle
        for side, offset in (('L', 0), ('R', .5)):
            wave = math.sin((p + offset) * math.tau)
            rotation('upper_arm.' + side, (1, 0, 0), -1.9 + .35 * wave)
            rotation('forearm.' + side, (1, 0, 0), -.45 + .25 * wave)
            rotation('fingers.' + side, (1, 0, 0), .4)
            leg(side, -.26, .44 + .16 * (wave + 1), -.08)
    elif name == 'wave':
        rotation('upper_arm.L', (0, 1, 0), -1.25 * arc)
        rotation('forearm.L', (0, 1, 0), -.9 * arc + .18 * math.sin(p * math.tau * 3) * fade)
        rotation('hand.L', (0, 1, 0), .22 * math.sin(p * math.tau * 3) * fade)
    elif name in ('point', 'camera', 'search', 'inspect_window', 'inspect_icon', 'scan_screen', 'sensor_scan', 'read', 'ponder', 'peek'):
        amount = -.15 if name == 'read' else (-1.1 if name == 'point' else -.65)
        rotation('upper_arm.L', (1, 0, 0), amount * arc)
        rotation('forearm.L', (1, 0, 0), -.35 * arc)
        rotation('head', (0, 0, 1), (.10 if name == 'read' else .22) * cycle * fade)
    elif name == 'pull_scroll':
        grab = (.25 + .75 * min(1, max(0, (p - .25) / .6))) if p < .85 else max(0, (1 - p) / .15)
        for side in ('L', 'R'):
            rotation('upper_arm.' + side, (1, 0, 0), -1.85 * grab)
            rotation('forearm.' + side, (1, 0, 0), -.5 * grab)
            rotation('fingers.' + side, (1, 0, 0), .6 * grab)
        rig.pose.bones['torso'].location.y = -.055 * arc
    elif name == 'fold_arms':
        for side, sign in (('L', 1), ('R', -1)):
            rotation('upper_arm.' + side, (0, 1, 0), sign * .35 * arc)
            rotation('forearm.' + side, (1, 0, 0), -1.65 * arc)
    elif name in ('dance', 'celebrate', 'stretch', 'fly', 'surprised'):
        for side, sign in (('L', -1), ('R', 1)):
            rotation('upper_arm.' + side, (0, 1, 0), sign * (1.2 + .25 * cycle) * arc)
            rotation('forearm.' + side, (1, 0, 0), -.35 * arc)
        rotation('torso', (0, 1, 0), .11 * math.sin(p * math.tau * 2) * fade)
        rig.pose.bones['torso'].location.y = .05 * abs(cycle) * fade
    elif name == 'jump':
        for side in ('L', 'R'):
            leg(side, .1, .4 + .12 * arc, -.05)
            rotation('upper_arm.' + side, (1, 0, 0), -.75 * arc)
    elif name == 'kick_ball':
        leg('L', -.1 - .5 * arc, .3 + .22 * arc, -.06)
        rotation('upper_arm.R', (1, 0, 0), -.5 * arc)
    elif name == 'roll':
        rotation('root', (0, 1, 0), p * math.tau)
        rig.pose.bones['root'].location.y = .3 * arc
    elif name == 'nod':
        rotation('head', (1, 0, 0), .16 * math.sin(p * math.tau * 2) * fade)
    elif name == 'wink':
        rig.pose.bones['eye.L'].scale.y = 1 - .97 * arc
    elif name == 'sleep':
        rotation('head', (1, 0, 0), .17 * arc)
        for side in ('L', 'R'):
            rig.pose.bones['eye.' + side].scale.y = 1 - .95 * arc
    elif name == 'replace_text':
        for side in ('L', 'R'):
            rotation('upper_arm.' + side, (1, 0, 0), -.8 * arc)
            rotation('forearm.' + side, (1, 0, 0), -.5 * arc)
    else:
        # Turn is real scene yaw in the runtime; idle keeps feet planted.
        rig.pose.bones['torso'].location.y = .018 * cycle
        rotation('head', (0, 0, 1), .025 * cycle)

    for side in ('L', 'R'):
        grip = (.9 if name == 'point' else .45 if name in ('climb', 'climb_dock', 'pull_scroll', 'fold_arms') else .12) * arc
        for finger in range(4):
            flex = 0 if name == 'point' and finger == 0 else grip
            rotation(f'digit{finger}.' + side, (1, 0, 0), -flex)
            rotation(f'digit_tip{finger}.' + side, (1, 0, 0), -flex * .75)
        rotation('thumb_tip.' + side, (1, 0, 0), -grip * .6)


# Clearance envelopes cover the entire forearm and glove, not just a wrist point.
# Adjust joint rotations only: limb lengths and material geometry remain identical.
def limb_collisions(side):
    head = rig.pose.bones['head'].matrix @ armature.bones['head'].matrix_local.inverted()
    inverse_head = head.inverted()
    shoulder = rig.pose.bones['upper_arm.' + side].head
    elbow = rig.pose.bones['upper_arm.' + side].tail
    wrist = rig.pose.bones['forearm.' + side].tail
    hand = rig.pose.bones['hand.' + side].tail
    points = [(shoulder.lerp(elbow, t), .15) for t in (.35, .6, .85)]
    points += [(elbow.lerp(wrist, t), .17) for t in (0, .25, .5, .75, 1)]
    points += [(wrist.lerp(hand, t), .24) for t in (.3, .7, 1)]
    collisions = 0
    for world, radius in points:
        point = inverse_head @ world
        x, y, z = point.x, point.y, point.z - (3.35 + HEAD_RISE)
        shell = (abs(x / (1.20 + radius)) ** (2 / .8) +
                 abs(y / (.84 + radius)) ** (2 / .8)) ** (.8 / .78) + abs(z / (1.02 + radius)) ** (2 / .78)
        ear = (abs(x) < 1.40 + radius and abs(x) > 1.08 - radius and
               math.hypot(y, z) < .39 + radius)
        if shell < 1 or ear:
            collisions += 1
    return collisions


def clear_arms():
    bpy.context.view_layer.update()
    for side, sign in (('L', 1), ('R', -1)):
        if not limb_collisions(side):
            continue
        joint = rig.pose.bones['upper_arm.' + side]
        original = joint.rotation_quaternion.copy()
        rest = armature.bones[joint.name].matrix_local.to_quaternion()
        found = False
        # Prefer a modest outward splay; forward reach is the second option.
        candidates = sorted(((x, y) for x in (0, -.15, -.3, -.5, -.75, -1.0)
                             for y in (0, -.15, -.3, -.5, -.75, .15, .3, .5, .75)),
                            key=lambda item: item[0] ** 2 + item[1] ** 2)
        for x, y in candidates:
            correction = Quaternion(Vector((1, 0, 0)), x) @ Quaternion(Vector((0, 1, 0)), sign * y)
            joint.rotation_quaternion = rest.inverted() @ correction @ rest @ original
            bpy.context.view_layer.update()
            if not limb_collisions(side):
                found = True
                break
        if not found:
            raise RuntimeError('Unable to clear the helmet for arm ' + side)


exec(compile((Path(__file__).parent / 'fluffy_animation.py').read_text(), 'fluffy_animation.py', 'exec'))

tree = ast.parse((REPO / 'dock_twoo/brain/animation.py').read_text())
durations = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'ACTIONS' for target in node.targets))
durations = {'idle': ('Idle', 4.0), 'run': ('Run', 1.0), **durations}
for name, (_label, seconds) in durations.items():
    if rig.animation_data:
        rig.animation_data.action = None
    action = bpy.data.actions.new(name)
    rig.animation_data_create()
    rig.animation_data.action = action
    frames = max(24, round((1.0 if name in ('walk', 'run', 'walk_window', 'chase_ball', 'climb', 'climb_dock') else seconds) * 30))
    for frame in sorted(set(range(0, frames + 1, 2)) | {frames}):
        pose(name, frame / frames)
        expressive_pose(name, frame / frames)
        clear_arms()
        finish_performance(name, frame / frames)
        for joint in rig.pose.bones:
            joint.keyframe_insert('location', frame=frame, group=joint.name)
            joint.keyframe_insert('rotation_quaternion', frame=frame, group=joint.name)
            joint.keyframe_insert('scale', frame=frame, group=joint.name)
    action.use_fake_user = True
    action['looping'] = name in ('idle', 'walk', 'run', 'walk_window', 'chase_ball', 'climb', 'climb_dock', 'read')
rig.animation_data.action = bpy.data.actions['idle']
scene.frame_start, scene.frame_end = 0, 120
scene.frame_set(0)

# A simple studio setup is included in the editable Blender source.
world = bpy.data.worlds.new('Soft studio world')
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (.25, .29, .35, 1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = .35
scene.world = world
for name, location, energy, size in (('Key softbox', (3, -4, 7), 450, 5),
                                      ('Fill softbox', (-4, -2, 4), 280, 4),
                                      ('Rim softbox', (2, 3, 6), 500, 3)):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy, data.shape, data.size = energy, 'DISK', size
    light = bpy.data.objects.new(name, data)
    scene.collection.objects.link(light)
    light.location = location
    light.rotation_euler = (Vector((0, 0, 2.5)) - light.location).to_track_quat('-Z', 'Y').to_euler()
camera_data = bpy.data.cameras.new('Character preview camera')
camera = bpy.data.objects.new('Character preview camera', camera_data)
scene.collection.objects.link(camera)
camera.location = (3.3, -9, 4.0)
camera.rotation_euler = (Vector((0, 0, 2.45)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
camera_data.type, camera_data.ortho_scale = 'ORTHO', 6.1
scene.camera = camera

reference = bpy.data.collections.new('User supplied redesign reference')
scene.collection.children.link(reference)
reference.hide_render = reference.hide_viewport = True
for index, filename in enumerate(('fluffy-blue-robot.png',)):
    image = bpy.data.images.load(str(REPO / 'character/references' / filename), check_existing=True)
    image.pack()
    empty = bpy.data.objects.new('Reference ' + filename, None)
    empty.empty_display_type, empty.data = 'IMAGE', image
    empty.empty_display_size = 5
    empty.location = (5 + index * 4, 0, 2.5)
    reference.objects.link(empty)

bpy.ops.object.select_all(action='DESELECT')
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.region_3d.view_distance = 8
            area.spaces.active.region_3d.view_location = (0, 0, 2.5)
            area.spaces.active.shading.type = 'MATERIAL'
for mat in list(bpy.data.materials):
    if not mat.users: bpy.data.materials.remove(mat)
args.project.parent.mkdir(parents=True, exist_ok=True)
for obj in objects:
    if obj.data.shape_keys:
        for key in list(obj.data.shape_keys.key_blocks)[1:]: key.value = 0
bpy.ops.wm.save_as_mainfile(filepath=str(args.project))

bpy.ops.object.select_all(action='DESELECT')
rig.select_set(True)
for obj in objects:
    obj.select_set(True)
args.export.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.preferences.addon_enable(module='io_scene_gltf2')
options = dict(filepath=str(args.export), export_format='GLB', use_selection=True,
               export_skins=True, export_animations=True, export_animation_mode='ACTIONS',
               export_force_sampling=True, export_anim_single_armature=True,
               export_morph=True, export_morph_animation=True, export_extras=True,
               export_yup=True, export_cameras=False, export_lights=False)
supported = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
bpy.ops.export_scene.gltf(**{key: value for key, value in options.items() if key in supported})
for obj in objects:
    if obj.data.shape_keys:
        for key in list(obj.data.shape_keys.key_blocks)[1:]: key.value = 0
report = {'project': str(args.project.relative_to(REPO)), 'glb': str(args.export.relative_to(REPO)), 'meshes': len(objects),
          'bones': len(armature.bones), 'triangles': sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in objects), 'design': rig['design'], 'actions': [action.name for action in bpy.data.actions],
          'materials': [mat.name for mat in bpy.data.materials]}
(args.project.parent / 'character-build.json').write_text(json.dumps(report, indent=2))
print('BRAIN_BUILD', json.dumps(report))
if args.preview:
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(args.project.parent / 'MiniAssistant-preview.png')
    bpy.ops.render.render(write_still=True)
