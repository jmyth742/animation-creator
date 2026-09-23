"""
RIG SHOWREEL — render a rigged character performing a battery of motions so the
rig's range can be judged by eye rather than by a static deformation gate.

Each clip is its own shot: the camera orbits slowly while following the hips, so
travel (walk, run) reads as travel rather than as the character sliding off frame.
Cel material + Freestyle contour, so what you see is the shipping look, not a grey
preview.

Retargeting is the same world-swing method as scripts/day4/retarget.py: each mapped
bone's direction is aimed at the source bone's world direction under the already-posed
parent, so a T-pose source drives an A-pose target without folding the arms in.

Run:
  blender -b --factory-startup --python rig_showreel.py -- <rigged.glb> <outdir> [height=1.6]
Env:
  RS_CLIPS   comma list of clip basenames in RS_BVHDIR   (default walk,turn,wave,point,run,idle)
  RS_BVHDIR  default /workspace/loopwork/day4
  RS_MAXF    max frames per clip (default 110)
  RS_RES     square render size (default 768)
  RS_FPS     default 20
"""
import sys, os, math
import bpy, mathutils

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
sys.path.insert(0, "/workspace/text-to-video/scripts/day4")
import character_kit as kit                                        # noqa: E402
from rig_map import map_unirig                                     # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT = args[0], args[1]
HEIGHT = float(args[2]) if len(args) > 2 else 1.6
BVHDIR = os.environ.get("RS_BVHDIR", "/workspace/loopwork/day4")
CLIPS = [c for c in os.environ.get("RS_CLIPS", "walk,turn,wave,point,run,idle").split(",") if c]
MAXF = int(os.environ.get("RS_MAXF", "110"))
RES = int(os.environ.get("RS_RES", "768"))
FPS = int(os.environ.get("RS_FPS", "20"))
os.makedirs(OUT, exist_ok=True)

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)

# ---------------------------------------------------------------- character
# Use the kit loader, not a raw glTF import. UniRig binds the mesh in the pose it
# was modelled in, and this mesh is a T-pose: the upper-arm bones point straight
# out along +X. Every walk then asks the shoulder for a ~90 deg rotation, which is
# exactly where this skin shears -- the arms render as detached sticks. The loader
# bakes an A-pose into the REST (pose arms down, apply the deform, apply pose as
# rest), so the same walk becomes a few degrees of delta instead of ninety. It also
# stands the feet on z=0, scales to height, bakes the facing yaw and applies the
# cel material.
char, T = kit.load_rigged_character(GLB, "hero", height=HEIGHT)
T.name = "target"
meshes = [char]

# weight smoothing and corrective smooth now happen inside the kit loader, BEFORE
# the A-pose bake -- doing it here was too late, the bake had already torn the
# shoulders using the raw weights.

roles = map_unirig(T); H_bone = roles.pop("_height")   # world-space bone extent, for stride scaling
H_t = HEIGHT                                          # silhouette height, for framing
FLOOR = min((char.matrix_world @ v.co).z for v in char.data.vertices)
print("SHOWREEL roles", len(roles), "height", round(H_t, 3), "floor", round(FLOOR, 3), flush=True)

# ---------------------------------------------------------------- retarget core
SRC = {"Hips": "hips", "Spine": "spine0", "Spine1": "spine1", "Spine2": "spine2", "Neck": "neck", "Head": "head",
       "LeftShoulder": "L_clav", "LeftArm": "L_upperarm", "LeftForeArm": "L_forearm", "LeftHand": "L_hand",
       "RightShoulder": "R_clav", "RightArm": "R_upperarm", "RightForeArm": "R_forearm", "RightHand": "R_hand",
       "LeftUpLeg": "L_upperleg", "LeftLeg": "L_lowerleg", "LeftFoot": "L_foot", "LeftToe": "L_toe",
       "RightUpLeg": "R_upperleg", "RightLeg": "R_lowerleg", "RightFoot": "R_foot", "RightToe": "R_toe"}
Y = mathutils.Vector((0, 1, 0))
rest_rot = lambda arm, b: (arm.matrix_world @ b.matrix_local).to_3x3()
T_rest = {b.name: rest_rot(T, b) for b in T.data.bones}
T_order = []
st = [b for b in T.data.bones if b.parent is None]
while st:
    b = st.pop(0); T_order.append(b); st.extend(b.children)
hips_t = roles["hips"]
for pb in T.pose.bones:
    pb.rotation_mode = 'QUATERNION'


def retarget(bvh_path):
    """Key the whole clip onto T. Returns (f0, f1)."""
    pre = set(sc.objects)
    bpy.ops.import_anim.bvh(filepath=bvh_path, axis_forward='-Z', axis_up='Y',
                            update_scene_fps=False, update_scene_duration=True)
    S = [o for o in sc.objects if o not in pre and o.type == 'ARMATURE'][0]
    S_rest = {b.name: rest_rot(S, b) for b in S.data.bones}
    zs = [(S.matrix_world @ b.head_local).z for b in S.data.bones] + \
         [(S.matrix_world @ b.tail_local).z for b in S.data.bones]
    H_s = max(zs) - min(zs)
    scale = H_bone / H_s if H_s > 0 else 1.0
    # RS_SKIP: roles to leave in their rest pose. The chibi's hands reconstruct as flat
    # fans of splayed fingers; driving them from a human hand's world direction turns
    # them into spikes, and leaving them alone is better than aiming them wrongly.
    _skip = set(x for x in os.environ.get("RS_SKIP", "").split(",") if x)
    pairs = {}
    for sname, role in SRC.items():
        if role in _skip:
            continue
        if sname in S.data.bones and role in roles:
            pairs[roles[role]] = sname
    # ROOT CORRECTION. The old code aligned the hips by rotating the target's hips BONE
    # AXIS onto the source's. That is meaningless for a root: this source's hips bone
    # points down (0, 0.46, -0.89) and the target's points up, so the "alignment" was a
    # 152.6 degree rotation applied to the whole body on every frame, while the limbs
    # were still aimed at correct world directions. The body came out back to front.
    # The only legitimate root correction is the YAW between the two rest facings, and
    # facing is measured from the hip joints, not from a bone axis.
    def facing(arm, lname, rname):
        L = arm.matrix_world @ arm.data.bones[lname].head_local
        R = arm.matrix_world @ arm.data.bones[rname].head_local
        lat = L - R; lat.z = 0
        if lat.length < 1e-6:
            return None
        return lat.normalized().cross(mathutils.Vector((0, 0, 1)))
    M3 = mathutils.Matrix.Identity(3)
    ft = facing(T, roles["L_upperleg"], roles["R_upperleg"]) if "L_upperleg" in roles and "R_upperleg" in roles else None
    fs = facing(S, "LeftUpLeg", "RightUpLeg") if "LeftUpLeg" in S.data.bones else None
    if ft is not None and fs is not None:
        th = math.atan2(ft.y, ft.x) - math.atan2(fs.y, fs.x)
        M3 = mathutils.Matrix.Rotation(th, 3, 'Z')
        print("RETARGET root yaw correction %.1f deg" % math.degrees(th), flush=True)
    M3i = M3.inverted()
    act = S.animation_data.action
    a0, a1 = int(act.frame_range[0]), int(act.frame_range[1])

    # TRIM THE DEAD AIR. MoMask clips open with roughly a second of the figure standing
    # still before the action starts; kept in, a six-shot reel is a third standing about
    # and the walk reads as a character that cannot get going.
    def _bone_sig(f):
        sc.frame_set(f)
        v = []
        for bn in ("LeftUpLeg", "RightUpLeg", "LeftArm", "RightArm", "Hips"):
            if bn in S.data.bones:
                m = S.matrix_world @ S.pose.bones[bn].matrix
                v.append(m.translation.copy())
                v.append((m.to_3x3() @ Y).normalized())
        return v

    if os.environ.get("RS_TRIM", "1") not in ("", "0"):
        base = _bone_sig(a0)
        # a fixed threshold either trims nothing or trims the whole clip depending on how
        # big the action is; scale it to this clip's own largest excursion instead
        span = 0.0
        for f in range(a0, a1 + 1, max(1, (a1 - a0) // 24)):
            sig = _bone_sig(f)
            span = max(span, max((a - b).length for a, b in zip(sig, base)))
        thresh = max(0.01, 0.10 * span)
        lead = a0
        for f in range(a0, min(a1, a0 + 120)):
            sig = _bone_sig(f)
            if max((a - b).length for a, b in zip(sig, base)) > thresh:
                lead = max(a0, f - 2)
                break
        tail = a1
        endsig = _bone_sig(a1)
        for f in range(a1, max(lead, a1 - 120), -1):
            sig = _bone_sig(f)
            if max((a - b).length for a, b in zip(sig, endsig)) > thresh:
                tail = min(a1, f + 2)
                break
        if tail - lead > 12:
            print("RETARGET trimmed %d..%d -> %d..%d" % (a0, a1, lead, tail), flush=True)
            a0, a1 = lead, tail
    a1 = min(a1, a0 + MAXF - 1)
    T.animation_data_clear()
    sc.frame_set(a0)
    ref = (S.matrix_world @ S.pose.bones["Hips"].matrix).translation.copy()

    # ARM SWING. These clips carry almost no arm motion of their own -- measured over the
    # walk, the upper arm moves about four degrees -- so a retarget that is faithful to
    # the source produces a figure gliding with its arms pinned. Where the source has no
    # swing, add one, counter-phased against the opposite thigh the way a human walks.
    def _facing_at(f):
        """The body's facing on THIS frame. Measuring a limb's forward angle against the
        rest facing conflates the swing with the body's own yaw: this walk turns as it
        goes, which is how a 2.5 degree arm swing measured as 27."""
        sc.frame_set(f)
        L = (S.matrix_world @ S.pose.bones["LeftUpLeg"].matrix).translation
        R = (S.matrix_world @ S.pose.bones["RightUpLeg"].matrix).translation
        lat = L - R; lat.z = 0
        if lat.length < 1e-6:
            return mathutils.Vector((0, -1, 0))
        return lat.normalized().cross(mathutils.Vector((0, 0, 1)))

    def _fwd_angle(bn, f_hat):
        m = (S.matrix_world @ S.pose.bones[bn].matrix).to_3x3()
        d = (m @ Y).normalized()
        return math.asin(max(-1.0, min(1.0, d.dot(f_hat))))
    swing = {}
    SW_GAIN = float(os.environ.get("RS_ARM_SWING", "0.62"))
    if SW_GAIN > 0 and all(b in S.data.bones for b in ("LeftUpLeg", "RightUpLeg", "LeftArm", "RightArm")):
        arm_range = []
        leg = {}
        face_at = {}
        for f in range(a0, a1 + 1):
            fh = _facing_at(f)
            face_at[f] = fh
            arm_range.append(_fwd_angle("LeftArm", fh))
            leg[f] = (_fwd_angle("LeftUpLeg", fh), _fwd_angle("RightUpLeg", fh))
        src_swing = (max(arm_range) - min(arm_range)) / 2.0
        # only on a clip that actually travels: adding leg-phased arm swing to a wave or
        # a point would fight the performance instead of supporting it
        # gait is better detected from the LEGS than from ground covered: these clips
        # travel slowly (half a metre over three seconds) but their legs still swing
        leg_amp = 0.0
        for f in range(a0, a1 + 1):
            lL, lR = leg[f]
            leg_amp = max(leg_amp, abs(lL - lR))
        leg_amp *= 0.5
        if leg_amp > math.radians(10) and src_swing < math.radians(18):
            swing = leg
            print("RETARGET source arm swing %.1f deg, leg swing %.1f deg -- adding counter-phased arm swing" %
                  (math.degrees(src_swing), math.degrees(leg_amp)), flush=True)
        else:
            print("RETARGET source arm swing %.1f deg, leg swing %.1f deg -- kept as authored" %
                  (math.degrees(src_swing), math.degrees(leg_amp)), flush=True)
    for f in range(a0, a1 + 1):
        sc.frame_set(f)
        deltas = {}
        for b in T_order:
            Dp = deltas[b.parent.name] if b.parent else mathutils.Matrix.Identity(3)
            if b.name in pairs:
                sn = pairs[b.name]
                pose_rot = (S.matrix_world @ S.pose.bones[sn].matrix).to_3x3()
                if b.name == hips_t:
                    # the source's own world rotation delta, expressed in the target's frame
                    D = M3 @ (pose_rot @ S_rest[sn].inverted()) @ M3i
                else:
                    cur = (Dp @ T_rest[b.name] @ Y).normalized()
                    want = (M3 @ (pose_rot @ Y)).normalized()
                    if swing and sn in ("LeftArm", "RightArm"):
                        # left leg forward pairs with right arm forward
                        lL, lR = swing.get(f, (0.0, 0.0))
                        phi = SW_GAIN * (lL if sn == "RightArm" else lR)
                        f_t = (M3 @ face_at.get(f, mathutils.Vector((0, -1, 0)))).normalized()
                        axis = f_t.cross(mathutils.Vector((0, 0, 1)))
                        if axis.length > 1e-6:
                            want = (mathutils.Matrix.Rotation(phi, 3, axis.normalized()) @ want).normalized()
                    D = cur.rotation_difference(want).to_matrix() @ Dp
            else:
                D = Dp
            deltas[b.name] = D
            pb = T.pose.bones[b.name]
            pb.rotation_quaternion = (T_rest[b.name].inverted() @ Dp.inverted() @ D @ T_rest[b.name]).to_quaternion()
            pb.keyframe_insert("rotation_quaternion", frame=f)
        hp = (S.matrix_world @ S.pose.bones["Hips"].matrix).translation
        dw = M3 @ ((hp - ref) * scale)
        pb = T.pose.bones[hips_t]
        pb.location = T_rest[hips_t].inverted() @ dw
        pb.keyframe_insert("location", frame=f)
    bpy.data.objects.remove(S, do_unlink=True)
    # SMOOTH THE RESULT CURVES. The swing-aim solve is computed independently per frame,
    # so any jitter in the source lands in the target unfiltered and the motion reads
    # mechanical. A 3-tap pass takes the buzz out without visibly softening the action.
    sm = int(os.environ.get("RS_CURVE_SMOOTH", "2"))
    if sm > 0 and T.animation_data and T.animation_data.action:
        for fc in T.animation_data.action.fcurves:
            kps = fc.keyframe_points
            for _ in range(sm):
                vals = [kp.co[1] for kp in kps]
                n = len(vals)
                for i in range(1, n - 1):
                    kps[i].co[1] = 0.25 * vals[i - 1] + 0.5 * vals[i] + 0.25 * vals[i + 1]
            for kp in kps:
                kp.interpolation = 'BEZIER'
        print("SHOWREEL curve smoothing passes", sm, flush=True)
    return a0, a1


# ---------------------------------------------------------------- stage
ground = bpy.data.meshes.new("ground")
gob = bpy.data.objects.new("ground", ground)
sc.collection.objects.link(gob)
import bmesh                                                        # noqa: E402
bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=60)
bm.to_mesh(ground); bm.free()
gm = bpy.data.materials.new("groundmat"); gm.use_nodes = True
gnt = gm.node_tree; gnt.nodes.clear()
gout = gnt.nodes.new("ShaderNodeOutputMaterial")
gdif = gnt.nodes.new("ShaderNodeBsdfDiffuse")
gchk = gnt.nodes.new("ShaderNodeTexChecker")
gchk.inputs["Scale"].default_value = 44.0
gchk.inputs["Color1"].default_value = (0.52, 0.55, 0.49, 1)
gchk.inputs["Color2"].default_value = (0.48, 0.51, 0.45, 1)
gnt.links.new(gchk.outputs["Color"], gdif.inputs["Color"])
gnt.links.new(gdif.outputs["BSDF"], gout.inputs["Surface"])
ground.materials.append(gm)

sun = bpy.data.objects.new("sun", bpy.data.lights.new("s", 'SUN'))
sun.data.energy = 3.4
sun.data.color = (1.0, 0.92, 0.82)
sun.data.angle = math.radians(3)
sun.rotation_euler = (math.radians(58), 0, math.radians(35))
sc.collection.objects.link(sun)
fill = bpy.data.objects.new("fill", bpy.data.lights.new("f", 'SUN'))
fill.data.energy = 0.9
fill.data.color = (0.72, 0.80, 1.0)
fill.rotation_euler = (math.radians(70), 0, math.radians(-140))
sc.collection.objects.link(fill)
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.58, 0.64, 0.72, 1)

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("c"))
cam.data.lens = 55
sc.collection.objects.link(cam); sc.camera = cam

sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = sc.render.resolution_y = RES
sc.render.fps = FPS
sc.render.image_settings.file_format = 'PNG'
try:
    sc.eevee.use_shadows = True
    sc.eevee.taa_render_samples = 24
except Exception:                                                   # noqa: BLE001
    pass

sc.render.use_freestyle = True
sc.render.line_thickness = 1.0
vl = sc.view_layers[0]
vl.use_freestyle = True
fs = vl.freestyle_settings
while fs.linesets:
    fs.linesets.remove(fs.linesets[0])
ls = fs.linesets.new("c")
ls.select_by_collection = False
ls.linestyle.thickness = 1.6
ls.select_silhouette = True
ls.select_external_contour = False
ls.select_border = False
ls.select_crease = False
ls.linestyle.color = (0.07, 0.05, 0.06)
ls.linestyle.use_length_min = True
ls.linestyle.length_min = 6

# ---------------------------------------------------------------- shots
ORBIT = {"walk": 26.0, "run": 22.0, "turn": 55.0, "wave": 70.0, "point": 70.0, "idle": 80.0, "sit": 60.0,
         "kneel": 60.0, "hug": 60.0, "sadwalk": 26.0}
START = {"walk": 25.0, "run": -20.0, "turn": 0.0, "wave": 20.0, "point": -25.0, "idle": 15.0}
rendered = []
for clip in CLIPS:
    path = os.path.join(BVHDIR, clip + ".bvh")
    if not os.path.exists(path):
        print("SHOWREEL skip (missing)", path, flush=True)
        continue
    f0, f1 = retarget(path)
    n = f1 - f0 + 1
    # hips path, to follow and to size the shot
    pts = []
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        pts.append((T.matrix_world @ T.pose.bones[hips_t].matrix).translation.copy())
    span = max((max(p.x for p in pts) - min(p.x for p in pts)),
               (max(p.y for p in pts) - min(p.y for p in pts)))
    dist = 1.62 * H_t + 0.28 * span
    # RS_STATIC_CAM=1: lock the camera off to the side of the travel line instead of
    # orbiting and following. A following camera hides foot slide and hides whether the
    # character actually goes anywhere; a locked camera is the honest test of a gait.
    STATIC = os.environ.get("RS_STATIC_CAM", "0") not in ("", "0")
    if STATIC:
        p0, p1 = pts[0], pts[-1]
        trav = mathutils.Vector((p1.x - p0.x, p1.y - p0.y, 0))
        if trav.length < 0.05 * H_t:
            trav = mathutils.Vector((0, -1, 0))
        trav.normalize()
        side = mathutils.Vector((-trav.y, trav.x, 0))
        mid = mathutils.Vector(((p0.x + p1.x) / 2, (p0.y + p1.y) / 2, FLOOR + H_t * 0.52))
        dd = 2.05 * H_t + 0.55 * (p1 - p0).length
        cam.location = mid + side * dd + mathutils.Vector((0, 0, H_t * 0.06))
        cam.rotation_euler = (mid - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
        d0 = os.path.join(OUT, clip)
        os.makedirs(d0, exist_ok=True)
        sc.render.filepath = os.path.join(d0, "f_")
        sc.frame_start, sc.frame_end = f0, f1
        bpy.ops.render.render(animation=True)
        print("SHOWREEL clip done", clip, n, "frames (static cam)", flush=True)
        rendered.append((clip, d0, n))
        continue
    base = math.radians(START.get(clip, 20.0))
    rate = math.radians(ORBIT.get(clip, 45.0))
    sc.frame_start, sc.frame_end = f0, f1
    for i, f in enumerate(range(f0, f1 + 1)):
        t = i / max(1, n - 1)
        # smoothstep the orbit so the move eases in and out instead of starting hard
        e = t * t * (3 - 2 * t)
        a = base + rate * e
        # follow the hips with a lag, so travel reads as travel
        j = max(0, i - 4)
        c = pts[j]
        ctr = mathutils.Vector((c.x, c.y, FLOOR + H_t * 0.54))
        cam.location = (ctr.x + dist * math.sin(a), ctr.y - dist * math.cos(a),
                        ctr.z + H_t * (0.08 + 0.04 * math.sin(math.pi * t)))
        cam.rotation_euler = (ctr - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    d = os.path.join(OUT, clip)
    os.makedirs(d, exist_ok=True)
    sc.render.filepath = os.path.join(d, "f_")
    bpy.ops.render.render(animation=True)
    print("SHOWREEL clip done", clip, n, "frames", flush=True)
    rendered.append((clip, d, n))
    cam.animation_data_clear()

print("SHOWREEL_DONE", ",".join("%s:%d" % (c, n) for c, _, n in rendered), flush=True)
