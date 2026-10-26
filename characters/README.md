# Brain companion library

Thirty separately editable Blender characters, with **136 Actions per file**
(4,080 stored clips). Each has an individual antenna, a smooth glossy finish,
a facial rig, a saved studio scene, and a runtime GLB. Birds have hinged upper
and lower beaks with an internal tongue; the other families have teeth and tongues.
The original Brain is the default. Its original geometry and 56 Actions are
preserved; 80 additional Actions expand its performance library.

Open `index.html` for the local visual catalog, or open the running app's
`http://127.0.0.1:28842/brain3d/library.html` for interactive 3D previews.
`library-contact-sheet.jpg` shows all thirty rendered designs. The local HTML
catalog also links directly to every Blender source. If the app uses another
port, substitute that port in the preview URL.

## Files and editing

Each folder uses its character ID for the source, export, and renders:

```
default/default.blend
corgi/corgi.blend
owl/owl.blend
artist/artist.blend
```

Open a `.blend`, select **Brain_Rig**, then select a named clip in the **Action
Editor**. Actions have fake users so they remain saved independently. Set the
scene's playback range to the chosen Action's range; the default timeline is the
idle range, not the duration of every clip. All sources include editable meshes,
materials, skeletons, morphs, and baked keyframes. No linked external model files
are needed.

Each folder contains a `character.json` manifest with clip names and durations,
a `character-build.json` report, a `validation.json` audit, a `.glb` export, and
six native Blender renders: idle, wave, walk, flight, speech and a specialty pose.
Existing default reference renders and videos are retained under default names.
They cover the original animation set; use the interactive preview for all clips.

## Collection

- **Robots:** Brain, Orbit, Ember, Mint, Cosmo, Pixel.
- **Dogs:** Biscuit (corgi), Scout (beagle), Frost (husky).
- **Cats:** Tux, Patches, Mochi.
- **Birds:** Luma (owl), Rio (parrot), Pip (robin), with articulated flying wings.
- **Other animals:** Remy, Pebble, Leo, Tango, Fable, Clover, Bao, Nori, Maple.
  Rat and mouse retain smaller world scales in desktop use.
- **People:** Nova, Ada, Indigo, Saffron, Kai, Zuri, with distinct skin, hair,
  clothing and profession accessories.

The shared vocabulary includes locomotion, flight, climbing, waving, speech,
reading, inspection, camera, scanning, dragging, pulling, gestures, reactions,
and desktop toy performances. Animals add tail, ear, grooming, sniffing and paw
motions; birds add flapping, preening, pecking, hopping, perching and aerial poses.
The catalog preview exposes each model's actual animation list. Walk, run and climb
are in-place cycles so the desktop controller can move the character along a
window or screen edge without conflicting root motion.

## Building and checking

Run from the repository root; replace `blender` with the installed executable.

```sh
blender --background --threads 4 --python scripts/blender/build_library.py -- --id corgi
python scripts/blender/build_all_characters.py --blender /path/to/blender --jobs 3
python scripts/blender/package_library.py
node scripts/verify_character_library.mjs
python scripts/verify_character_library.py
python -m pytest tests/test_character_library.py tests/test_brain_3d.py -q
```

The last renderer check requires the local app server and Qt WebEngine. It runs
without the microphone. `runtime-validation.json` records Three.js clip loading,
finite poses, motion and loop checks. `webgl-validation.json` records real Qt
rendering across the collection; `runtime-gallery/` contains those captures.
The default also retains its frame-level arm/helmet and toy-contact audits.

`bird-speech.gif` and `bird-speech.mp4` show the three birds in close-up. Their
upper and lower beaks are separate solid meshes with hinged speech morphs.
`node scripts/verify_bird_beaks.mjs` measures the bill-tip positions during
authored talking, live speech over idle/waving, and the return to a closed bill.
The tongue follows the lower beak; birds have no human teeth or floating smile.

Motion is procedural choreography adapted to the three rig families, with
character-specific timing and follow-through. Each file owns its keyframes;
shared semantic actions are reused across characters. The uniqueness audit
samples 25 poses per clip and excludes antenna motion, so antenna changes alone
cannot inflate the count. Duplicate legacy clips are reported and excluded from
the distinct-motion total. These checks do not prove full-body collision-free
physics or artist-polished contact for every action on every anatomy. Desktop
speech uses amplitude-driven mouth motion, not phoneme-timed lip sync.

The runtime's default `brain.glb` remains a compatibility copy of
`default/default.glb`; it is outside the default source folder. A preview query
such as `index.html?character=owl` selects another model, while existing desktop
companions continue using the default unless their model URL is changed.
