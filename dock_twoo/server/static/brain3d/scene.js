import * as THREE from 'three';
import { GLTFLoader } from './vendor/loaders/GLTFLoader.js';
import { FaceOverlay } from './face.js';
import { RoomEnvironment } from './vendor/environments/RoomEnvironment.js';

const embedded = new URLSearchParams(location.search).has('embedded');
document.querySelector('#controls').hidden = embedded;
if (embedded) document.querySelector('#controls').style.display = 'none';
else document.body.classList.add('preview');
let bridge, model, mixer, current, clips = {}, bones = {}, mouth, mouthIndex, bulb, face;
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
function report(message,error=false){document.querySelector('#status').textContent=message;document.body.dataset.ready=error?'error':'true'; if(bridge) error?bridge.failed(message):bridge.ready();}
if(window.qt && window.QWebChannel) new QWebChannel(qt.webChannelTransport, channel=>{bridge=channel.objects.brain;if(model)bridge.ready();});
window.setBrainState = payload => {state={...state,...payload};};
const select=document.querySelector('#action');
select.addEventListener('change',()=>{state.action=select.value;previewTime=0;});
document.querySelector('#yaw').addEventListener('input',event=>state.yaw=Number(event.target.value));
let previewTime=0;
const clock=new THREE.Timer();
new GLTFLoader().load('./brain.glb',gltf=>{
  model=gltf.scene; scene.add(model); mixer=new THREE.AnimationMixer(model);
  model.traverse(node=>{
    if(node.isBone)bones[node.name]=node;
    if(node.isMesh){node.frustumCulled=false;node.castShadow=false;node.receiveShadow=false;}
    if(node.morphTargetDictionary?.mouth_open!==undefined){mouth=node;mouthIndex=node.morphTargetDictionary.mouth_open;}
    if(node.name==='Antenna_bulb' || node.name==='Antenna bulb'){bulb=node.material;}
  });
  for(const clip of gltf.animations){clips[clip.name]=mixer.clipAction(clip);select.add(new Option(clip.name,clip.name));}
  face = new FaceOverlay(bones);
  select.value='idle';window.brainDiagnostics={clips:Object.keys(clips),bones:Object.keys(bones),meshes:0,renderedFrames:0,nonFinite:false,translucent:false};
  model.traverse(node=>{if(node.isMesh)window.brainDiagnostics.meshes++;});
  report('Ready · '+gltf.animations.length+' animations');
},undefined,error=>{console.error(error);report('Character could not load: '+error.message,true);});

function frame(){
  requestAnimationFrame(frame);clock.update();const dt=Math.min(clock.getDelta(),.05);previewTime+=dt;
  if(!model)return;
  const name=clips[state.action]?state.action:'idle', action=clips[name];
  if(current!==action){action.reset().play();if(current){action.crossFadeFrom(current,.16,false);}current=action;}
  face.beforeMixer();
  mixer.update(state.reducedMotion?0:dt);
  if(state.reducedMotion){action.time=0;mixer.update(0);}
  // Drive locomotion by distance travelled rather than the cursor's speed.
  if(embedded && name!=='idle'){
    const duration=action.getClip().duration;
    const locomotion=['walk','walk_window','run','chase_ball','explore','climb','climb_dock'].includes(name);
    action.time=locomotion?((state.distance/(['climb','climb_dock'].includes(name)?44:68))%1)*duration:Math.min(.999,state.progress)*duration;
    mixer.update(0);
  }
  model.rotation.y=state.yaw*Math.PI/2;
  const previewBlink = embedded ? state.blink : Math.max(0, 1-Math.abs((previewTime%4.2)-3.8)/.085);
  const previewGaze = embedded ? state.gazeX : Math.sin(previewTime*.7)*.25;
  face.afterMixer({...state, blink:previewBlink, gazeX:previewGaze});
  if(mouth)mouth.morphTargetInfluences[mouthIndex]=Math.min(1,Math.max(0,(!embedded && document.querySelector('#speech').checked)?(.25+.65*Math.abs(Math.sin(previewTime*7))):state.mouth));
  if(bulb){const color={listening:0x21e8db,thinking:0xab8cea,processing:0xf4c36b,error:0xf77778,offline:0x8794a0}[state.activity]||0x08dca6;bulb.color.setHex(color);bulb.emissive?.setHex(color);}
  window.brainDiagnostics.renderedFrames++;
  window.brainDiagnostics.eyeScales = face.scales();
  window.brainDiagnostics.action = name;
  window.brainDiagnostics.mouth = mouth?.morphTargetInfluences[mouthIndex] || 0;
  window.brainDiagnostics.actionTime = action.time;
  window.brainDiagnostics.handPositions = ['handL','handR'].map(name=>bones[name]?.getWorldPosition(new THREE.Vector3()).toArray());
  model.traverse(node=>{if(node.isMesh){if(node.material.opacity<1 || node.material.transparent)window.brainDiagnostics.translucent=true;}if(node.isBone && !node.position.toArray().every(Number.isFinite))window.brainDiagnostics.nonFinite=true;});
  renderer.render(scene,camera);
}
frame();
window.addEventListener('error',event=>{if(bridge)bridge.failed(event.message);});
