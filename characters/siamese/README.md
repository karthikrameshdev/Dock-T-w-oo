# Mochi

Open `siamese.blend` and select **Brain_Rig** in the Action Editor.

Family: quadruped; design: siamese; 136 independent Action datablocks.
Every file contains its own keyed rig and antenna. The smooth geometry is editable.

`siamese.glb` is the exported runtime model. `character.json` lists every clip and duration.
`validation.json` records the pose-sampling audit and source/export hashes.

Rebuild new characters with `scripts/blender/build_library.py -- --id siamese`.
The default's original meshes and actions are preserved; its build only appends missing actions.
