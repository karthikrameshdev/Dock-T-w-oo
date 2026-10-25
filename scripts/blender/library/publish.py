"""Export individual saved sources and produce content-addressed manifests."""
import hashlib,json,shutil
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[3]
STATIC=ROOT/'dock_twoo/server/static/brain3d'

def export_saved(desc,version='4.0.0'):
    source=Path(bpy.data.filepath);rig=bpy.data.objects['Brain_Rig'];scene=bpy.context.scene
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    meshes=[o for o in scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
    bpy.ops.object.select_all(action='DESELECT');rig.select_set(True);bpy.context.view_layer.objects.active=rig
    for o in meshes:o.select_set(True)
    rig.animation_data.action=bpy.data.actions['idle'];scene.frame_set(0)
    path=source.with_suffix('.glb')
    bpy.ops.preferences.addon_enable(module='io_scene_gltf2')
    options=dict(filepath=str(path),export_format='GLB',use_selection=True,export_skins=True,
      export_animations=True,export_animation_mode='ACTIONS',export_force_sampling=True,
      export_anim_single_armature=True,export_morph=True,export_morph_animation=True,
      export_extras=True,export_yup=True,export_cameras=False,export_lights=False)
    supported=bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    bpy.ops.export_scene.gltf(**{k:v for k,v in options.items() if k in supported})
    output=STATIC/'characters'/desc['id'];output.mkdir(parents=True,exist_ok=True);shutil.copy2(path,output/path.name)
    release={**desc,'version':version,'design':desc.get('species','Glossy Blue').replace('_',' ').title(),
      'source':str(source.relative_to(ROOT)),'source_sha256':source_hash,'asset':path.name,
      'asset_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bones':len(rig.data.bones),'meshes':len(meshes),
      'actions':{a.name:{'duration':round((a.frame_range[1]-a.frame_range[0])/scene.render.fps,4),'loop':bool(a.get('looping',False)),
                         'category':a.get('category','original'),'description':a.get('description',a.name.replace('_',' ').title())} for a in bpy.data.actions}}
    (output/'character.json').write_text(json.dumps(release,indent=2)+'\n')
    (source.parent/'character.json').write_text(json.dumps(release,indent=2)+'\n')
    report={**release,'project':release['source'],'glb':str(path.relative_to(ROOT)),'actions':list(release['actions']),
            'triangles':sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in meshes)}
    (source.parent/'character-build.json').write_text(json.dumps(report,indent=2)+'\n')
    if desc['id']=='default':
        shutil.copy2(path,STATIC/'brain.glb');compat={**release,'asset':'brain.glb'}
        (STATIC/'character.json').write_text(json.dumps(compat,indent=2)+'\n')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
    return release
