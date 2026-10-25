"""Build, bake, export, render and audit one explicit roster entry."""
import ast,hashlib,json,math,shutil
from pathlib import Path
import bpy
from mathutils import Vector,Quaternion
from .roster import ROSTER
from . import motions,geometry
from .publish import export_saved,ROOT,STATIC


def mesh_hash():
    d=hashlib.sha256()
    for o in sorted((o for o in bpy.context.scene.objects if o.type=='MESH'),key=lambda o:o.name):
        d.update(o.name.encode())
        for v in o.data.vertices:d.update(str(tuple(v.co)).encode())
    return d.hexdigest()


def helper_namespace(rig):
    ns={'bpy':bpy,'math':math,'rig':rig,'armature':rig.data,'Vector':Vector,'Quaternion':Quaternion,'HEAD_RISE':.34}
    tree=ast.parse((ROOT/'scripts/blender/rig_helpers.py').read_text())
    funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('limb_collisions','clear_arms')]
    exec(compile(ast.Module(body=funcs,type_ignores=[]),'<clearance>','exec'),ns);return ns


def curves(action):
    for l in action.layers:
        for s in l.strips:
            for b in s.channelbags:
                yield from b.fcurves


def bake(rig,desc,names,existing=False):
    family=desc['family'];safe=helper_namespace(rig) if family in ('robot','human') else None
    fps=bpy.context.scene.render.fps=30
    for index,name in enumerate(names):
        if bpy.data.actions.get(name):continue
        rig.animation_data_create();rig.animation_data.action=None
        a=bpy.data.actions.new(name);a.use_fake_user=True;rig.animation_data.action=a
        looping=name in ('idle','walk','run','dash','chase_ball','walk_window','climb','climb_dock','glide','hover','flap_wings','tail_wag')
        seconds=2.4+(index%7)*.15
        if name in ('walk','run','dash','chase_ball','walk_window','climb','climb_dock'):seconds=1.2 if name!='run' else .8
        if name=='idle':seconds=4
        frames=round(seconds*fps)
        a['looping']=looping;a['category']='locomotion' if name in motions.LOCOMOTION else 'species' if name in motions.QUAD_SPECIAL+motions.BIRD_SPECIAL else 'acting'
        a['description']=name.replace('_',' ').title()+' · '+desc['name']
        for f in sorted(set(range(0,frames+1,2))|{frames}):
            motions.pose(rig,name,f/frames,family,desc['index'])
            if safe:safe['clear_arms']()
            for b in rig.pose.bones:
                for prop in ('location','rotation_quaternion','scale'):b.keyframe_insert(prop,frame=f,group=b.name)
        for c in curves(a):
            for k in c.keyframe_points:k.interpolation='LINEAR'
        print('BAKED',desc['id'],name,flush=True)
    rig.animation_data.action=bpy.data.actions['idle'];bpy.context.scene.frame_set(0)


def recolor(desc):
    def lin(v):return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
    rgb=Vector(tuple(lin(int(desc['main'][i:i+2],16)/255) for i in (1,3,5)))
    for o in bpy.context.scene.objects:
        if o.type!='MESH':continue
        attr=o.data.color_attributes.get('AccentGradient')
        if attr:
            low=min(v.co.z for v in o.data.vertices);high=max(v.co.z for v in o.data.vertices)
            for v,c in zip(o.data.vertices,attr.data):
                t=(v.co.z-low)/max(.001,high-low);color=rgb.lerp(Vector((.8,.9,1)),t*.28)*( .65+.35*t)
                c.color=(*color,1)
    for name in ('Aqua antenna glow','Electric cyan light'):
        m=bpy.data.materials.get(name)
        if m:
            c=tuple(lin(int(desc['accent'][i:i+2],16)/255) for i in (1,3,5));p=m.node_tree.nodes.get('Principled BSDF')
            p.inputs['Base Color'].default_value=(*c,1);p.inputs['Emission Color'].default_value=(*c,1)


def personalize(rig,desc):
    # Small performance differences on the new acting clips. Existing contact
    # animations retain their solved grips and foot contacts.
    gain=.88+(desc['index']%5)*.025
    tempo=.91+(desc['index']%7)*.025
    for a in bpy.data.actions:
        if a.name not in motions.EXTENSIONS:continue
        groups={}
        for c in curves(a):
            for k in c.keyframe_points:k.co.x*=tempo
            if any('"'+name+'"' in c.data_path for name in ('head','torso')) and c.data_path.endswith('rotation_quaternion'):
                groups.setdefault(c.data_path,{})[c.array_index]=c
        for channels in groups.values():
            if set(channels)!={0,1,2,3}:continue
            for i in range(len(channels[0].keyframe_points)):
                q=Quaternion([channels[j].keyframe_points[i].co.y for j in range(4)]).normalized()
                q=Quaternion().slerp(q,gain)
                for j in range(4):channels[j].keyframe_points[i].co.y=q[j]


def remove_bound(rig,all_body=False):
    for o in list(bpy.context.scene.objects):
        if o.type!='MESH':continue
        bones={g.name for g in o.vertex_groups}
        antenna=bool('antenna' in bones or o.name=='Antenna base')
        remove=antenna or (all_body and not any(n.startswith(('prop.','jet.')) for n in bones))
        if remove and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers):bpy.data.objects.remove(o,do_unlink=True)


def studio(desc):
    scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE';scene.render.film_transparent=True
    scene.render.resolution_x=scene.render.resolution_y=640;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX'
    scene.eevee.taa_render_samples=24
    for o in list(scene.objects):
        if o.type in ('LIGHT','CAMERA'):bpy.data.objects.remove(o,do_unlink=True)
    world=bpy.data.worlds.new('Companion studio');world.use_nodes=True;world.node_tree.nodes['Background'].inputs['Color'].default_value=(.35,.42,.5,1);world.node_tree.nodes['Background'].inputs['Strength'].default_value=.45;scene.world=world
    height=5.2 if desc['family'] in ('robot','human') else 3.6*desc['scale']
    target=Vector((0,0,height*.47))
    for name,pos,energy,size in [('Key',(4,-6,7),550,5),('Fill',(-4,-3,5),320,4),('Rim',(1,4,6),600,3)]:
        data=bpy.data.lights.new(name,'AREA');data.energy=energy;data.shape='DISK';data.size=size
        o=bpy.data.objects.new(name,data);scene.collection.objects.link(o);o.location=pos;o.rotation_euler=(target-o.location).to_track_quat('-Z','Y').to_euler()
    data=bpy.data.cameras.new('Character camera');o=bpy.data.objects.new('Character camera',data);scene.collection.objects.link(o)
    o.location=(5,-8,4.0 if desc['family'] in ('robot','human') else 3.8*desc['scale']);o.rotation_euler=(target-o.location).to_track_quat('-Z','Y').to_euler();data.type='ORTHO';data.ortho_scale=height*1.25;scene.camera=o


def audit(desc,release):
    rig=bpy.data.objects['Brain_Rig'];scene=bpy.context.scene;signatures={};duplicates=[];issues=[];samples=0
    for a in bpy.data.actions:
        rig.animation_data.action=a;seq=[]
        for i in range(25):
            frame=a.frame_range[0]+(a.frame_range[1]-a.frame_range[0])*i/24
            scene.frame_set(int(frame),subframe=frame%1);samples+=1
            values=[]
            for b in rig.pose.bones:
                vals=tuple(b.location)+tuple(b.rotation_quaternion)+tuple(b.scale)
                if not all(math.isfinite(v) for v in vals):issues.append({'clip':a.name,'bone':b.name,'reason':'nonfinite'})
                if b.name!='antenna':values.extend(round(v,4) for v in vals)
            seq.extend(values)
        digest=hashlib.sha256(json.dumps(seq).encode()).hexdigest()
        if digest in signatures:duplicates.append([signatures[digest],a.name])
        else:signatures[digest]=a.name
    count=len(bpy.data.actions);minimum=len(signatures)>=120
    antenna=any(o.name=='Antenna bulb' for o in scene.objects) and 'antenna' in rig.data.bones
    rig.animation_data.action=bpy.data.actions['idle'];scene.frame_set(0)
    binding_errors=[]
    for o in scene.objects:
        if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers):
            if not o.vertex_groups or any(g.name not in rig.data.bones for g in o.vertex_groups):binding_errors.append(o.name)
    report={'id':desc['id'],'source_sha256':release['source_sha256'],'asset_sha256':release['asset_sha256'],'actions':count,'independent_motion_signatures':len(signatures),'duplicate_motions':duplicates,'samples':samples,'antenna':antenna,'binding_errors':binding_errors,'issues':issues,'success':minimum and antenna and not issues and not binding_errors,
            'scope':'25 normalized pose samples per action, finite transforms, non-antenna motion uniqueness, skin bindings, antenna presence; not full mesh collision simulation'}
    folder=ROOT/'characters'/desc['id'];(folder/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print('CHARACTER_AUDIT',json.dumps(report),flush=True)
    return report


def previews(desc):
    folder=ROOT/'characters'/desc['id'];scene=bpy.context.scene;rig=bpy.data.objects['Brain_Rig']
    for label,clip,p in [('preview','idle',0),('wave','wave',.4),('walk','walk',.25),('fly','fly',.4),('talk','talk',.45),('special','tail_wag' if desc['family']=='quadruped' else 'flap_wings' if desc['family']=='bird' else 'salute',.4)]:
        rig.animation_data.action=bpy.data.actions[clip];scene.frame_set(round(rig.animation_data.action.frame_range[1]*p))
        scene.render.filepath=str(folder/(desc['id']+'-'+label+'.png'));bpy.ops.render.render(write_still=True)
    shutil.copy2(folder/(desc['id']+'-preview.png'),STATIC/'characters'/desc['id']/'preview.png')


def build(identifier):
    desc=next(d for d in ROSTER if d['id']==identifier);folder=ROOT/'characters'/identifier;folder.mkdir(parents=True,exist_ok=True)
    default=ROOT/'characters/default/default.blend'
    if identifier=='default':
        bpy.ops.wm.open_mainfile(filepath=str(default));rig=bpy.data.objects['Brain_Rig'];before=mesh_hash()
        original_names=list(bpy.data.actions.keys());bake(rig,desc,motions.EXTENSIONS)
        assert mesh_hash()==before,'Default mesh changed'
        rig['original_geometry_sha256']=before;rig['preserved_original_actions']=json.dumps(original_names)
    elif desc['family'] in ('robot','human'):
        bpy.ops.wm.open_mainfile(filepath=str(default));rig=bpy.data.objects['Brain_Rig']
        remove_bound(rig,desc['family']=='human');recolor(desc)
        if desc['family']=='human':geometry.human(desc,rig)
        else:geometry.robot_variant(desc,rig)
        # The independent file owns all channels. Add authored personality to
        # the antenna on top of the retained full biped performances.
        for a in bpy.data.actions:
            for c in curves(a):
                if 'antenna' in c.data_path and 'rotation_quaternion' in c.data_path and c.array_index>0:
                    for k in c.keyframe_points:k.co.y*=1+desc['index']*.025
        personalize(rig,desc)
        rig['source_design']='Brain chassis / '+desc['name']
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True);s=geometry.animal(desc);rig=s.rig
        core=json.loads((ROOT/'dock_twoo/server/static/brain3d/character.json').read_text())['actions']
        # Use the original 56 shared behaviors, plus 60 general and 20 anatomical actions.
        original=json.loads((ROOT/'characters/default/default-original-actions.json').read_text())
        names=list(original)+motions.EXTENSIONS
        replace=['salute','clap','high_five','beckon','shrug','facepalm','apologize','give_thanks','heart_gesture','offer_hug','thumbs_up','thumbs_down','knock','open_door','give_gift','juggle','sweep','polish','write','draw']
        extra=motions.QUAD_SPECIAL if desc['family']=='quadruped' else motions.BIRD_SPECIAL
        names=[n for n in names if n not in replace]+extra
        bake(rig,desc,names)
        rig.scale=(desc['scale'],)*3
    rig['character_id']=identifier;rig['character_name']=desc['name'];rig['family']=desc['family'];rig['antenna_style']=desc['species']
    studio(desc);rig.animation_data.action=bpy.data.actions['idle'];bpy.context.scene.frame_set(0)
    bpy.context.scene.frame_start=0;bpy.context.scene.frame_end=120
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(folder/(identifier+'.blend')))
    release=export_saved(desc);report=audit(desc,release);previews(desc)
    readme=f"# {desc['name']}\n\nOpen `{identifier}.blend` and select **Brain_Rig** in the Action Editor.\n\nFamily: {desc['family']}; design: {desc['species']}; {len(release['actions'])} independent Action datablocks.\nEvery file contains its own keyed rig and antenna. The smooth geometry is editable.\n\n`{identifier}.glb` is the exported runtime model. `character.json` lists every clip and duration.\n`validation.json` records the pose-sampling audit and source/export hashes.\n\nRebuild new characters with `scripts/blender/build_library.py -- --id {identifier}`.\nThe default's original meshes and actions are preserved; its build only appends missing actions.\n"
    if identifier!='default':(folder/'README.md').write_text(readme)
    print('CHARACTER_COMPLETE',identifier,'success='+str(report['success']),flush=True)
    if not report['success']:raise RuntimeError('Character validation failed: '+identifier)
