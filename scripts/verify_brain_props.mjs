/** Exercise the shipped GLB with the actual Three.js mixer. */
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {AnimationMixer,Vector3} from '../dock_twoo/server/static/brain3d/vendor/three.module.js';
import {register} from 'node:module';
register('./brain_three_loader.mjs',import.meta.url);
const {GLTFLoader}=await import('../dock_twoo/server/static/brain3d/vendor/loaders/GLTFLoader.js');
const bytes=await readFile(new URL('../dock_twoo/server/static/brain3d/brain.glb',import.meta.url));
const gltf=await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
const model=gltf.scene,mixer=new AnimationMixer(model),bones={};
model.traverse(node=>{if(node.isBone)bones[node.name]=node;});
const props=['propball','prophammer','propanvil','proptether','propballoon','propparachute'];
assert.ok(props.every(name=>bones[name]));
function pose(name,time){mixer.stopAllAction();const clip=gltf.animations.find(clip=>clip.name===name);const action=mixer.clipAction(clip);action.reset().play();action.time=time;mixer.update(0);model.updateMatrixWorld(true);}
pose('kick_ball',8/30);const start=bones.propball.getWorldPosition(new Vector3());
for(let frame=8;frame<=42;frame+=.25){pose('kick_ball',frame/30);assert.ok(bones.propball.getWorldPosition(new Vector3()).distanceTo(start)<1e-5,'Ball moved before foot contact');}
pose('kick_ball',43/30);assert.ok(bones.propball.getWorldPosition(new Vector3()).distanceTo(start)>.02);
for(const name of ['hammer','balloon','parachute']){
 pose(name,1.5);
 assert.ok(bones[{hammer:'prophammer',balloon:'proptether',parachute:'propparachute'}[name]].scale.x>.9);
 pose('idle',.5);assert.ok(props.every(name=>bones[name].scale.x<.002),'A toy remained visible in idle');
}
console.log('PASS: exported ball stays still through foot contact; toys deploy and retract with the real mixer.');
