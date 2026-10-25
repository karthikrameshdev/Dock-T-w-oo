/** Keep only the current clip and its short transition in the live mixer.
 * A faded AnimationAction is disabled, but Three.js does not remove it from the
 * active mixer. Repeated roaming used to retain every visited action forever.
 */
export class ActionPlayer {
  constructor(mixer, clips, fadeSeconds=.16) {
    this.mixer=mixer; this.clips=new Map(clips.map(clip=>[clip.name,clip]));
    this.fadeSeconds=fadeSeconds; this.current=null; this.previous=null; this.until=0;
  }
  retire(action) {
    action.stop();
    this.mixer.uncacheAction(action.getClip());
  }
  select(name) {
    const clip=this.clips.get(name) || this.clips.get('idle');
    if(this.current?.getClip()===clip)return this.current;
    if(this.previous){this.retire(this.previous);this.previous=null;}
    const next=this.mixer.clipAction(clip).reset().play();
    if(this.current){
      // An interrupted transition starts from a full-weight outgoing pose.
      this.current.stopFading().setEffectiveWeight(1);
      next.crossFadeFrom(this.current,this.fadeSeconds,false);
      this.previous=this.current;this.until=this.mixer.time+this.fadeSeconds;
    }
    this.current=next;
    return next;
  }
  update(dt) {
    this.mixer.update(dt);
    if(this.previous && this.mixer.time>=this.until){this.retire(this.previous);this.previous=null;}
  }
  dispose(){this.mixer.stopAllAction();this.mixer.uncacheRoot(this.mixer.getRoot());this.current=this.previous=null;}
}
