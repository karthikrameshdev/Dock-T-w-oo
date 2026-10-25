"""Remove retired reference data while preserving the saved Brain meshes/actions.

A recoverable source copy is placed outside the repository before saving.
"""
from pathlib import Path
import hashlib,json,os,shutil
import bpy
source=Path(bpy.data.filepath)
assert source.name=='Brain.blend'
backup_dir=Path(os.environ.get('BRAIN_CHARACTER_BACKUP_DIR',str(Path.home()/'.dock-twoo/character-backups')))
backup_dir.mkdir(parents=True,exist_ok=True)
backup=backup_dir/('Brain-'+hashlib.sha256(source.read_bytes()).hexdigest()[:12]+'.blend')
if not backup.exists():shutil.copy2(source,backup)
meshes={obj.name:obj.data for obj in bpy.context.scene.objects if obj.type=='MESH'}
actions=set(bpy.data.actions.keys());removed=[]
for obj in list(bpy.data.objects):
    if obj.type=='EMPTY' and obj.name.startswith('Reference '):
        removed.append(obj.name);bpy.data.objects.remove(obj,do_unlink=True)
for image in list(bpy.data.images):
    if image.users==0 and image.name not in ('Render Result','Viewer Node'):
        removed.append(image.name);bpy.data.images.remove(image)
for collection in list(bpy.data.collections):
    if collection.name.lower().startswith('reference') and not collection.all_objects:
        bpy.data.collections.remove(collection)
assert all(bpy.data.objects[name].data==mesh for name,mesh in meshes.items())
assert set(bpy.data.actions.keys())==actions
bpy.ops.wm.save_as_mainfile(filepath=str(source))
print('BRAIN_LEGACY_CLEANUP',json.dumps({'preserved_meshes':len(meshes),'preserved_actions':len(actions),'removed':removed,'backup':str(backup)}))
