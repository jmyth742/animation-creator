"""
Retarget a MoMask/Mixamo-named BVH onto a UniRig-rigged GLB and render it.
Run: blender -b --factory-startup --python retarget.py -- <rigged.glb> <clip.bvh> <outdir> <tag> [fps=20] [render=1]
Method: per frame, each mapped source bone's WORLD rotation delta from its rest
is applied to the target bone's rest orientation, with the parent's delta
removed so the result is a local rotation (rest-pose differences — T-pose
source vs A-pose target — stay folded into the rest, so a walk swings around
the character's own arms-down pose). Hips translation is scaled by height.
Writes <outdir>/<tag>_####.png (+ <outdir>/<tag>.glb with the animation).
"""
import sys, os, math
import bpy, mathutils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rig_map import map_unirig

args = sys.argv[sys.argv.index("--") + 1:]
glb, bvh, outdir, tag = args[0], args[1], args[2], args[3]
FPS = int(args[4]) if len(args) > 4 else 20
RENDER = (args[5] if len(args) > 5 else "1") == "1"
os.makedirs(outdir, exist_ok=True)
sc = bpy.context.scene
for ob in list(sc.objects): bpy.data.objects.remove(ob, do_unlink=True)

bpy.ops.import_scene.gltf(filepath=glb)
T = [o for o in sc.objects if o.type == 'ARMATURE'][0]; T.name = "target"
meshes = [o for o in sc.objects if o.type == 'MESH']
roles = map_unirig(T); H_t = roles.pop("_height")
bpy.ops.import_anim.bvh(filepath=bvh, axis_forward='-Z', axis_up='Y', update_scene_fps=False, update_scene_duration=True)
S = [o for o in sc.objects if o.type == 'ARMATURE' and o is not T][0]; S.name = "source"
sc.render.fps = FPS
src_zs = [(S.matrix_world @ b.head_local).z for b in S.data.bones] + [(S.matrix_world @ b.tail_local).z for b in S.data.bones]
H_s = max(src_zs) - min(src_zs)
scale = H_t / H_s if H_s > 0 else 1.0

# source (Mixamo/HumanML3D names) -> role
SRC = {"Hips": "hips", "Spine": "spine0", "Spine1": "spine1", "Spine2": "spine2", "Neck": "neck", "Head": "head",
       "LeftShoulder": "L_clav", "LeftArm": "L_upperarm", "LeftForeArm": "L_forearm", "LeftHand": "L_hand",
       "RightShoulder": "R_clav", "RightArm": "R_upperarm", "RightForeArm": "R_forearm", "RightHand": "R_hand",
       "LeftUpLeg": "L_upperleg", "LeftLeg": "L_lowerleg", "LeftFoot": "L_foot", "LeftToe": "L_toe",
       "RightUpLeg": "R_upperleg", "RightLeg": "R_lowerleg", "RightFoot": "R_foot", "RightToe": "R_toe"}
# if the target has fewer spine bones, the top source spine bones fold into the last target one
pairs = {}
for sname, role in SRC.items():
    if sname in S.data.bones and role in roles: pairs[roles[role]] = sname
if "spine2" not in roles and "Spine2" in S.data.bones and "spine1" in roles: pairs.setdefault(roles["spine1"], "Spine1")
print("RETARGET pairs", len(pairs), {k: v for k, v in pairs.items()})

# rest matrices (world, rotation only)
def rest_rot(arm, bone): return (arm.matrix_world @ bone.matrix_local).to_3x3()
S_rest = {b.name: rest_rot(S, b) for b in S.data.bones}
T_rest = {b.name: rest_rot(T, b) for b in T.data.bones}
T_order = []  # hierarchy order
st = [b for b in T.data.bones if b.parent is None]
while st: b = st.pop(0); T_order.append(b); st.extend(b.children)
hips_t = roles["hips"]; hips_s = "Hips"
hips_rest_s = (S.matrix_world @ S.data.bones[hips_s].matrix_local).translation
hips_rest_t = (T.matrix_world @ T.data.bones[hips_t].matrix_local).translation

f0, f1 = sc.frame_start, sc.frame_end
for pb in T.pose.bones: pb.rotation_mode = 'QUATERNION'
for f in range(f0, f1 + 1):
    sc.frame_set(f)
    deltas = {}  # target bone name -> world rotation delta (Matrix 3x3)
    for b in T_order:
        if b.name in pairs:
            sname = pairs[b.name]
            pose_rot = (S.matrix_world @ S.pose.bones[sname].matrix).to_3x3()
            deltas[b.name] = pose_rot @ S_rest[sname].inverted()
        else:
            deltas[b.name] = deltas[b.parent.name] if b.parent else mathutils.Matrix.Identity(3)
    for b in T_order:
        pb = T.pose.bones[b.name]
        Dp = deltas[b.parent.name] if b.parent else mathutils.Matrix.Identity(3)
        Rloc = T_rest[b.name].inverted() @ Dp.inverted() @ deltas[b.name] @ T_rest[b.name]
        pb.rotation_quaternion = Rloc.to_quaternion()
        pb.keyframe_insert("rotation_quaternion", frame=f)
    # hips translation (world delta, scaled) expressed in the hips' rest frame
    hp = (S.matrix_world @ S.pose.bones[hips_s].matrix).translation
    dw = (hp - hips_rest_s) * scale
    pb = T.pose.bones[hips_t]
    pb.location = T_rest[hips_t].inverted() @ (T.matrix_world.to_3x3().inverted() @ dw)
    pb.keyframe_insert("location", frame=f)
S.hide_render = True; S.hide_viewport = True
print("RETARGET keyed", f1 - f0 + 1, "frames, scale", round(scale, 3))

# export the animated rig for Day-5 integration
bpy.ops.object.select_all(action='DESELECT')
T.select_set(True)
for m in meshes: m.select_set(True)
bpy.ops.export_scene.gltf(filepath=f"{outdir}/{tag}.glb", use_selection=True, export_animations=True, export_apply=False)

if RENDER:
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('s', 'SUN')); sun.data.energy = 3.5
    sun.rotation_euler = (math.radians(60), 0, math.radians(25)); sc.collection.objects.link(sun)
    wd = bpy.data.worlds.new('w'); sc.world = wd; wd.use_nodes = True
    wd.node_tree.nodes['Background'].inputs['Color'].default_value = (0.62, 0.60, 0.58, 1)
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera = cam
    sc.render.engine = 'BLENDER_EEVEE_NEXT'; sc.view_settings.view_transform = 'Standard'
    # frame the whole motion: bounding box of the hips path plus the character height
    xs, ys = [], []
    for f in range(f0, f1 + 1):
        sc.frame_set(f); p = (T.matrix_world @ T.pose.bones[hips_t].matrix).translation; xs.append(p.x); ys.append(p.y)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys), H_t)
    ctr = mathutils.Vector((cx, cy, hips_rest_t.z))
    a = math.radians(35); d = 2.4 * span + 1.5
    cam.location = (ctr.x + d * math.sin(a), ctr.y - d * math.cos(a), ctr.z + 0.25 * H_t)
    dv = ctr - cam.location; cam.rotation_euler = dv.to_track_quat('-Z', 'Y').to_euler()
    sc.render.resolution_x, sc.render.resolution_y = 640, 480
    sc.frame_start, sc.frame_end = f0, f1
    sc.render.filepath = f"{outdir}/{tag}_"; sc.render.image_settings.file_format = 'PNG'
    bpy.ops.render.render(animation=True)
print("RETARGET DONE", tag)
