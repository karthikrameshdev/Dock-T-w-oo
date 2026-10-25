# Brain 3.2.0 · Glossy Blue

`Brain.blend` is the artist-authored source for the application's only character.
The saved silver ceramic and cobalt-blue geometry, neck, face, individual fingers,
and spring antenna are preserved. The original 222 character meshes retain their
geometry hash when adding props. The complete rig has 58 bones and 56 clips.

The application renders `dock_twoo/server/static/brain3d/brain.glb` with Three.js
inside the transparent Qt view. The release manifest identifies the exact saved
source and export by SHA-256. It is checked before the renderer accepts the model.
There is no raster character, alternate head, 2D toy window, or legacy fallback.
Loading and renderer errors display status text rather than another character.

## Edit and export

Open `Brain.blend`, select **Brain_Rig**, and choose a named action in Blender's
Dope Sheet Action Editor. Match the playback range to the action's range. Edit
and save the existing project, then export with a new semantic version:

```bash
blender --background character/Brain.blend \
  --python scripts/blender/export_character.py -- --version 3.2.0
```

The exporter reads the saved project without rebuilding or saving over it.
`rig_helpers.py` contains non-destructive mesh and IK helpers for the prop and
clearance scripts. There is no alternate procedural character generator.

## Actions

All clips are available in Brain settings → Motions → Character Library, the
context menu, and explicit voice requests such as “Brain, play the hammer
animation.” Listening, thinking, and speech choose corresponding acting when no
explicit gesture is active. Walking and running are driven by distance travelled;
turns rotate the same three-dimensional skeleton.

The face retains its authored brows, eyes and pupils. Repeated blinks reopen
fully. Live audio drives the four mouth surfaces together: lip, cavity, teeth,
and tongue. This is amplitude-driven mouth animation, rather than phoneme timing.
The `speech` bone and `mouth_open`, `mouth_round`, and `tongue_curl` keys remain
editable in Blender. Authored facial animation plays outside live speech.

The head indicator shows online green, offline red, listening yellow, and thinking
purple, responding cyan, and queued orange, with corresponding glow and motion.
Only the microphone owner has a yellow aura behind its body. Reduced motion freezes body acting.

## Contact-based toys

Run `add_prop_actions.py` on the saved project to regenerate the four toy clips.
It preserves the character meshes and adds props bound to the same skeleton.

- Ball: stationary through foot contact at frame 42; launch at frame 43, followed
  by gravity, damped bounces and rolling friction.
- Hammer: grip follows the palm; the striking surface meets the pad at frames 45
  and 86, followed by rebound and recovery.
- Balloon: tether follows the hand; the balloon sways around its attachment.
- Parachute: both hands track suspension endpoints on the moving canopy.

Body and prop share one animation clock. Separate widgets and timers cannot
launch a ball before foot contact. Starting a conversation puts the toys away.

## Verification

After exporting, run:

```bash
blender --background character/Brain.blend --python scripts/blender/verify_brain.py
blender --background character/Brain.blend --python scripts/blender/verify_prop_actions.py
node scripts/verify_brain_props.mjs
python scripts/verify_brain_3d.py --all-actions
```

The Qt check needs the running local console server. Blender reports cover 3,607
frames, 504 transition samples, and 573 prop samples. Contact and clearance reports
are bound to both source and export hashes. The arm/helmet audit uses conservative
envelopes; it is not a full-body physics collision solver.

`Brain-hero.png` and `Brain-preview.png` show the saved design. `Brain-actions.mp4`
shows twelve body actions; `Brain-props.mp4` shows the four toy performances rendered
from Blender. `previews/props/` contains contact and grip poses. Preview tools read
the saved project without saving or changing its design.

The interactive preview at `http://127.0.0.1:28842/brain3d/index.html` supports all
clips, speech, indicator states, and full rotation. Three.js is vendored locally.

## Shared desktop playground

`add_social_actions.py` adds six dense Blender performances without changing any
mesh: handshake, dance_together, playful_spar, dash, air_spin, and cheer_partner. The clearance
audit covers these clips too. The local playground schedules these with existing
handshakes, walking, flying, waving and ball contact clips; it does not call an LLM.
The eight group activities are available under Brain's right-click **Play together**
menu. Playful sparring is a gesture sequence, not a full rigid-body physics engine.

**Add another Brain** works on one display or several. Characters have separate
positions, gestures and conversation histories; audio, reading, model execution and
credit limits remain shared. The layout fits crowds to the available space and
steers characters around each other's window footprints. **Roam across all screens**
lets characters cross connected extended displays independently of dock placement.
