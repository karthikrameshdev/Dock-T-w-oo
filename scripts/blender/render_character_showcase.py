"""Render the character itself (not a concept image) as a studio hero and reel."""
import bpy, math, sys
from pathlib import Path
from mathutils import Vector
root=Path(bpy.data.filepath).parent
scene=bpy.context.scene;rig=bpy.data.objects['Brain_Rig']
scene.render.image_settings.file_format='PNG'
scene.render.film_transparent=False
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.48,.57,.63,1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.5
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,.015))
floor=bpy.context.object;floor.name='Preview studio floor'
mat=bpy.data.materials.new('Studio mist');mat.diffuse_color=(.48,.57,.63,1);mat.use_nodes=True
mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.48,.57,.63,1)
mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.85
floor.data.materials.append(mat)
scene.camera.location=(3.1,-9,3.9)
scene.camera.rotation_euler=(Vector((0,0,2.5))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
scene.camera.data.ortho_scale=6.0
scene.render.resolution_x=scene.render.resolution_y=1024;scene.render.resolution_percentage=100
scene.eevee.taa_render_samples=64
rig.animation_data.action=bpy.data.actions['wave'];scene.frame_set(18)
scene.render.filepath=str(root/'Brain-hero.png');bpy.ops.render.render(write_still=True)
if '--video' in sys.argv:
    out=root/'previews'/'reel-frames';out.mkdir(exist_ok=True,parents=True)
    scene.render.resolution_x=scene.render.resolution_y=640;scene.eevee.taa_render_samples=16
    shots=['wave','walk','run','climb','fly','talk','magnifier','camera','read','scan_code','drag','dance']
    labels=['HELLO, HUMAN','WALK','RUN','CLIMB','FLY','TALK','INSPECT','TAKE A PHOTO','READ','SCAN CODE','DRAG & PULL','CELEBRATE']
    idx=0
    for shot,label in zip(shots,labels):
        action=bpy.data.actions[shot];rig.animation_data.action=action
        for f in range(48):
            p=f/47;frame=action.frame_range[1]*p;scene.frame_set(int(frame),subframe=frame%1)
            yaw=.32 if shot not in ('walk','run','climb') else .75
            scene.camera.location=(math.sin(yaw)*10,-math.cos(yaw)*10,3.9)
            scene.camera.rotation_euler=(Vector((0,0,2.5))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
            scene.render.filepath=str(out/f'{idx:04d}.png');bpy.ops.render.render(write_still=True)
            idx+=1
    (root/'previews'/'reel-labels.txt').write_text('\n'.join(labels))
print('SHOWCASE_READY',root)
