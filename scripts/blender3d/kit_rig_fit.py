"""
FIT THE KIT'S OWN RIG TO A CHARACTER, instead of asking an auto-rigger to guess.

Why this exists: the original cast animates well because it was never auto-rigged. The
kit builds the skeleton itself at known positions and skins it with a deterministic
nearest-segment rule, with everything above the neck rigidly parented to the head so a
head turn cannot smear the face. UniRig, by contrast, predicts both skeleton and weights,
and on these characters it puts the shoulder joint inside the torso and hands each arm
bone a slab of chest and flank. Measured: the predicted arm bones sit 54-118 mm off the
centre line of an arm about 60 mm thick.

The kit's template is written for human proportions (hips at 0.95 of 1.75, shoulders at
1.42). A chibi is a third head, so the template has to be FITTED rather than scaled: this
measures the feet, the crotch, the neck and the crown from the mesh and maps the template
through those landmarks piecewise, then fits the widths from the silhouette.

  blender -b --factory-startup --python kit_rig_fit.py -- <mesh.glb> <out.glb> [height=1.6]
Env: KRF_CRISP (0.10) weight crispness, KRF_FALLOFF (0.05), KRF_HEAD (0.0) extra head
     rigidity above the neck.
"""
import sys, os, math
import bpy, mathutils
import numpy as np

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import character_kit as kit                                        # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
SRC, DST = a[0], a[1]
H = float(a[2]) if len(a) > 2 else 1.6

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
char = kit.load_character(SRC, "fit", height=H)
n = len(char.data.vertices)
co = np.empty(n * 3)
char.data.vertices.foreach_get("co", co)
P = co.reshape(-1, 3)                                    # load_character normalises to world
zmin, zmax = float(P[:, 2].min()), float(P[:, 2].max())
Ht = zmax - zmin

# ---- landmarks -------------------------------------------------------------
# Anchored on the HEAD, which is the one landmark that can be measured reliably on these
# characters: the skull is the widest slice in the upper body and the neck is the
# narrowest slice below it. Trying to find the crotch from a gap in the centre line
# instead found the space between the boots and put every landmark a metre too low.
def halfwidth_profile(lo, hi, k=140, band=0.012):
    zz = np.linspace(lo, hi, k)
    out = []
    for z in zz:
        m = np.abs(P[:, 2] - z) < band * Ht
        out.append(float(np.percentile(np.abs(P[m, 0]), 96)) if m.sum() > 8 else np.nan)
    return zz, np.array(out)

zz, hw = halfwidth_profile(zmin + 0.50 * Ht, zmax)
ok = ~np.isnan(hw)
top_half = zz > zz[0] + 0.45 * (zz[-1] - zz[0])
i_skull = int(np.argmax(np.where(top_half & ok, hw, -1)))
below = (zz < zz[i_skull]) & ok
z_neck = float(zz[int(np.argmin(np.where(below, hw, 1e9)))]) if below.sum() > 4 else float(zz[0])
head_h = zmax - z_neck

# everything else in proportion to the body BELOW the neck, which is the part that has
# to move. These ratios are the standard ones and they hold for chibi and adult alike
# once the head is taken out of the measurement.
body = z_neck - zmin
z_sh = z_neck - 0.10 * body
crotch = zmin + 0.50 * body
z_knee = zmin + 0.26 * body
z_foot = zmin + 0.045 * body

def torso_halfwidth(z, band=0.02):
    """Width of the BODY at this height, not of the body plus outstretched arms. The mesh
    is a T-pose, so at shoulder height the widest point is a hand: sort the |x| values and
    cut at the first real gap, which is the space between the torso and the arm."""
    m = np.abs(P[:, 2] - z) < band * body
    if m.sum() < 12:
        return np.nan
    xs = np.sort(np.abs(P[m, 0]))
    gaps = np.diff(xs)
    big = np.where(gaps > 0.035 * body)[0]
    if len(big):
        xs = xs[:big[0] + 1]
    return float(np.percentile(xs, 97))


zz2, hw2 = halfwidth_profile(zmin, z_neck)
ok2 = ~np.isnan(hw2)
sh_band = (zz2 > z_sh - 0.12 * body) & (zz2 < z_neck) & ok2
# measure the chest BELOW the shoulder line: on a T-pose mesh the arm touches the
# shoulder, so there is no gap to cut at shoulder height itself
w_sh = 1.05 * float(np.nanmedian([torso_halfwidth(z)
                                  for z in np.linspace(z_sh - 0.30 * body, z_sh - 0.12 * body, 9)]))
if not np.isfinite(w_sh):
    w_sh = 0.20 * body
hip_band = (zz2 > crotch - 0.05 * body) & (zz2 < crotch + 0.18 * body) & ok2
w_hip = float(np.nanmedian([torso_halfwidth(z) for z in np.linspace(crotch, crotch + 0.14 * body, 7)]))
if not np.isfinite(w_hip):
    w_hip = 0.18 * body
reach = float(np.nanmax(np.where(ok2 & (zz2 > z_sh - 0.25 * body), hw2, np.nan)))
print("KRF head from %.3f (body %.3f) | shoulder z %.3f half %.3f | hip half %.3f | reach %.3f"
      % (z_neck, body, z_sh, w_sh, w_hip, reach), flush=True)

# ---- fitted bone template ---------------------------------------------------
# ARM AXIS from the mesh. The kit template angles the arm down and out, which is right
# for a character modelled in an A-pose and wrong for one modelled in a T-pose: the bone
# then runs through empty space beside the arm and the limb does not follow it. Take the
# geometry lateral to the torso around shoulder height and fit its axis.
def arm_axis(sign):
    """Direction of the arm from the geometry WELL CLEAR of the body. Selecting from just
    outside the torso width pulled in the edge of the cape, and the fitted axis pointed
    backward: the bone then lay beside the arm, and rotating it to hang brought the hands
    up in front of the face. The far half of the arm is unambiguous, so fit that and
    anchor the line at the shoulder joint."""
    m = ((P[:, 2] > z_sh - 0.10 * body) & (P[:, 2] < z_sh + 0.55 * body) &
         (P[:, 0] * sign > w_sh * 1.35))
    if m.sum() < 60:
        return None
    A = P[m]
    c = A.mean(axis=0)
    u = np.linalg.svd(A - c, full_matrices=False)[2][0]
    if (u[0] > 0) != (sign > 0):
        u = -u
    t = (A - c) @ u
    tip = c + u * float(np.percentile(t, 98))
    root = np.array((sh_x * sign, c[1] + u[1] * float(np.percentile(t, 2) - 0.0), z_sh))
    # the line from the shoulder joint to the fingertip IS the arm
    return root, tip


sh_x = 0.78 * w_sh
hip_x = 0.52 * w_hip
elbow_x = sh_x + (reach - sh_x) * 0.45
hand_x = sh_x + (reach - sh_x) * 0.90
z_hip = crotch + 0.06 * (z_sh - crotch)
z_chest = crotch + 0.62 * (z_sh - crotch)
z_foot = zmin + 0.045 * Ht
z_knee = zmin + 0.50 * (crotch - zmin)
z_elbow = z_sh - 0.42 * (z_sh - crotch)
z_hand_b = z_sh - 0.86 * (z_sh - crotch)

BONES = {
    "hips":  ((0, 0, z_hip), (0, 0, z_chest), None),
    "spine": ((0, 0, z_chest), (0, 0, z_sh), "hips"),
    "head":  ((0, 0, z_neck), (0, 0, zmax - 0.04 * head_h), "spine"),
    "jaw":   ((0, -0.02 * head_h, z_neck + 0.42 * head_h),
              (0, -0.10 * head_h, z_neck + 0.30 * head_h), "head"),
}
for sgn, side in ((1, "L"), (-1, "R")):
    BONES["thigh.%s" % side] = ((hip_x * sgn, 0, z_hip), (hip_x * sgn, 0, z_knee), "hips")
    BONES["shin.%s" % side] = ((hip_x * sgn, 0, z_knee), (hip_x * sgn, 0, z_foot), "thigh.%s" % side)
    BONES["foot.%s" % side] = ((hip_x * sgn, 0, z_foot),
                               (hip_x * sgn, -0.10 * body, zmin + 0.01 * Ht), "shin.%s" % side)
    ax = arm_axis(sgn)
    if ax is not None:
        root, tip = ax
        root = np.array((sh_x * sgn, root[1], root[2]))      # start at the shoulder joint
        mid = root + (tip - root) * 0.48
        BONES["arm.%s" % side] = (tuple(root), tuple(mid), "spine")
        BONES["fore.%s" % side] = (tuple(mid), tuple(root + (tip - root) * 0.97), "arm.%s" % side)
        if sgn > 0:
            print("KRF arm axis L root %.3f,%.3f,%.3f tip %.3f,%.3f,%.3f"
                  % (root[0], root[1], root[2], tip[0], tip[1], tip[2]), flush=True)
    else:
        BONES["arm.%s" % side] = ((sh_x * sgn, 0, z_sh), (elbow_x * sgn, 0, z_elbow), "spine")
        BONES["fore.%s" % side] = ((elbow_x * sgn, 0, z_elbow), (hand_x * sgn, 0, z_hand_b), "arm.%s" % side)

arm = bpy.data.armatures.new("fit_rig")
rig = bpy.data.objects.new("fit_rig", arm)
sc.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='EDIT')
for nm, (h, t, par) in BONES.items():
    b = arm.edit_bones.new(nm)
    b.head, b.tail = h, t
    if par:
        b.parent = arm.edit_bones[par]
bpy.ops.object.mode_set(mode='OBJECT')

# ---- deterministic skinning (the kit's rule, kept) ---------------------------
names = [nm for nm in BONES if nm != "jaw"]
D = np.empty((n, len(names)))
for bi, nm in enumerate(names):
    aa = np.array(BONES[nm][0], dtype=float)
    bb = np.array(BONES[nm][1], dtype=float)
    ab = bb - aa
    tt = np.clip(((P - aa) @ ab) / max(1e-9, (ab @ ab)), 0, 1)
    D[:, bi] = np.linalg.norm(P - (aa + tt[:, None] * ab), axis=1)
order = np.argsort(D, axis=1)
near2 = order[:, :2]
d2 = np.take_along_axis(D, near2, axis=1)
FALL = float(os.environ.get("KRF_FALLOFF", "0.05")) * (body / 1.05)
CRISP = float(os.environ.get("KRF_CRISP", "0.10")) * (body / 1.05)
w = np.exp(-d2 / FALL)
w /= w.sum(axis=1, keepdims=True)
crisp = d2[:, 1] - d2[:, 0] > CRISP
w[crisp, 0], w[crisp, 1] = 1.0, 0.0
# everything above the neck belongs to the head, rigidly. This is the rule that keeps a
# face from smearing when the head turns, and it is the one an auto-rigger never applies.
head_region = P[:, 2] > z_neck - float(os.environ.get("KRF_HEAD", "0.0")) * Ht
hbi = names.index("head")
w[head_region, 0], w[head_region, 1] = 1.0, 0.0
near2[head_region, 0] = hbi
groups = {nm: char.vertex_groups.new(name=nm) for nm in names}
Q = 64
for k in (0, 1):
    qw = np.round(w[:, k] * Q) / Q
    for bi, nm in enumerate(names):
        sel = near2[:, k] == bi
        for lvl in np.unique(qw[sel]):
            if lvl > 0:
                idx = np.where(sel & (qw == lvl))[0]
                groups[nm].add(idx.tolist(), float(lvl), 'ADD')
jaw_g = char.vertex_groups.new(name="jaw")
jz = z_neck + 0.30 * head_h
jsel = np.where((np.abs(P[:, 2] - jz) < 0.06 * head_h) & (P[:, 1] < 0.0))[0]
for i in jsel:
    f = 1.0 - abs(P[i, 2] - jz) / (0.06 * head_h)
    if f > 0:
        jaw_g.add([int(i)], min(0.85, float(f)), 'ADD')

# ---- bind in an A-pose --------------------------------------------------------
# The mesh is modelled arms-out. Every clip has the arms down, so something has to close
# that gap. Doing it by posing the finished rig runs a 90 degree rotation through the
# skin and tears the shoulder. Doing it HERE is free: the weights are already known, so
# the arm vertices and the arm bones are rotated together about the shoulder joint, with
# the rotation faded in by the vertex's own arm weight. Nothing is deformed -- the arm is
# simply modelled in a different place.
APOSE = float(os.environ.get("KRF_APOSE", "58"))
if APOSE > 0:
    armw = np.zeros(n)
    for k in (0, 1):
        for bi, nm in enumerate(names):
            if nm.startswith(("arm.", "fore.")):
                armw += np.where(near2[:, k] == bi, w[:, k], 0.0)
    armw_full = np.clip(armw, 0.0, 1.0)
    edits = {}
    for sgn, side in ((1, "L"), (-1, "R")):
        armw = armw_full.copy()
        an = "arm.%s" % side
        head = np.array(BONES[an][0], dtype=float)
        tail = np.array(BONES["fore.%s" % side][1], dtype=float)
        u0 = tail - head
        L0 = np.linalg.norm(u0)
        if L0 < 1e-6:
            continue
        u0 = u0 / L0
        want = np.array((0.34 * sgn, 0.0, -1.0))
        want = want / np.linalg.norm(want)
        q = mathutils.Vector(u0).rotation_difference(mathutils.Vector(want))
        ang = q.angle
        axis = q.axis
        # only geometry actually NEAR the arm travels with it. A cloak hangs beside the
        # arm and carries arm weight, and rotating it a hundred degrees with the limb
        # drags the cape into a flat wing across the back.
        segs = [(np.array(BONES[an][0], dtype=float), np.array(BONES[an][1], dtype=float)),
                (np.array(BONES["fore.%s" % side][0], dtype=float),
                 np.array(BONES["fore.%s" % side][1], dtype=float))]
        dmin = None
        for aa, bb in segs:
            ab = bb - aa
            tt = np.clip(((P - aa) @ ab) / max(1e-9, (ab @ ab)), 0, 1)
            dd = np.linalg.norm(P - (aa + tt[:, None] * ab), axis=1)
            dmin = dd if dmin is None else np.minimum(dmin, dd)
        ARM_R = float(os.environ.get("KRF_ARM_R", "0.11")) * body
        near_arm = np.clip(1.0 - (dmin - ARM_R) / (0.5 * ARM_R), 0.0, 1.0)
        armw = armw * near_arm
        side_mask = (P[:, 0] * sgn > 0) & (armw > 0.001)
        for i in np.where(side_mask)[0]:
            wi = float(armw[i])
            qi = mathutils.Quaternion(axis, ang * wi)
            v = mathutils.Vector(P[i] - head)
            v.rotate(qi)
            P[i] = head + np.array(v)
        M = mathutils.Quaternion(axis, ang).to_matrix()
        for bn in (an, "fore.%s" % side):
            h0 = np.array(BONES[bn][0], dtype=float)
            t0 = np.array(BONES[bn][1], dtype=float)
            edits[bn] = (head + np.array(M @ mathutils.Vector(h0 - head)),
                         head + np.array(M @ mathutils.Vector(t0 - head)))
        print("KRF A-pose %s by %.0f deg" % (side, math.degrees(ang)), flush=True)
    char.data.vertices.foreach_set("co", P.reshape(-1))
    char.data.update()
    try:
        bpy.context.view_layer.objects.active = char
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    except Exception:                                               # noqa: BLE001
        pass
    for poly in char.data.polygons:
        poly.use_smooth = True
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    for bn, (h2, t2) in edits.items():
        eb = rig.data.edit_bones[bn]
        eb.head = mathutils.Vector(h2)
        eb.tail = mathutils.Vector(t2)
    bpy.ops.object.mode_set(mode='OBJECT')

char.parent = rig
mod = char.modifiers.new("rig", 'ARMATURE')
mod.object = rig
print("KRF bones", len(BONES), "verts", n, "head-locked", int(head_region.sum()), flush=True)

bpy.ops.object.select_all(action='DESELECT')
char.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.export_scene.gltf(filepath=DST, use_selection=True, export_apply=False,
                          export_animations=False, export_format='GLB')
print("KRF_DONE", DST, os.path.getsize(DST), flush=True)
