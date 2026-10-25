# Cosmo

Open `cosmo.blend` and select **Brain_Rig** in the Action Editor.

Family: robot; design: space; 136 independent Action datablocks.
Every file contains its own keyed rig and antenna. The smooth geometry is editable.

`cosmo.glb` is the exported runtime model. `character.json` lists every clip and duration.
`validation.json` records the pose-sampling audit and source/export hashes.

Rebuild new characters with `scripts/blender/build_library.py -- --id cosmo`.
The default's original meshes and actions are preserved; its build only appends missing actions.
