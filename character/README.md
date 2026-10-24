# Brain character source

Open `MiniAssistant.blend` in Blender. This is the editable source for the desktop
assistant, including its mint pillow-shaped helmet, curved inset visor, white eyes
and smile, dark pupils, ivory body, lavender joints, and matching gloves and boots.
Original reference images are packed into the hidden **Original design references**
collection. There is one helmet and one antenna; no bag, scan fan, or faded sprites.

**Brain_Rig** has 21 bones and 35 named Actions. Select the rig and open the Action
Editor to preview idle, walking, running, climbing, waving, reading, pulling, and the
other assistant gestures. Each solid mechanical part is rigidly weighted to its
joint. The smile has a `mouth_open` shape key, with its default value zero. The eyes
and pupils have separate bones for blinking and gaze. Scene yaw provides real turns.

The app uses `dock_twoo/server/static/brain3d/brain.glb`. Its animation mixer blends
skeletal poses on a single opaque mesh set. Locomotion phase follows distance
travelled; hand meshes disable stale bind-pose frustum culling. Live gaze, blinks,
voice mouth motion, and antenna status are applied to the same model.

## Rebuild

From the repository root on macOS:

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background \
  --python scripts/blender/build_brain.py -- \
  --project "$PWD/character/MiniAssistant.blend" \
  --export "$PWD/dock_twoo/server/static/brain3d/brain.glb" --preview
```

The builder recreates the model and actions; save manual Blender edits separately
before rebuilding. Recovery `.blend1` and `.pre-codex.blend` files remain local and
are ignored by Git. The preview PNG and portable manifest are regenerated here.

## Validate

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background \
  character/MiniAssistant.blend --python scripts/blender/verify_brain.py
.venv/bin/python scripts/verify_brain_3d.py
```

The Blender audit evaluates every frame and sampled idle/action transitions against
conservative helmet and ear clearance envelopes for both forearms and gloves.
`animation-validation.json` records its result; this is a clearance check rather
than a full rigid-body physics simulation. The native Qt check loads the actual
GLB, verifies its animation library, renders six transparent overlay views, and
reports invalid transforms or translucent body materials under `/tmp`.

The interactive preview at `http://127.0.0.1:28842/brain3d/index.html` (or your
configured console port) offers animation selection and continuous head/body yaw.
Three.js 0.186.1 is vendored locally under its MIT license; playback needs no CDN.
