"""Semantic, separately baked animation programs for the character library.

No alias Actions are emitted. Biped, quadruped and avian performances use their
own gaits and appendages. A normalized pose digest audits within-character reuse.
"""
import math
from mathutils import Vector, Quaternion, Euler

# Preserve the default's 56 existing actions and append these 80 performances.
# Each tuple describes a different acting pose: head xyz, torso xyz, left arm
# xyz, right arm xyz, forearm flex, rhythm, root lift. Values are radians.
GESTURES = {
'bow':((.38,0,0),(.25,0,0),(0,0,.05),(0,0,-.05),-.12,1,-.08),
'salute':((0,-.06,0),(0,0,.04),(-1.5,-.65,0),(-.08,0,0),-.65,1,0),
'clap':((-.04,0,0),(0,0,0),(-.8,.4,0),(-.8,-.4,0),-.65,4,0),
'high_five':((-.08,-.10,0),(0,-.04,0),(-.6,-1.2,0),(-.15,0,0),-.3,2,0),
'beckon':((.05,0,.08),(0,0,.05),(-.9,-.2,0),(-.1,0,0),-.55,3,0),
'shrug':((-.06,.1,0),(0,0,0),(-.3,-.75,0),(-.3,.75,0),-.85,2,.035),
'facepalm':((.14,0,.1),(.08,0,0),(-1.25,-.18,0),(-.15,0,0),-1.1,1,0),
'apologize':((.20,0,0),(.12,0,0),(-.5,.25,0),(-.5,-.25,0),-.7,2,-.02),
'give_thanks':((.14,.02,0),(.06,0,0),(-.85,.15,0),(-.85,-.15,0),-.60,2,0),
'heart_gesture':((-.04,-.09,0),(0,0,0),(-.7,.4,0),(-.7,-.4,0),-1.05,1,.015),
'offer_hug':((-.06,0,0),(-.03,0,0),(-.5,-.8,0),(-.5,.8,0),-.25,1,0),
'thumbs_up':((0,-.08,.03),(0,0,-.05),(-.55,-.35,0),(-.1,0,0),-.9,2,0),
'thumbs_down':((.12,.05,0),(.03,0,0),(-.6,-.2,0),(-.15,0,0),-.78,1,-.01),
'point_up':((-.24,0,-.08),(0,0,0),(-.4,-1.1,0),(-.1,0,0),-.4,1,0),
'point_down':((.25,0,.06),(.12,0,0),(-.25,-.15,0),(-.12,0,0),.14,1,-.04),
'present_left':((-.02,0,.23),(0,0,.14),(-.6,-.6,0),(-.15,0,0),-.5,1,0),
'present_right':((-.02,0,-.23),(0,0,-.14),(-.15,0,0),(-.6,.6,0),-.5,1,0),
'knock':((.02,0,-.08),(0,0,-.05),(-.15,0,0),(-1.1,.08,0),-.35,3,0),
'open_door':((.04,0,.13),(0,0,.20),(-.8,-.2,.12),(-.2,0,0),-.6,1,-.02),
'carry_box':((.10,0,0),(-.06,0,0),(-.7,-.2,0),(-.7,.2,0),-.85,2,-.04),
'lift_object':((-.12,0,0),(-.12,0,0),(-1.15,-.3,0),(-1.15,.3,0),-.55,1,.09),
'set_object_down':((.22,0,0),(.22,0,0),(-.8,-.1,0),(-.8,.1,0),-.25,1,-.12),
'give_gift':((-.04,-.05,0),(-.06,0,0),(-.95,-.1,0),(-.95,.1,0),-.32,1,.02),
'catch':((-.16,0,.04),(-.10,0,0),(-1.05,-.4,0),(-1.05,.4,0),-.6,2,-.06),
'throw':((-.04,0,-.16),(0,0,-.25),(-.3,0,0),(-1.2,.6,.25),-.5,1,.035),
'juggle':((-.18,0,0),(0,0,.04),(-.85,-.25,0),(-.55,.25,0),-.7,5,.025),
'sweep':((.14,0,.12),(.12,0,.2),(-.65,-.1,.15),(-.65,.1,-.15),-.45,3,-.03),
'polish':((.1,0,.08),(.06,0,.1),(-.8,-.2,0),(-.25,0,0),-.65,5,-.02),
'write':((.22,0,.05),(.08,0,0),(-.75,-.1,0),(-.45,.1,0),-.8,6,0),
'draw':((.18,0,-.06),(.04,0,-.04),(-.55,-.2,0),(-.8,.2,0),-.65,4,0),
'paint':((.08,-.06,.1),(0,0,.1),(-.9,-.45,0),(-.35,.25,0),-.45,3,0),
'stir':((.18,0,0),(.06,0,0),(-.65,-.3,0),(-.65,.3,0),-.9,4,0),
'cook':((.12,.04,.08),(.05,0,.08),(-.85,-.25,0),(-.4,.35,0),-.6,3,.01),
'water_plant':((.22,0,-.12),(.1,0,-.08),(-.35,-.2,0),(-.9,.4,0),-.7,1,-.02),
'smell':((.10,0,0),(-.025,0,0),(-.95,-.15,0),(-.15,0,0),-.8,3,.015),
'taste':((.08,-.08,0),(0,0,0),(-1.05,-.1,0),(-.2,0,0),-.95,2,0),
'laugh':((-.18,0,0),(-.10,0,0),(-.2,-.3,0),(-.2,.3,0),-.65,5,.035),
'cry':((.23,0,0),(.10,0,0),(-1.2,-.2,0),(-1.2,.2,0),-.8,3,-.025),
'sneeze':((.28,0,.04),(.18,0,0),(-1,-.15,0),(-.2,0,0),-.9,1,-.06),
'shiver':((.12,0,0),(.05,0,0),(-.45,.15,0),(-.45,-.15,0),-1.1,9,0),
'yawn':((-.23,0,0),(-.08,0,0),(-1.1,-.2,0),(-.3,.25,0),-.9,1,.02),
'wake_up':((-.15,0,.12),(-.12,0,0),(-.55,-.8,0),(-.55,.8,0),-.3,1,.06),
'look_left':((0,0,.38),(0,0,.05),(-.04,0,0),(-.04,0,0),-.08,1,0),
'look_right':((0,0,-.38),(0,0,-.05),(-.04,0,0),(-.04,0,0),-.08,1,0),
'look_up':((-.32,0,0),(-.04,0,0),(-.05,-.1,0),(-.05,.1,0),-.12,1,0),
'look_down':((.30,0,0),(.05,0,0),(-.05,0,0),(-.05,0,0),-.10,1,0),
'glance_back':((0,.10,.42),(0,0,.22),(-.08,-.2,0),(-.12,.1,0),-.12,2,0),
'head_tilt':((.05,.24,0),(0,-.035,0),(-.05,0,0),(-.04,0,0),-.08,2,0),
'shake_head':((0,0,.24),(0,0,-.04),(-.15,-.1,0),(-.15,.1,0),-.2,4,0),
'double_blink':((.04,.03,0),(0,0,0),(-.02,0,0),(-.02,0,0),-.05,2,0),
'power_up':((-.12,0,0),(-.06,0,0),(-.3,-.5,0),(-.3,.5,0),-.3,2,.06),
'power_down':((.25,0,0),(.14,0,0),(.06,0,0),(.06,0,0),.08,1,-.08),
'charge':((.12,0,0),(.03,0,0),(-.3,.1,0),(-.3,-.1,0),-.65,3,0),
'self_check':((.20,0,.17),(.05,0,.08),(-.45,-.1,0),(-.7,.15,0),-.65,3,0),
'victory_pose':((-.12,-.08,0),(-.04,0,0),(-.4,-1.1,0),(-.5,.85,0),-.4,2,.055),
'balanced_pose':((-.04,0,.05),(0,.1,0),(-.25,-.9,0),(-.25,.9,0),-.1,1,.05),
'stretch_left':((0,-.18,0),(0,-.2,0),(-.4,-.8,0),(-.15,.2,0),-.2,1,.02),
'stretch_right':((0,.18,0),(0,.2,0),(-.15,-.2,0),(-.4,.8,0),-.2,1,.02),
'lean_forward':((-.07,0,0),(.2,0,0),(.1,-.15,0),(.1,.15,0),-.15,1,-.025),
'lean_back':((.08,0,0),(-.16,0,0),(-.25,-.3,0),(-.25,.3,0),-.2,1,-.025),
}
LOCOMOTION = ['backstep','tiptoe','sidestep_left','sidestep_right','sneak','crawl','brake','trip_recover','crouch','kneel','sit','stand_up','lie_down','spin_left','spin_right','takeoff','glide','bank_left','bank_right','touchdown']
EXTENSIONS = list(GESTURES) + LOCOMOTION
assert len(EXTENSIONS)==80,len(EXTENSIONS)
# Family-specific clips replace unsuitable biped-only specialties, keeping 136.
QUAD_SPECIAL = ['tail_wag','ear_flick','groom','scratch_ear','sniff_ground','pounce','beg','play_bow','shake_body','paw_tap','roll_back','stretch_spine','chase_tail','dig','bury','drink','nuzzle','roar','howl','snuggle']
BIRD_SPECIAL = ['flap_wings','fold_wings','spread_wings','preen','peck','perch','talon_grab','wing_salute','chirp','head_bob','hop_left','hop_right','hop_forward','hop_back','ruffle','soar','dive','air_brake','wing_stretch','nestle']


def quat(rig,name,angles):
    if name not in rig.pose.bones:return
    rest=rig.data.bones[name].matrix_local.to_quaternion()
    q=Euler(angles,'XYZ').to_quaternion()
    rig.pose.bones[name].rotation_quaternion=rest.inverted() @ q @ rest


def shift(rig,name,world):
    if name in rig.pose.bones:
        rig.pose.bones[name].location=rig.data.bones[name].matrix_local.to_quaternion().inverted() @ Vector(world)


def reset(rig):
    for b in rig.pose.bones:
        b.rotation_mode='QUATERNION';b.rotation_quaternion=Quaternion();b.location=(0,0,0)
        b.scale=(.001,)*3 if b.name.startswith(('prop.','jet.')) else (1,1,1)


def pose(rig,name,p,family='robot',personality=0):
    reset(rig)
    t=p*math.tau;env=math.sin(math.pi*p)**2
    rhythm=.9+(personality%7)*.025
    # Typed appendages add character-specific secondary motion without aliases.
    quat(rig,'antenna',(.035*math.sin(t*2)*env,.04*math.sin(t*3)*env,0))
    for side,sign in [('L',1),('R',-1)]:
        quat(rig,'ear.'+side,(.035*math.sin(t*2+sign)*env,0,.04*sign*env))
    for i,b in enumerate(['tail','tail.mid','tail.tip']):
        quat(rig,b,(.03*math.sin(t+i)*env,0,.11*math.sin(t*2-i*.4)*env))
    if name in GESTURES:
        h,tr,l,r,flex,repeats,lift=GESTURES[name]
        pulse=math.sin(t*repeats);beat=env*(.82+.18*pulse)
        quat(rig,'head',tuple(x*beat for x in h));quat(rig,'torso',tuple(x*env for x in tr));shift(rig,'root',(0,0,lift*env))
        for side,angles in [('L',l),('R',r)]:
            gain=.72 if family=='quadruped' else .85 if family=='bird' else 1
            quat(rig,'upper_arm.'+side,tuple(x*env*gain for x in angles))
            quat(rig,'forearm.'+side,(flex*beat*gain,0,0))
            quat(rig,'hand.'+side,(.10*pulse*env,0,(.08 if side=='L' else -.08)*env))
            for i in range(4):
                grip=.65 if name in ('thumbs_up','thumbs_down','knock','carry_box','lift_object','catch') else .18
                if name.startswith('point') and i==0:grip=0
                quat(rig,f'digit{i}.'+side,(-grip*env,0,(i-1.5)*.035*env))
                quat(rig,f'digit_tip{i}.'+side,(-grip*.7*env,0,0))
        if name in ('double_blink','power_down','cry','yawn'):
            blink=abs(math.sin(t*2)) if name=='double_blink' else env*.85
            for side in ('L','R'):
                if 'eye.'+side in rig.pose.bones:rig.pose.bones['eye.'+side].scale.y=1-.94*blink
        if name in ('laugh','cry','sneeze','yawn','taste'):
            if 'speech' in rig.pose.bones:rig.pose.bones['speech'].scale.y=1+(.8 if name=='yawn' else .55)*env*(.6+.4*abs(pulse))
        if name=='shake_head':quat(rig,'head',(0,0,.28*pulse*env))
        if name=='balanced_pose':quat(rig,'thigh.R',(-.45*env,0,0));quat(rig,'shin.R',(.65*env,0,0))
    elif name in LOCOMOTION or name in ('walk','run','dash','chase_ball','explore','walk_window','climb','climb_dock'):
        locomotion(rig,name,p,family,personality)
    elif name in QUAD_SPECIAL:
        quadruped_special(rig,name,p)
    elif name in BIRD_SPECIAL:
        bird_special(rig,name,p)
    else:
        core_pose(rig,name,p,family,personality)
    if family in ('quadruped','bird') and name in ('kick_ball','hammer','balloon','parachute'):
        prop={'kick_ball':'prop.ball','hammer':'prop.hammer','balloon':'prop.balloon','parachute':'prop.parachute'}[name]
        visible=max(.001,min(1,p/.12,(1-p)/.12))
        rig.pose.bones[prop].scale=(visible,)*3
        if name=='kick_ball':
            launch=max(0,(p-.48)/.52)
            shift(rig,prop,(0,-1.7*launch,.16*abs(math.sin(launch*math.tau))*math.exp(-launch*2)))
            quat(rig,prop,(launch*math.tau*2,0,0))
            if family=='quadruped':quat(rig,'upper_arm.L',(-.65*env,0,0))
        elif name=='hammer':
            rig.pose.bones['prop.anvil'].scale=(visible,)*3
            quat(rig,'hand.L',(.4*math.sin(t*2)*env,0,0))
        elif name=='balloon':quat(rig,prop,(.07*math.sin(t*2)*env,.08*math.sin(t)*env,0))
        elif name=='parachute':quat(rig,prop,(0,.035*math.sin(t*2)*env,0))
    if family in ('quadruped','bird'):
        # Temperament changes the head's follow-through, in addition to each
        # anatomy's actual gait/wing/tail choreography.
        bone=rig.pose.bones['head']
        bone.rotation_quaternion=bone.rotation_quaternion @ Euler((.018*env*math.sin(t*2)*rhythm,0,(personality%5-2)*.009*env),'XYZ').to_quaternion()
    if 'brow.L' in rig.pose.bones:
        for side,sign in [('L',1),('R',-1)]:quat(rig,'brow.'+side,(0,sign*.045*env*math.sin(t*2),0))


def locomotion(rig,name,p,family,personality):
    t=p*math.tau;env=math.sin(math.pi*p)**2
    if name in ('crouch','kneel','sit','stand_up','lie_down','crawl'):
        amount={'crouch':.28,'kneel':.38,'sit':.48,'stand_up':.36,'lie_down':.62,'crawl':.30}[name]
        e=(1-p)**2 if name=='stand_up' else env
        shift(rig,'root',(0,.08*e,-amount*e))
        quat(rig,'torso',((.9 if name=='lie_down' and family not in ('quadruped','bird') else .12)*e,0,0))
        for side,sign in [('L',1),('R',-1)]:
            bend=e*(.85 if name in ('sit','stand_up') else .55)
            quat(rig,'thigh.'+side,(-bend,0,0));quat(rig,'shin.'+side,(bend*1.9,0,0));quat(rig,'foot.'+side,(-bend*.9,0,0))
            quat(rig,'upper_arm.'+side,((-.65 if family=='quadruped' else -.25)*e,sign*.1*e,0))
            quat(rig,'forearm.'+side,(-.5*e,0,0))
        if name=='kneel':quat(rig,'thigh.R',(.3*e,0,0));quat(rig,'shin.R',(1.05*e,0,0))
        if name=='crawl':
            for side,sign in [('L',1),('R',-1)]:quat(rig,'upper_arm.'+side,(-.6*env+.20*math.sin(t*2+sign)*env,0,0))
    elif name in ('takeoff','glide','bank_left','bank_right','touchdown'):
        lift=(.42*env if name=='takeoff' else .35*(1-p)**2 if name=='touchdown' else .28+.025*math.sin(t))
        shift(rig,'root',(0,0,lift));bank=-.25 if name=='bank_left' else .25 if name=='bank_right' else 0
        quat(rig,'torso',(-.08,bank*env,0));quat(rig,'head',(.04,-bank*.4*env,0))
        for side,sign in [('L',1),('R',-1)]:
            angle=1.18 if family=='bird' else .55
            flap=.3*math.sin(t*4)*env if name=='takeoff' else .06*math.sin(t*2)
            quat(rig,'upper_arm.'+side,(0,-sign*(angle+flap)*env,0));quat(rig,'forearm.'+side,(0,-sign*.32*env,0))
            quat(rig,'shin.'+side,(.4*env,0,0))
            if 'jet.'+side in rig.pose.bones:rig.pose.bones['jet.'+side].scale=(max(.001,env),)*3
    elif name in ('spin_left','spin_right'):
        quat(rig,'root',(0,0,(1 if name=='spin_left' else -1)*math.tau*p))
        for side,sign in [('L',1),('R',-1)]:quat(rig,'upper_arm.'+side,(0,-sign*.55*env,0))
        shift(rig,'root',(0,0,.05*env))
    else:
        running=name in ('run','dash','chase_ball');climb=name in ('climb','climb_dock')
        amp=.48 if running else .26;freq=2 if name=='dash' else 1
        if name=='tiptoe':amp=.17
        if name=='sneak':amp=.22
        if name=='backstep':amp=-.23
        if name=='brake':amp*=1-p
        if name=='trip_recover':amp*=1-.5*env
        height= -.09 if name in ('sneak','brake') else 0
        shift(rig,'root',((.16 if name=='sidestep_left' else -.16 if name=='sidestep_right' else 0)*math.sin(t),0,height*env+(.045 if running else .015)*(1-math.cos(t*2))))
        quat(rig,'torso',((-.12 if running else .10 if name=='sneak' else 0)*env,0,.025*math.sin(t)))
        if name=='trip_recover':quat(rig,'torso',(.32*math.sin(t)*env,0,.12*env))
        for side,sign in [('L',1),('R',-1)]:
            wave=math.sin(t*freq+(0 if sign==1 else math.pi))
            quat(rig,'thigh.'+side,(amp*wave,0,0));quat(rig,'shin.'+side,(max(0,-wave)*abs(amp)*1.3,0,0))
            quat(rig,'foot.'+side,(-amp*.4*wave+(.15 if name=='tiptoe' else 0),0,0))
            front=-wave if family=='quadruped' else wave
            quat(rig,'upper_arm.'+side,((-1.4+.25*wave if climb else -.7*amp*front),0,0))
            quat(rig,'forearm.'+side,((-.45 if climb else -.15 if family!='quadruped' else max(0,front)*.25),0,0))


def quadruped_special(rig,name,p):
    t=p*math.tau;env=math.sin(math.pi*p)**2;i=QUAD_SPECIAL.index(name)
    if name=='tail_wag':
        for j,b in enumerate(['tail','tail.mid','tail.tip']):quat(rig,b,(0,0,.7*math.sin(t*4-j*.45)*env))
    elif name=='ear_flick':
        for side,sign in [('L',1),('R',-1)]:quat(rig,'ear.'+side,(.35*math.sin(t*3+sign)*env,sign*.15*env,0))
    elif name in ('sniff_ground','drink','dig','bury','peck'):
        quat(rig,'head',(.34*env,0,.1*math.sin(t*3)*env));quat(rig,'torso',(.12*env,0,0))
        for side,sign in [('L',1),('R',-1)]:quat(rig,'upper_arm.'+side,(-.15*env+(.3*math.sin(t*3+sign) if name in ('dig','bury') else .02*math.sin(t))*env,0,0))
    elif name in ('groom','scratch_ear'):
        quat(rig,'head',(.15*env,.18*env,.13*env));quat(rig,'upper_arm.L',(-1.1*env,-.25*env,0));quat(rig,'forearm.L',(-.5*env+.18*math.sin(t*6)*env,0,0))
        if name=='scratch_ear':quat(rig,'thigh.L',(-.7*env,-.3*env,0))
    elif name in ('pounce','play_bow','stretch_spine'):
        amount=.25 if name=='play_bow' else .18
        quat(rig,'torso',(amount*env,0,0));quat(rig,'head',(-.15*env,0,0))
        shift(rig,'root',(0,-.2*env,(.35*env if name=='pounce' else -.12*env)))
        for side in ('L','R'):quat(rig,'upper_arm.'+side,(-.55*env,0,0));quat(rig,'forearm.'+side,(-.25*env,0,0))
    elif name in ('beg','paw_tap'):
        quat(rig,'torso',(-.20*env,0,0))
        for side,sign in [('L',1),('R',-1)]:quat(rig,'upper_arm.'+side,(-.8*env+(.15*math.sin(t*3)*env if name=='paw_tap' and sign==1 else 0),0,0))
    elif name in ('roll_back','chase_tail'):
        quat(rig,'root',(0,(math.pi*.85 if name=='roll_back' else .15)*env,(math.tau*p if name=='chase_tail' else 0)))
        quat(rig,'head',(0,.1*env,.3*env));shift(rig,'root',(0,0,.2*env))
    elif name=='shake_body':quat(rig,'torso',(0,0,.13*math.sin(t*7)*env));quat(rig,'head',(0,0,-.2*math.sin(t*7)*env))
    elif name in ('roar','howl'):
        quat(rig,'head',((-.25 if name=='howl' else -.12)*env,0,0));rig.pose.bones['speech'].scale.y=1+.8*env
    elif name=='nuzzle':quat(rig,'head',(.1*env,.2*math.sin(t)*env,.18*env));shift(rig,'root',(.12*env,-.1*env,0))
    else:quat(rig,'head',(.22*env,0,.15*env));shift(rig,'root',(0,0,-.12*env))
    # Different timing/appendages for species-specific performances.
    quat(rig,'antenna',(.035*math.sin(t*(2+i%3))*env,.025*math.sin(t*3)*env,0))
    quat(rig,'trunk',(.22*math.sin(t*2+i*.1)*env,0,0))


def bird_special(rig,name,p):
    t=p*math.tau;env=math.sin(math.pi*p)**2;i=BIRD_SPECIAL.index(name)
    if name in ('flap_wings','spread_wings','fold_wings','wing_salute','wing_stretch','ruffle'):
        opening=(1-p if name=='fold_wings' else env)
        for side,sign in [('L',1),('R',-1)]:
            amount=(1.2+.3*math.sin(t*(4 if name=='flap_wings' else 7 if name=='ruffle' else 1)))*opening
            if name=='wing_salute' and side=='R':amount*=.2
            quat(rig,'upper_arm.'+side,(.1*env,-sign*amount,0));quat(rig,'forearm.'+side,(0,-sign*.38*opening,0))
    elif name.startswith('hop'):
        d={'hop_left':(.23,0),'hop_right':(-.23,0),'hop_forward':(0,-.23),'hop_back':(0,.23)}[name]
        shift(rig,'root',(d[0]*env,d[1]*env,.3*env));quat(rig,'head',(-.1*env,0,0))
        for side in ('L','R'):quat(rig,'shin.'+side,(.4*env,0,0))
    elif name in ('preen','peck','head_bob','chirp'):
        quat(rig,'head',((.3 if name=='peck' else .14)*math.sin(t*(4 if name=='peck' else 2))*env,0,.22*env if name=='preen' else 0))
        rig.pose.bones['speech'].scale.y=1+(.6 if name=='chirp' else .15)*abs(math.sin(t*4))*env
        if name=='preen':quat(rig,'upper_arm.L',(0,-.7*env,0))
    elif name in ('soar','dive','air_brake'):
        locomotion(rig,'glide',p,'bird',0);quat(rig,'torso',((.35 if name=='dive' else -.25 if name=='air_brake' else -.06)*env,0,0))
        shift(rig,'root',(0,-.1*env,(.3 if name!='dive' else .15)*env))
    else:
        shift(rig,'root',(0,0,-.13*env));quat(rig,'head',(.10*env,0,.12*env if name=='nestle' else 0))
        for side in ('L','R'):quat(rig,'foot.'+side,((.5 if name=='talon_grab' else .2)*env,0,0))
    quat(rig,'tail',(0,.02*env,.06*math.sin(t*(2+i%3))*env))


def core_pose(rig,name,p,family,personality):
    """Anatomy-aware versions of the shared desktop gesture vocabulary."""
    t=p*math.tau;env=math.sin(math.pi*p)**2
    names=['idle','camera','celebrate','dance','drag','fly','fold_arms','greet','happy','hover','inspect_icon','inspect_window','jump','kick_ball','land','listen','magnifier','nod','peek','point','ponder','pull_scroll','push','read','replace_text','roll','sad','scan_code','scan_screen','search','sensor_scan','sleep','stretch','surprised','talk','turn_around','type','wave','whistle','wink','air_spin','balloon','cheer_partner','dance_together','hammer','handshake','parachute','playful_spar']
    if name not in names:raise ValueError(name)
    if name=='idle':
        shift(rig,'torso',(0,0,.012*math.sin(t)));quat(rig,'head',(0,0,.018*math.sin(t)))
    elif name in ('fly','hover','land','parachute','air_spin'):
        locomotion(rig,'touchdown' if name=='land' else 'glide' if name=='hover' else 'takeoff',p,family,personality)
        if name=='air_spin':quat(rig,'root',(0,0,math.tau*p))
        if name=='parachute':quat(rig,'head',(-.18*env,0,0))
    elif name in ('wave','greet','handshake','point','peek'):
        angle={'wave':.9,'greet':.75,'handshake':.4,'point':.3,'peek':.5}[name]
        quat(rig,'upper_arm.L',(-.6*env,-angle*env,0));quat(rig,'forearm.L',(-.45*env+.1*math.sin(t*3)*env,0,0))
        quat(rig,'hand.L',(0,0,.25*math.sin(t*(3 if name=='wave' else 2))*env))
        quat(rig,'head',(-.04*env,-.08*env,.1*env if name=='peek' else 0))
    elif name in ('talk','listen','ponder','nod','whistle','wink','sleep','happy','sad','surprised'):
        head={'talk':(.04,.03,.09),'listen':(-.06,.15,0),'ponder':(.12,.12,.10),'nod':(.20,0,0),'whistle':(-.13,0,.05),'wink':(0,-.12,0),'sleep':(.24,.16,0),'happy':(-.12,0,.12),'sad':(.24,.05,0),'surprised':(-.20,0,0)}[name]
        quat(rig,'head',tuple(a*env*math.sin(t*2) if name=='nod' else a*env for a in head))
        if 'speech' in rig.pose.bones:rig.pose.bones['speech'].scale.y=1+(max(0,math.sin(t*5))*.8*env if name=='talk' else .6*env if name=='surprised' else .2*env if name=='whistle' else 0)
        for side in ('L','R'):
            if name=='sleep' or name=='wink' and side=='L':rig.pose.bones['eye.'+side].scale.y=1-.95*env
        if name in ('happy','surprised'):shift(rig,'root',(0,0,.06*env))
    elif name in ('dance','dance_together','celebrate','cheer_partner','stretch'):
        freq={'dance':3,'dance_together':2,'celebrate':4,'cheer_partner':5,'stretch':1}[name]
        quat(rig,'torso',(0,.10*math.sin(t*freq)*env,.05*math.sin(t*2)*env));quat(rig,'head',(0,-.08*math.sin(t*freq)*env,0));shift(rig,'root',(0,0,.06*abs(math.sin(t*freq))*env))
        for side,sign in [('L',1),('R',-1)]:quat(rig,'upper_arm.'+side,(-.3*env,-sign*(.5+.2*math.sin(t*freq))*env,0))
    elif name in ('read','type','camera','magnifier','search','inspect_icon','inspect_window','scan_code','scan_screen','sensor_scan'):
        idx=['read','type','camera','magnifier','search','inspect_icon','inspect_window','scan_code','scan_screen','sensor_scan'].index(name)
        quat(rig,'head',((.16 if name in ('read','type') else -.02)*env,0,.13*math.sin(t*(1+idx%3))*env))
        quat(rig,'upper_arm.L',(-(.55+idx*.035)*env,-.1*env,0));quat(rig,'forearm.L',(-.5*env,0,0))
        if name in ('read','type','camera'):quat(rig,'upper_arm.R',(-.65*env,.1*env,0));quat(rig,'forearm.R',(-.5*env,0,0))
        prop='prop.tablet' if name in ('read','type') else 'prop.camera' if name=='camera' else 'prop.magnifier' if name in ('search','magnifier','inspect_icon') else 'prop.scan'
        if prop in rig.pose.bones:rig.pose.bones[prop].scale=(max(.001,env),)*3
    elif name in ('drag','push','pull_scroll','replace_text','hammer','balloon','playful_spar','fold_arms'):
        idx=['drag','push','pull_scroll','replace_text','hammer','balloon','playful_spar','fold_arms'].index(name)
        for side,sign in [('L',1),('R',-1)]:quat(rig,'upper_arm.'+side,(-(.55+idx*.035)*env+.12*math.sin(t*(2+idx%3)+sign)*env,0,0));quat(rig,'forearm.'+side,(-.6*env,0,0))
        quat(rig,'torso',((-.1 if name=='push' else .08)*env,0,.05*math.sin(t*2)*env));shift(rig,'root',(0,0,-.045*env))
    elif name=='jump':
        shift(rig,'root',(0,0,.4*env));quat(rig,'torso',(-.1*math.sin(t)*env,0,0))
        for side in ('L','R'):quat(rig,'shin.'+side,(.5*env,0,0))
    elif name=='kick_ball':quat(rig,'thigh.L',(-.65*env,0,0));quat(rig,'upper_arm.R',(-.3*env,0,0))
    elif name=='roll':quat(rig,'root',(0,math.tau*p,0));shift(rig,'root',(0,0,.3*env))
    elif name=='turn_around':quat(rig,'root',(0,0,math.pi*env))
