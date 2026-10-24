import * as THREE from './vendor/three.module.js';
// Extend the real rig at runtime. Meshes, proportions and artist clips remain
// unchanged; the hand stays below the head throughout this chest-level reach.
export function handshakeClip(bones) {
 const times=[0,.3,.55,.8,1.05,1.3,1.55,1.8,2.1,2.5],tracks=[];
 for(const [name,reach,shake] of [['upper_armR',-.55,.035],['forearmR',-.72,.11],['handR',.12,.06]]) {
  const bone=bones[name] || bones[name.replace(/R$/,'.R')];if(!bone)continue;
  const rest=bone.quaternion.clone(),values=[];
  for(const t of times) {
   const envelope=Math.min(1,t/.45,(2.5-t)/.45);
   const pulse=t>.5 && t<2?Math.sin((t-.5)*Math.PI*5)*shake:0;
   const q=rest.clone().multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler((reach+pulse)*Math.max(0,envelope),0,0)));
   values.push(...q.toArray());
  }
  tracks.push(new THREE.QuaternionKeyframeTrack(bone.name+'.quaternion',times,values));
 }
 return new THREE.AnimationClip('handshake',2.5,tracks);
}
