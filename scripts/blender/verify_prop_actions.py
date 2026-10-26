"""Measure authored prop contact, attachment and stationary anticipation."""
import hashlib,json,math
from pathlib import Path
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parents[2]
rig=bpy.data.objects['Brain_Rig'];scene=bpy.context.scene
issues=[];samples=0

def frame(action,time):
    rig.animation_data.action=bpy.data.actions[action]
    scene.frame_set(int(time),subframe=time%1);bpy.context.view_layer.update()

def transform(name):return rig.pose.bones[name].matrix @ rig.data.bones[name].matrix_local.inverted()

def mesh_points(obj):
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=evaluated.to_mesh()
    points=[obj.matrix_world @ vertex.co for vertex in mesh.vertices]
    polygons=[tuple(poly.vertices) for poly in mesh.polygons]
    evaluated.to_mesh_clear();return points,polygons

def foot_tree():
    points,polygons=[],[]
    for obj in scene.objects:
        if obj.type!='MESH' or 'foot.R' not in obj.vertex_groups:continue
        vertices,faces=mesh_points(obj);offset=len(points);points.extend(vertices)
        polygons.extend(tuple(offset+index for index in face) for face in faces)
    return BVHTree.FromPolygons(points,polygons)

start=Vector(bpy.data.actions['kick_ball']['ball_start']);contact_distances=[]
for index in range(8*4,44*4):
    value=index/4;frame('kick_ball',value);samples+=1
    center=transform('prop.ball') @ Vector((0,0,0))
    distance=foot_tree().find_nearest(center)[3]
    contact_distances.append((value,float(distance)))
    if value<=42 and (center-start).length>1e-5:issues.append({'before_contact_movement':value})
    if value<41.75 and distance<.23-.012:issues.append({'early_foot_penetration':value,'distance':distance})
frame('kick_ball',42);contact=foot_tree().find_nearest(start)[3]
if abs(contact-.23)>.002:issues.append({'missed_ball_contact':contact})
frame('kick_ball',43);launch=(transform('prop.ball') @ Vector((0,0,0))-start).length
if launch<.02:issues.append({'missing_launch':launch})

hammer_contacts=[]
for f in (45,86):
    frame('hammer',f)
    vertices,_=mesh_points(bpy.data.objects['Brain toy hammer head'])
    pad,_=mesh_points(bpy.data.objects['Brain toy stand contact pad'])
    bottom=min(v.z for v in vertices);top=max(v.z for v in pad)
    hammer_contacts.append({'frame':f,'gap':bottom-top})
    if abs(bottom-top)>.025:issues.append({'missed_hammer_contact':f,'gap':bottom-top})

# The handle and string origins must remain rigidly bound to the palm.
max_grip_error=0.;max_rope_error=0.
for action,prop in (('hammer','prop.hammer'),('balloon','prop.tether'),('parachute','prop.parachute')):
    end=int(bpy.data.actions[action].frame_range[1])
    for f in range(1,end):
        frame(action,f);samples+=1
        for side,sign in (('L',1),('R',-1)) if action=='parachute' else (('L',1),):
            origin=Vector((sign*1.14,-.055,1.33));hand=transform('hand.'+side) @ origin
            if action=='parachute':
                if 16<f<end-16:
                    rope=transform(prop) @ Vector((sign*1.17,-.35,2.30))
                    max_rope_error=max(max_rope_error,(hand-rope).length)
            else:
                grip=transform(prop) @ origin
                max_grip_error=max(max_grip_error,(hand-grip).length)
if max_grip_error>.01:issues.append({'grip_separation':max_grip_error})
if max_rope_error>.05:issues.append({'parachute_grip_separation':max_rope_error})
report={'success':not issues,'samples':samples,'ball_contact_frame':42,'ball_contact_gap':contact-.23,
        'ball_launch_frame':43,'ball_launch_distance':launch,'hammer_contacts':hammer_contacts,
        'maximum_grip_error':max_grip_error,'maximum_rope_grip_error':max_rope_error,'issues':issues,
        'blend_sha256':hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),
        'glb_sha256':hashlib.sha256((ROOT/'dock_twoo/server/static/brain3d/brain.glb').read_bytes()).hexdigest()}
(ROOT/'characters/default/prop-animation-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print('BRAIN_PROP_VALIDATION',json.dumps(report))
if issues:raise RuntimeError('Prop contact or grip checks failed')
