/** Resolve the renderer's browser import-map entry in Node regression checks. */
export function resolve(specifier,context,nextResolve){
 if(specifier==='three')return nextResolve(new URL('../dock_twoo/server/static/brain3d/vendor/three.module.js',import.meta.url).href,context);
 return nextResolve(specifier,context);
}
