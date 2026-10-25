"""Render a close-up from a saved bird's actual talk Action without changing source."""
import bpy,sys
from pathlib import Path
from mathutils import Vector
rig=bpy.data.objects['Brain_Rig'];scene=bpy.context.scene;identifier=rig['character_id'];source=Path(bpy.data.filepath)
rig.animation_data.action=bpy.data.actions['talk'];action=rig.animation_data.action
# Refresh the full-body still at an open syllable, rather than a closed pause.
scene.frame_set(round(action.frame_range[1]*.45));scene.render.filepath=str(source.parent/(identifier+'-talk.png'));bpy.ops.render.render(write_still=True)
scale=rig.scale.x;target=Vector((0,-.25,2.42))*scale
camera=scene.camera;camera.location=Vector((2.0,-5.3,2.85))*scale
camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.ortho_scale=1.85*scale
scene.render.resolution_x=scene.render.resolution_y=384;scene.render.film_transparent=False
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.035,.06,.08,1)
folder=Path('/tmp/brain-bird-speech')/identifier;folder.mkdir(parents=True,exist_ok=True)
for index in range(48):
    f=action.frame_range[0]+(action.frame_range[1]-action.frame_range[0])*index/48
    scene.frame_set(int(f),subframe=f%1);scene.render.filepath=str(folder/f'{index:03d}.png');bpy.ops.render.render(write_still=True)
print('BIRD_SPEECH_RENDER_COMPLETE',identifier)
