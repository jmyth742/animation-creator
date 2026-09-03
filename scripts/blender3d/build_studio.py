"""
Build the VIRTUAL STUDIO: the valley set, the rigged and dressed character,
and his walk performance, saved as one .blend. Open it in Blender to orbit,
place cameras and scrub the take; render any angle with film.py.

Run: blender -b --factory-startup --python build_studio.py -- \
       <mesh.glb> <sheet.png> <out.blend>
"""
import sys
import math
import bpy
import mathutils

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import valley_set                                              # noqa: E402

mesh_path, sheet_path, out_blend = sys.argv[-3:]
FPS, FRAMES = 16, 81

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.render.resolution_x, sc.render.resolution_y = 832, 480
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, FRAMES
sc.render.use_motion_blur = False
sc.eevee.use_shadows = True
sc.view_settings.view_transform = 'Standard'

valley_set.build_set(sc)

cam = bpy.data.cameras.new("cam_master"); cam.lens = 35
camo = bpy.data.objects.new("cam_master", cam)
camo.location = (-0.5, -12, 2.2)
camo.rotation_euler = (math.radians(84), 0, 0)
sc.collection.objects.link(camo); sc.camera = camo

# ── character ────────────────────────────────────────────────────────
bpy.ops.import_scene.gltf(filepath=mesh_path)
parts = [o for o in sc.objects if o.type == 'MESH' and o.name.startswith(
    ("geometry", "mesh", "Mesh", "world", "oisin"))]
if not parts:   # fall back: newest mesh objects with no material from the set
    parts = [o for o in sc.objects if o.type == 'MESH'
             and not o.data.materials]
for o in sc.objects:
    o.select_set(False)
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
if len(parts) > 1:
    bpy.ops.object.join()
char = bpy.context.view_layer.objects.active
char.name = "oisin"

mn = mathutils.Vector((1e9,) * 3); mx = mathutils.Vector((-1e9,) * 3)
for c in char.bound_box:
    w = char.matrix_world @ mathutils.Vector(c)
    mn = mathutils.Vector(map(min, mn, w)); mx = mathutils.Vector(map(max, mx, w))
H = 1.75
s = H / (mx.z - mn.z)
char.scale = (char.scale[0] * s,) * 3
char.location = (-(mn.x + mx.x) / 2 * s, -(mn.y + mx.y) / 2 * s, -mn.z * s)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# projected costume, but LIT: two-tone light mask multiplied over the texture
uv = char.data.uv_layers.new(name="proj")
mn2 = mathutils.Vector((1e9,) * 3); mx2 = mathutils.Vector((-1e9,) * 3)
for v in char.data.vertices:
    mn2 = mathutils.Vector(map(min, mn2, v.co))
    mx2 = mathutils.Vector(map(max, mx2, v.co))
for poly in char.data.polygons:
    for li in poly.loop_indices:
        co = char.data.vertices[char.data.loops[li].vertex_index].co
        u = (co.x - mn2.x) / (mx2.x - mn2.x)
        w = (co.z - mn2.z) / (mx2.z - mn2.z)
        if w > 0.84:
            uv.data[li].uv = (0.50 + u * 0.07, 0.908)   # hair band (probed)
        else:
            uv.data[li].uv = (0.28 + u * 0.44, 0.05 + w * 0.90)
simg = bpy.data.images.load(sheet_path)
cmat = bpy.data.materials.new("charmat"); cmat.use_nodes = True
ct = cmat.node_tree; ct.nodes.clear()
cuv = ct.nodes.new("ShaderNodeUVMap"); cuv.uv_map = "proj"
ctx = ct.nodes.new("ShaderNodeTexImage"); ctx.image = simg
diff = ct.nodes.new("ShaderNodeBsdfDiffuse")
torgb = ct.nodes.new("ShaderNodeShaderToRGB")
ramp = ct.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.interpolation = 'CONSTANT'
ramp.color_ramp.elements[0].color = (0.5, 0.5, 0.55, 1)
ramp.color_ramp.elements[1].position = 0.5
ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
mix = ct.nodes.new("ShaderNodeMixRGB"); mix.blend_type = 'MULTIPLY'
mix.inputs["Fac"].default_value = 1.0
cem = ct.nodes.new("ShaderNodeEmission")
cou = ct.nodes.new("ShaderNodeOutputMaterial")
ct.links.new(cuv.outputs["UV"], ctx.inputs["Vector"])
ct.links.new(diff.outputs["BSDF"], torgb.inputs["Shader"])
ct.links.new(torgb.outputs["Color"], ramp.inputs["Fac"])
ct.links.new(ramp.outputs["Color"], mix.inputs["Color1"])
ct.links.new(ctx.outputs["Color"], mix.inputs["Color2"])
ct.links.new(mix.outputs["Color"], cem.inputs["Color"])
ct.links.new(cem.outputs["Emission"], cou.inputs["Surface"])
char.data.materials.clear()
char.data.materials.append(cmat)

# ── rig + walk (the v2 armature, staged on the real floor) ───────────
arm = bpy.data.armatures.new("rig")
rig = bpy.data.objects.new("rig", arm)
sc.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='EDIT')

def bone(name, head, tail, parent=None):
    b = arm.edit_bones.new(name)
    b.head, b.tail = head, tail
    if parent:
        b.parent = arm.edit_bones[parent]
    return b

bone("hips", (0, 0, 0.95), (0, 0, 1.15))
bone("spine", (0, 0, 1.15), (0, 0, 1.45), "hips")
bone("head", (0, 0, 1.45), (0, 0, 1.75), "spine")
for sgn, side in ((1, "L"), (-1, "R")):
    bone(f"thigh.{side}", (0.10 * sgn, 0, 0.95), (0.11 * sgn, 0, 0.50), "hips")
    bone(f"shin.{side}", (0.11 * sgn, 0, 0.50), (0.12 * sgn, 0, 0.05), f"thigh.{side}")
    bone(f"arm.{side}", (0.20 * sgn, 0, 1.42), (0.26 * sgn, 0, 1.05), "spine")
    bone(f"fore.{side}", (0.26 * sgn, 0, 1.05), (0.30 * sgn, 0, 0.75), f"arm.{side}")
bpy.ops.object.mode_set(mode='OBJECT')
for o in sc.objects:
    o.select_set(False)
char.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type='ARMATURE_AUTO')

def floor_z(x, y):
    r = math.hypot(x, y - 20)
    return 0.35 * math.sin(x * 0.35) * math.cos(y * 0.3) * min(1, r / 8)

STRIDE_HZ = 1.45
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='POSE')
pb = rig.pose.bones
for f in range(1, FRAMES + 1):
    t = (f - 1) / (FRAMES - 1)
    sc.frame_set(f)
    ph = 2 * math.pi * STRIDE_HZ * (f - 1) / FPS
    # follow the path ribbon: same curve build_set laid the quads on
    pt = 0.12 + 0.33 * t
    px = 0.9 - 2.6 * pt + 0.5 * math.sin(pt * 5)
    py = -4 + 22 * pt
    rig.location = (px, py, floor_z(px, py) + 0.02 * abs(math.sin(ph)))
    # face along the direction of travel (away from camera)
    d = 0.01
    px2 = 0.9 - 2.6 * (pt + d) + 0.5 * math.sin((pt + d) * 5)
    heading = math.atan2(-(px2 - px), 22 * d)
    rig.rotation_euler = (0, 0, math.radians(180) + heading)
    rig.keyframe_insert("location"); rig.keyframe_insert("rotation_euler")
    for side, sgn in (("L", 1), ("R", -1)):
        pb[f"thigh.{side}"].rotation_mode = 'XYZ'
        pb[f"thigh.{side}"].rotation_euler = (sgn * 0.45 * math.sin(ph), 0, 0)
        pb[f"thigh.{side}"].keyframe_insert("rotation_euler")
        pb[f"shin.{side}"].rotation_mode = 'XYZ'
        pb[f"shin.{side}"].rotation_euler = (max(0.0, -sgn * 0.9 * math.sin(ph + 0.6)), 0, 0)
        pb[f"shin.{side}"].keyframe_insert("rotation_euler")
        pb[f"arm.{side}"].rotation_mode = 'XYZ'
        pb[f"arm.{side}"].rotation_euler = (-sgn * 0.30 * math.sin(ph), 0, 0)
        pb[f"arm.{side}"].keyframe_insert("rotation_euler")
    pb["spine"].rotation_mode = 'XYZ'
    pb["spine"].rotation_euler = (0.03, 0, 0.05 * math.sin(ph))
    pb["spine"].keyframe_insert("rotation_euler")
bpy.ops.object.mode_set(mode='OBJECT')

bpy.ops.file.pack_all()          # textures travel inside the .blend
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("STUDIO SAVED", out_blend)
