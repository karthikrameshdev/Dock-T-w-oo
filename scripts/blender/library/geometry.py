"""Editable, smooth companion sculptures and anatomy-specific skeletons."""
import math
import bpy
from mathutils import Vector
from .roster import SKINS,HAIR


def mat(name,color,metal=.12,rough=.3,glow=0):
    def lin(v):return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
    rgb=tuple(lin(int(color[i:i+2],16)/255) for i in (1,3,5))
    m=bpy.data.materials.new(name);m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*rgb,1)
    p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough;p.inputs['Coat Weight'].default_value=.4
    if glow:p.inputs['Emission Color'].default_value=(*rgb,1);p.inputs['Emission Strength'].default_value=glow
    m.diffuse_color=(*rgb,1)
    if name.startswith('Enamel ·'):
        m['gradient_rgb']=rgb
        v=m.node_tree.nodes.new('ShaderNodeVertexColor');v.layer_name='CompanionTint'
        m.node_tree.links.new(v.outputs['Color'],p.inputs['Base Color'])
    return m


class Sculpture:
    def __init__(self,desc,rig=None):
        self.d=desc;self.objects=[];self.bindings={};self.rig=rig
        self.main=mat('Enamel · '+desc['name'],desc['main'],.18)
        self.secondary=mat('Companion trim',desc['secondary'],.12)
        self.accent=mat('Antenna and status light',desc['accent'],.18,.22,1.2)
        self.dark=mat('Graphite joints','#25343F',.55)
        self.silver=mat('Pearl ceramic','#E5EEF0',.35,.24)
        self.black=mat('Pupils and nose','#14242B',.05)
        self.white=mat('Eye white','#EFF8F5',.02)
        self.pink=mat('Tongue and inner ears','#DE8EAA',.02,.42)
        self.brown=mat('Warm iris','#568B83',.1)
    def finish(self,o,name,m,bone):
        o.name=name;o.data.materials.append(m)
        for p in o.data.polygons:p.use_smooth=True
        self.objects.append(o);self.bindings[o.name]=bone;return o
    def sphere(self,name,c,s,m,bone='head',seg=28):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=seg,ring_count=18,location=c)
        o=bpy.context.object;o.scale=s;return self.finish(o,name,m,bone)
    def box(self,name,c,s,m,bone='torso',radius=.08):
        bpy.ops.mesh.primitive_cube_add(size=1,location=c);o=bpy.context.object;o.dimensions=s
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        b=o.modifiers.new('Rounded edges','BEVEL');b.width=radius;b.segments=4
        o.modifiers.new('Weighted surface normals','WEIGHTED_NORMAL')
        return self.finish(o,name,m,bone)
    def rod(self,name,a,b,r,m,bone='head',end=None):
        v=Vector(b)-Vector(a)
        bpy.ops.mesh.primitive_cone_add(vertices=24,radius1=r,radius2=r if end is None else end,depth=v.length,location=(Vector(a)+Vector(b))/2)
        o=bpy.context.object;o.rotation_euler=v.to_track_quat('Z','Y').to_euler()
        mod=o.modifiers.new('Soft ends','BEVEL');mod.width=min(.025,r*.25);mod.segments=4
        return self.finish(o,name,m,bone)
    def capsule(self,name,a,b,r,m,bone):
        v=Vector(b)-Vector(a)
        o=self.sphere(name,(Vector(a)+Vector(b))*.5,(r,r,v.length*.5+r*.45),m,bone)
        o.rotation_euler=v.to_track_quat('Z','Y').to_euler()
        return o
    def ring(self,name,c,r,thick,m,bone='head',rot=(math.pi/2,0,0)):
        bpy.ops.mesh.primitive_torus_add(major_segments=36,minor_segments=10,major_radius=r,minor_radius=thick,location=c,rotation=rot)
        return self.finish(bpy.context.object,name,m,bone)
    def curve(self,name,points,r,m,bone='head'):
        bpy.ops.object.select_all(action='DESELECT')
        data=bpy.data.curves.new(name,'CURVE');data.dimensions='3D';data.bevel_depth=r;data.bevel_resolution=2
        sp=data.splines.new('BEZIER');sp.bezier_points.add(len(points)-1)
        for h,p in zip(sp.bezier_points,points):h.co=p;h.handle_left_type=h.handle_right_type='AUTO'
        o=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(o);o.select_set(True);bpy.context.view_layer.objects.active=o
        bpy.ops.object.convert(target='MESH');return self.finish(o,name,m,bone)
    def bind(self):
        for o in self.objects:
            bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
            for mod in list(o.modifiers):bpy.ops.object.modifier_apply(modifier=mod.name)
            if not o.data.shape_keys:bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
            material=o.data.materials[0]
            if 'gradient_rgb' in material:
                colors=o.data.color_attributes.new(name='CompanionTint',type='FLOAT_COLOR',domain='POINT')
                base=Vector(material['gradient_rgb']);low=min(v.co.z for v in o.data.vertices);high=max(v.co.z for v in o.data.vertices)
                for v,c in zip(o.data.vertices,colors.data):
                    t=(v.co.z-low)/max(.001,high-low)
                    rgb=base.lerp(Vector((.75,.86,.93)),.11*t)*(.72+.28*t)
                    c.color=(*rgb,1)
                o.data.color_attributes.active_color=colors
            vg=o.vertex_groups.new(name=self.bindings[o.name]);vg.add(list(range(len(o.data.vertices))),1,'REPLACE')
            mod=o.modifiers.new('Character skeleton','ARMATURE');mod.object=self.rig;o.parent=self.rig
        for o in self.objects:
            if o.data.shape_keys:
                for key in list(o.data.shape_keys.key_blocks)[1:]:
                    key.value=0;driver=key.driver_add('value').driver
                    var=driver.variables.new();var.name='v';var.type='SINGLE_PROP';var.targets[0].id=self.rig
                    axis=1 if key.name in ('mouth_open','tongue_curl') else 0
                    var.targets[0].data_path=f'pose.bones["speech"].scale[{axis}]';driver.expression=('0.3*max(0,min(1,v-1))' if key.name=='tongue_curl' else 'max(0,min(1,v-1))')
    def face(self,center,width=.27,eye_z=.14,eye_y=-.45,kind='animal'):
        x,y,z=center
        for sign,side in ((1,'L'),(-1,'R')):
            ex=x+sign*width;ey=y+eye_y;ez=z+eye_z
            self.sphere('Eye white.'+side,(ex,ey,ez),(.165,.058,.21),self.white,'eye.'+side)
            iris=self.sphere('Iris.'+side,(ex,ey-.052,ez),(.105,.028,.145),self.brown,'pupil.'+side)
            self.sphere('Pupil.'+side,(ex,ey-.076,ez),(.057,.02,.095),self.black,'pupil.'+side)
            self.sphere('Eye sparkle.'+side,(ex-.031,ey-.095,ez+.061),(.028,.012,.035),self.white,'pupil.'+side,18)
            self.curve('Eyebrow.'+side,[(ex-.10,ey+.01,ez+.29),(ex,ey-.01,ez+.32),(ex+.10,ey+.01,ez+.29)],.018,self.dark,'brow.'+side)
    def mouth(self,c,width=.20):
        """Four actual morph surfaces, including a tongue; compatible with live speech."""
        cx,cy,cz=c
        for name,material,rim in [('Speaking smile',self.dark,True),('Mouth cavity',self.black,False)]:
            verts=[];opened=[];faces=[]
            for ring in range(2 if rim else 8):
                scale=(1 if ring==0 else .84) if rim else ring/7
                for i in range(48):
                    a=i*math.tau/48
                    x=width*math.cos(a)*scale
                    z=-.055*math.sin(a)**2+.014*math.sin(a)
                    verts.append((cx+x,cy-(.015 if rim else 0),cz+z*scale))
                    oz=(.06 if math.sin(a)>0 else .14)*math.sin(a)
                    opened.append((cx+x,cy-(.015 if rim else 0),cz+oz*scale))
            for r in range((2 if rim else 8)-1):
                for i in range(48):a=r*48+i;b=r*48+(i+1)%48;faces.append((a,b,b+48,a+48))
            mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
            obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj);self.finish(obj,name,material,'head')
            obj.shape_key_add(name='Basis');k=obj.shape_key_add(name='mouth_open')
            for v,p in zip(k.data,opened):v.co=p
            k=obj.shape_key_add(name='mouth_round')
            for v,p in zip(k.data,verts):v.co.x=cx+(p[0]-cx)*.7
        for name,loc,size,material in [('Tongue',(cx,cy-.025,cz-.08),(width*.45,.023,.035),self.pink),('Upper teeth',(cx,cy-.025,cz+.025),(width*.4,.018,.018),self.white)]:
            o=self.sphere(name,loc,size,material,'head',20)
            bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o;bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
            o.shape_key_add(name='Basis');o.shape_key_add(name='mouth_open')
            for v in o.data.shape_keys.key_blocks['Basis'].data:v.co=(cx+(v.co.x-cx)*.001,cy+.04,cz)
    def beak(self,kind):
        """Two solid hinged bill halves plus a fitted oral cavity and tongue.

        All four use the speech controller in Blender and mouth_open in glTF,
        so live audio opens the actual bill even over a non-talking body clip.
        """
        from mathutils import Quaternion
        hinge=Vector((0,-.57,2.14))
        beak_material=mat('Golden beak','#E8B660' if kind=='owl' else '#F2BF52' if kind=='parrot' else '#D89157',.08,.28)
        length=.39 if kind=='owl' else .47 if kind=='parrot' else .43
        def rotate(point,angle):return hinge+Quaternion((1,0,0),angle) @ (Vector(point)-hinge)
        def opening(o,angle):
            bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
            bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
            basis=o.shape_key_add(name='Basis');key=o.shape_key_add(name='mouth_open')
            for v,b in zip(key.data,basis.data):v.co=rotate(b.co,angle)
            return key
        for upper,label,angle in [(True,'Upper beak',-.14),(False,'Lower beak',.58)]:
            verts=[];faces=[];samples=16
            # A rounded wedge with a flat biting edge, not a spherical nose.
            for j,(fraction,width,height) in enumerate([(0,.13,.08),(.25,.18,.19 if kind=='parrot' else .14),(.65,.125,.105),(1,.012,.012)]):
                y=hinge.y-length*fraction;z=hinge.z+(.006 if upper else -.006)
                for i in range(samples):
                    a=math.pi*i/(samples-1)
                    verts.append((math.cos(a)*width*(1 if upper else .92),y,z+(1 if upper else -.65)*math.sin(a)*height))
            for j in range(3):
                for i in range(samples):
                    a=j*samples+i;b=j*samples+(i+1)%samples
                    faces.append((a,b,b+samples,a+samples))
            faces.extend([tuple(reversed(range(samples))),tuple(range(3*samples,4*samples))])
            mesh=bpy.data.meshes.new(label);mesh.from_pydata(verts,[],faces);mesh.update()
            o=bpy.data.objects.new(label,mesh);bpy.context.scene.collection.objects.link(o);self.finish(o,label,beak_material,'head')
            opening(o,angle);o['beak_part']='upper' if upper else 'lower';o['beak_hinge']=list(hinge)
            o['beak_tip_vertex']=3*samples+samples//2
        # Rounded oral depth, recessed between the moving bill halves.
        # Its edges are occluded by the bill instead of forming a flat mouth bar.
        verts=[(0,-.69,2.14)];opened_verts=[(0,-.69,2.112)]
        for i in range(40):
            a=i*math.tau/40
            verts.append((.137*math.cos(a),-.69,2.14+.004*math.sin(a)))
            opened_verts.append((.137*math.cos(a),-.69,2.112+.060*math.sin(a)))
        faces=[(0,i+1,(i+1)%40+1) for i in range(40)]
        mesh=bpy.data.meshes.new('Beak interior');mesh.from_pydata(verts,[],faces);mesh.update()
        cavity=bpy.data.objects.new('Beak interior',mesh);bpy.context.scene.collection.objects.link(cavity);self.finish(cavity,'Beak interior',self.black,'head')
        cavity.shape_key_add(name='Basis');key=cavity.shape_key_add(name='mouth_open')
        for v,point in zip(key.data,opened_verts):v.co=point
        tongue_material=mat('Bird tongue','#D66A85',.02,.38)
        tongue=self.sphere('Tongue',(0,-.78,2.115),(.085,.125,.022),tongue_material,'head',24)
        opened=opening(tongue,.58)
        curl=tongue.shape_key_add(name='tongue_curl')
        for v,b in zip(curl.data,tongue.data.shape_keys.key_blocks['Basis'].data):
            v.co=b.co;v.co.z+=.025*max(0,min(1,(-b.co.y-.75)/.14))

    def antenna(self,mount):
        """One unique silhouette per character; a single named emissive status tip."""
        x,y,z=mount;i=self.d['index'];kind=i%6
        self.sphere('Antenna socket',(x,y,z),(.105,.10,.065),self.silver,'head')
        tip=Vector((x+(.13+.025*(i%5))*(-1 if i%2 else 1),y+.03*(i%3),z+.42+.035*(i%4)))
        self.curve('Antenna stem',[(x,y,z),(x,y,z+.15),(tip.x*.75+x*.25,tip.y,z+.32),tip],.022,self.dark,'antenna')
        if kind==0:self.ring('Antenna orbit',tip,.14,.018,self.accent,'antenna',(0,.3,0))
        elif kind==1:
            for s in (-1,1):self.rod('Antenna fork',(tip.x,tip.y,tip.z-.12),(tip.x+s*.10,tip.y,tip.z+.02),.013,self.silver,'antenna')
        elif kind==2:
            for j in range(7):self.ring('Antenna spring '+str(j),(x+(tip.x-x)*j/8,y,z+.06+j*.037),.038,.009,self.silver,'antenna',(0,.3,0))
        elif kind==3:self.sphere('Antenna leaf',tip+Vector((.07,0,-.035)),(.10,.035,.17),self.main,'antenna')
        elif kind==4:
            self.rod('Antenna diamond',tip-Vector((0,0,.1)),tip,.08,self.accent,'antenna',0)
        elif kind==5:
            self.ring('Antenna halo',tip,.13,.018,self.silver,'antenna')
            self.sphere('Antenna satellite',tip+Vector((.13,0,0)),(.034,)*3,self.accent,'antenna',16)
        self.sphere('Antenna bulb',tip,(.075,.075,.082),self.accent,'antenna',24)
        return tip


def skeleton(desc):
    fam=desc['family'];bird=fam=='bird'
    a=bpy.data.armatures.new(desc['name']+' articulated skeleton');rig=bpy.data.objects.new('Brain_Rig',a);bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
    def bone(n,h,t,parent=None):
        b=a.edit_bones.new(n);b.head=h;b.tail=t
        if parent:b.parent=a.edit_bones[parent]
    bone('root',(0,0,0),(0,0,.25));bone('torso',(0,0,1.05),(0,0,1.75),'root')
    hc=(0,-.08,2.35) if bird else (0,-.86,2.2)
    bone('head',(0,-.15 if bird else -.60,1.75),(0,-.15 if bird else -.60,2.55),'torso')
    for side,sgn in [('L',1),('R',-1)]:
        arm=[(sgn*.53,.05,1.85),(sgn*1.02,.10,1.50),(sgn*1.20,.10,.85)] if bird else [(sgn*.43,-.5,1.20),(sgn*.43,-.53,.64),(sgn*.43,-.68,.24)]
        leg=[(sgn*.28,.12,.8),(sgn*.28,.03,.38),(sgn*.28,-.1,.16)] if bird else [(sgn*.44,.65,1.20),(sgn*.44,.78,.66),(sgn*.44,.78,.24)]
        for n,h,t,par in [('upper_arm',arm[0],arm[1],'torso'),('forearm',arm[1],arm[2],'upper_arm.'+side),('hand',arm[2],(arm[2][0],arm[2][1]-.18,arm[2][2]-.06),'forearm.'+side),('thigh',leg[0],leg[1],'root'),('shin',leg[1],leg[2],'thigh.'+side),('foot',leg[2],(leg[2][0],leg[2][1]-.24,.1),'shin.'+side)]:bone(n+'.'+side,h,t,par)
        ey=(sgn*.27,hc[1]-.47,hc[2]+.14)
        bone('eye.'+side,ey,(ey[0],ey[1],ey[2]+.10),'head');bone('pupil.'+side,(ey[0],ey[1]-.07,ey[2]),(ey[0],ey[1]-.07,ey[2]+.06),'eye.'+side)
        bone('brow.'+side,(ey[0],ey[1],ey[2]+.31),(ey[0],ey[1],ey[2]+.4),'head')
        bone('ear.'+side,(sgn*.48,hc[1],hc[2]+.38),(sgn*.58,hc[1],hc[2]+.75),'head')
    tail=[(0,.8,1.35),(0,1.25,1.55),(0,1.65,1.85),(0,1.95,2.1)] if not bird else [(0,.42,1.1),(0,.75,.85),(0,1,.75),(0,1.2,.8)]
    for i,n in enumerate(['tail','tail.mid','tail.tip']):bone(n,tail[i],tail[i+1],'torso' if i==0 else ['tail','tail.mid'][i-1])
    bone('speech',(0,0,2.2),(0,0,2.3),'head')
    mount=(0,hc[1]+.1,hc[2]+.68)
    if desc['species']=='rabbit':mount=(0,hc[1]+.05,hc[2]+.76)
    bone('antenna',mount,(mount[0]+.1,mount[1],mount[2]+.5),'head')
    bone('trunk',(0,-1.42,2.1),(0,-1.65,1.6),'head');bone('trunk.tip',(0,-1.65,1.6),(0,-1.78,1.15),'trunk')
    for name,loc,parent in [('prop.magnifier',(.43,-.7,.2),'hand.L'),('prop.camera',(.43,-.7,.2),'hand.L'),('prop.tablet',(-.43,-.7,.2),'hand.R'),('prop.scan',(0,-1.4,1.25),'torso')]:bone(name,loc,(loc[0],loc[1],loc[2]+.1),parent)
    grip=a.edit_bones['hand.L'].head.copy()
    for name,loc,parent in [('prop.hammer',grip,'hand.L'),('prop.balloon',grip,'hand.L'),('prop.ball',(.43,-1.10,.22),'root'),('prop.anvil',(0,-1.65,.42),'root'),('prop.parachute',(0,0,2.7),'root')]:
        bone(name,loc,(loc[0],loc[1],loc[2]+.1),parent)
    bpy.ops.object.mode_set(mode='OBJECT');rig.show_in_front=True
    return rig,hc,mount,tail


def animal(desc):
    rig,hc,mount,tail=skeleton(desc);s=Sculpture(desc,rig);sp=desc['species']
    bird=desc['family']=='bird'
    if bird:return avian(s,hc,mount,tail)
    body=(.63,.92,.61)
    if sp in ('corgi','rabbit'):body=(.65,.85,.58)
    if sp in ('rat','mouse'):body=(.58,.83,.58)
    if sp=='elephant':body=(.72,.95,.68)
    s.sphere('Rounded torso',(0,.18,1.28),body,s.main,'torso',36)
    s.sphere('Soft belly plate',(0,-.22,1.12),(.48,.68,.39),s.secondary,'torso',32)
    s.sphere('Companion head',hc,(.69,.56,.65),s.main,'head',40)
    # Muzzle and readable species markings.
    if sp in ('tuxedo','calico','siamese','fox','red_panda','panda'):
        for sign in (-1,1):s.sphere('Cream cheek',(sign*.30,-1.24,2.01),(.28,.18,.23),s.secondary if sp!='panda' else s.white)
    elif sp!='elephant':s.sphere('Muzzle',(0,-1.31,2.03),(.39,.24,.25),s.secondary)
    s.face(hc,eye_y=-.49)
    s.mouth((0,-1.56,1.91),.19)
    if sp!='elephant':s.sphere('Nose',(0,-1.555,2.12),(.115,.071,.075),s.pink if sp in ('rat','mouse','calico','siamese','rabbit') else s.black)
    pointed=sp in ('corgi','husky','tuxedo','calico','siamese','tiger','fox','red_panda')
    floppy=sp=='beagle'
    for sign,side in [(1,'L'),(-1,'R')]:
        if pointed:
            o=s.rod('Pointed ear.'+side,(sign*.50,-.81,2.53),(sign*.60,-.81,3.15),.23,s.main,'ear.'+side,.025)
            o=s.sphere('Inner ear.'+side,(sign*.56,-.982,2.84),(.105,.025,.21),s.pink,'ear.'+side);o.rotation_euler.y=sign*.17
        elif sp=='rabbit':
            o=s.sphere('Long ear.'+side,(sign*.37,-.82,3.03),(.18,.16,.65),s.main,'ear.'+side,32);o.rotation_euler.y=sign*.16
            o=s.sphere('Long inner ear.'+side,(sign*.37,-.968,3.03),(.10,.025,.49),s.pink,'ear.'+side);o.rotation_euler.y=sign*.16
        elif sp=='elephant':
            s.sphere('Large ear.'+side,(sign*.77,-.76,2.21),(.46,.15,.56),s.main,'ear.'+side,36)
            s.sphere('Inner ear.'+side,(sign*.80,-.90,2.22),(.30,.025,.40),s.secondary,'ear.'+side)
        elif floppy:
            o=s.sphere('Floppy ear.'+side,(sign*.66,-.77,2.27),(.23,.18,.49),s.main,'ear.'+side);o.rotation_euler.y=sign*.15
        else:
            r=.31 if sp=='mouse' else .26 if sp=='rat' else .22
            s.sphere('Round ear.'+side,(sign*.55,-.77,2.68),(r,.14,r),s.secondary if sp=='panda' else s.main,'ear.'+side)
            s.sphere('Round inner ear.'+side,(sign*.55,-.90,2.68),(r*.66,.025,r*.66),s.pink,'ear.'+side)
        for front in (True,False):
            upper='upper_arm.'+side if front else 'thigh.'+side;lower='forearm.'+side if front else 'shin.'+side;foot='hand.'+side if front else 'foot.'+side
            b=rig.data.bones[upper];c=rig.data.bones[lower]
            s.capsule(('Front' if front else 'Rear')+' upper leg.'+side,b.head_local,b.tail_local,.23,s.main,upper)
            s.sphere('Leg joint',b.tail_local,(.17,)*3,s.secondary,lower)
            s.capsule('Lower leg',c.head_local,c.tail_local,.19,s.main,lower)
            p=c.tail_local
            s.sphere('Paw',(p.x,p.y-.11,.18),(.23,.30,.17),s.secondary,foot)
            for toe in (-1,0,1):s.curve('Toe seam',[(p.x+toe*.075,p.y-.35,.20),(p.x+toe*.075,p.y-.29,.25)],.008,s.main,foot)
    # Characteristic masks, spots and stripes are geometry, not flat sprites.
    if sp in ('husky','panda','siamese','beagle'):
        for sign in (-1,1):s.sphere('Eye mask',(sign*.29,-1.31,2.38),(.25,.035,.28),s.secondary,'head',28)
        # Bring the existing eye layers ahead of the fitted mask.
        for o in s.objects:
            if o.name.startswith(('Eye white','Iris','Pupil','Eye sparkle')):o.location.y-=.075
    if sp in ('tiger','calico','beagle','fox','red_panda'):
        for sign in (-1,1):
            if sp=='tiger':
                for j in range(5):
                    yy=-.35+j*.28;s.curve('Tiger flank stripe',[(sign*.59,yy,1.12),(sign*.63,yy+.05,1.43),(sign*.48,yy+.12,1.70)],.035,s.secondary,'torso')
                for j in range(3):s.curve('Tiger forehead stripe',[(sign*(.12+j*.13),-1.18,2.70),(sign*(.12+j*.12),-1.27,2.55)],.023,s.secondary)
            elif sp=='calico':s.sphere('Calico patch',(sign*.56,.15+sign*.3,1.53),(.10,.38,.27),s.secondary,'torso')
            elif sp=='beagle':s.sphere('Beagle saddle',(sign*.48,.42,1.56),(.16,.55,.32),s.dark,'torso')
            elif sp=='red_panda':s.curve('Red panda cheek blaze',[(sign*.40,-1.31,2.27),(sign*.53,-1.18,2.14)],.065,s.white)
    if sp=='lion':
        for j in range(18):
            a=j*math.tau/18;c=(math.sin(a)*.65,-.70,2.20+math.cos(a)*.65)
            o=s.sphere('Sculpted mane lock '+str(j),c,(.24,.30,.29),s.secondary);o.rotation_euler.y=-a
    if sp=='elephant':
        s.curve('Trunk upper',[(0,-1.34,2.13),(0,-1.60,1.92),(0,-1.65,1.60)],.16,s.main,'trunk')
        s.curve('Trunk tip',[(0,-1.65,1.60),(0,-1.78,1.28),(0,-1.91,1.23)],.12,s.main,'trunk.tip')
        for sign in (-1,1):s.curve('Ivory tusk',[(sign*.25,-1.33,1.98),(sign*.30,-1.52,1.78),(sign*.31,-1.68,1.91)],.055,s.white)
    if sp in ('rat','mouse','tuxedo','calico','siamese','fox','rabbit'):
        for sign in (-1,1):
            for j in range(3):s.curve('Whisker',[(sign*.17,-1.54,2.0),(sign*.45,-1.53,1.98+(j-1)*.07),(sign*.63,-1.46,1.98+(j-1)*.12)],.006,s.silver)
    if sp=='rabbit':s.sphere('Pom tail',(0,1.04,1.35),(.27,)*3,s.white,'tail')
    else:
        radius=.045 if sp in ('rat','mouse') else .20 if sp in ('fox','red_panda') else .08
        for j,b in enumerate(['tail','tail.mid','tail.tip']):
            s.rod('Tail section '+str(j),tail[j],tail[j+1],radius*(1-j*.16),s.pink if sp in ('rat','mouse') else s.white if sp=='fox' and j==2 else s.main,b,radius*(.82-j*.16))
            if sp=='red_panda':
                v=(Vector(tail[j+1])-Vector(tail[j]));c=Vector(tail[j])+v*.5
                s.rod('Tail ring '+str(j),c-v*.13,c+v*.13,radius*(1-j*.16)+.007,s.secondary,b)
        if sp=='lion':s.sphere('Tail tuft',tail[-1],(.14,.14,.2),s.secondary,'tail.tip')
    # A tiny collar/status medallion unifies the animal and robot collections.
    s.ring('Companion collar',(0,-.63,1.78),.35,.04,s.accent,'torso',(math.pi/2,0,0))
    s.sphere('Chest medallion',(0,-.97,1.64),(.10,.025,.10),s.silver,'torso')
    s.antenna(mount);tools(s);s.bind()
    if sp in ('corgi','rabbit','rat','mouse'):
        # Shorter lower limbs and a low body give these species their own silhouette.
        factor=.64 if sp=='corgi' else .82 if sp=='rabbit' else .88
        def zmap(z):return z*factor if z<1.2 else z-1.2*(1-factor)
        for o in s.objects:
            for v in o.data.vertices:v.co.z=zmap(v.co.z)
            if o.data.shape_keys:
                for key in o.data.shape_keys.key_blocks:
                    for v in key.data:v.co.z=zmap(v.co.z)
        bpy.context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='EDIT')
        for b in rig.data.edit_bones:b.head.z=zmap(b.head.z);b.tail.z=zmap(b.tail.z)
        bpy.ops.object.mode_set(mode='OBJECT')
    return s


def avian(s,hc,mount,tail):
    sp=s.d['species'];rig=s.rig
    s.sphere('Bird body',(0,.08,1.30),(.66,.51,.80),s.main,'torso',36)
    s.sphere('Bird breast',(0,-.36,1.32),(.48,.18,.60),s.secondary,'torso',32)
    s.sphere('Bird head',hc,(.70,.56,.67),s.main,'head',40)
    if sp=='owl':
        for sign in (-1,1):s.sphere('Owl facial disc',(sign*.27,-.56,2.43),(.36,.09,.42),s.secondary)
        for sign,side in [(1,'L'),(-1,'R')]:s.rod('Owl ear crown.'+side,(sign*.48,-.04,2.78),(sign*.61,-.04,3.12),.15,s.main,'ear.'+side,.015)
    elif sp=='parrot':
        for j in range(3):s.sphere('Crest feather '+str(j),((j-1)*.11,.05,3.0+j*.025),(.10,.12,.30),s.secondary)
    s.face(hc,eye_y=-.52)
    s.beak(sp)
    for sign,side in [(1,'L'),(-1,'R')]:
        for b in ('upper_arm.','forearm.'):
            bone=rig.data.bones[b+side]
            s.capsule('Wing leading edge.'+side,bone.head_local,bone.tail_local,.17,s.main,b+side)
        for j in range(6):
            c=(sign*(.64+j*.09),.08,1.42-j*.075)
            o=s.sphere('Primary feather.'+side+'.'+str(j),c,(.13,.12,.46-j*.025),s.secondary if j%3==0 else s.main,'forearm.'+side)
            o.rotation_euler.y=sign*(.12+j*.035)
        for b in ('thigh.','shin.'):
            bone=rig.data.bones[b+side];s.rod('Bird leg',bone.head_local,bone.tail_local,.075,s.dark,b+side)
        foot=rig.data.bones['foot.'+side].head_local
        s.sphere('Bird foot',foot,(.12,.16,.07),s.secondary,'foot.'+side)
        for toe in (-1,0,1):s.curve('Talon',[(foot.x,foot.y,.14),(foot.x+toe*.09,foot.y-.22,.11),(foot.x+toe*.10,foot.y-.29,.12)],.027,s.secondary,'foot.'+side)
    for j in range(5):
        o=s.sphere('Tail feather '+str(j),((j-2)*.14,.66,.86),(.12,.44,.12),s.secondary if j%2 else s.main,'tail');o.rotation_euler.z=(j-2)*.12
    s.antenna(mount);tools(s);s.bind();return s


def tools(s):
    # Compact solid props attach to a forepaw / wing grip in the character rig.
    s.rod('Magnifier handle',(.43,-.7,.23),(.43,-.7,.62),.03,s.dark,'prop.magnifier')
    s.ring('Magnifier rim',(.43,-.7,.80),.18,.025,s.silver,'prop.magnifier')
    s.curve('Magnifier reflection',[(.33,-.71,.82),(.35,-.71,.91),(.42,-.71,.94)],.008,s.accent,'prop.magnifier')
    s.box('Camera body',(.43,-.73,.22),(.35,.18,.24),s.dark,'prop.camera',.04)
    s.rod('Camera lens',(.43,-.83,.23),(.43,-.91,.23),.08,s.silver,'prop.camera')
    s.sphere('Camera lens glass',(.43,-.92,.23),(.06,.01,.06),s.accent,'prop.camera')
    s.box('Tablet case',(-.43,-.73,.30),(.38,.06,.44),s.silver,'prop.tablet',.04)
    s.box('Tablet screen',(-.43,-.77,.30),(.32,.015,.37),s.dark,'prop.tablet',.025)
    for j in range(4):s.box('Tablet line',(-.43,-.784,.42-j*.07),(.22,.007,.012),s.accent,'prop.tablet',.004)
    for sign in (-1,1):s.curve('Scan bracket',[(sign*.18,-1.43,1.42),(sign*.25,-1.43,1.32),(sign*.18,-1.43,1.22)],.012,s.accent,'prop.scan')

    # The shared desktop toy actions have real bound objects on animal rigs too.
    grip=s.rig.data.bones['hand.L'].head_local.copy()
    s.rod('Toy hammer handle',grip,grip+Vector((0,0,.40)),.028,s.secondary,'prop.hammer')
    s.box('Toy hammer head',grip+Vector((0,0,.43)),(.36,.16,.15),s.silver,'prop.hammer',.04)
    s.box('Toy anvil base',(0,-1.65,.16),(.55,.37,.17),s.dark,'prop.anvil',.05)
    s.box('Toy anvil pad',(0,-1.65,.38),(.48,.30,.14),s.silver,'prop.anvil',.04)
    s.sphere('Toy ball',(.43,-1.10,.22),(.21,)*3,s.accent,'prop.ball')
    s.ring('Toy ball band',(.43,-1.10,.22),.208,.014,s.white,'prop.ball')
    top=grip+Vector((0,0,2.7))
    s.curve('Balloon tether',[grip,grip+Vector((.10,.02,1.4)),top],.008,s.silver,'prop.balloon')
    s.sphere('Balloon envelope',top+Vector((0,0,.32)),(.31,.27,.40),s.main,'prop.balloon')
    s.sphere('Balloon shine',top+Vector((-.1,-.25,.43)),(.035,.012,.10),s.white,'prop.balloon')
    s.sphere('Parachute canopy',(0,0,3.85),(1.15,.82,.25),s.main,'prop.parachute',36)
    for sign in (-1,1):
        for back in (-1,1):s.curve('Parachute suspension',[(sign*.29,back*.12,1.8),(sign*.66,back*.38,2.8),(sign*1.0,back*.5,3.78)],.012,s.silver,'prop.parachute')
    s.ring('Flight harness',(0,0,1.8),.34,.035,s.secondary,'prop.parachute',(0,0,0))


def human(desc,rig):
    s=Sculpture(desc,rig);skin=mat('Skin',SKINS[desc['species']],.02,.45);hair=mat('Hair',HAIR[desc['species']],.03,.36)
    sp=desc['species']
    s.sphere('Human face',(0,-.02,3.66),(.89,.68,.91),skin,'head',48)
    s.sphere('Nose',(0,-.702,3.57),(.10,.10,.14),skin)
    for sign,side in [(1,'L'),(-1,'R')]:s.sphere('Human ear.'+side,(sign*.87,0,3.66),(.12,.13,.22),skin)
    s.face((0,-.18,3.69),width=.38,eye_y=-.50)
    s.mouth((0,-.745,3.33),.23)
    # Hair is a fitted cap plus silhouette locks, leaving the face readable.
    s.sphere('Hair cap',(0,.08,4.02),(.90,.67,.61),hair)
    for j in range(7):
        x=(j-3)*.22;z=4.22+.08*math.sin(j*.8)
        o=s.sphere('Fringe lock '+str(j),(x,-.54,z),(.19,.14,.24),hair);o.rotation_euler.y=(j-3)*.10
    if sp=='scientist':
        for sign in (-1,1):s.sphere('Hair bun',(sign*.65,.37,4.28),(.25,)*3,hair)
        for sign in (-1,1):s.ring('Glasses',(sign*.38,-.79,3.83),.21,.018,s.dark)
        s.rod('Glasses bridge',(-.16,-.79,3.83),(.16,-.79,3.83),.012,s.dark)
    elif sp=='musician':
        for j in range(11):
            a=j*math.tau/11;s.sphere('Curl '+str(j),(.69*math.sin(a),.22+.42*math.cos(a),4.10+.10*math.cos(a)),(.27,.25,.27),hair)
        for sign in (-1,1):s.sphere('Headphone cup',(sign*.93,.01,3.72),(.12,.19,.24),s.main)
        s.curve('Headphone band',[(-.91,.02,3.84),(-.72,.03,4.38),(0,.03,4.60),(.72,.03,4.38),(.91,.02,3.84)],.06,s.secondary)
    elif sp in ('explorer','artist'):
        s.sphere('Hat brim',(0,0,4.35),(1.0,.80,.10),s.secondary)
        s.sphere('Hat crown',(0,.05,4.51),(.67,.55,.25 if sp=='explorer' else .14),s.main)
    elif sp=='chef':
        s.rod('Chef hat band',(0,.03,4.30),(0,.03,4.63),.58,s.white)
        for x,y,z in [(-.35,.03,4.72),(0,-.1,4.80),(.35,.03,4.72),(0,.3,4.75)]:s.sphere('Chef hat puff',(x,y,z),(.34,.34,.30),s.white)
    elif sp=='astronaut':
        s.ring('Helmet collar',(0,0,2.87),.36,.08,s.silver,'torso',(0,0,0))
        for sign in (-1,1):s.sphere('Comms ear pad',(sign*.93,.05,3.6),(.12,.21,.24),s.secondary)
    s.sphere('Shirt torso',(0,0,2.03),(.69,.43,.63),s.main,'torso',36)
    s.capsule('Neck',(0,0,2.48),(0,0,2.96),.19,skin,'head')
    s.ring('Shirt collar',(0,0,2.55),.23,.055,s.secondary,'torso',(0,0,0))
    for side in ('L','R'):
        b=rig.data.bones['upper_arm.'+side]
        s.sphere('Shoulder.'+side,b.head_local,(.23,.24,.24),s.main,'upper_arm.'+side)
    s.box('Waist belt',(0,-.015,1.53),(.76,.53,.13),s.secondary,'root',.06)
    s.sphere('Trousers pelvis',(0,0,1.39),(.44,.32,.22),s.secondary,'root')
    if sp in ('scientist','chef'):
        for sign in (-1,1):s.box('Coat front',(sign*.23,-.45,1.98),(.37,.08,.80),s.white,'torso',.07)
        for z in (1.76,1.94,2.12,2.3):s.sphere('Coat button',(0,-.52,z),(.024,.013,.024),s.dark,'torso',12)
    elif sp=='artist':
        s.box('Apron bib',(0,-.47,2.1),(.61,.06,.61),s.secondary,'torso',.12)
        for x,z in [(-.13,2.12),(.12,1.98),(.19,2.25)]:s.sphere('Paint spot',(x,-.515,z),(.06,.01,.065),s.accent,'torso',16)
    elif sp=='explorer':
        for sign in (-1,1):s.box('Vest pocket',(sign*.29,-.44,2.10),(.22,.10,.24),s.secondary,'torso',.035)
    elif sp=='astronaut':
        s.box('Suit controls',(0,-.46,2.17),(.43,.10,.30),s.secondary,'torso',.05)
        for x in (-.1,0,.1):s.sphere('Suit indicator',(x,-.53,2.2),(.025,.012,.025),s.accent,'torso',12)
    elif sp=='musician':
        for sign in (-1,1):s.curve('Jacket piping',[(sign*.4,-.31,2.45),(sign*.25,-.40,2.1),(sign*.20,-.34,1.66)],.018,s.accent,'torso')
    for side,sign in [('L',1),('R',-1)]:
        for part,m,r in [('upper_arm',s.main,.18),('forearm',skin,.135),('thigh',s.secondary,.19),('shin',s.secondary,.17)]:
            b=rig.data.bones[part+'.'+side];s.capsule(part+'.'+side,b.head_local,b.tail_local,r*1.2,m,part+'.'+side)
            s.sphere('Joint.'+part+'.'+side,b.tail_local,(r*.9,)*3,m,part+'.'+side)
        s.sphere('Human palm.'+side,(sign*1.14,-.055,1.37),(.17,.12,.17),skin,'hand.'+side)
        for i in range(4):
            for part in (f'digit{i}.',f'digit_tip{i}.'):
                b=rig.data.bones[part+side];s.rod('Human finger',b.head_local,b.tail_local,.034,skin,part+side)
        for part in ('thumb.','thumb_tip.'):
            b=rig.data.bones[part+side];s.rod('Human thumb',b.head_local,b.tail_local,.042,skin,part+side)
        s.sphere('Shoe upper.'+side,(sign*.38,-.19,.24),(.31,.44,.21),s.main,'foot.'+side)
        s.box('Shoe sole.'+side,(sign*.38,-.19,.09),(.64,.86,.12),s.secondary,'foot.'+side,.055)
    mount=(.48,.10,4.50 if sp not in ('chef','explorer','artist') else 4.88 if sp=='chef' else 4.69)
    s.antenna(mount);s.bind();return s


def robot_variant(desc,rig):
    s=Sculpture(desc,rig);sp=desc['species']
    # Preserve the proven mechanical chassis and add a distinct silhouette.
    if sp=='orbital':
        s.ring('Orbital crown',(0,.12,4.48),.60,.045,s.main,'head',(0,.25,0))
        for sign in (-1,1):s.sphere('Orbit shoulder shell',(sign*.84,.07,2.43),(.28,.26,.20),s.main,'upper_arm.'+('L' if sign==1 else 'R'))
    elif sp=='rescue':
        s.box('Rescue visor cap',(0,-.24,4.25),(1.5,.65,.16),s.main,'head',.07)
        for sign in (-1,1):s.box('Rescue backpack',(sign*.30,.51,2.07),(.30,.26,.66),s.secondary,'torso',.10)
        s.box('Rescue chest badge',(0,-.52,2.39),(.12,.035,.29),s.accent,'torso',.02)
    elif sp=='medic':
        s.box('Medical crest',(0,-.49,4.10),(.44,.07,.27),s.white,'head',.06)
        s.box('Medical cross vertical',(0,-.535,4.1),(.065,.02,.19),s.main,'head',.02)
        s.box('Medical cross horizontal',(0,-.54,4.1),(.19,.02,.065),s.main,'head',.02)
        s.curve('Diagnostic cable',[(-.30,-.36,2.44),(-.42,-.49,2.1),(0,-.53,1.91),(.36,-.43,2.2),(.30,-.36,2.44)],.025,s.dark,'torso')
    elif sp=='space':
        for sign,side in [(1,'L'),(-1,'R')]:
            s.box('Space shoulder fin.'+side,(sign*.95,.03,2.48),(.39,.35,.13),s.main,'upper_arm.'+side,.06)
            s.box('Space jet pod.'+side,(sign*.40,.52,2.12),(.31,.35,.71),s.silver,'torso',.13)
        s.box('Navigation crest',(0,-.36,4.25),(.30,.22,.26),s.accent,'head',.07)
    elif sp=='retro':
        s.box('Retro top cap',(0,.04,4.48),(1.65,1.05,.18),s.main,'head',.13)
        for sign in (-1,1):s.box('Retro side grille',(sign*1.31,.03,3.7),(.12,.42,.66),s.secondary,'head',.045)
        for j in range(4):s.box('Retro chest equalizer',(-.18+j*.12,-.505,1.94),(.065,.025,.12+j*.035),s.accent,'torso',.015)
    s.antenna((.52,.08,4.54));s.bind();return s
