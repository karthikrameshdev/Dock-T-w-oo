"""Non-destructive mesh and IK helpers for the saved Brain rig.

Functions are loaded into the active Blender scene namespace by the prop and
clearance scripts. This module does not rebuild or replace the artist's design.
"""
HEAD_RISE = .34

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

def arm_target(side, target, hint):
    """Two-bone reach with a stable elbow pole; the hand remains rigidly attached."""
    bpy.context.view_layer.update()
    upper=rig.pose.bones['upper_arm.'+side];lower=rig.pose.bones['forearm.'+side]
    parent=upper.parent.matrix @ upper.parent.bone.matrix_local.inverted()
    shoulder=parent @ upper.bone.head_local
    delta=Vector(target)-shoulder
    length= min(delta.length, upper.bone.length+lower.bone.length-.005)
    direction=delta.normalized()
    a,b=upper.bone.length,lower.bone.length
    along=(a*a+length*length-b*b)/(2*length)
    pole=Vector(hint)-shoulder; pole=(pole-direction*pole.dot(direction)).normalized()
    elbow=shoulder+direction*along+pole*math.sqrt(max(.00001,a*a-along*along))
    actual=shoulder+direction*length
    upper_global=(upper.bone.tail_local-upper.bone.head_local).rotation_difference(elbow-shoulder)
    lower_global=(lower.bone.tail_local-lower.bone.head_local).rotation_difference(actual-elbow)
    rest=upper.bone.matrix_local.to_quaternion()
    upper.rotation_quaternion=rest.inverted() @ parent.to_quaternion().inverted() @ upper_global @ rest
    rest=lower.bone.matrix_local.to_quaternion()
    lower.rotation_quaternion=rest.inverted() @ upper_global.inverted() @ lower_global @ rest
