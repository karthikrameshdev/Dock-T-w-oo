import * as THREE from 'three';
import { GLTFLoader } from './vendor/loaders/GLTFLoader.js';
import { HeadIndicator } from './indicator.js';
import { FaceOverlay, SpeechOverlay } from './face.js';
import { RoomEnvironment } from './vendor/environments/RoomEnvironment.js';
import { InputShape } from './input-shape.js';
import { ActionPlayer } from './action-player.js';

const params = new URLSearchParams(location.search);
const embedded = params.has('embedded');
const characterId = params.get('character') || 'default';
document.querySelector('#controls').hidden = embedded;
if (embedded) document.querySelector('#controls').style.display = 'none';
else document.body.classList.add('preview');
let bridge, model, mixer, player, current, clips = {}, bones = {}, mouth, mouthIndex, bulb, face, speech, flash, release, indicator;
const mouthMeshes=[];
let state = {online:embedded?null:true, listeningAuraAllowed:false, action:'idle', yaw:0, progress:0, distance:0, blink:0, mouth:0, gazeX:0, gazeY:0, activity:'idle'};
const scene = new THREE.Scene();
const camera = new THREE.OrthographicCamera(-3.3,3.3,3.3,-3.3,.1,50);
camera.position.set(0,2.45,10); camera.lookAt(0,2.45,0);
const renderer = new THREE.WebGLRenderer({alpha:true, antialias:true, powerPreference:'low-power'});
const inputShape = new InputShape(renderer);
renderer.setPixelRatio(Math.min(devicePixelRatio,2)); renderer.setClearColor(0,0);
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = .9;
document.body.prepend(renderer.domElement);
const pmrem = new THREE.PMREMGenerator(renderer);
const environment = new RoomEnvironment();
const environmentMap = pmrem.fromScene(environment,.04);
scene.environment = environmentMap.texture; scene.environmentIntensity = .45; environment.dispose(); pmrem.dispose();
scene.add(new THREE.HemisphereLight(0xeaffff,0x625b78,.6));
const key = new THREE.DirectionalLight(0xffffff,1.25); key.position.set(3,6,5); scene.add(key);
const fill = new THREE.DirectionalLight(0xcad4ff,.5); fill.position.set(-4,3,1); scene.add(fill);
function resize(){const aspect=innerWidth/innerHeight;camera.left=-3.3*aspect;camera.right=3.3*aspect;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);}
addEventListener('resize',resize); resize();
function report(message,error=false){document.querySelector('#status').textContent=message;document.body.dataset.ready=error?'error':'true'; if(bridge) error?bridge.failed(message):bridge.ready(release.version,release.asset_sha256);}
if(window.qt && window.QWebChannel) new QWebChannel(qt.webChannelTransport, channel=>{bridge=channel.objects.brain;if(model)bridge.ready(release.version,release.asset_sha256);});
window.setBrainState = payload => {
  state={...state,...payload};
  const ratio=Math.min(devicePixelRatio,state.pixelRatio||2);
  if(renderer.getPixelRatio()!==ratio){renderer.setPixelRatio(ratio);resize();}
};
const select=document.querySelector('#action');
select.addEventListener('change',()=>{state.action=select.value;previewTime=0;});
document.querySelector('#yaw').addEventListener('input',event=>state.yaw=Number(event.target.value));
document.querySelector('#indicatorPreview').addEventListener('change',event=>{
  const mode=event.target.value;state.online=mode!=='offline';state.activity=mode==='online'?'idle':mode;
});
let previewTime=0,lastRender=-Infinity,lastDiagnostics=-Infinity;
const clock=new THREE.Timer();
async function loadCharacter(){
  const catalogResponse=await fetch('./catalog.json',{cache:'no-store'});
  if(!catalogResponse.ok)throw new Error('Character catalog could not load');
  const catalog=await catalogResponse.json();
  const entry=catalog.characters.find(item=>item.id===characterId);
  if(!entry)throw new Error('Unknown character. Choose a companion from the library.');
  const characterSelect=document.querySelector('#character');
  for(const item of catalog.characters)characterSelect.add(new Option(`${item.name} · ${item.species.replaceAll('_',' ')}`,item.id));
  characterSelect.value=characterId;
  characterSelect.addEventListener('change',()=>{
    const url=new URL(location.href);url.searchParams.set('character',characterSelect.value);location.assign(url);
  });
  const manifestUrl=new URL(characterId==='default'?'./character.json':`./characters/${characterId}/character.json`,location.href);
  const response=await fetch(manifestUrl,{cache:'no-store'});
  if(!response.ok)throw new Error('Character release metadata could not load');
  release=await response.json();
  document.querySelector('#characterTitle').textContent=`${release.name} · ${release.design}`;
  document.title=`${release.name} · Voice Assistant`;
  const assetUrl=new URL(release.asset,manifestUrl);assetUrl.searchParams.set('v',release.asset_sha256.slice(0,16));
  const assetResponse=await fetch(assetUrl,{cache:'no-store'});
  if(!assetResponse.ok)throw new Error('The character model could not load');
  const bytes=await assetResponse.arrayBuffer();
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(value=>value.toString(16).padStart(2,'0')).join('');
  if(digest!==release.asset_sha256)throw new Error('The character export differs from its release. Export the saved Blender model again.');
  const gltf=await new GLTFLoader().parseAsync(bytes,new URL('./',location.href).href);
  model=gltf.scene; scene.add(model); mixer=new THREE.AnimationMixer(model);
  // Desktop companions share a world scale, so the rat and mouse stay small.
  // The standalone inspector fits the selected model for comfortable editing.
  if(!embedded && release.family!=='robot' && release.family!=='human'){
    model.updateMatrixWorld(true);
    const bounds=new THREE.Box3().setFromObject(model),height=bounds.max.y-bounds.min.y;
    const center=(bounds.max.y+bounds.min.y)/2;
    camera.position.set(0,center,10);camera.lookAt(0,center,0);
    camera.zoom=Math.min(3,5.2/Math.max(1,height));camera.updateProjectionMatrix();
  }
  model.traverse(node=>{
    if(node.isBone)bones[node.name]=node;
    if(node.isMesh){node.frustumCulled=false;node.castShadow=false;node.receiveShadow=false;}
    if(node.morphTargetDictionary?.mouth_open!==undefined){mouthMeshes.push(node);mouth=node;mouthIndex=node.morphTargetDictionary.mouth_open;}
    if(node.name.replaceAll('_',' ')==='Camera flash'){node.material=node.material.clone();flash=node.material;}
    if(node.name==='Antenna_bulb' || node.name==='Antenna bulb'){bulb=node;}
  });
  if(bulb)indicator=new HeadIndicator(model,bulb,bones.antenna);
  face = new FaceOverlay(bones); speech = new SpeechOverlay(mouthMeshes);
  for(const clip of gltf.animations){
    for(const track of clip.tracks)track.name=track.name.replace('.morphTargetInfluences','.authoredMorphTargetInfluences');
    clips[clip.name]=clip;select.add(new Option(clip.name,clip.name));
  }
  player=new ActionPlayer(mixer,gltf.animations);
  const requestedAction=params.get('action');
  state.action=gltf.animations.some(clip=>clip.name===requestedAction)?requestedAction:'idle';
  select.value=state.action;window.brainDiagnostics={characterId,version:release.version,assetHash:release.asset_sha256,clips:Object.keys(clips),bones:Object.keys(bones),meshes:0,renderedFrames:0,nonFinite:false,translucent:false};
  model.traverse(node=>{if(node.isMesh)window.brainDiagnostics.meshes++;});
  report(`${gltf.animations.length} animations · ${release.version}`);

}
loadCharacter().catch(error=>report(error.message,true));

function frame(){
  requestAnimationFrame(frame);
  if(state.visible===false)return;
  const now=performance.now();if(now-lastRender<1000/(state.maxFps||60))return;lastRender=now;
  clock.update();const dt=Math.min(clock.getDelta(),.05);previewTime+=dt;
  if(!model)return;
  const activityClip={speaking:'talk',listening:'listen',thinking:'ponder',processing:'ponder',error:'sad'}[state.activity];
  const automatic=['idle','listen'].includes(state.action) && clips[activityClip];
  const name=automatic?activityClip:(clips[state.action]?state.action:'idle'), action=player.select(name);
  current=action;
  face.beforeMixer();speech.beforeMixer();
  player.update(state.reducedMotion?0:dt);
  if(state.reducedMotion){action.time=0;mixer.update(0);}
  // Drive locomotion by distance travelled rather than the cursor's speed.
  if(embedded && name!=='idle' && !automatic && !state.reducedMotion){
    const duration=action.getClip().duration;
    const locomotion=['walk','walk_window','run','dash','chase_ball','explore','climb','climb_dock'].includes(name);
    const stride=['run','dash','chase_ball'].includes(name)?90:(['climb','climb_dock'].includes(name)?44:68);
    action.time=locomotion?((state.distance/stride)%1)*duration:Math.min(.999,state.progress)*duration;
    mixer.update(0);
  }
  model.rotation.y=state.yaw*Math.PI/2;
  const previewBlink = embedded ? state.blink : Math.max(0, 1-Math.abs((previewTime%4.2)-3.8)/.085);
  const previewGaze = embedded ? state.gazeX : Math.sin(previewTime*.7)*.25;
  face.afterMixer({...state, blink:previewBlink, gazeX:previewGaze});
  const previewSpeech=!embedded && (document.querySelector('#speech').checked || name==='talk');
  const speechLevel=previewSpeech ? Math.max(0,Math.sin(previewTime*8)+.25*Math.sin(previewTime*19))*.8 : state.mouth;
  speech.update({preserveAuthored:true,mouth:speechLevel, speaking:previewSpeech || state.activity==='speaking', reducedMotion:state.reducedMotion},dt);
  const progress=action.time/action.getClip().duration;
  if(flash)flash.emissiveIntensity=name==='camera' ? 1+14*Math.exp(-(((progress-.58)/.025)**2)) : 1;

  window.brainDiagnostics.indicator=indicator?.update(state,previewTime);
  window.brainDiagnostics.listeningAura=false;
  window.brainDiagnostics.renderedFrames++;
  window.brainDiagnostics.activeActions=mixer.stats.actions.inUse;
  window.brainDiagnostics.cachedActions=mixer.stats.actions.total;
  window.brainDiagnostics.eyeScales = face.scales();
  window.brainDiagnostics.action = name;
  window.brainDiagnostics.mouth = mouth?.morphTargetInfluences[mouthIndex] || 0;
  window.brainDiagnostics.actionTime = action.time;
  window.brainDiagnostics.speechMeshes=mouthMeshes.length;
  window.brainDiagnostics.triangles=renderer.info.render.triangles;
  window.brainDiagnostics.drawCalls=renderer.info.render.calls;
  window.brainDiagnostics.propScales=Object.fromEntries(['propmagnifier','propcamera','proptablet','propscan','jetL','jetR','propball','prophammer','propanvil','proptether','propballoon','propparachute'].map(key=>[key,bones[key]?.scale.x ?? 0]));
  // Full pose snapshots are useful in the inspector, not on every frame of
  // thirty resident characters. Avoid thousands of temporary arrays per tick.
  if(!embedded || now-lastDiagnostics>=1000){
  lastDiagnostics=now;
  window.brainDiagnostics.poseSignature=Object.values(bones).flatMap(bone=>[...bone.position.toArray(),...bone.quaternion.toArray(),...bone.scale.toArray()]);
  window.brainDiagnostics.handPositions = ['handL','handR'].map(name=>bones[name]?.getWorldPosition(new THREE.Vector3()).toArray());
  window.brainDiagnostics.armPoseSignature = Object.values(bones).filter(bone=>/^(upper_arm|forearm|hand|digit|thumb)/.test(bone.name)).flatMap(bone=>[...bone.position.toArray(),...bone.quaternion.toArray(),...bone.scale.toArray()]);
  model.traverse(node=>{if(node.isMesh && !node.userData.statusEffect){if(node.material.opacity<1 || node.material.transparent)window.brainDiagnostics.translucent=true;}if(node.isBone && ![...node.position.toArray(),...node.quaternion.toArray(),...node.scale.toArray()].every(Number.isFinite))window.brainDiagnostics.nonFinite=true;});
  }
  renderer.render(scene,camera);
  if(bridge?.silhouette) {
    const shape=inputShape.sample(scene,camera,model,innerWidth,innerHeight,previewTime,state.shapeFps||30);
    if(shape)bridge.silhouette(JSON.stringify({...shape,characterId}));
    window.brainDiagnostics.inputShapeSamples=inputShape.samples;
    window.brainDiagnostics.inputShapeMilliseconds=inputShape.elapsed/Math.max(1,inputShape.samples);
  }
}
frame();
window.addEventListener('error',event=>{if(bridge)bridge.failed(event.message);});
