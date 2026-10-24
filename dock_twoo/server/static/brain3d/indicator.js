import * as THREE from './vendor/three.module.js';

export function indicatorState({online=null,activity='idle'}) {
  if(activity==='error' || activity==='offline' || online===false)return {name:'offline',color:0xef4444,effect:'pulse'};
  if(activity==='listening')return {name:'listening',color:0xfacc15,effect:'waves'};
  if(activity==='thinking' || activity==='processing')return {name:'thinking',color:0xa855f7,effect:'spin'};
  if(online===null)return {name:'unknown',color:0x94a3b8,effect:'steady'};
  return {name:'online',color:0x22c55e,effect:'glow'};
}

export class HeadIndicator {
  constructor(model, bulb, antenna) {
    this.bulb=bulb;
    // The artist shares this material with the chest and scanner. Status color
    // belongs only to the antenna, so keep those surfaces unchanged.
    bulb.material=bulb.material.clone();
    model.updateMatrixWorld(true);
    bulb.geometry.computeBoundingBox();
    const world=bulb.geometry.boundingBox.getCenter(new THREE.Vector3()).applyMatrix4(bulb.matrixWorld);
    this.anchor=new THREE.Group();
    (antenna||model).add(this.anchor);
    this.anchor.position.copy((antenna||model).worldToLocal(world));
    const canvas=document.createElement('canvas');canvas.width=canvas.height=64;
    const context=canvas.getContext('2d');
    const glow=context.createRadialGradient(32,32,0,32,32,32);
    glow.addColorStop(0,'rgba(255,255,255,.9)');glow.addColorStop(.35,'rgba(255,255,255,.25)');glow.addColorStop(1,'rgba(255,255,255,0)');
    context.fillStyle=glow;context.fillRect(0,0,64,64);
    this.halo=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(canvas),transparent:true,depthWrite:false,blending:THREE.AdditiveBlending}));
    this.halo.userData.statusEffect=true;this.anchor.add(this.halo);
    this.rings=Array.from({length:3},()=>{
      const ring=new THREE.Mesh(new THREE.TorusGeometry(.21,.008,6,48),new THREE.MeshBasicMaterial({transparent:true,opacity:.6,depthWrite:false}));
      ring.userData.statusEffect=true;this.anchor.add(ring);return ring;
    });
  }
  update(state,time) {
    const status=indicatorState(state), reduced=state.reducedMotion;
    const pulse=reduced?1:(.75+.25*Math.sin(time*2.5));
    this.bulb.material.color.setHex(status.color);this.bulb.material.emissive.setHex(status.color);
    this.bulb.material.emissiveIntensity=status.name==='offline'?(reduced?1:1+.8*Math.sin(time*4)**2):1.2+.4*pulse;
    this.halo.material.color.setHex(status.color);this.halo.material.opacity=.3*pulse;
    this.halo.scale.setScalar(.7+.08*pulse);
    this.rings.forEach((ring,index)=>{
      ring.material.color.setHex(status.color);
      ring.visible=!reduced && ['waves','spin'].includes(status.effect);
      if(status.effect==='waves') {
        const phase=(time*.8+index/3)%1;
        ring.scale.setScalar(1+phase*1.4);ring.material.opacity=(1-phase)*.65;ring.rotation.set(0,0,0);
      } else {
        ring.scale.setScalar(1+index*.2);ring.material.opacity=.5;
        ring.rotation.set(time*(1+index*.3),index*Math.PI/3+time*.8,0);
      }
    });
    return status;
  }
}
