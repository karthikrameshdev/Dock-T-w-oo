/** Load every exported library clip through the actual vendored Three.js mixer. */
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {register} from 'node:module';
import {AnimationMixer} from '../dock_twoo/server/static/brain3d/vendor/three.module.js';
register('./brain_three_loader.mjs',import.meta.url);
const {GLTFLoader}=await import('../dock_twoo/server/static/brain3d/vendor/loaders/GLTFLoader.js');
const root=new URL('../',import.meta.url),catalog=JSON.parse(await readFile(new URL('characters/catalog.json',root)));
const requested=process.argv.slice(2),report={success:true,characters:[],errors:[]};
for(const entry of catalog.characters.filter(e=>!requested.length||requested.includes(e.id))){
 try{
  const base=new URL(`characters/${entry.id}/`,root),release=JSON.parse(await readFile(new URL('character.json',base))),audit=JSON.parse(await readFile(new URL('validation.json',base)));
  const source=await readFile(new URL(`${entry.id}.blend`,base)),bytes=await readFile(new URL(`${entry.id}.glb`,base));
  const hash=data=>createHash('sha256').update(data).digest('hex');
  assert.equal(hash(source),release.source_sha256);assert.equal(hash(bytes),release.asset_sha256);
  assert.equal(audit.source_sha256,release.source_sha256);assert.ok(audit.success);assert.ok(audit.independent_motion_signatures>=120);
  const gltf=await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
  const model=gltf.scene,mixer=new AnimationMixer(model),bones=[],mouths=[];let antenna=false;
  model.traverse(n=>{if(n.isBone)bones.push(n);if(n.name.replaceAll('_',' ')==='Antenna bulb')antenna=true;if(n.morphTargetDictionary?.mouth_open!==undefined)mouths.push(n);});
  assert.ok(antenna&&bones.some(b=>b.name==='antenna'));assert.equal(mouths.length,4);
  assert.equal(gltf.animations.length,136);assert.deepEqual(gltf.animations.map(a=>a.name).sort(),Object.keys(release.actions).sort());
  const pose=()=>bones.filter(b=>b.name!=='antenna').flatMap(b=>[...b.position,...b.quaternion,...b.scale]);
  let samples=0,staticClips=[];const loops=[];
  for(const clip of gltf.animations){
    mixer.stopAllAction();const action=mixer.clipAction(clip);action.reset().play();
    let first,moved=false;
    for(const fraction of [0,.13,.37,.58,.83,.999]){
      action.time=clip.duration*fraction;mixer.update(0);model.updateMatrixWorld(true);
      const values=pose();assert.ok(values.every(Number.isFinite),`${clip.name}: nonfinite pose`);
      if(!first)first=values;else if(values.some((v,i)=>Math.abs(v-first[i])>1e-4))moved=true;
      samples++;
    }
    if(!moved)staticClips.push(clip.name);
    if(release.actions[clip.name].loop){
      action.time=0;mixer.update(0);model.updateMatrixWorld(true);const a=bones.flatMap(b=>[...b.matrixWorld.elements]);action.time=clip.duration-1e-5;mixer.update(0);model.updateMatrixWorld(true);const b=bones.flatMap(b=>[...b.matrixWorld.elements]);
      const gap=Math.max(...a.map((v,i)=>Math.abs(v-b[i])));loops.push({clip:clip.name,gap});assert.ok(gap<.015,`${clip.name}: loop gap ${gap}`);
    }
  }
  assert.deepEqual(staticClips,[],'Static clip found');
  mixer.stopAllAction();const idle=mixer.clipAction(gltf.animations.find(a=>a.name==='idle'));idle.play();idle.time=0;mixer.update(0);
  assert.ok(bones.filter(b=>b.name.startsWith('prop')).every(b=>b.scale.x<.002),'Idle props visible');
  report.characters.push({id:entry.id,actions:gltf.animations.length,distinctMotions:audit.independent_motion_signatures,poseSamples:samples,loopChecks:loops.length,antenna,mouthSurfaces:mouths.length,assetHash:hash(bytes)});
  model.traverse(n=>{n.geometry?.dispose();if(n.material){for(const m of Array.isArray(n.material)?n.material:[n.material])m.dispose();}});
  console.log(`PASS ${entry.id}: 136 clips, ${samples} runtime poses, ${loops.length} loops`);
 }catch(error){report.errors.push({id:entry.id,message:error.message});report.success=false;console.error(`FAIL ${entry.id}: ${error.message}`);}
}
await writeFile(new URL(requested.length?'characters/runtime-sample-validation.json':'characters/runtime-validation.json',root),JSON.stringify(report,null,2)+'\n');
if(!report.success)process.exitCode=1;
