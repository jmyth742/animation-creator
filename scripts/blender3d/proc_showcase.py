"""
PROCEDURAL SHOWCASE — the character moving the way the films actually animate it.

Retargeted MoMask clips gave a figure shuffling half a metre in three seconds with its
arms pinned. kit.apply_walk and kit.apply_idle were written for this skeleton: the stride
phase drives the legs, the arms counter-swing, the hips and spine sway and the body bobs,
all in step by construction. This renders those, with the camera tracking alongside so the
character stays large while the ground moves past.

Shots: walk across, walk a curve (turn), idle with gestures, and a close idle.

  blender -b --factory-startup --python proc_showcase.py -- <rigged.glb> <outdir> [height]
Env: PS_RES (768), PS_FPS (20), PS_SPEED (body heights per second, 0.85)
"""
import sys, os, math
import bpy, bmesh, mathutils

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import character_kit as kit                                        # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT = a[0], a[1]
H = float(a[2]) if len(a) > 2 else 1.6
RES = int(os.environ.get("PS_RES", "1080"))
FPS = int(os.environ.get("PS_FPS", "20"))
SPEED = float(os.environ.get("PS_SPEED", "0.85"))
os.makedirs(OUT, exist_ok=True)

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
char, rig = kit.load_rigged_character(GLB, "hero", height=H)

me = bpy.data.meshes.new("g")
bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=80)
bm.to_mesh(me); bm.free()
go = bpy.data.objects.new("g", me); sc.collection.objects.link(go)
gm = bpy.data.materials.new("gm"); gm.use_nodes = True
nt = gm.node_tree; nt.nodes.clear()
o = nt.nodes.new("ShaderNodeOutputMaterial"); df = nt.nodes.new("ShaderNodeBsdfDiffuse")
ck = nt.nodes.new("ShaderNodeTexChecker"); ck.inputs["Scale"].default_value = 52.0
ck.inputs["Color1"].default_value = (0.53, 0.56, 0.50, 1)
ck.inputs["Color2"].default_value = (0.49, 0.52, 0.46, 1)
nt.links.new(ck.outputs["Color"], df.inputs["Color"]); nt.links.new(df.outputs["BSDF"], o.inputs["Surface"])
me.materials.append(gm)

sun = bpy.data.objects.new("s", bpy.data.lights.new("s", 'SUN'))
sun.data.energy = 3.4; sun.data.color = (1.0, 0.94, 0.86); sun.data.angle = math.radians(3)
sun.rotation_euler = (math.radians(56), 0, math.radians(34)); sc.collection.objects.link(sun)
fl = bpy.data.objects.new("f", bpy.data.lights.new("f", 'SUN'))
fl.data.energy = 0.95; fl.data.color = (0.74, 0.82, 1.0)
fl.rotation_euler = (math.radians(70), 0, math.radians(-138)); sc.collection.objects.link(fl)
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.58, 0.64, 0.72, 1)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); cam.data.lens = 55
sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = 'BLENDER_EEVEE_NEXT'
try:
    sc.eevee.taa_render_samples = int(os.environ.get("PS_SAMPLES", "96"))
    sc.eevee.use_shadows = True
    sc.eevee.use_raytracing = True
    sc.eevee.shadow_ray_count = 2
    sc.eevee.shadow_step_count = 8
except Exception:                                                   # noqa: BLE001
    pass
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = sc.render.resolution_y = RES
sc.render.fps = FPS
sc.render.image_settings.file_format = 'PNG'
sc.render.use_freestyle = True
sc.render.line_thickness = 1.0
vl = sc.view_layers[0]; vl.use_freestyle = True
fs = vl.freestyle_settings
while fs.linesets:
    fs.linesets.remove(fs.linesets[0])
ls = fs.linesets.new("c")
ls.select_by_collection = False
ls.linestyle.thickness = 1.6 * (RES / 768.0)
ls.select_silhouette = True
ls.select_external_contour = False
ls.select_border = False
ls.select_crease = False
ls.linestyle.color = (0.07, 0.05, 0.06)
ls.linestyle.use_length_min = True
ls.linestyle.length_min = 6 * (RES / 768.0)


def render_tracked(tag, f0, f1, angle_deg, dist_mul=1.9, height_mul=0.52, lens=55):
    cam.data.lens = lens
    cam.animation_data_clear()
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        p = (rig.matrix_world @ rig.pose.bones["hips"].matrix).translation.copy()
        ctr = mathutils.Vector((p.x, p.y, H * height_mul))
        ang = math.radians(angle_deg)
        d = dist_mul * H
        cam.location = (ctr.x + d * math.sin(ang), ctr.y - d * math.cos(ang), ctr.z + 0.10 * H)
        cam.rotation_euler = (ctr - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    d0 = os.path.join(OUT, tag)
    os.makedirs(d0, exist_ok=True)
    sc.render.filepath = os.path.join(d0, "f_")
    sc.frame_start, sc.frame_end = f0, f1
    bpy.ops.render.render(animation=True)
    print("PS shot", tag, f1 - f0 + 1, "frames", flush=True)


floor = lambda x, y: 0.0
shots = []
WANT = set(x for x in os.environ.get("PS_SHOTS", "walk,turn,idle,close").split(",") if x)

# 1. walk across, seen from the side-front
N = 96
dist = SPEED * H * (N / float(FPS))
rig.animation_data_clear()
kit.apply_walk(rig, kit.path_fn_from_points([(0.0, 0.0), (0.0, -dist)], floor), 1, N, fps=FPS)
if "walk" in WANT: render_tracked("walk", 1, N, 62)
shots.append(("walk", N))

# 2. walk a curve, so the turn is carried by the body
N2 = 104
rig.animation_data_clear()
kit.apply_walk(rig, kit.path_fn_from_points(
    [(0.0, 0.0), (0.0, -2.2), (1.6, -4.0), (3.4, -4.6)], floor), 1, N2, fps=FPS)
if "turn" in WANT: render_tracked("turn", 1, N2, 30)
shots.append(("turn", N2))

# 3. idle with gestures
N3 = 110
rig.animation_data_clear()
kit.apply_idle(rig, 1, N3, (0.0, 0.0, 0.0), math.pi, fps=FPS,
               gestures=[(14, 40, "nod"), (52, 84, "hand_raise"), (90, 108, "weight_shift")])
if "idle" in WANT: render_tracked("idle", 1, N3, 24, dist_mul=1.75)
shots.append(("idle", N3))

# 4. close idle, head and shoulders
N4 = 80
rig.animation_data_clear()
kit.apply_idle(rig, 1, N4, (0.0, 0.0, 0.0), math.pi, fps=FPS,
               gestures=[(10, 36, "look_away"), (46, 74, "lean_in")])
if "close" in WANT: render_tracked("close", 1, N4, 34, dist_mul=0.95, height_mul=0.80, lens=75)
shots.append(("close", N4))

print("PS_DONE", ",".join("%s:%d" % s for s in shots), flush=True)
