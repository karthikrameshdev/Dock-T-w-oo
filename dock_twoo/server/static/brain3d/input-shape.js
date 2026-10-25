import * as THREE from 'three';

// A separate opaque pass uses the current skinned/morphed pose. Decorative light
// and detached props never enlarge the native hit region or the body collision.
export class InputShape {
  constructor(renderer) {
    this.renderer=renderer;
    this.target=new THREE.WebGLRenderTarget(1,1,{depthBuffer:true});
    this.material=new THREE.MeshBasicMaterial({color:0xffffff});
    this.lastTime=-Infinity;this.lastBits='';this.samples=0;this.elapsed=0;
  }
  sample(scene,camera,model,width,height,time,fps=30) {
    if(time-this.lastTime<1/Math.max(2,Math.min(30,fps)))return null;
    this.lastTime=time;
    width=Math.round(width);height=Math.round(height);
    if(width<1 || height<1 || width>1024 || height>1024)return null;
    const started=performance.now(),hidden=[];
    scene.traverse(node=>{
      if(node.visible && (node.isSprite || node.userData.statusEffect ||
          /^(Brain_toy|Brain toy|Camera[ _]|Code[ _]|Magnifier[ _]|Reading[ _]tablet|Tablet[ _]text|Scan[ _]|Scanner[ _]|Jet[ _]flame)/i.test(node.name))) {
        hidden.push(node);node.visible=false;
      }
    });
    const renderer=this.renderer,previous=renderer.getRenderTarget(),override=scene.overrideMaterial;
    let pixels;
    try {
      this.target.setSize(width,height);
      scene.overrideMaterial=this.material;
      renderer.setRenderTarget(this.target);renderer.clear();renderer.render(scene,camera);
      if(this.pixels?.length!==width*height*4)this.pixels=new Uint8Array(width*height*4);
      pixels=this.pixels;
      renderer.readRenderTargetPixels(this.target,0,0,width,height,pixels);
    } finally {
      renderer.setRenderTarget(previous);scene.overrideMaterial=override;
      hidden.forEach(node=>node.visible=true);
    }
    const stride=Math.ceil(width/32)*4,bits=new Uint8Array(stride*height);
    for(let y=0;y<height;y++)for(let x=0;x<width;x++) {
      if(pixels[((height-1-y)*width+x)*4+3]>=128)bits[y*stride+(x>>3)]|=128>>(x&7);
    }
    let binary='';
    for(let i=0;i<bits.length;i+=16384)binary+=String.fromCharCode(...bits.subarray(i,i+16384));
    const encoded=btoa(binary);
    this.samples++;this.elapsed+=performance.now()-started;
    const key=`${width}:${height}:${encoded}`;
    if(key===this.lastBits)return null;
    this.lastBits=key;
    return {width,height,bits:encoded};
  }
}
