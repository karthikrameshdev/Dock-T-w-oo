/** Release GPU allocations owned by a character document, once per resource. */
export function disposeScene(root) {
  const geometries=new Set(),materials=new Set(),textures=new Set(),skeletons=new Set(),images=new Set();
  root.traverse(node=>{
    if(node.geometry)geometries.add(node.geometry);
    if(node.skeleton)skeletons.add(node.skeleton);
    for(const material of (Array.isArray(node.material)?node.material:[node.material])) {
      if(!material)continue;
      materials.add(material);
      for(const value of Object.values(material))if(value?.isTexture)textures.add(value);
    }
  });
  for(const skeleton of skeletons)skeleton.dispose();
  for(const geometry of geometries)geometry.dispose();
  for(const material of materials)material.dispose();
  for(const texture of textures){
    if(texture.source?.data)images.add(texture.source.data);
    texture.dispose();
  }
  for(const image of images)if(typeof image.close==='function')image.close();
  root.clear();
}
