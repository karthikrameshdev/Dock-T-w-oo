/** Verify actual bill-tip geometry during authored and live speech, not only weights. */
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {register} from 'node:module';
import {AnimationMixer,Vector3} from '../dock_twoo/server/static/brain3d/vendor/three.module.js';
import {SpeechOverlay} from '../dock_twoo/server/static/brain3d/face.js';
register('./brain_three_loader.mjs',import.meta.url);
const {GLTFLoader}=await import('../dock_twoo/server/static/brain3d/vendor/loaders/GLTFLoader.js');
const root=new URL('../',import.meta.url),report={success:true,birds:[],errors:[]};
for(const id of ['owl','parrot','robin']){
 try{
  const bytes=await readFile(new URL(`characters/${id}/${id}.glb`,root));
  const gltf=await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
  const model=gltf.scene,meshes=[];let upper,lower;
  model.traverse(n=>{if(n.morphTargetDictionary?.mouth_open!==undefined)meshes.push(n);if(n.userData.beak_part==='upper')upper=n;if(n.userData.beak_part==='lower')lower=n;});
  assert.ok(upper&&lower,'Bill halves must be separate hinged surfaces');assert.equal(meshes.length,4);
  const speech=new SpeechOverlay(meshes);
  for(const clip of gltf.animations)for(const track of clip.tracks)track.name=track.name.replace('.morphTargetInfluences','.authoredMorphTargetInfluences');
  const mixer=new AnimationMixer(model);
  function pose(name,phase){mixer.stopAllAction();const clip=gltf.animations.find(a=>a.name===name),action=mixer.clipAction(clip);action.reset().play();action.time=clip.duration*phase;mixer.update(0);model.updateMatrixWorld(true);speech.update({mouth:0,preserveAuthored:true},1/30);}
  function tip(mesh){return mesh.getVertexPosition(mesh.userData.beak_tip_vertex,new Vector3()).applyMatrix4(mesh.matrixWorld);}
  const gap=()=>tip(upper).distanceTo(tip(lower));
  pose('idle',0);const rest=gap(),closedUpper=tip(upper),closedLower=tip(lower);
  pose('talk',.45);const authored=gap();assert.ok(authored>rest+.06,`Authored speech did not open bill: ${authored}`);
  pose('idle',0);
  for(let i=0;i<30;i++)speech.update({mouth:.9,speaking:true,preserveAuthored:true},1/30);
  const live=gap(),openUpper=tip(upper),openLower=tip(lower);
  assert.ok(live>rest+.08,'Live audio did not open physical bill');
  assert.ok(openUpper.y>closedUpper.y+.01,'Upper bill did not lift');
  assert.ok(openLower.y<closedLower.y-.06,'Lower bill did not hinge down');
  for(let i=0;i<40;i++)speech.update({mouth:0,speaking:false,preserveAuthored:true},1/30);
  const recovered=gap();assert.ok(Math.abs(recovered-rest)<.002,'Beak failed to close after speech');
  pose('wave',.4);const waving=gap();
  for(let i=0;i<30;i++)speech.update({mouth:.8,speaking:true,preserveAuthored:true},1/30);
  assert.ok(gap()>waving+.06,'Live speech must articulate the bill over other body actions');
  report.birds.push({id,assetHash:createHash('sha256').update(bytes).digest('hex'),closedGap:rest,authoredTalkGap:authored,liveSpeechGap:live,recoveredGap:recovered,upperLift:openUpper.y-closedUpper.y,lowerDrop:closedLower.y-openLower.y});
  console.log(`PASS ${id}: hinged beak opens in talk and live speech, then closes`);
 }catch(error){report.success=false;report.errors.push({id,message:error.message});console.error(`FAIL ${id}: ${error.message}`);}
}
await writeFile(new URL('characters/beak-validation.json',root),JSON.stringify(report,null,2)+'\n');if(!report.success)process.exitCode=1;
