# Brain character library implementation plan

Target: 30 editable characters, each with at least 120 independently stored and
keyed Blender Actions, an individual antenna, a GLB, a preview, and an audit.

1. Move the current complete `character/` directory to `characters/default/` and
   rename its saved source to `default.blend`. Preserve the current 56 actions,
   248 meshes, materials, mouth shapes, and contact-based toys. Append 80 motions.
2. Build five additional robot styles, three dogs, three cats, three flying birds,
   a small rat and mouse, seven other animals, and six human companions. Use the
   explicit roster in `scripts/blender/library/roster.py`.
3. Author separate biped, quadruped, and avian motion programs: limb counts, wing
   hinges, tails, ears, and head motion must suit the body. Shared semantic actions
   may be retargeted, but every source owns baked keyframes. Do not count aliases,
   empty clips, or exact duplicated motions toward the minimum.
4. Keep default animation names compatible with desktop behaviors. Export every
   model with its own manifest, source/export hashes, action durations, and rig
   metadata. Keep `brain.glb` and `character.json` as the default runtime entry.
5. Provide a visual catalog and per-character animation preview. Validate bone
   bindings, finite transforms, action counts and uniqueness, loop boundaries,
   antenna presence, species-appropriate limbs, and runtime loading. Preserve
   default toy-contact and arm/helmet audits. Render every character for review.

Style: smooth, cute, three-dimensional companions with glossy color accents;
no strand fur. Animals have readable ears, muzzles/beaks, tails, and markings.
Humans have distinct skin tones, hair, clothes, and profession accessories.
Rat and mouse remain visibly smaller than the other companions.

The motion library is procedural keyframe authoring, not 4,080 individually
hand-animated performances. Validation must state what is measured; geometric
clearance checks are not a complete physics simulation.
