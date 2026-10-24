/** Real Three.js mixer regression: blinks must reopen and gaze must not drift. */
import assert from 'node:assert/strict';
import {Bone, AnimationClip, AnimationMixer, VectorKeyframeTrack, LoopRepeat, NumberKeyframeTrack, Mesh, BufferGeometry, Float32BufferAttribute} from '../dock_twoo/server/static/brain3d/vendor/three.module.js';
import {FaceOverlay, SpeechOverlay} from '../dock_twoo/server/static/brain3d/face.js';
const root=new Bone(), bones={};
for(const side of ['L','R']) {
  const eye=new Bone();eye.name='eye'+side;root.add(eye);bones[eye.name]=eye;
  const pupil=new Bone();pupil.name='pupil'+side;eye.add(pupil);bones[pupil.name]=pupil;
}
const tracks=Object.keys(bones).flatMap(name=>[
  new VectorKeyframeTrack(name+'.scale',[0,1],[1,1,1,1,1,1]),
  new VectorKeyframeTrack(name+'.position',[0,1],[0,0,0,0,0,0]),
]);
const mixer=new AnimationMixer(root);
const action=mixer.clipAction(new AnimationClip('idle',1,tracks));action.setLoop(LoopRepeat).play();
const face=new FaceOverlay(bones);
for(let frame=0;frame<1200;frame++){
  face.beforeMixer();mixer.update(1/60);
  const blink=frame%60<12?Math.sin((frame%60)/12*Math.PI):0;
  face.afterMixer({blink,gazeX:Math.sin(frame/10),gazeY:.5});
  if(blink===0)assert.deepEqual(face.scales(),[1,1]);
  assert.ok(Math.abs(bones.pupilL.position.x)<=.0350001);
  assert.ok(Math.abs(bones.pupilL.position.y)<=.0250001);
}
console.log('PASS: 20 repeated blinks reopen fully; gaze does not accumulate over 1,200 frames.');

// Speech moves all four surfaces together, stays bounded, then fully closes.
const surfaces=Array.from({length:4},()=>({morphTargetDictionary:{mouth_open:0,mouth_round:1,tongue_curl:2},morphTargetInfluences:[0,0,0]}));
const speech=new SpeechOverlay(surfaces);
for(let frame=0;frame<300;frame++){
  speech.update({mouth:frame<120?.8:0,speaking:frame<120},1/60);
  for(const mesh of surfaces){
    assert.ok(mesh.morphTargetInfluences.every(v=>Number.isFinite(v)&&v>=0&&v<=1));
    assert.equal(mesh.morphTargetInfluences[0],surfaces[0].morphTargetInfluences[0]);
  }
  if(frame===119)assert.ok(surfaces[0].morphTargetInfluences[0]>.79);
}
assert.ok(surfaces.every(mesh=>mesh.morphTargetInfluences.every(v=>v===0)));
console.log('PASS: lip, cavity, teeth and tongue share bounded visemes and close after speech.');

// Saved Blender mouth acting survives when no live audio is overriding it.
const geometry = new BufferGeometry();
geometry.morphAttributes.position = [new Float32BufferAttribute([0,0,0],3)];
const lip = new Mesh(geometry);lip.name='Lip';
lip.morphTargetDictionary={mouth_open:0};lip.morphTargetInfluences=[0];
const overlay=new SpeechOverlay([lip]);
const savedMixer=new AnimationMixer(lip);
const savedAction=savedMixer.clipAction(new AnimationClip('authored talk',1,[new NumberKeyframeTrack('Lip.authoredMorphTargetInfluences[0]',[0,1],[.65,.65])])).play();
for(let frame=0;frame<180;frame++){
  overlay.beforeMixer();savedMixer.update(1/60);
  overlay.update({preserveAuthored:true},1/60);
  assert.ok(Math.abs(lip.morphTargetInfluences[0]-.65)<.00001);
}
savedAction.stop();
savedMixer.clipAction(new AnimationClip('rest',1,[new NumberKeyframeTrack('Lip.authoredMorphTargetInfluences[0]',[0,1],[0,0])])).play();
for(let frame=0;frame<30;frame++){
  overlay.beforeMixer();savedMixer.update(1/60);overlay.update({preserveAuthored:true},1/60);
}
assert.equal(lip.morphTargetInfluences[0],0);
console.log('PASS: authored Blender mouth morphs play intact and return to the neutral pose.');
