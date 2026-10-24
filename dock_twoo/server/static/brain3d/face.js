/** Apply live facial motion without accumulating edits on cached mixer bindings. */
export class FaceOverlay {
  constructor(bones) {
    this.eyes = ['L', 'R'].map(side => ({
      eye: bones['eye.'+side] || bones['eye'+side] || bones['eye_'+side],
      pupil: bones['pupil.'+side] || bones['pupil'+side] || bones['pupil_'+side],
      authoredScale: null, authoredPosition: null,
    }));
  }
  beforeMixer() {
    // Three's PropertyMixer skips unchanged animation values. Restore the last
    // authored pose first, or repeated procedural blinks shrink eyes forever.
    for (const part of this.eyes) {
      if (part.eye && part.authoredScale) part.eye.scale.copy(part.authoredScale);
      if (part.pupil && part.authoredPosition) part.pupil.position.copy(part.authoredPosition);
    }
  }
  afterMixer({blink=0, gazeX=0, gazeY=0}) {
    for (const part of this.eyes) {
      if (part.eye) {
        part.authoredScale = part.eye.scale.clone();
        part.eye.scale.y = part.authoredScale.y * Math.max(.035, 1-Math.max(0,Math.min(1,blink)));
      }
      if (part.pupil) {
        part.authoredPosition = part.pupil.position.clone();
        part.pupil.position.x += Math.max(-1,Math.min(1,gazeX))*.035;
        part.pupil.position.y -= Math.max(-1,Math.min(1,gazeY))*.025;
      }
    }
  }
  scales() { return this.eyes.map(part=>part.eye?.scale.y ?? 0); }
}
