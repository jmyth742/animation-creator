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
# per mapped bone: world rotation A taking the target's rest bone direction onto the source's
# rest bone direction, so the target tracks the source's world direction (twist ignored).
# Without this, a T-pose source walking arms-down folds an A-pose target's arms across its chest.
Y = mathutils.Vector((0, 1, 0))
ALIGN = {}
for tname, sname in pairs.items():
    t_dir = (T_rest[tname] @ Y).normalized(); s_dir = (S_rest[sname] @ Y).normalized()
    ALIGN[tname] = t_dir.rotation_difference(s_dir).to_matrix()
hips_rest_s = (S.matrix_world @ S.data.bones[hips_s].matrix_local).translation
hips_rest_t = (T.matrix_world @ T.data.bones[hips_t].matrix_local).translation

act = S.animation_data.action
f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
sc.frame_start, sc.frame_end = f0, f1
for pb in T.pose.bones: pb.rotation_mode = 'QUATERNION'
# BVH root positions are absolute: measure hips travel from the FIRST animated frame, not the rest offset
sc.frame_set(f0); hips_ref_s = (S.matrix_world @ S.pose.bones[hips_s].matrix).translation.copy()
for f in range(f0, f1 + 1):
    sc.frame_set(f)
    # world rotation D per target bone. Hips: full delta (facing). Every other
    # mapped bone: SWING-ONLY aim — rotate the bone's current direction (under
    # its already-posed parent) onto the source bone's world direction; no
    # twist is transferred (bone rolls differ between rigs). Unmapped bones
    # ride along with their parent.
    deltas = {}
    for b in T_order:
        Dp = deltas[b.parent.name] if b.parent else mathutils.Matrix.Identity(3)
        if b.name in pairs:
            sname = pairs[b.name]
            pose_rot = (S.matrix_world @ S.pose.bones[sname].matrix).to_3x3()
            if b.name == hips_t:
                D = pose_rot @ S_rest[sname].inverted() @ ALIGN[b.name]
            else:
                cur_dir = (Dp @ T_rest[b.name] @ Y).normalized()
                want_dir = (pose_rot @ Y).normalized()
                D = cur_dir.rotation_difference(want_dir).to_matrix() @ Dp
        else:
            D = Dp
        deltas[b.name] = D
        pb = T.pose.bones[b.name]
        Rloc = T_rest[b.name].inverted() @ Dp.inverted() @ D @ T_rest[b.name]
        pb.rotation_quaternion = Rloc.to_quaternion()
        pb.keyframe_insert("rotation_quaternion", frame=f)
    # hips translation (world delta, scaled) expressed in the hips' rest frame
    hp = (S.matrix_world @ S.pose.bones[hips_s].matrix).translation
    dw = (hp - hips_ref_s) * scale
    pb = T.pose.bones[hips_t]
    pb.location = T_rest[hips_t].inverted() @ (T.matrix_world.to_3x3().inverted() @ dw)
    pb.keyframe_insert("location", frame=f)
S.hide_render = True; S.hide_viewport = True
print("RETARGET keyed", f1 - f0 + 1, "frames, scale", round(scale, 3), "hips travel", round(((S.matrix_world @ S.pose.bones[hips_s].matrix).translation - hips_ref_s).length * scale, 2))

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
    t_zs = [(T.matrix_world @ b.head_local).z for b in T.data.bones] + [(T.matrix_world @ b.tail_local).z for b in T.data.bones]
    ctr = mathutils.Vector((cx, cy, (min(t_zs) + max(t_zs)) / 2))
    a = math.radians(35); d = 2.2 * max(span, H_t) + 1.0
    cam.location = (ctr.x + d * math.sin(a), ctr.y - d * math.cos(a), ctr.z + 0.12 * H_t)
    dv = ctr - cam.location; cam.rotation_euler = dv.to_track_quat('-Z', 'Y').to_euler()
    sc.render.resolution_x, sc.render.resolution_y = 640, 480
    sc.frame_start, sc.frame_end = f0, f1
    sc.render.filepath = f"{outdir}/{tag}_"; sc.render.image_settings.file_format = 'PNG'
    bpy.ops.render.render(animation=True)
print("RETARGET DONE", tag)
