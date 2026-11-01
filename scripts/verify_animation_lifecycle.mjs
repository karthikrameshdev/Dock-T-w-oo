/** Exercise real mixer ownership across thousands of long-running transitions. */
import assert from 'node:assert/strict';
import {register} from 'node:module';
import {readFile} from 'node:fs/promises';
import {AnimationMixer} from '../dock_twoo/server/static/brain3d/vendor/three.module.js';
import {ActionPlayer} from '../dock_twoo/server/static/brain3d/action-player.js';
import {FaceOverlay, SpeechOverlay} from '../dock_twoo/server/static/brain3d/face.js';
import {disposeScene} from '../dock_twoo/server/static/brain3d/dispose-scene.js';
register('./brain_three_loader.mjs',import.meta.url);
const {GLTFLoader}=await import('../dock_twoo/server/static/brain3d/vendor/loaders/GLTFLoader.js');
const bytes=await readFile(new URL('../characters/default/default.glb',import.meta.url));
const gltf=await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
// Reproduce the former retention bug using the same vendored Three.js version.
const old=new AnimationMixer(gltf.scene);let previous;
for(const clip of gltf.animations){const next=old.clipAction(clip).reset().play();if(previous)next.crossFadeFrom(previous,.16,false);old.update(.2);previous=next;}
assert.equal(old.stats.actions.inUse,gltf.animations.length);
const previousActiveActions=old.stats.actions.inUse;
old.stopAllAction();old.uncacheRoot(gltf.scene);
const mixer=new AnimationMixer(gltf.scene),player=new ActionPlayer(mixer,gltf.animations);
for(let index=0;index<3000;index++){
 const action=player.select(gltf.animations[index%gltf.animations.length].name);
 assert.ok(mixer.stats.actions.inUse<=2);
 assert.ok(mixer.stats.actions.total<=2);
 // Include fast interruptions and loops, not only completed transitions.
 player.update(index%3===0?.03:.2);
 assert.ok(Number.isFinite(action.time));
}
player.update(.2);assert.equal(mixer.stats.actions.inUse,1);assert.equal(mixer.stats.actions.total,1);
// The resource cap freezes only the skeleton; facial overlays remain live.
const bones={},mouths=[];
gltf.scene.traverse(n=>{if(n.isBone)bones[n.name]=n;if(n.morphTargetDictionary?.mouth_open!==undefined)mouths.push(n);});
const face=new FaceOverlay(bones),speech=new SpeechOverlay(mouths);
face.beforeMixer();player.setStationary(true);
const pose=()=>Object.values(bones).filter(b=>!/^eye|^pupil/.test(b.name)).flatMap(b=>[...b.position,...b.quaternion,...b.scale]);
const fixed=pose();
let scratch;
for(let frame=0;frame<120;frame++){
 face.beforeMixer();player.setStationary(true);
 face.afterMixer({blink:frame%2?1:0,gazeX:.5});
 speech.update({mouth:.8,speaking:true,preserveAuthored:true},1/18);
 assert.deepEqual(pose(),fixed);assert.equal(player.current.time,0);
 const currentScratch=face.eyes.flatMap(part=>[part.authoredScale,part.authoredPosition]);
 if(scratch)currentScratch.forEach((value,index)=>assert.equal(value,scratch[index]));
 scratch=currentScratch;
}
assert.ok(mouths.some(n=>n.morphTargetInfluences[n.morphTargetDictionary.mouth_open]>.5));
assert.ok(face.scales().some(v=>v>0 && v<.1));
player.setStationary(false);player.select('wave');player.update(.2);
assert.ok(player.current.time>0);assert.notDeepEqual(pose(),fixed);
player.dispose();assert.equal(mixer.stats.actions.inUse,0);assert.equal(mixer.stats.bindings.total,0);
const resources=new Map();
gltf.scene.traverse(node=>{
 for(const resource of [node.geometry,...(Array.isArray(node.material)?node.material:[node.material])]) {
  if(resource && !resources.has(resource)){
   resources.set(resource,0);resource.addEventListener('dispose',()=>resources.set(resource,resources.get(resource)+1));
  }
 }
});
assert.ok(resources.size>0);
disposeScene(gltf.scene);
assert.equal(gltf.scene.children.length,0);
assert.ok([...resources.values()].every(count=>count===1),'Shared geometry/materials must be released exactly once');
disposeScene(gltf.scene);
assert.ok([...resources.values()].every(count=>count===1));
console.log(JSON.stringify({previousActiveActions,currentMaxActiveActions:2,transitions:3000,releasedResources:resources.size,success:true}));
