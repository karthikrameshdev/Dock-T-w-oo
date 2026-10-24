"""Reference-driven mesh construction, executed in build_brain's helper namespace.

Smooth ceramic and glossy gradient enamel replace the earlier fiber trim.
Gradients use vertex colors so Blender and glTF share the same finish.
"""
GRADIENT_PALETTES = {}


def gradient_enamel(name, palette, roughness=.20, metallic=.45):
    result = material(name, '#FFFFFF', roughness, metallic)
    shader = result.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Coat Weight'].default_value = .70
    shader.inputs['Coat Roughness'].default_value = .12
    vertex_color = result.node_tree.nodes.new('ShaderNodeVertexColor')
    vertex_color.layer_name = 'AccentGradient'
    vertex_color.label = 'Baked cobalt-to-cyan gradient (glTF COLOR_0)'
    result.node_tree.links.new(vertex_color.outputs['Color'], shader.inputs['Base Color'])
    GRADIENT_PALETTES[result.name] = [tuple(linear(int(c[i:i+2],16)/255) for i in (1,3,5)) for c in palette]
    return result


def paint_accent_gradient(obj):
    """Bake a smooth color transition after bevels and rest transforms are applied."""
    palette = next((GRADIENT_PALETTES[m.name] for m in obj.data.materials if m.name in GRADIENT_PALETTES), None)
    if palette is None:
        return
    attribute = obj.data.color_attributes.new(name='AccentGradient', type='FLOAT_COLOR', domain='POINT')
    obj.data.color_attributes.active_color_index = 0
    low = min(v.co.z for v in obj.data.vertices)
    high = max(v.co.z for v in obj.data.vertices)
    for vertex, color in zip(obj.data.vertices, attribute.data):
        t = (vertex.co.z-low) / max(.0001, high-low)
        t = t*t*(3-2*t)
        segment = min(len(palette)-2, int(t*(len(palette)-1)))
        fraction = t*(len(palette)-1)-segment
        a,b = palette[segment:segment+2]
        color.color = tuple(x+(y-x)*fraction for x,y in zip(a,b)) + (1,)


MINT = gradient_enamel('Glossy azure gradient enamel', ('#235FA7','#2A86C1','#5BC9E1'))
IVORY = material('Pearl silver ceramic', '#E2E9EB', .24, .48)
PURPLE = gradient_enamel('Glossy cobalt gradient enamel', ('#173E79','#22649E','#3D9FC3'), .22, .50)
PURPLE_DARK = material('Rubber joint seals', '#122B3A', .46, .12)
VISOR = material('Obsidian curved glass', '#06131E', .19, .25)
GRAPHITE = material('Brushed titanium', '#354550', .28, .8)
TRIM = material('Silver machined edges', '#A5BBC4', .24, .8)
WHITE = material('Soft white eye glints', '#E3FFFF', .25, .05, 1.8)
PUPIL = material('Deep navy pupils', '#031827', .22, .1)
TEAL = material('Electric cyan light', '#13C9F4', .3, .1, 1.4)
GREEN = material('Aqua antenna glow', '#71F6FF', .22, .18, 2)
SEAM = material('Panel gaps', '#123B54', .4, .35)
PINK = material('Peach tongue', '#F588A6', .38, .02)
MOUTH_DARK = material('Mouth interior', '#040A14', .6, 0)
def helmet_front(x,z):
    # A round dome with a broad softly squared face, matching the supplied robot.
    v=max(0.,1-abs((z-3.35)/.98)**(2/.78))
    h=max(0.,v**(.78/.8)-abs(x/1.17)**(2/.8))
    return -.81*h**(.8/2)

vertices,faces=[],[]
segments,rings=80,40
for ring in range(rings+1):
    a=-math.pi/2+math.pi*ring/rings
    for seg in range(segments):
        b=math.tau*seg/segments;c=math.copysign(abs(math.cos(a))**.78,math.cos(a))
        vertices.append((1.17*c*math.copysign(abs(math.cos(b))**.8,math.cos(b)),.81*c*math.copysign(abs(math.sin(b))**.8,math.sin(b)),3.35+.98*math.copysign(abs(math.sin(a))**.78,math.sin(a))))
for r in range(rings):
    for i in range(segments):
        a=r*segments+i;b=r*segments+(i+1)%segments
        faces.append((a,b,b+segments,a+segments))
mesh=bpy.data.meshes.new('Spherical silver helmet');mesh.from_pydata(vertices,[],faces);mesh.update()
obj=bpy.data.objects.new('Helmet',mesh);scene.collection.objects.link(obj);finish(obj,'Helmet',IVORY,'head')
rounded_panel('Visor titanium gasket',(0,-.025,3.32),2.08,1.57,.02,.57,GRAPHITE,'head',True)
rounded_panel('Visor silver lip',(0,-.046,3.32),2.02,1.51,.015,.55,TRIM,'head',True)
rounded_panel('Visor glass',(0,-.068,3.32),1.94,1.43,.012,.52,VISOR,'head',True)
# A center crown insert and symmetric helmet panel seams.
rounded_panel('Crown blue inset',(0,-.015,4.13),.62,.23,.015,.10,PURPLE,'head',True)
for sign,side in ((1,'L'),(-1,'R')):
    curve('Helmet segmented seam.'+side,[(sign*x,helmet_front(sign*x,z)-.013,z) for x,z in ((.49,4.21),(.68,4.08),(.8,3.94))],.012,SEAM,'head')
    ex=sign*.40;ey=helmet_front(ex,3.48)-.11
    sphere('Eye white.'+side,(ex,ey,3.48),(.246,.032,.31),TEAL,'eye.'+side)
    sphere('Eye iris.'+side,(ex,ey-.033,3.48),(.167,.021,.233),PUPIL,'pupil.'+side)
    sphere('Eye glint.'+side,(ex-.055,ey-.059,3.61),(.045,.012,.057),WHITE,'pupil.'+side,20)
    sphere('Eye small glint.'+side,(ex+.052,ey-.056,3.38),(.018,.008,.022),TEAL,'pupil.'+side,16)
    curve('Eyebrow.'+side,[(x,helmet_front(x,z)-.12,z) for x,z in ((ex-.14,3.86),(ex,3.91),(ex+.14,3.87))],.022,TEAL,'brow.'+side)
    for i in range(3):
        sphere(f'Cheek light.{side}.{i}',(sign*(.64+i*.058),helmet_front(sign*(.64+i*.058),3.12)-.105,3.12),(.013,.012,.022),MINT,'head',12)
    cylinder('Ear blue housing.'+side,(sign*1.04,.02,3.37),(sign*1.24,.02,3.37),.395,PURPLE,'head')
    cylinder('Ear silver disc.'+side,(sign*1.24,.02,3.37),(sign*1.32,.02,3.37),.33,IVORY,'head')
    torus('Ear luminous ring.'+side,(sign*1.375,.02,3.37),.25,.022,TEAL,'head',(0,math.pi/2,0))
    cylinder('Ear acoustic panel.'+side,(sign*1.33,.02,3.37),(sign*1.38,.02,3.37),.22,MINT,'head')
# Slim, polished protective trim follows the helmet contour.
sphere('Glossy blue chin trim',(0,.015,2.69),(1.035,.72,.19),MINT,'head',48)
for sign,side in ((1,'L'),(-1,'R')):
    sphere('Glossy blue cheek trim.'+side,(sign*.95,.035,3.02),(.19,.60,.31),MINT,'head',48)

sphere('Antenna base',(.52,.08,4.20),(.13,.14,.11),MINT,'head')
curve('Flexible antenna cable',[(.52,.08,4.21),(.58,.08,4.43),(.72,.08,4.65),(.9,.08,4.76)],.032,GRAPHITE,'antenna')
for i in range(14):
    t=i/13;x=.52+.38*t*t;z=4.24+.51*t
    torus('Antenna coil '+str(i),(x,.08,z),.037,.009,TRIM,'antenna',(0,.35+.45*t,0))
sphere('Antenna bulb',(.92,.08,4.78),(.145,.145,.145),GREEN,'antenna')

cylinder('Neck titanium spindle',(0,0,2.47),(0,0,2.86),.20,GRAPHITE,'torso')
for i in range(4): torus('Neck articulation ring '+str(i),(0,0,2.52+i*.075),.21,.025,TRIM,'torso')
sphere('Pearl chest armor',(0,0,2.04),(.65,.44,.55),IVORY,'torso')
def chest_front(x,z): return -.44*math.sqrt(max(.01,1-(x/.65)**2-((z-2.04)/.55)**2))
rounded_panel('Blue chest yoke',(0,-.028,2.31),.97,.40,.018,.16,MINT,'torso',chest_front)
rounded_panel('Blue abdominal armor',(0,-.025,1.92),.67,.37,.018,.16,PURPLE,'torso',chest_front)
rounded_panel('Silver abdominal accent',(0,-.055,1.79),.46,.16,.016,.07,TRIM,'torso',chest_front)
for radius,minor,mat,yy in ((.215,.042,GRAPHITE,-.443),(.19,.024,IVORY,-.48),(.15,.016,TEAL,-.50)):
    torus('Reactor bezel '+str(radius),(0,yy,2.18),radius,minor,mat,'torso',(math.pi/2,0,0))
sphere('Chest reactor',(0,-.504,2.18),(.124,.038,.124),GREEN,'torso')
for s in (-1,1):
    for x,z in ((.40,2.39),(.46,1.99),(.22,1.74)):
        sphere('Armor rivet',(s*x,chest_front(s*x,z)-.045,z),(.022,.012,.022),GRAPHITE,'torso',12)
    for i in range(3): rounded_box('Side cooling louvre',(s*.603,.05,2.04+i*.075),(.035,.22,.025),.01,GRAPHITE,'torso')
sphere('Glossy waist connector',(0,0,1.64),(.52,.365,.15),MINT,'root',48)
sphere('Pelvis ceramic shell',(0,0,1.43),(.43,.33,.24),IVORY,'root')
# Compact twin thrusters, visible in side and back views.
for sign,side in ((1,'L'),(-1,'R')):
    cylinder('Jet engine.'+side,(sign*.43,.39,1.76),(sign*.43,.39,2.31),.155,PURPLE,'torso')
    for z in (1.80,1.88,2.26):torus('Jet collar.'+side+str(z),(sign*.43,.39,z),.16,.022,TRIM,'torso')
    cylinder('Thruster nozzle.'+side,(sign*.43,.39,1.70),(sign*.43,.39,1.82),.10,GRAPHITE,'torso',.15)
    sphere('Jet flame.'+side,(sign*.43,.39,1.49),(.08,.08,.25),TEAL,'jet.'+side)
    sphere('Jet flame core.'+side,(sign*.43,.39,1.61),(.047,.047,.13),WHITE,'jet.'+side)

for sign,side in ((1,'L'),(-1,'R')):
    shoulder,elbow,wrist=(sign*.77,0,2.35),(sign*1.,0,1.88),(sign*1.12,-.025,1.49)
    sphere('Shoulder titanium core.'+side,shoulder,(.23,.21,.22),GRAPHITE,'upper_arm.'+side)
    sphere('Shoulder silver pauldron.'+side,(sign*.82,-.025,2.46),(.27,.24,.16),IVORY,'upper_arm.'+side)
    torus('Shoulder mechanical ring.'+side,(sign*.98,0,2.35),.15,.026,TRIM,'upper_arm.'+side,(0,math.pi/2,0))
    cylinder('Upper arm piston.'+side,(sign*.83,0,2.22),(sign*.97,0,1.98),.11,GRAPHITE,'upper_arm.'+side)
    sphere('Glossy upper arm sleeve.'+side,(sign*.91,0,2.11),(.145,.145,.17),MINT,'upper_arm.'+side,40)
    sphere('Elbow titanium hinge.'+side,elbow,(.15,.15,.15),GRAPHITE,'forearm.'+side)
    for rad,mat,xx in ((.115,TRIM,1.12),(.075,PURPLE,1.14),(.04,TRIM,1.16)):
        cylinder('Elbow concentric hub.'+side+str(rad),(sign*xx,0,1.88),(sign*(xx+.025),0,1.88),rad,mat,'forearm.'+side)
    armor('Forearm blue gauntlet.'+side,(sign*1.02,0,1.79),(sign*1.10,-.02,1.58),.36,.35,MINT,'forearm.'+side)
    armor('Forearm silver plate.'+side,(sign*1.03,-.13,1.78),(sign*1.10,-.15,1.60),.27,.11,IVORY,'forearm.'+side)
    sphere('Glossy wrist cuff.'+side,(sign*1.12,-.015,1.51),(.16,.15,.095),MINT,'hand.'+side,40)
    sphere('Wrist joint.'+side,wrist,(.12,.12,.10),GRAPHITE,'hand.'+side)
    sphere('Silver glove palm.'+side,(sign*1.14,-.055,1.37),(.18,.135,.17),IVORY,'hand.'+side)
    sphere('Blue palm pad.'+side,(sign*1.14,-.176,1.39),(.12,.025,.11),MINT,'hand.'+side)
    for finger in range(4):
        x=sign*(.995+finger*.092);length=.22 if finger in (1,2) else .18
        bn=f'digit{finger}.'+side;tip=f'digit_tip{finger}.'+side
        cylinder('Finger proximal.'+side+str(finger),(x,-.055,1.245),(x,-.075,1.15),.035,TRIM,bn)
        sphere('Finger hinge.'+side+str(finger),(x,-.075,1.15),(.039,.039,.039),GRAPHITE,tip,16)
        cylinder('Finger distal.'+side+str(finger),(x,-.075,1.15),(x,-.12,1.245-length),.033,IVORY,tip)
        sphere('Fingertip sensor.'+side+str(finger),(x,-.145,1.245-length),(.021,.015,.025),TEAL,tip,12)
    cylinder('Thumb proximal.'+side,(sign*1.29,-.055,1.40),(sign*1.37,-.10,1.32),.048,TRIM,'thumb.'+side)
    sphere('Thumb knuckle.'+side,(sign*1.37,-.10,1.32),(.05,.05,.05),GRAPHITE,'thumb_tip.'+side,16)
    cylinder('Thumb distal.'+side,(sign*1.37,-.10,1.32),(sign*1.34,-.15,1.25),.043,IVORY,'thumb_tip.'+side)
    sphere('Hip titanium ball.'+side,(sign*.38,0,1.42),(.19,.18,.19),GRAPHITE,'thigh.'+side)
    sphere('Glossy thigh shell.'+side,(sign*.38,0,1.12),(.185,.185,.215),MINT,'thigh.'+side,40)
    sphere('Knee hinge.'+side,(sign*.38,0,.87),(.17,.17,.15),GRAPHITE,'shin.'+side)
    sphere('Blue kneecap.'+side,(sign*.38,-.15,.89),(.16,.09,.18),MINT,'shin.'+side)
    cylinder('Sculpted shin armor.'+side,(sign*.38,0,.73),(sign*.38,0,.36),.20,IVORY,'shin.'+side,.24)
    sphere('Boot blue shell.'+side,(sign*.38,-.16,.25),(.34,.47,.24),MINT,'foot.'+side)
    sphere('Boot silver toe.'+side,(sign*.38,-.27,.29),(.30,.39,.20),IVORY,'foot.'+side)
    rounded_box('Rubber boot sole.'+side,(sign*.38,-.18,.10),(.66,.91,.13),.06,GRAPHITE,'foot.'+side)
    curve('Boot blue toe bumper.'+side,[(sign*.38-.27,-.49,.17),(sign*.38,-.61,.17),(sign*.38+.27,-.49,.17)],.045,MINT,'foot.'+side)
    for j in range(5):rounded_box('Sole tread.'+side+str(j),(sign*.38,-.52+j*.17,.046),(.59,.045,.045),.013,PURPLE_DARK,'foot.'+side)
    cylinder('Ankle silver disk.'+side,(sign*.64,-.06,.35),(sign*.69,-.06,.35),.104,TRIM,'foot.'+side)
    cylinder('Ankle cyan center.'+side,(sign*.69,-.06,.35),(sign*.705,-.06,.35),.065,TEAL,'foot.'+side)

# A filled, concave mouth, cyan lip and independently morphing tongue and teeth.
# Both open and rounded visemes are exported and driven together by the runtime.
def mouth_shape(t,opened=False):
    x=.29*math.cos(t)
    z=3.035-.085*math.sin(t)**2+.014*math.sin(t)
    if opened:z=3.005+(.075 if math.sin(t)>0 else .18)*math.sin(t)
    return x,z

def mouth_mesh(name,mat,rim=False):
    verts,opens,faces=[],[],[]
    for ring in range(2 if rim else 9):
        scale=(1 if ring==0 else .86) if rim else ring/8
        for i in range(64):
            t=i/64*math.tau
            for dst,op in ((verts,False),(opens,True)):
                x,z=mouth_shape(t,op); x*=scale;z=3.00+(z-3.00)*scale
                dst.append((x,helmet_front(x,z)-(.137 if rim else .113)+.02*(1-scale),z))
    count=2 if rim else 9
    for r in range(count-1):
        for i in range(64):a=r*64+i;b=r*64+(i+1)%64;faces.append((a,b,b+64,a+64))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);scene.collection.objects.link(obj);finish(obj,name,mat,'head')
    obj.shape_key_add(name='Basis');key=obj.shape_key_add(name='mouth_open')
    for v,co in zip(key.data,opens):v.co=co
    key=obj.shape_key_add(name='mouth_round')
    for v,co in zip(key.data,verts):v.co.x=co[0]*.62
    return obj
mouth=mouth_mesh('Speaking smile',TEAL,True)
mouth_mesh('Mouth cavity',MOUTH_DARK)
for name,loc,size,mat in (('Tongue',(0,-.94,2.90),(.13,.026,.054),PINK),('Upper teeth',(0,-.94,3.04),(.115,.022,.026),IVORY)):
    obj=sphere(name,loc,size,mat,'head',24)
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    obj.shape_key_add(name='Basis');key=obj.shape_key_add(name='mouth_open')
    for v in obj.data.shape_keys.key_blocks['Basis'].data:
        v.co.x*=.001;v.co.z=3.015+(v.co.z-3.015)*.001;v.co.y=helmet_front(0,3.015)-.08
    if name=='Tongue':
        curl=obj.shape_key_add(name='tongue_curl')
        for v,b in zip(curl.data,obj.data.shape_keys.key_blocks['Basis'].data):
            v.co=b.co; v.co.z+=.025
    # Key still contains the full tongue/teeth shape; zero is tucked behind visor.
    obj.shape_key_add(name='mouth_round')
    for v,b in zip(obj.data.shape_keys.key_blocks['mouth_round'].data,obj.data.shape_keys.key_blocks['Basis'].data):v.co=b.co

# Hand-held tools are skinned to dedicated bones, animated from a collapsed scale.
# Their grip origins coincide with the palm; geometry stays attached during blends.
hand=(1.14,-.055,1.33)
# Magnifier extends below the grip in bind pose, so it rises above a raised palm.
cylinder('Magnifier handle',(1.14,-.055,1.38),(1.14,-.055,.50),.044,PURPLE,'prop.magnifier')
torus('Magnifier silver frame',(1.14,-.055,.25),.24,.035,TRIM,'prop.magnifier',(math.pi/2,0,0))
torus('Magnifier cyan lens edge',(1.14,-.06,.25),.207,.012,TEAL,'prop.magnifier',(math.pi/2,0,0))
curve('Lens reflection',[(1.01,-.07,.29),(1.02,-.07,.38),(1.09,-.07,.42)],.012,WHITE,'prop.magnifier')
rounded_box('Camera blue body',(1.14,-.055,1.20),(.50,.23,.32),.065,PURPLE,'prop.camera')
rounded_box('Camera silver top',(1.14,-.055,1.36),(.47,.24,.07),.026,IVORY,'prop.camera')
cylinder('Camera lens barrel',(1.14,-.18,1.20),(1.14,-.28,1.20),.12,GRAPHITE,'prop.camera')
torus('Camera lens light',(1.14,-.29,1.20),.085,.014,TEAL,'prop.camera',(math.pi/2,0,0))
sphere('Camera optical glass',(1.14,-.29,1.20),(.07,.015,.07),MINT,'prop.camera')
rounded_box('Camera flash',(1.31,-.18,1.30),(.07,.035,.05),.015,WHITE,'prop.camera')
rounded_box('Reading tablet silver case',(-1.14,-.10,1.18),(.58,.07,.70),.065,IVORY,'prop.tablet')
rounded_box('Reading tablet screen',(-1.14,-.143,1.18),(.49,.018,.60),.045,PURPLE_DARK,'prop.tablet')
for i in range(6):rounded_box('Tablet text '+str(i),(-1.17,-.16,1.39-i*.075),(.30 if i%3 else .20,.01,.016),.007,TEAL,'prop.tablet')
# A visible scan reticle and code glyphs, rendered as emissive solid geometry.
for s in (-1,1):
    for v in (-1,1):curve('Scanner reticle',[(s*.32,-1.05,2.0+v*.18),(s*.32,-1.05,2.0+v*.28),(s*.22,-1.05,2.0+v*.28)],.012,TEAL,'prop.scan')
curve('Scan sweep',[(-.30,-1.06,2.0),(.30,-1.06,2.0)],.009,GREEN,'prop.scanline')
curve('Code left bracket',[(-.12,-1.06,2.08),(-.21,-1.06,2),(-.12,-1.06,1.92)],.012,WHITE,'prop.scan')
curve('Code right bracket',[(.12,-1.06,2.08),(.21,-1.06,2),(.12,-1.06,1.92)],.012,WHITE,'prop.scan')
curve('Code slash',[(-.04,-1.06,1.90),(.04,-1.06,2.1)],.012,TEAL,'prop.scan')
