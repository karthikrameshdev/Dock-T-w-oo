"""Render actual contact poses from the saved Brain project, without saving it."""
from pathlib import Path
import math,bpy,sys
from mathutils import Vector
root=Path(bpy.data.filepath).parent;scene=bpy.context.scene;rig=bpy.data.objects['Brain_Rig']
scene.render.engine='CYCLES';scene.cycles.samples=12
scene.render.resolution_x=640;scene.render.resolution_y=640;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.055,.075,.09,1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.5
scene.camera.data.ortho_scale=6.3
out=root/'previews'/'props';out.mkdir(exist_ok=True,parents=True)
shots=[('kick_ball',32),('kick_ball',42),('kick_ball',48),('kick_ball',61),
       ('hammer',22),('hammer',45),('hammer',86),('balloon',40),('balloon',80),('parachute',40)]
for action,frame in shots:
    rig.animation_data.action=bpy.data.actions[action];scene.frame_set(frame)
    scene.camera.location=(5.8,-8.5,3.6)
    target=Vector((0,-.5,2.4))
    scene.camera.rotation_euler=(target-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(out/f'{action}-{frame}.png');bpy.ops.render.render(write_still=True)
if '--video' in sys.argv:
    scene.render.resolution_x=scene.render.resolution_y=448;scene.cycles.samples=8
    frames=root/'previews'/'prop-reel';frames.mkdir(exist_ok=True,parents=True)
    index=0
    for name in ('kick_ball','hammer','balloon','parachute'):
        action=bpy.data.actions[name];rig.animation_data.action=action
        for frame in range(int(action.frame_range[1])+1):
            scene.frame_set(frame)
            scene.render.filepath=str(frames/f'{index:04d}.png');bpy.ops.render.render(write_still=True)
            index+=1
print('BRAIN_PROP_RENDERS',out)
