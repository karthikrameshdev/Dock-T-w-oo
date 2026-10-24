/** Real Three.js mixer regression: blinks must reopen and gaze must not drift. */
import assert from 'node:assert/strict';
import {Bone, AnimationClip, AnimationMixer, VectorKeyframeTrack, LoopRepeat} from '../dock_twoo/server/static/brain3d/vendor/three.module.js';
import {FaceOverlay} from '../dock_twoo/server/static/brain3d/face.js';
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
