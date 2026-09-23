"""
WALK A/B — the kit's own procedural gait against the retargeted MoMask clip.

The films were animated with kit.apply_walk, not with retargeted motion capture. That
animator was written for this skeleton: it keys the hips, spine, head, both legs and both
arms every frame with a stride phase, so the feet, the arm swing and the body sway are in
step by construction. A retarget inherits whatever the source clip has, and these clips
have a slow shuffle with almost no arm movement.

Renders the same character walking the same distance both ways, from a locked side camera,
and reports foot slide for each: how far the planted foot travels across the ground while
it is meant to be planted, in millimetres per frame. Lower is better; a skating character
is the single loudest tell that motion is fake.

  blender -b --factory-startup --python walk_ab.py -- <rigged.glb> <outdir> [height=1.6]
Env: WAB_FRAMES (96), WAB_RES (720), WAB_BVH (walk), WAB_STRIDE (1.45)
"""
import sys, os, math
import bpy, bmesh, mathutils

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
sys.path.insert(0, "/workspace/text-to-video/scripts/day4")
import character_kit as kit                                        # noqa: E402
from rig_map import map_unirig                                     # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT = a[0], a[1]
H = float(a[2]) if len(a) > 2 else 1.6
NF = int(os.environ.get("WAB_FRAMES", "96"))
RES = int(os.environ.get("WAB_RES", "720"))
FPS = 20
os.makedirs(OUT, exist_ok=True)

sc = bpy.context.scene
sc.render.fps = FPS


def stage():
    me = bpy.data.meshes.new("g")
    bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=60)
    bm.to_mesh(me); bm.free()
    go = bpy.data.objects.new("g", me); sc.collection.objects.link(go)
    m = bpy.data.materials.new("gm"); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial"); df = nt.nodes.new("ShaderNodeBsdfDiffuse")
    ck = nt.nodes.new("ShaderNodeTexChecker"); ck.inputs["Scale"].default_value = 44.0
    ck.inputs["Color1"].default_value = (0.52, 0.55, 0.49, 1)
    ck.inputs["Color2"].default_value = (0.48, 0.51, 0.45, 1)
    nt.links.new(ck.outputs["Color"], df.inputs["Color"]); nt.links.new(df.outputs["BSDF"], o.inputs["Surface"])
    me.materials.append(m)
    sun = bpy.data.objects.new("s", bpy.data.lights.new("s", 'SUN')); sun.data.energy = 3.4
    sun.rotation_euler = (math.radians(58), 0, math.radians(35)); sc.collection.objects.link(sun)
    fl = bpy.data.objects.new("f", bpy.data.lights.new("f", 'SUN')); fl.data.energy = 0.9
    fl.rotation_euler = (math.radians(70), 0, math.radians(-140)); sc.collection.objects.link(fl)
    wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
    wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.58, 0.64, 0.72, 1)
    cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); cam.data.lens = 55
    sc.collection.objects.link(cam); sc.camera = cam
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.view_settings.view_transform = 'Standard'
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.image_settings.file_format = 'PNG'
    return cam


def foot_slide(rig, f0, f1):
    """Millimetres of horizontal travel per frame of the LOWER foot, which is the one
    carrying weight. A planted foot should not move across the ground."""
    names = [n for n in ("foot.L", "foot.R") if n in rig.pose.bones]
    if len(names) < 2:
        return -1.0
    prev = {}
    tot, cnt = 0.0, 0
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        pos = {n: (rig.matrix_world @ rig.pose.bones[n].matrix).translation.copy() for n in names}
        low = min(names, key=lambda n: pos[n].z)
        if low in prev:
            d = pos[low] - prev[low]
            tot += math.hypot(d.x, d.y)
            cnt += 1
        prev = pos
    return 1000.0 * tot / max(1, cnt)


def shoot(tag, rig, char, f0, f1):
    cam = sc.camera
    pts = []
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        pts.append((rig.matrix_world @ rig.pose.bones["hips"].matrix).translation.copy())
    p0, p1 = pts[0], pts[-1]
    trav = mathutils.Vector((p1.x - p0.x, p1.y - p0.y, 0))
    if trav.length < 0.05 * H:
        trav = mathutils.Vector((0, -1, 0))
    trav.normalize()
    side = mathutils.Vector((-trav.y, trav.x, 0))
    mid = mathutils.Vector(((p0.x + p1.x) / 2, (p0.y + p1.y) / 2, H * 0.52))
    d = 2.05 * H + 0.55 * (p1 - p0).length
    cam.location = mid + side * d + mathutils.Vector((0, 0, H * 0.06))
    cam.rotation_euler = (mid - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
    dd = os.path.join(OUT, tag)
    os.makedirs(dd, exist_ok=True)
    sc.render.filepath = os.path.join(dd, "f_")
    sc.frame_start, sc.frame_end = f0, f1
    bpy.ops.render.render(animation=True)
    print("WAB shot", tag, f1 - f0 + 1, "frames travel %.2f m" % (p1 - p0).length, flush=True)


# ---------------------------------------------------------------- procedural
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
char, rig = kit.load_rigged_character(GLB, "hero", height=H)
cam = stage()
dist = 0.85 * H * (NF / float(FPS))                # a believable 0.85 body heights/second
pathfn = kit.path_fn_from_points([(0.0, 0.0), (0.0, -dist)], lambda x, y: 0.0)
kit.apply_walk(rig, pathfn, 1, NF, fps=FPS, stride_hz=float(os.environ.get("WAB_STRIDE", "1.45")))
slide_p = foot_slide(rig, 1, NF)
shoot("proc", rig, char, 1, NF)
print("WAB foot slide procedural %.1f mm/frame" % slide_p, flush=True)

# ---------------------------------------------------------------- tracked shot
# A camera locked to the side of a six-metre walk has to stand far enough back to cover
# the whole path, which leaves the character tiny. Tracking alongside at a fixed offset
# keeps them large while the ground slides past, which is what reads as locomotion.
def shoot_tracked(tag, rig, f0, f1):
    cam = sc.camera
    cam.animation_data_clear()
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        p = (rig.matrix_world @ rig.pose.bones["hips"].matrix).translation.copy()
        ctr = mathutils.Vector((p.x, p.y, H * 0.52))
        ang = math.radians(float(os.environ.get("WAB_ANGLE", "62")))
        d = 1.9 * H
        cam.location = (ctr.x + d * math.sin(ang), ctr.y - d * math.cos(ang), ctr.z + 0.10 * H)
        cam.rotation_euler = (ctr - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    dd = os.path.join(OUT, tag)
    os.makedirs(dd, exist_ok=True)
    sc.render.filepath = os.path.join(dd, "f_")
    sc.frame_start, sc.frame_end = f0, f1
    bpy.ops.render.render(animation=True)
    print("WAB tracked shot", tag, f1 - f0 + 1, "frames", flush=True)


shoot_tracked("proc_track", rig, 1, NF)
print("WAB_DONE", flush=True)
