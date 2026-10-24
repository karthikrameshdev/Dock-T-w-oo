"""Distinct acting beats layered over the compatible mechanical action library."""

def blend_rotation(name, axis, angle):
    joint=rig.pose.bones[name]
    rest=armature.bones[name].matrix_local.to_quaternion()
    joint.rotation_quaternion = joint.rotation_quaternion @ (rest.inverted() @ Quaternion(Vector(axis),angle) @ rest)


def arm_target(side, target, hint):
    """Two-bone reach with a stable elbow pole; the hand remains rigidly attached."""
    bpy.context.view_layer.update()
    upper=rig.pose.bones['upper_arm.'+side];lower=rig.pose.bones['forearm.'+side]
    parent=upper.parent.matrix @ upper.parent.bone.matrix_local.inverted()
    shoulder=parent @ upper.bone.head_local
    delta=Vector(target)-shoulder
    length= min(delta.length, upper.bone.length+lower.bone.length-.005)
    direction=delta.normalized()
    a,b=upper.bone.length,lower.bone.length
    along=(a*a+length*length-b*b)/(2*length)
    pole=Vector(hint)-shoulder; pole=(pole-direction*pole.dot(direction)).normalized()
    elbow=shoulder+direction*along+pole*math.sqrt(max(.00001,a*a-along*along))
    actual=shoulder+direction*length
    upper_global=(upper.bone.tail_local-upper.bone.head_local).rotation_difference(elbow-shoulder)
    lower_global=(lower.bone.tail_local-lower.bone.head_local).rotation_difference(actual-elbow)
    rest=upper.bone.matrix_local.to_quaternion()
    upper.rotation_quaternion=rest.inverted() @ parent.to_quaternion().inverted() @ upper_global @ rest
    rest=lower.bone.matrix_local.to_quaternion()
    lower.rotation_quaternion=rest.inverted() @ upper_global.inverted() @ lower_global @ rest


def expressive_pose(name,p):
    cycle=math.sin(math.tau*p);arc=math.sin(math.pi*p)
    envelope=min(1,p*7,(1-p)*7); envelope=envelope*envelope*(3-2*envelope)
    # Props collapse into their own grip origin rather than living at world zero.
    for b in rig.pose.bones:
        if b.name.startswith(('prop.','jet.')):b.scale=(.001,)*3
    def show(bone,amount=envelope):rig.pose.bones[bone].scale=(max(.001,amount),)*3
    rotation('antenna',(0,1,0), .05*math.sin(math.tau*p*2+.3))
    for side,sign in (('L',1),('R',-1)):
        rotation('brow.'+side,(0,1,0),sign*.035*cycle)
    if name in ('walk','walk_window','run','chase_ball','explore'):
        running=name in ('run','chase_ball')
        blend_rotation('torso',(1,0,0),-.13 if running else -.025)
        blend_rotation('torso',(0,0,1),.055*cycle)
        blend_rotation('head',(0,0,1),-.04*cycle)
        rotation('antenna',(1,0,0),(.14 if running else .07)*math.sin(math.tau*p-.4))
        for side,phase in (('L',p),('R',(p+.5)%1)):
            blend_rotation('foot.'+side,(1,0,0),.10*math.sin(phase*math.tau))
    elif name in ('wave','greet'):
        # Wrist waves beyond the helmet, with head tilt and finger fan.
        rotation('upper_arm.L',(0,1,0),-1.42*envelope)
        rotation('forearm.L',(0,1,0),(-.65+.14*math.sin(p*math.tau*3))*envelope)
        rotation('hand.L',(1,0,0),.23*math.sin(p*math.tau*3)*envelope)
        rotation('head',(0,1,0),-.07*arc)
        for i in range(4):
            rotation(f'digit{i}.L',(0,1,0),(i-1.5)*.09*envelope)
            rotation(f'digit_tip{i}.L',(1,0,0),.07*math.sin(p*math.tau*3+i)*envelope)
    elif name in ('search','inspect_icon','magnifier'):
        show('prop.magnifier')
        arm_target('L',(1.15,-.60,2.35+.63*envelope),(1.55,-.25,2.35))
        rotation('hand.L',(1,0,0),-.25*envelope)
        rotation('head',(0,0,1),(.14*cycle-.10)*envelope)
        rotation('head',(0,1,0),-.08*envelope)
        blend_rotation('torso',(1,0,0),-.08*envelope)
    elif name in ('read','type'):
        show('prop.tablet')
        arm_target('R',(-.62,-.70*envelope,1.49+.85*envelope),(-1.15,-.25,1.9))
        rotation('hand.R',(1,0,0),1.25*envelope)
        rotation('upper_arm.L',(1,0,0),-.9*envelope)
        rotation('forearm.L',(1,0,0),-.75*envelope)
        rotation('head',(1,0,0),.12*envelope)
        blend_rotation('head',(0,0,1),.075*math.sin(math.tau*p*2)*envelope)
        # Index traces lines; other fingers stay curled.
        rotation('hand.L',(0,1,0),.13*math.sin(math.tau*p*3)*envelope)
        rotation('digit0.L',(1,0,0),-.5*max(0,math.sin(math.tau*p*4))*envelope)
    elif name=='camera':
        show('prop.camera')
        arm_target('L',(.68,-.76*envelope,1.49+1.08*envelope),(1.1,-.35,2.1))
        rotation('hand.L',(1,0,0),1.0*envelope)
        arm_target('R',(-.38,-.72*envelope,1.49+.83*envelope),(-1.1,-.35,2.0))
        rotation('head',(0,1,0),-.06*envelope)
        # Aim, squeeze shutter, then settle after the photograph.
        shutter=math.exp(-((p-.58)/.06)**2)
        rotation('digit0.L',(1,0,0),-.8*shutter)
        rig.pose.bones['eye.R'].scale.y=1-.92*shutter
        blend_rotation('torso',(1,0,0),.035*shutter)
    elif name in ('scan_screen','sensor_scan','inspect_window','scan_code'):
        show('prop.scan');show('prop.scanline',1)
        rig.pose.bones['prop.scanline'].location.y=.21*math.sin(math.tau*p*2)
        rotation('head',(0,0,1),.25*cycle*envelope)
        rotation('upper_arm.L',(1,0,0),-.95*envelope)
        rotation('forearm.L',(1,0,0),-.45*envelope)
        rotation('brow.L',(0,1,0),.18*envelope)
        rotation('brow.R',(0,1,0),-.18*envelope)
    elif name in ('fly','hover','land'):
        lift=(.30*arc if name=='fly' else .22+.035*cycle if name=='hover' else .32*(1-p)**2-.07*math.exp(-((p-.8)/.10)**2))
        rig.pose.bones['root'].location.y=lift
        for side,sign in (('L',-1),('R',1)):
            show('jet.'+side, (.6+.2*math.sin(math.tau*p*5))*(1 if name=='hover' else envelope))
            rotation('upper_arm.'+side,(0,1,0),sign*.65*envelope)
            rotation('forearm.'+side,(1,0,0),-.32*envelope)
            rotation('thigh.'+side,(1,0,0),.15*envelope)
            rotation('shin.'+side,(1,0,0),.34*envelope)
            rotation('foot.'+side,(1,0,0),.13*envelope)
        rotation('torso',(1,0,0),-.10*envelope)
        rotation('antenna',(1,0,0),.16*envelope+.05*cycle)
    elif name in ('climb','climb_dock'):
        # Alternating reach and contact with a consistent elbow pole.
        for side,sign,phase in (('L',1,p),('R',-1,(p+.5)%1)):
            reach=math.sin(phase*math.tau)
            arm_target(side,(sign*.88,-.82,2.53+.18*reach),(sign*1.5,-.35,2.3))
            rotation('hand.'+side,(1,0,0),-.15)
        rotation('head',(1,0,0),-.10)
        rotation('antenna',(1,0,0),.08*cycle)
    elif name in ('pull_scroll','drag','push'):
        reach=.5+.5*math.sin(math.tau*p-.7)
        for side,sign in (('L',1),('R',-1)):
            arm_target(side,(sign*.73,-(.55+.20*reach)*envelope,1.65+.3*envelope),(sign*1.5,-.1,1.8))
            for i in range(4):
                rotation(f'digit{i}.'+side,(1,0,0),-.85*envelope)
                rotation(f'digit_tip{i}.'+side,(1,0,0),-.7*envelope)
        rotation('torso',(1,0,0),(.14 if name!='push' else -.14)*envelope)
        rig.pose.bones['root'].location.y=-.10*envelope
        leg('L',-.14,.30,-.10*envelope);leg('R',.13,.30,-.10*envelope)
    elif name in ('talk','listen','happy','sad'):
        rotation('head',(0,0,1),.08*math.sin(math.tau*p)*envelope)
        blend_rotation('head',(1,0,0),.045*math.sin(math.tau*p*3)*envelope)
        for side,sign in (('L',1),('R',-1)):
            rotation('upper_arm.'+side,(1,0,0),(-.3-.14*math.sin(math.tau*p*2+sign))*envelope)
            rotation('forearm.'+side,(1,0,0),-.55*envelope)
            rotation('hand.'+side,(0,1,0),sign*.18*envelope)
            rotation('brow.'+side,(0,1,0),sign*(.20 if name=='sad' else -.07)*envelope)
    elif name=='jump':
        rig.pose.bones['root'].location.y=.38*max(0,math.sin(math.pi*p))-.09*math.sin(math.tau*p)**2
        rotation('antenna',(1,0,0),.18*math.sin(math.tau*p-.3))
    elif name=='dance':
        rotation('head',(0,1,0),.12*math.sin(math.tau*p*4))
        rotation('antenna',(0,1,0),.15*math.sin(math.tau*p*4-.5))
    elif name=='sleep':
        rotation('head',(0,1,0),.14*arc)
        rig.pose.bones['torso'].location.y=.014*math.sin(math.tau*p*2)

    # Grip the tools with all four digits and a thumb.
    for side in ('L','R'):
        gripping=(side=='L' and name in ('camera','search','magnifier','inspect_icon')) or (side=='R' and name in ('read','type'))
        if gripping:
            for i in range(4):
                rotation(f'digit{i}.'+side,(1,0,0),-.70*envelope)
                rotation(f'digit_tip{i}.'+side,(1,0,0),-.65*envelope)


def finish_performance(name,p):
    """Orient tools about their actual grip after the arm-clearance solver."""
    envelope=min(1,p*7,(1-p)*7);envelope=envelope*envelope*(3-2*envelope)
    def orient(bone, axis,angle):
        joint=rig.pose.bones[bone]
        parent=joint.parent.matrix @ joint.parent.bone.matrix_local.inverted()
        rest=joint.bone.matrix_local.to_quaternion()
        desired=Quaternion(Vector(axis),angle)
        if bone=='prop.magnifier': desired=Quaternion(Vector((1,0,0)),.35*envelope) @ desired
        joint.rotation_quaternion=rest.inverted() @ parent.to_quaternion().inverted() @ desired @ rest
    bpy.context.view_layer.update()
    if name in ('search','magnifier','inspect_icon'):
        orient('prop.magnifier',(0,1,0),2.38*envelope)
    elif name=='camera':orient('prop.camera',(1,0,0),-.10*envelope)
    elif name in ('read','type'):orient('prop.tablet',(1,0,0),-.6*envelope)
    # This bone also drives Blender's editable speech shape keys. The desktop
    # renderer uses live audio amplitude instead of these demonstration visemes.
    speech=rig.pose.bones['speech']
    level=max(0,math.sin(p*math.tau*5)+.2*math.sin(p*math.tau*11))*.85*envelope if name=='talk' else (.65*envelope if name=='surprised' else .15*envelope if name=='whistle' else 0)
    speech.scale.y=1+level
    speech.scale.x=1+level*(.5+.5*math.sin(p*math.tau*3))*.6
    speech.scale.z=1+level*(.5+.5*math.sin(p*math.tau*7))*.5
