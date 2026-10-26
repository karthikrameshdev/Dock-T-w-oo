"""Append local playground performances to the saved Brain without changing meshes.

blender --background characters/default/default.blend --python scripts/blender/add_social_actions.py
Export afterwards; all clips are dense skeletal keys, including hand articulation.
"""
import ast,hashlib,json,math,os,shutil
from pathlib import Path
import bpy
from mathutils import Quaternion,Vector

ROOT=Path(__file__).resolve().parents[2]
source=Path(bpy.data.filepath)
assert source.name=='default.blend'
backup=Path(os.environ.get('BRAIN_CHARACTER_BACKUP_DIR',str(Path.home()/'.dock-twoo/character-backups')))
backup.mkdir(parents=True,exist_ok=True)
sha=hashlib.sha256(source.read_bytes()).hexdigest();saved=backup/('Brain-'+sha[:12]+'.blend')
if not saved.exists():shutil.copy2(source,saved)
rig=bpy.data.objects['Brain_Rig'];armature=rig.data;scene=bpy.context.scene;HEAD_RISE=.34
helpers=ast.parse((ROOT/'scripts/blender/rig_helpers.py').read_text())
required={'rotation','leg','limb_collisions','clear_arms','arm_target'}
exec(compile(ast.Module(body=[n for n in helpers.body if isinstance(n,ast.FunctionDef) and n.name in required],type_ignores=[]),'<social helpers>','exec'))
def geometry_hash():
 digest=hashlib.sha256()
 for obj in sorted((o for o in scene.objects if o.type=='MESH'),key=lambda o:o.name):
  digest.update(obj.name.encode())
  for vertex in obj.data.vertices:digest.update(str(tuple(vertex.co)).encode())
 return digest.hexdigest()
before=geometry_hash()

def reset():
 for bone in rig.pose.bones:
  bone.rotation_mode='QUATERNION';bone.rotation_quaternion=Quaternion();bone.location=(0,0,0)
  bone.scale=(.001,)*3 if bone.name.startswith(('prop.','jet.')) else (1,1,1)

def pose(name,p):
 reset();t=p*math.tau;envelope=math.sin(math.pi*p)**2
 sway=math.sin(t*2)*envelope
 rotation('antenna',(1,0,0),.065*math.sin(t*3)*envelope)
 if name=='handshake':
  reach=min(1,p/.18,(1-p)/.18)
  shake=.055*math.sin(t*4)*envelope
  arm_target('R',(-.76,-.15-1.10*reach,1.45+.14*reach+shake),(-1.30,-.4,1.7))
  rotation('head',(1,0,0),.04*envelope)
 elif name=='dance_together':
  rig.pose.bones['root'].location.z=.055*(1-math.cos(t*4))*envelope
  rotation('torso',(0,1,0),.10*sway);rotation('head',(0,1,0),-.07*sway)
  for side,sign in (('L',1),('R',-1)):
   rotation('upper_arm.'+side,(0,1,0),sign*.22*envelope)
   rotation('upper_arm.'+side,(1,0,0),sign*.23*sway)
   rotation('forearm.'+side,(1,0,0),-.25*envelope)
   leg(side,sign*.10*sway,.31+.05*max(0,sign*sway),rig.pose.bones['root'].location.z)
 elif name=='playful_spar':
  rotation('torso',(0,0,1),.08*sway)
  rotation('head',(0,0,1),-.05*sway)
  for side,sign in (('L',1),('R',-1)):
   # Small forward jabs stay below the helmet and outside the torso.
   jab=max(0,math.sin(t*3+sign*math.pi/2))*envelope
   arm_target(side,(sign*1.10,-.40-.36*jab,1.67),(sign*1.55,-.2,1.6))
   for index in range(3):
    rotation(f'digit{index}.'+side,(1,0,0),-.55*envelope)
    rotation(f'digit_tip{index}.'+side,(1,0,0),-.55*envelope)
 elif name=='dash':
  rotation('torso',(1,0,0),-.10*envelope);rotation('head',(1,0,0),.08*envelope)
  for side,sign in (('L',1),('R',-1)):
   wave=math.sin(t*3+ (0 if sign==1 else math.pi))
   leg(side,.25*wave,.31+.16*max(0,wave),0,-.08*wave)
   rotation('upper_arm.'+side,(1,0,0),-.38*wave*envelope)
   rotation('forearm.'+side,(1,0,0),-.25*envelope)
 elif name=='air_spin':
  rig.pose.bones['root'].location.z=.12*envelope
  rotation('torso',(0,0,1),.14*sway);rotation('head',(0,1,0),.08*sway)
  for side,sign in (('L',1),('R',-1)):
   rotation('upper_arm.'+side,(0,1,0),sign*.4*envelope)
   rotation('forearm.'+side,(1,0,0),-.20*envelope)
   leg(side,.08*sign*sway,.36+.10*envelope,.12*envelope)
   rig.pose.bones['jet.'+side].scale=(max(.001,envelope),)*3
 elif name=='cheer_partner':
  rotation('head',(1,0,0),.1*sway)
  for side,sign in (('L',1),('R',-1)):
   rotation('upper_arm.'+side,(0,1,0),sign*.30*envelope)
   rotation('forearm.'+side,(1,0,0),-.35*envelope)
   rotation('hand.'+side,(0,1,0),.2*sway)
 clear_arms()

report={'preserved_mesh_sha256':before,'actions':{},'source':'characters/default/default.blend'}
for name,frames in [('handshake',75),('dance_together',120),('playful_spar',120),('dash',60),('air_spin',90),('cheer_partner',90)]:
 old=bpy.data.actions.get(name)
 if old:bpy.data.actions.remove(old)
 action=bpy.data.actions.new(name);action.use_fake_user=True;action['looping']=True
 rig.animation_data.action=action
 for frame in range(frames+1):
  pose(name,frame/frames)
  for bone in rig.pose.bones:
   for prop in ('location','rotation_quaternion','scale'):bone.keyframe_insert(prop,frame=frame,group=bone.name)
 for layer in action.layers:
  for strip in layer.strips:
   for bag in strip.channelbags:
    for curve in bag.fcurves:
     for key in curve.keyframe_points:key.interpolation='LINEAR'
 report['actions'][name]={'frames':frames+1,'looping':True}
assert before==geometry_hash(),'The artist mesh was changed'
rig.animation_data.action=bpy.data.actions['idle'];scene.frame_set(0)
scene['brain_playground_version']='3.2.0'
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(source))
report['source_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
(ROOT/'characters/default/social-animation-build.json').write_text(json.dumps(report,indent=2)+'\n')
print('BRAIN_SOCIAL_ACTIONS',json.dumps(report))
