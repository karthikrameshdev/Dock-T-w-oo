/** Exercise real mixer ownership across thousands of long-running transitions. */
import assert from 'node:assert/strict';
import {register} from 'node:module';
import {readFile} from 'node:fs/promises';
import {AnimationMixer} from '../dock_twoo/server/static/brain3d/vendor/three.module.js';
import {ActionPlayer} from '../dock_twoo/server/static/brain3d/action-player.js';
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
player.dispose();assert.equal(mixer.stats.actions.inUse,0);assert.equal(mixer.stats.bindings.total,0);
console.log(JSON.stringify({previousActiveActions,currentMaxActiveActions:2,transitions:3000,success:true}));
