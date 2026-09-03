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
yc = (mn2.y + mx2.y) / 2
for poly in char.data.polygons:
    for li in poly.loop_indices:
        co = char.data.vertices[char.data.loops[li].vertex_index].co
        u = (co.x - mn2.x) / (mx2.x - mn2.x)
        w = (co.z - mn2.z) / (mx2.z - mn2.z)
        if w > 0.84:
            if co.y < yc:
                # front of the head: the sheet's actual face, mapped to the
                # head's narrow span instead of the full body width
                hw = (w - 0.84) / 0.16
                uv.data[li].uv = (0.455 + u * 0.11, 0.845 + hw * 0.085)
            else:
                uv.data[li].uv = (0.50 + u * 0.07, 0.908)   # hair (probed)
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
    bone(f"shin.{side}", (0.11 * sgn, 0, 0.50), (0.12 * sgn, 0, 0.08), f"thigh.{side}")
    bone(f"foot.{side}", (0.12 * sgn, 0, 0.08), (0.12 * sgn, -0.17, 0.02), f"shin.{side}")
    bone(f"arm.{side}", (0.20 * sgn, 0, 1.42), (0.26 * sgn, 0, 1.05), "spine")
    bone(f"fore.{side}", (0.26 * sgn, 0, 1.05), (0.30 * sgn, 0, 0.75), f"arm.{side}")
bpy.ops.object.mode_set(mode='OBJECT')
# Blender's bone-heat weighting fails SILENTLY on marching-cubes meshes
# (it did here: bones swung, mesh never followed). Deterministic skinning
# instead: each vertex weighted to its two nearest bone segments.
import numpy as np

BONES = {
    "hips": ((0, 0, 0.95), (0, 0, 1.15)),
    "spine": ((0, 0, 1.15), (0, 0, 1.45)),
    "head": ((0, 0, 1.45), (0, 0, 1.75)),
}
for sgn, side in ((1, "L"), (-1, "R")):
    BONES[f"thigh.{side}"] = ((0.10 * sgn, 0, 0.95), (0.11 * sgn, 0, 0.50))
    BONES[f"shin.{side}"] = ((0.11 * sgn, 0, 0.50), (0.12 * sgn, 0, 0.08))
    BONES[f"foot.{side}"] = ((0.12 * sgn, 0, 0.08), (0.12 * sgn, -0.17, 0.02))
    BONES[f"arm.{side}"] = ((0.20 * sgn, 0, 1.42), (0.26 * sgn, 0, 1.05))
    BONES[f"fore.{side}"] = ((0.26 * sgn, 0, 1.05), (0.30 * sgn, 0, 0.75))

n = len(char.data.vertices)
co = np.empty(n * 3)
char.data.vertices.foreach_get("co", co)
P = co.reshape(-1, 3)
names = list(BONES)
D = np.empty((n, len(names)))
for bi, nm in enumerate(names):
    a = np.array(BONES[nm][0]); b = np.array(BONES[nm][1])
    ab = b - a
    tt = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
    D[:, bi] = np.linalg.norm(P - (a + tt[:, None] * ab), axis=1)
order = np.argsort(D, axis=1)
near2 = order[:, :2]
d2 = np.take_along_axis(D, near2, axis=1)
w = np.exp(-d2 / 0.05)
w /= w.sum(axis=1, keepdims=True)
# a vertex much closer to one bone belongs to it outright (crisp joints)
crisp = d2[:, 1] - d2[:, 0] > 0.10
w[crisp, 0], w[crisp, 1] = 1.0, 0.0

groups = {nm: char.vertex_groups.new(name=nm) for nm in names}
Q = 64
for k in (0, 1):
    qw = np.round(w[:, k] * Q) / Q
    for bi, nm in enumerate(names):
        sel = near2[:, k] == bi
        for lvl in np.unique(qw[sel]):
            if lvl <= 0:
                continue
            idx = np.where(sel & (qw == lvl))[0]
            groups[nm].add(idx.tolist(), float(lvl), 'ADD')

char.parent = rig
mod = char.modifiers.new("rig", 'ARMATURE')
mod.object = rig

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
    sway = 0.028 * math.sin(ph)
    bob = 0.030 - 0.030 * abs(math.cos(ph))
    rig.location = (px + sway, py, floor_z(px, py) + bob)
    # face along the direction of travel (away from camera)
    d = 0.01
    px2 = 0.9 - 2.6 * (pt + d) + 0.5 * math.sin((pt + d) * 5)
    heading = math.atan2(-(px2 - px), 22 * d)
    rig.rotation_euler = (0, 0, math.radians(180) + heading)
    rig.keyframe_insert("location"); rig.keyframe_insert("rotation_euler")
    for side, sgn in (("L", 1), ("R", -1)):
        sl = math.sin(ph) * sgn              # this leg's swing phase
        # thigh: fuller swing, slight forward bias (walkers lean into it)
        pb[f"thigh.{side}"].rotation_mode = 'XYZ'
        pb[f"thigh.{side}"].rotation_euler = (0.50 * sl + 0.06, 0, 0)
        pb[f"thigh.{side}"].keyframe_insert("rotation_euler")
        # knee: big flex through swing (leg coming forward), near-straight
        # in stance with a soft loading dip at contact
        swing = max(0.0, -math.sin(ph + 0.55) * sgn)
        stance_dip = 0.12 * max(0.0, math.sin(ph - 0.3) * sgn)
        pb[f"shin.{side}"].rotation_mode = 'XYZ'
        pb[f"shin.{side}"].rotation_euler = (0.95 * swing ** 1.3 + stance_dip, 0, 0)
        pb[f"shin.{side}"].keyframe_insert("rotation_euler")
        # foot: toe-off push behind, lift toes through swing
        pb[f"foot.{side}"].rotation_mode = 'XYZ'
        pb[f"foot.{side}"].rotation_euler = (
            -0.35 * max(0.0, math.sin(ph - 2.4) * sgn)
            + 0.25 * swing, 0, 0)
        pb[f"foot.{side}"].keyframe_insert("rotation_euler")
        # arm: counter-swing from the shoulder, elbow always a little bent
        # and bending more as the arm comes forward
        pb[f"arm.{side}"].rotation_mode = 'XYZ'
        pb[f"arm.{side}"].rotation_euler = (-0.38 * sl, 0, sgn * 0.06)
        pb[f"arm.{side}"].keyframe_insert("rotation_euler")
        pb[f"fore.{side}"].rotation_mode = 'XYZ'
        pb[f"fore.{side}"].rotation_euler = (-0.20 - 0.22 * max(0.0, -sl), 0, 0)
        pb[f"fore.{side}"].keyframe_insert("rotation_euler")
    # pelvis rolls with the stride; the torso counters it; the head stays put
    pb["hips"].rotation_mode = 'XYZ'
    pb["hips"].rotation_euler = (0, 0.10 * math.sin(ph), 0.09 * math.sin(ph))
    pb["hips"].keyframe_insert("rotation_euler")
    pb["spine"].rotation_mode = 'XYZ'
    pb["spine"].rotation_euler = (0.06, -0.07 * math.sin(ph), -0.12 * math.sin(ph))
    pb["spine"].keyframe_insert("rotation_euler")
    pb["head"].rotation_mode = 'XYZ'
    pb["head"].rotation_euler = (-0.04, -0.03 * math.sin(ph), 0.04 * math.sin(ph))
    pb["head"].keyframe_insert("rotation_euler")
bpy.ops.object.mode_set(mode='OBJECT')

bpy.ops.file.pack_all()          # textures travel inside the .blend
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("STUDIO SAVED", out_blend)
