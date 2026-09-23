"""
RIGIFY FIT — a real deform skeleton for a character, fitted from its own geometry.

The kit's 14-bone rig is the ceiling on motion quality: no clavicles, no neck, one spine
bone, no wrists, distance-falloff weights. Rigify (bundled with Blender) generates a
full production rig from a metarig: spine chain, clavicles, neck, IK/FK limbs with foot
roll, and it binds with bone heat, which on a clean retopologised quad mesh is a solved
skin rather than a guess. This script fits the basic-human metarig to the character's
measured landmarks, generates, binds, and saves a .blend plus a deform-only glb.

  blender -b --python rigify_fit.py -- <retopo.glb> <out_prefix> [height=1.6]
Writes <out_prefix>.blend (the rig to animate) and <out_prefix>_gate.png.
"""
import sys, os, math
import bpy, mathutils
import numpy as np

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import character_kit as kit                                        # noqa: E402
from char_landmarks import measure                                 # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
SRC, OUTP = a[0], a[1]
H = float(a[2]) if len(a) > 2 else 1.6
bpy.ops.preferences.addon_enable(module="rigify")

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
char = kit.load_character(SRC, "hero", height=H)
n = len(char.data.vertices)
co = np.empty(n * 3)
char.data.vertices.foreach_get("co", co)
P = co.reshape(-1, 3) @ np.array(char.matrix_world.to_3x3()).T + np.array(char.matrix_world.translation)
L = measure(P)
print("RF landmarks", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in L.items() if k not in ("arm_L", "arm_R")}, flush=True)
for k in ("arm_L", "arm_R"):
    print("RF", k, None if L[k] is None else [tuple(round(float(x), 3) for x in q) for q in L[k]], flush=True)

bpy.ops.object.armature_basic_human_metarig_add()
meta = bpy.context.active_object
meta.name = "metarig"
bpy.ops.object.mode_set(mode='EDIT')
eb = meta.data.edit_bones
V = lambda x, y, z: mathutils.Vector((x, y, z))

# ---- torso: spine chain from crotch to neck, neck+head to the crown
body, zn, zmax = L["body"], L["z_neck"], L["zmax"]
z0 = L["crotch"] + 0.04 * body
yh, yc, yn = L["y_hip"], L["y_chest"], L["y_neck"]
chain = [("spine", z0, 0.22), ("spine.001", None, 0.40), ("spine.002", None, 0.60), ("spine.003", None, 1.0)]
zs = [z0 + (L["z_sh"] - z0) * f for _, _, f in chain]
prev = z0
for (nm, _, f), z in zip(chain, zs):
    t = (prev - z0) / max(1e-6, (L["z_sh"] - z0))
    eb[nm].head = V(0, yh + (yc - yh) * t, prev)
    eb[nm].tail = V(0, yh + (yc - yh) * f, z)
    prev = z
# neck and head
eb["spine.004"].head = V(0, yc, L["z_sh"]); eb["spine.004"].tail = V(0, yn, zn)
eb["spine.005"].head = V(0, yn, zn);        eb["spine.005"].tail = V(0, yn, zn + 0.18 * L["head_h"])
eb["spine.006"].head = V(0, yn, zn + 0.18 * L["head_h"]); eb["spine.006"].tail = V(0, yn, zmax - 0.03 * L["head_h"])

# ---- arms
for side, sgn in (("L", 1), ("R", -1)):
    ax = L["arm_" + side]
    if ax is None:
        continue
    root, tip = (np.array(ax[0]), np.array(ax[1]))
    eb["shoulder." + side].head = V(0.08 * sgn * L["w_sh"], yc, L["z_sh"] + 0.02 * body)
    eb["shoulder." + side].tail = V(*root)
    u = tip - root
    j1 = root + u * 0.46
    j2 = root + u * 0.86
    eb["upper_arm." + side].head = V(*root); eb["upper_arm." + side].tail = V(*j1)
    eb["forearm." + side].head = V(*j1);     eb["forearm." + side].tail = V(*j2)
    eb["hand." + side].head = V(*j2);        eb["hand." + side].tail = V(*tip)
    eb["breast." + side].head = V(0.5 * sgn * L["w_sh"], yc, L["z_sh"] - 0.25 * body)
    eb["breast." + side].tail = V(0.5 * sgn * L["w_sh"], yc - 0.08 * body, L["z_sh"] - 0.25 * body)

# ---- legs
hx, zc, zk, za = L["hip_x"], L["crotch"], L["z_knee"], L["z_ankle"]
for side, sgn in (("L", 1), ("R", -1)):
    eb["pelvis." + side].head = V(0, yh, z0); eb["pelvis." + side].tail = V(hx * sgn * 1.1, yh - 0.05 * body, z0 + 0.10 * body)
    eb["thigh." + side].head = V(hx * sgn, yh, zc + 0.06 * body)
    eb["thigh." + side].tail = V(hx * sgn, yh - 0.02 * body, zk)
    eb["shin." + side].head = V(hx * sgn, yh - 0.02 * body, zk)
    eb["shin." + side].tail = V(hx * sgn, yh + 0.01 * body, za)
    eb["foot." + side].head = V(hx * sgn, yh + 0.01 * body, za)
    eb["foot." + side].tail = V(hx * sgn, L["toe_y"] + 0.35 * (L["heel_y"] - L["toe_y"]), L["zmin"] + 0.012 * body)
    eb["toe." + side].head = eb["foot." + side].tail.copy()
    eb["toe." + side].tail = V(hx * sgn, L["toe_y"], L["zmin"] + 0.012 * body)
    eb["heel.02." + side].head = V(hx * sgn - 0.04 * body, L["heel_y"], L["zmin"])
    eb["heel.02." + side].tail = V(hx * sgn + 0.04 * body, L["heel_y"], L["zmin"])
# a zero-length or collinear-with-parent bone makes Rigify's generator throw a bare
# "zero length vectors have no valid angle"; name the culprit before it can
for b in eb:
    L_ = (b.tail - b.head).length
    if L_ < 1e-4:
        print("RF WARNING zero-length bone", b.name, "at", tuple(round(v, 3) for v in b.head), flush=True)
        b.tail = b.head + mathutils.Vector((0, 0, 0.02 * body))
for side in ("L", "R"):
    ua, fa = eb["upper_arm." + side], eb["forearm." + side]
    v1, v2 = (ua.tail - ua.head).normalized(), (fa.tail - fa.head).normalized()
    if v1.length and v2.length and v1.cross(v2).length < 1e-3:
        # bend the elbow a hair backward so the IK pole has a plane to live in
        fa.head = fa.head + mathutils.Vector((0, 0.012 * body, 0)); ua.tail = fa.head.copy()
        print("RF nudged elbow", side, "off collinear", flush=True)
    th, sh = eb["thigh." + side], eb["shin." + side]
    v1, v2 = (th.tail - th.head).normalized(), (sh.tail - sh.head).normalized()
    if v1.length and v2.length and v1.cross(v2).length < 1e-3:
        sh.head = sh.head + mathutils.Vector((0, -0.012 * body, 0)); th.tail = sh.head.copy()
        print("RF nudged knee", side, "off collinear", flush=True)
bpy.ops.object.mode_set(mode='OBJECT')
print("RF metarig fitted", flush=True)

# ---- generate and bind
bpy.context.view_layer.objects.active = meta
bpy.ops.pose.rigify_generate()
rig = bpy.context.active_object
rig.name = "rig"
print("RF generated", len(rig.data.bones), "bones,", sum(1 for b in rig.data.bones if b.use_deform), "deform", flush=True)
bpy.ops.object.select_all(action='DESELECT')
char.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type='ARMATURE_AUTO')
print("RF heat-bound", sum(1 for v in char.data.vertices if v.groups), "of", n, flush=True)
meta.hide_viewport = True; meta.hide_render = True
bpy.ops.wm.save_as_mainfile(filepath=OUTP + ".blend")
print("RF_DONE", OUTP + ".blend", flush=True)
