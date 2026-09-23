"""
IK WALK on a Rigify-fitted character: feet PLANTED, no sliding.

The kit's walk was sinusoids on FK bones and its feet skated 80 mm per frame. On the
Rigify rig the feet are IK targets, so a stride is authored as contact positions on the
ground: each foot is keyed to a fixed world point for the whole stance phase, lifts
along an arc during swing, and lands at the next contact. Foot slide is zero by
construction. The torso rides forward continuously with a bob at the double-support
beats; the hips and chest counter-rotate; the arms swing FK opposite to the legs.

  blender -b <fit.blend> --python rigify_walk.py -- <outdir> [frames=96] [speed=0.85 heights/s]
Env: RW_RES (1080), RW_FPS (20), RW_STRIDE (0.62 of body height per full cycle),
     RW_LIFT (0.06), RW_SHOTS (walk,turn,idle), RW_FACES (face set name, optional)
"""
import sys, os, math
import bpy, bmesh, mathutils

a = sys.argv[sys.argv.index("--") + 1:]
OUT = a[0]
NF = int(a[1]) if len(a) > 1 else 96
SPEED = float(a[2]) if len(a) > 2 else 0.85
RES = int(os.environ.get("RW_RES", "1080"))
FPS = int(os.environ.get("RW_FPS", "20"))
WANT = set(x for x in os.environ.get("RW_SHOTS", "walk,turn,idle").split(",") if x)
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import character_kit as kit                                        # noqa: E402

sc = bpy.context.scene
sc.render.fps = FPS
rig = bpy.data.objects["rig"]
char = bpy.data.objects["hero"]
pb = rig.pose.bones
zs = [(char.matrix_world @ v.co).z for v in char.data.vertices]
H = max(zs) - min(zs)
FWD = mathutils.Vector((0, -1, 0))                 # the rig faces -Y
STRIDE = float(os.environ.get("RW_STRIDE", "0.62")) * H       # one full cycle (two steps)
LIFT = float(os.environ.get("RW_LIFT", "0.06")) * H
# cel look
img = None
for m in char.data.materials:
    if m and m.use_nodes:
        for nd in m.node_tree.nodes:
            if nd.type == 'TEX_IMAGE' and nd.image:
                img = nd.image
if img is not None and char.data.uv_layers:
    char.data.materials.clear()
    char.data.materials.append(kit.cel_material("hero", img, char.data.uv_layers[0].name))
for p in char.data.polygons:
    p.use_smooth = True

# stage
for o in list(sc.objects):
    if o.type in ('LIGHT', 'CAMERA'):
        bpy.data.objects.remove(o, do_unlink=True)
me = bpy.data.meshes.new("g"); bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=80)
bm.to_mesh(me); bm.free(); go = bpy.data.objects.new("g", me); sc.collection.objects.link(go)
gm = bpy.data.materials.new("gm"); gm.use_nodes = True; nt = gm.node_tree; nt.nodes.clear()
o_ = nt.nodes.new("ShaderNodeOutputMaterial"); df = nt.nodes.new("ShaderNodeBsdfDiffuse")
ck = nt.nodes.new("ShaderNodeTexChecker"); ck.inputs["Scale"].default_value = 52.0
ck.inputs["Color1"].default_value = (0.53, 0.56, 0.50, 1); ck.inputs["Color2"].default_value = (0.49, 0.52, 0.46, 1)
nt.links.new(ck.outputs["Color"], df.inputs["Color"]); nt.links.new(df.outputs["BSDF"], o_.inputs["Surface"])
me.materials.append(gm)
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", 'SUN')); sun.data.energy = 3.4
sun.data.color = (1.0, 0.94, 0.86); sun.data.angle = math.radians(3)
sun.rotation_euler = (math.radians(56), 0, math.radians(34)); sc.collection.objects.link(sun)
fl = bpy.data.objects.new("f", bpy.data.lights.new("f", 'SUN')); fl.data.energy = 0.95
fl.data.color = (0.74, 0.82, 1.0); fl.rotation_euler = (math.radians(70), 0, math.radians(-138)); sc.collection.objects.link(fl)
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.58, 0.64, 0.72, 1)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); cam.data.lens = 55
sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = 'BLENDER_EEVEE_NEXT'; sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = sc.render.resolution_y = RES
sc.render.image_settings.file_format = 'PNG'
try:
    sc.eevee.taa_render_samples = 96; sc.eevee.use_shadows = True; sc.eevee.use_raytracing = True
except Exception:                                                   # noqa: BLE001
    pass
sc.render.use_freestyle = True; sc.render.line_thickness = 1.0
vl = sc.view_layers[0]; vl.use_freestyle = True; fs = vl.freestyle_settings
while fs.linesets:
    fs.linesets.remove(fs.linesets[0])
ls = fs.linesets.new("c"); ls.select_by_collection = False
ls.linestyle.thickness = 1.6 * RES / 768.0; ls.select_silhouette = True; ls.select_external_contour = False
ls.select_border = False; ls.select_crease = False; ls.linestyle.color = (0.07, 0.05, 0.06)
ls.linestyle.use_length_min = True; ls.linestyle.length_min = 6 * RES / 768.0
meta = bpy.data.objects.get("metarig")
if meta:
    meta.hide_render = True


def clear_anim():
    rig.animation_data_clear()
    for b in pb:
        b.rotation_mode = 'XYZ'; b.rotation_euler = (0, 0, 0); b.location = (0, 0, 0)
    for side in ("L", "R"):
        pb["thigh_parent." + side]["IK_FK"] = 0.0
        pb["upper_arm_parent." + side]["IK_FK"] = 1.0
    rig.location = (0, 0, 0); rig.rotation_euler = (0, 0, 0)


def rest_world(name):
    return rig.matrix_world @ rig.data.bones[name].head_local


def key_loc_world(name, world, f):
    """Key a control's location so that its head lands at `world` (rig space == world here)."""
    b = pb[name]
    rest = rig.data.bones[name]
    local = rest.matrix_local.inverted() @ (rig.matrix_world.inverted() @ world)
    b.location = local
    b.keyframe_insert("location", frame=f)


def key_rot(name, eul, f):
    pb[name].rotation_euler = eul
    pb[name].keyframe_insert("rotation_euler", frame=f)


def walk(f0, f1, heading_fn, speed_mps):
    """heading_fn(t)->(x, y, yaw) of the root path at time t seconds."""
    clear_anim()
    dur = (f1 - f0) / FPS
    cycle = STRIDE / speed_mps                                  # seconds per full cycle
    foot_rest = {s: rest_world("foot_ik." + s) for s in ("L", "R")}
    for f in range(f0, f1 + 1):
        t = (f - f0) / FPS
        x, y, yaw = heading_fn(t)
        ph = (t / cycle) % 1.0
        fwd = mathutils.Vector((-math.sin(yaw), -math.cos(yaw), 0))     # -Y at yaw 0
        side = mathutils.Vector((math.cos(yaw), -math.sin(yaw), 0))
        # torso: continuous, with a bob and a slight lean
        bob = -0.018 * H * abs(math.sin(2 * math.pi * ph))
        rig.location = (x, y, bob); rig.rotation_euler = (0, 0, yaw)
        rig.keyframe_insert("location", frame=f); rig.keyframe_insert("rotation_euler", frame=f)
        key_rot("torso", (math.radians(4), 0, 0), f)
        key_rot("hips", (0, 0, math.radians(-6) * math.sin(2 * math.pi * ph)), f)
        key_rot("chest", (0, 0, math.radians(5) * math.sin(2 * math.pi * ph)), f)
        key_rot("head", (0, 0, math.radians(-2) * math.sin(2 * math.pi * ph)), f)
        # feet: contact positions along the path, planted for the stance half of the cycle
        for s, off in (("L", 0.0), ("R", 0.5)):
            pl = (ph + off) % 1.0
            # this foot's current stride index and its contact point
            k = math.floor((t / cycle) + off)
            def contact(idx):
                tt = (idx - off) * cycle                         # time the contact was planted
                cx, cy, cyaw = heading_fn(max(0.0, tt))
                fw = mathutils.Vector((-math.sin(cyaw), -math.cos(cyaw), 0))
                sd = mathutils.Vector((math.cos(cyaw), -math.sin(cyaw), 0))
                lat = foot_rest[s].x
                return mathutils.Vector((cx, cy, 0)) + fw * (STRIDE * 0.25) + sd * lat
            if pl < 0.5:                                        # stance: planted
                pos = contact(k)
                pos.z = foot_rest[s].z
            else:                                               # swing: arc to the next contact
                u = (pl - 0.5) / 0.5
                ue = u * u * (3 - 2 * u)
                p0, p1 = contact(k), contact(k + 1)
                pos = p0.lerp(p1, ue)
                pos.z = foot_rest[s].z + LIFT * math.sin(math.pi * u)
            # express in rig-local space (rig is translated/yawed): the IK control lives
            # under the root, so subtract the object transform
            local_world = rig.matrix_world.inverted() @ pos if False else pos
            Mw = mathutils.Matrix.Translation((x, y, bob)) @ mathutils.Matrix.Rotation(yaw, 4, 'Z')
            key_loc_world("foot_ik." + s, Mw.inverted() @ pos, f)
            # heel-toe roll through the stance
            roll = 0.0
            if pl < 0.12:
                roll = math.radians(-14) * (1 - pl / 0.12)
            elif pl > 0.38 and pl < 0.5:
                roll = math.radians(22) * ((pl - 0.38) / 0.12)
            key_rot("foot_ik." + s, (roll, 0, 0), f)
        # arms FK, counter-phased to the legs
        for s, sg in (("L", 1), ("R", -1)):
            sw = math.sin(2 * math.pi * ph) * sg
            key_rot("upper_arm_fk." + s, (math.radians(22) * sw, 0, math.radians(-8) * sg), f)
            key_rot("forearm_fk." + s, (math.radians(18 + 14 * max(0.0, -sw)), 0, 0), f)


def render_tracked(tag, f0, f1, angle_deg, dist_mul=1.9, height_mul=0.52, lens=55):
    cam.data.lens = lens; cam.animation_data_clear()
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        p = (rig.matrix_world @ pb["torso"].head)
        ctr = mathutils.Vector((p.x, p.y, H * height_mul)); ang = math.radians(angle_deg); d = dist_mul * H
        cam.location = (ctr.x + d * math.sin(ang), ctr.y - d * math.cos(ang), ctr.z + 0.10 * H)
        cam.rotation_euler = (ctr - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
        cam.keyframe_insert("location", frame=f); cam.keyframe_insert("rotation_euler", frame=f)
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    d0 = os.path.join(OUT, tag); os.makedirs(d0, exist_ok=True)
    sc.render.filepath = os.path.join(d0, "f_"); sc.frame_start, sc.frame_end = f0, f1
    bpy.ops.render.render(animation=True)
    print("RW shot", tag, f1 - f0 + 1, flush=True)


def foot_slide(f0, f1):
    prev, tot, cnt = {}, 0.0, 0
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        pos = {s: (rig.matrix_world @ pb["DEF-foot." + s].head).copy() for s in ("L", "R")}
        low = min(pos, key=lambda s: pos[s].z)
        if low in prev:
            d = pos[low] - prev[low]; tot += math.hypot(d.x, d.y); cnt += 1
        prev = pos
    return 1000.0 * tot / max(1, cnt)


speed = SPEED * H
if "walk" in WANT:
    walk(1, NF, lambda t: (0.0, -speed * t, 0.0), speed)
    print("RW foot slide walk %.1f mm/frame" % foot_slide(1, NF), flush=True)
    render_tracked("walk", 1, NF, 62)
if "turn" in WANT:
    R = 1.6 * H
    def curve(t):
        s_ = speed * t; ang = s_ / R
        return (R * (1 - math.cos(ang)), -R * math.sin(ang), -ang)
    walk(1, NF, curve, speed)
    render_tracked("turn", 1, NF, 30)
print("RW_DONE", flush=True)
