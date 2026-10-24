# Brain 3.0.0 · Glossy Blue

`MiniAssistant.blend` is the editable, fully three-dimensional character, rebuilt
from `references/fluffy-blue-robot.png`. The previous design is preserved locally
as `MiniAssistant.before-fluffy.blend` (and the earlier `.pre-codex.blend`).

The current finish replaces all fiber geometry with smooth, polished blue trim
around the cheeks, chin, waist, wrists, upper arms, and thighs. The trim is slimmer
than the earlier fluffy version. A subtle cobalt-to-cyan gradient runs through the
blue enamel accents, with clearcoat reflections and silver ceramic armor.

The gradients are baked into vertex colors and connected to the material's base
color, so Blender and the desktop GLB use the same finish. No fur particles, fiber
meshes, or fuzzy textures remain. The 52-bone rig, 47 actions, tool props, and speech
animation are preserved. The previous fluffy model is saved locally as
`MiniAssistant.before-glossy.blend`. The original reference is packed into a hidden
Blender collection.


This release uses the saved artist-authored `.blend` as its source. The native app,
character preview, and Brain settings display **Brain 3.0.0**. The release manifest
`dock_twoo/server/static/brain3d/character.json` records the source and GLB SHA-256
hashes, 52 bones and 47 named clips. The renderer verifies the actual model bytes
before accepting the version.

To publish saved Blender edits to the local application without rebuilding the design:

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background \
  character/MiniAssistant.blend --python scripts/blender/export_character.py -- --version 3.0.0
```

Use a new semantic version for later character releases. This exporter never saves
or recreates the source project. The procedural builder below is a separate way to
regenerate a design and should not be run over manual edits.

All clips are available in Brain settings → Motions → Character Library, in the
context menu, and by explicit voice requests such as “Brain, play the magnifier
animation.” Listening, thinking and speech select their corresponding body acting
when no explicit gesture is active. Running uses the authored run clip and turns
the body toward its route. Authored facial morphs remain intact outside live speech.

## Review the result

- `MiniAssistant-hero.png`: studio render of the actual model.
- `MiniAssistant-preview.png`: transparent three-quarter view.
- `animation-contact-sheet.jpg`: body views and representative action poses.
- `MiniAssistant-actions.mp4`: 24-second reel of twelve actions.
- `previews/`: individual front, side, back, and action renders.
- `runtime-preview/`: captures and validation report from the actual Qt/WebGL view.

In Blender, select **Brain_Rig** and choose an Action in the Dope Sheet's Action
Editor. Set the playback range to that action's range. The rig has **52 bones and
47 actions**. The head, brows, eyes, pupils, antenna, individual finger segments,
limbs, props, and speech control remain editable. Solid mechanical components are
rigidly weighted; the polished trim follows its corresponding body segment.

The mouth has a cyan lip, a dark interior, upper teeth, and a pink tongue. The
`speech` control bone drives `mouth_open`, `mouth_round`, and `tongue_curl` shape
keys in Blender. The `talk` action includes baked morph animation in the GLB.
During live speech the desktop renderer blends opening, rounded vowels, and tongue
motion using the incoming speech amplitude, with a talking body gesture when idle.
This is amplitude-driven lip animation; phoneme alignment is not implemented.

## Action library

| Purpose | Actions and details |
| --- | --- |
| Travel | `walk`, `run`, `walk_window`, `chase_ball`, `explore`: alternating steps, foot roll, arm swing, body counter-rotation and antenna follow-through |
| Climbing | `climb`, `climb_dock`: alternating reaches, elbow poles, finger grips and lifting feet |
| Flight | `fly`, `hover`, `land`: thruster flames, floating body, tucked legs and landing compression |
| Conversation | `talk`, `listen`, `happy`, `sad`, `nod`, `wink`, `whistle`, `surprised`: head, brow, eye and hand acting |
| Inspection | `magnifier`, `search`, `inspect_icon`: a hand-held magnifier raised in front of the face |
| Photography | `camera`: a three-dimensional camera, aim, shutter finger press, wink and runtime flash |
| Reading | `read`, `type`: a tablet with luminous text, tracking gaze and tapping fingers |
| Scanning | `scan_code`, `scan_screen`, `sensor_scan`, `inspect_window`: code glyphs, reticle and moving scan line |
| Manipulation | `drag`, `push`, `pull_scroll`, `replace_text`: reaching, closed grips and body weight shifts |
| Personality | `wave`, `greet`, `point`, `fold_arms`, `dance`, `celebrate`, `stretch`, `jump`, `kick_ball`, `roll`, `peek`, `ponder`, `sleep`, `turn_around`, `idle` |

The camera, scanning and manipulation clips are visual performances. Existing app
features determine what is photographed, inspected, or moved. Props are skinned to
their grip bones and animate from a collapsed scale when inactive. Character
surfaces remain opaque, preserving the transparent desktop overlay.

## Runtime and source

The application loads `dock_twoo/server/static/brain3d/brain.glb`. The renderer
blends named skeletal actions, drives travel phase by distance, and layers live
blinks, gaze and speech over the same character. The preview at
`http://127.0.0.1:28842/brain3d/index.html` offers all actions, speech preview and
full 360-degree rotation. Three.js is vendored locally; no CDN is needed.

Geometry is authored in `scripts/blender/fluffy_design.py`; acting and prop grips
are in `scripts/blender/fluffy_animation.py`. `build_brain.py` supplies mesh helpers,
rig construction, action baking, lighting, reference packing and export.

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background \
  --python scripts/blender/build_brain.py -- \
  --project "$PWD/character/MiniAssistant.blend" \
  --export "$PWD/dock_twoo/server/static/brain3d/brain.glb" --preview
```

The builder recreates the asset, so save manual edits to a separate `.blend` before
rebuilding. All paths above assume the repository root.

## Validation and renders

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background \
  character/MiniAssistant.blend --python scripts/blender/verify_brain.py
.venv/bin/python -m pytest tests/test_brain_3d.py tests/test_voice_and_motion.py -q
.venv/bin/python scripts/verify_brain_3d.py --all-actions --output /tmp/brain-3-runtime
node scripts/verify_brain_face.mjs
```

Run the Blender audit before pytest: the audit records hashes of the current
`.blend` and GLB. It checks every frame and sampled action transitions against
conservative helmet and ear clearance envelopes for forearms and hands. This is
not a full physics or all-mesh collision test. The Qt check renders the actual
export and verifies blinking, speech, moving skeletons, props and finite transforms.

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background \
  character/MiniAssistant.blend --python scripts/blender/render_character_gallery.py
/Applications/Blender.app/Contents/MacOS/Blender --background \
  character/MiniAssistant.blend --python scripts/blender/render_character_showcase.py -- --video
python3 scripts/blender/package_character_previews.py
```

The showcase renderer creates temporary frames under `previews/reel-frames/`.
Packaging uses Pillow (available in this machine's system Python), labels the contact sheet, and encodes the reel using ffmpeg. The source
`.blend` keeps its transparent studio setup; showcase staging is never saved over it.

## Brain 3.0.0 verification

The saved source was exported without modification. The Blender audit passed
2,524 frames and 423 transition samples. The native renderer exercised all 47
clips across 54 states, including props, blink recovery, live and authored mouth
motion, activity-driven listening/thinking, and reduced motion. The release source
and asset hashes are recorded in `character.json`; unit and integration checks
cover the complete voice animation dispatch and the full demo playlist.

The saved runtime report reflects a run alongside the desktop app and test suite;
its measured frame rate is an observation, not a cross-device performance guarantee.
