"""Render reproducible hero views and action contact-sheet sources from the asset."""
import bpy, math
from pathlib import Path
from mathutils import Vector
root=Path(bpy.data.filepath).parent
out=root/'previews';out.mkdir(exist_ok=True)
scene=bpy.context.scene;rig=bpy.data.objects['Brain_Rig']
scene.render.resolution_x=scene.render.resolution_y=512
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.film_transparent=True
scene.eevee.taa_render_samples=24
camera=scene.camera
views=[('hero','wave',.40,(3.3,-9,4)),('front','idle',0,(0,-10,3.4)),('back','idle',0,(4,9,3.6)),('side','idle',0,(10,-.3,3.6)),('walk','walk',.23,(7,-8,3.8)),('run','run',.21,(7,-8,3.8)),('climb','climb',.35,(4,-9,4)),('fly','fly',.5,(3.3,-9,4)),('talk','talk',.43,(3.3,-9,4)),('magnifier','magnifier',.5,(3.3,-9,4)),('camera','camera',.58,(3.3,-9,4)),('read','read',.5,(3.3,-9,4)),('scan_code','scan_code',.4,(3.3,-9,4)),('drag','drag',.5,(3.3,-9,4))]
for label,action,p,pos in views:
    rig.animation_data.action=bpy.data.actions[action]
    scene.frame_set(round(rig.animation_data.action.frame_range[1]*p))
    for obj in bpy.data.objects:
        if obj.type=='MESH' and obj.data.shape_keys:
            keys=obj.data.shape_keys.key_blocks
            if 'mouth_open' in keys:keys['mouth_open'].value=.75 if label=='talk' else 0
            if 'mouth_round' in keys:keys['mouth_round'].value=.10 if label=='talk' else 0
    camera.location=pos;camera.rotation_euler=(Vector((0,0,2.5))-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(out/(label+'.png'))
    bpy.ops.render.render(write_still=True)
print('GALLERY_READY',out)
