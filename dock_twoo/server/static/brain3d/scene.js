import * as THREE from 'three';
import { GLTFLoader } from './vendor/loaders/GLTFLoader.js';
import { FaceOverlay, SpeechOverlay } from './face.js';
import { RoomEnvironment } from './vendor/environments/RoomEnvironment.js';

const embedded = new URLSearchParams(location.search).has('embedded');
document.querySelector('#controls').hidden = embedded;
if (embedded) document.querySelector('#controls').style.display = 'none';
else document.body.classList.add('preview');
let bridge, model, mixer, current, clips = {}, bones = {}, mouth, mouthIndex, bulb, face, speech, flash, release;
const mouthMeshes=[];
let state = {action:'idle', yaw:0, progress:0, distance:0, blink:0, mouth:0, gazeX:0, gazeY:0, activity:'idle'};
const scene = new THREE.Scene();
const camera = new THREE.OrthographicCamera(-3.3,3.3,3.3,-3.3,.1,50);
camera.position.set(0,2.45,10); camera.lookAt(0,2.45,0);
const renderer = new THREE.WebGLRenderer({alpha:true, antialias:true, powerPreference:'low-power'});
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
window.setBrainState = payload => {state={...state,...payload};};
const select=document.querySelector('#action');
select.addEventListener('change',()=>{state.action=select.value;previewTime=0;});
document.querySelector('#yaw').addEventListener('input',event=>state.yaw=Number(event.target.value));
let previewTime=0;
const clock=new THREE.Timer();
async function loadCharacter(){
  const response=await fetch('./character.json',{cache:'no-store'});
  if(!response.ok)throw new Error('Character release metadata could not load');
  release=await response.json();
  document.querySelector('#characterTitle').textContent=`Brain ${release.version} · ${release.design}`;
  const assetResponse=await fetch(`./${release.asset}?v=${release.asset_sha256.slice(0,16)}`,{cache:'no-store'});
  if(!assetResponse.ok)throw new Error('The character model could not load');
  const bytes=await assetResponse.arrayBuffer();
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(value=>value.toString(16).padStart(2,'0')).join('');
  if(digest!==release.asset_sha256)throw new Error('The character export differs from its release. Export the saved Blender model again.');
  const gltf=await new GLTFLoader().parseAsync(bytes,new URL('./',location.href).href);
  model=gltf.scene; scene.add(model); mixer=new THREE.AnimationMixer(model);
  model.traverse(node=>{
    if(node.isBone)bones[node.name]=node;
    if(node.isMesh){node.frustumCulled=false;node.castShadow=false;node.receiveShadow=false;}
    if(node.morphTargetDictionary?.mouth_open!==undefined){mouthMeshes.push(node);mouth=node;mouthIndex=node.morphTargetDictionary.mouth_open;}
    if(node.name.replaceAll('_',' ')==='Camera flash'){node.material=node.material.clone();flash=node.material;}
    if(node.name==='Antenna_bulb' || node.name==='Antenna bulb'){bulb=node.material;}
  });
  face = new FaceOverlay(bones); speech = new SpeechOverlay(mouthMeshes);
  for(const clip of gltf.animations){
    for(const track of clip.tracks)track.name=track.name.replace('.morphTargetInfluences','.authoredMorphTargetInfluences');
    clips[clip.name]=mixer.clipAction(clip);select.add(new Option(clip.name,clip.name));
  }
  select.value='idle';window.brainDiagnostics={version:release.version,assetHash:release.asset_sha256,clips:Object.keys(clips),bones:Object.keys(bones),meshes:0,renderedFrames:0,nonFinite:false,translucent:false};
  model.traverse(node=>{if(node.isMesh)window.brainDiagnostics.meshes++;});
  report(`Brain ${release.version} · ${gltf.animations.length} animations ready`);

}
loadCharacter().catch(error=>report(error.message,true));

function frame(){
  requestAnimationFrame(frame);clock.update();const dt=Math.min(clock.getDelta(),.05);previewTime+=dt;
  if(!model)return;
  const activityClip={speaking:'talk',listening:'listen',thinking:'ponder',processing:'ponder',error:'sad'}[state.activity];
  const automatic=['idle','listen'].includes(state.action) && clips[activityClip];
  const name=automatic?activityClip:(clips[state.action]?state.action:'idle'), action=clips[name];
  if(current!==action){action.reset().play();if(current){action.crossFadeFrom(current,.16,false);}current=action;}
  face.beforeMixer();speech.beforeMixer();
  mixer.update(state.reducedMotion?0:dt);
  if(state.reducedMotion){action.time=0;mixer.update(0);}
  // Drive locomotion by distance travelled rather than the cursor's speed.
  if(embedded && name!=='idle' && !automatic && !state.reducedMotion){
    const duration=action.getClip().duration;
    const locomotion=['walk','walk_window','run','chase_ball','explore','climb','climb_dock'].includes(name);
    const stride=['run','chase_ball'].includes(name)?90:(['climb','climb_dock'].includes(name)?44:68);
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

  if(bulb){const color={listening:0x21e8db,thinking:0xab8cea,processing:0xf4c36b,error:0xf77778,offline:0x8794a0}[state.activity]||0x71f6ff;bulb.color.setHex(color);bulb.emissive?.setHex(color);}
  window.brainDiagnostics.renderedFrames++;
  window.brainDiagnostics.eyeScales = face.scales();
  window.brainDiagnostics.action = name;
  window.brainDiagnostics.mouth = mouth?.morphTargetInfluences[mouthIndex] || 0;
  window.brainDiagnostics.actionTime = action.time;
  window.brainDiagnostics.speechMeshes=mouthMeshes.length;
  window.brainDiagnostics.triangles=renderer.info.render.triangles;
  window.brainDiagnostics.drawCalls=renderer.info.render.calls;
  window.brainDiagnostics.propScales=Object.fromEntries(['propmagnifier','propcamera','proptablet','propscan','jetL','jetR'].map(key=>[key,bones[key]?.scale.x ?? 0]));
  window.brainDiagnostics.poseSignature=Object.values(bones).flatMap(bone=>[...bone.position.toArray(),...bone.quaternion.toArray(),...bone.scale.toArray()]);
  window.brainDiagnostics.handPositions = ['handL','handR'].map(name=>bones[name]?.getWorldPosition(new THREE.Vector3()).toArray());
  model.traverse(node=>{if(node.isMesh){if(node.material.opacity<1 || node.material.transparent)window.brainDiagnostics.translucent=true;}if(node.isBone && ![...node.position.toArray(),...node.quaternion.toArray(),...node.scale.toArray()].every(Number.isFinite))window.brainDiagnostics.nonFinite=true;});
  renderer.render(scene,camera);
}
frame();
window.addEventListener('error',event=>{if(bridge)bridge.failed(event.message);});
