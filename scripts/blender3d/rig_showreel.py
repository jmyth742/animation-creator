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
    pairs = {}
    for sname, role in SRC.items():
        if sname in S.data.bones and role in roles:
            pairs[roles[role]] = sname
    ALIGN = {}
    for tn, sn in pairs.items():
        ALIGN[tn] = (T_rest[tn] @ Y).normalized().rotation_difference((S_rest[sn] @ Y).normalized()).to_matrix()
    act = S.animation_data.action
    a0, a1 = int(act.frame_range[0]), int(act.frame_range[1])
    a1 = min(a1, a0 + MAXF - 1)
    T.animation_data_clear()
    sc.frame_set(a0)
    ref = (S.matrix_world @ S.pose.bones["Hips"].matrix).translation.copy()
    for f in range(a0, a1 + 1):
        sc.frame_set(f)
        deltas = {}
        for b in T_order:
            Dp = deltas[b.parent.name] if b.parent else mathutils.Matrix.Identity(3)
            if b.name in pairs:
                sn = pairs[b.name]
                pose_rot = (S.matrix_world @ S.pose.bones[sn].matrix).to_3x3()
                if b.name == hips_t:
                    D = pose_rot @ S_rest[sn].inverted() @ ALIGN[b.name]
                else:
                    cur = (Dp @ T_rest[b.name] @ Y).normalized()
                    want = (pose_rot @ Y).normalized()
                    D = cur.rotation_difference(want).to_matrix() @ Dp
            else:
                D = Dp
            deltas[b.name] = D
            pb = T.pose.bones[b.name]
            pb.rotation_quaternion = (T_rest[b.name].inverted() @ Dp.inverted() @ D @ T_rest[b.name]).to_quaternion()
            pb.keyframe_insert("rotation_quaternion", frame=f)
        hp = (S.matrix_world @ S.pose.bones["Hips"].matrix).translation
        dw = (hp - ref) * scale
        pb = T.pose.bones[hips_t]
        pb.location = T_rest[hips_t].inverted() @ dw
        pb.keyframe_insert("location", frame=f)
    bpy.data.objects.remove(S, do_unlink=True)
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
