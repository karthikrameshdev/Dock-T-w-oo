import assert from 'node:assert/strict';
import * as THREE from '../dock_twoo/server/static/brain3d/vendor/three.module.js';
import {HeadIndicator,indicatorState} from '../dock_twoo/server/static/brain3d/indicator.js';
for(const [activity,online,name,color] of [['idle',true,'online',0x22c55e],['idle',false,'offline',0xef4444],['listening',true,'listening',0xfacc15],['thinking',true,'thinking',0xa855f7],['processing',true,'thinking',0xa855f7]]) {
  assert.deepEqual([indicatorState({activity,online}).name,indicatorState({activity,online}).color],[name,color]);
}
globalThis.document={createElement:()=>({getContext:()=>({createRadialGradient:()=>({addColorStop(){}}),fillRect(){}})})};
const model=new THREE.Group(),antenna=new THREE.Bone();model.add(antenna);
const original=new THREE.MeshStandardMaterial({color:0x71f6ff,emissive:0x71f6ff});
const bulb=new THREE.Mesh(new THREE.SphereGeometry(.145),original);bulb.position.set(.92,5.12,0);model.add(bulb);
const indicator=new HeadIndicator(model,bulb,antenna);
indicator.update({activity:'listening',online:true},0);
const scale=indicator.rings[0].scale.x;
indicator.update({activity:'listening',online:true},.4);
assert.notEqual(indicator.rings[0].scale.x,scale);
assert.equal(bulb.material.color.getHex(),0xfacc15);
assert.equal(original.color.getHex(),0x71f6ff,'Status must not recolor the shared chest/scanner material');
indicator.update({activity:'thinking',online:true},.8);
assert.ok(indicator.rings[0].rotation.x>0);
indicator.update({activity:'thinking',online:true,reducedMotion:true},1);
assert.ok(indicator.rings.every(ring=>!ring.visible));
console.log('PASS: green/red/yellow/purple states, animated waves/orbits, reduced motion, isolated antenna material.');
