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

/** Coordinated visemes for the lip, inner mouth, teeth and tongue. */
export class SpeechOverlay {
  constructor(meshes) {
    this.meshes=meshes; this.level=0; this.time=0;
    // Keep mixer-owned morphs separate from the live audio output. PropertyMixer
    // caches unchanged values, so writing over its target can freeze expressions.
    for(const mesh of meshes)mesh.authoredMorphTargetInfluences=[...mesh.morphTargetInfluences];
  }
  beforeMixer() {}
  update({mouth=0, speaking=false, reducedMotion=false, preserveAuthored=false}, dt) {
    if(preserveAuthored) for(const mesh of this.meshes)mesh.morphTargetInfluences.splice(0,mesh.morphTargetInfluences.length,...mesh.authoredMorphTargetInfluences);
    this.time += reducedMotion ? 0 : dt;
    const target=Math.max(0,Math.min(1,Number.isFinite(mouth)?mouth:0));
    this.level += (target-this.level)*(1-Math.exp(-dt*(target>this.level?22:16)));
    if(this.level<.001)this.level=0;
    if(preserveAuthored && !speaking && this.level===0)return this.level;
    // Alternate open and rounded vowels while retaining the incoming amplitude.
    const rounded=speaking ? this.level*(.5+.5*Math.sin(this.time*9.3))*.65 : 0;
    for(const mesh of this.meshes){
      const keys=mesh.morphTargetDictionary;
      mesh.morphTargetInfluences[keys.mouth_open]=this.level;
      if(keys.mouth_round!==undefined)mesh.morphTargetInfluences[keys.mouth_round]=rounded;
      if(keys.tongue_curl!==undefined)mesh.morphTargetInfluences[keys.tongue_curl]=this.level*(.5+.5*Math.sin(this.time*14))*.5;
    }
    return this.level;
  }
}
