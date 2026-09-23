"""
TALK on a Rigify-fitted character: the jaw opens geometrically from the audio, the
painted visemes and expressions ride on top, the body idles underneath.

Drives, per frame at the audio's own rate:
  jaw_master rotation  <- jawOpen + mouthLowerDown (the two channels LAM voices opening with)
  texture visemes      <- the 6-way mouth switch already derived from the same curves
  texture blink        <- eyeBlink
  texture expressions  <- browInnerUp -> surprise, mouthSmile -> smile, browDown -> angry
  head / chest         <- a breath and slow sway, and a nod on stressed syllables

  blender -b <fit_face.blend> --python rigify_talk.py -- <lam.json> <vis.npy> <blink.npy> <wav> <facesdir> <facename> <outdir>
Env: RT_RES (1080), RT_FPS (16, must match the npy rate), RT_FRAMES (cap)
"""
import sys, os, math, json
import bpy, mathutils
import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
LAM, VIS, BLINK, WAV, FDIR, FNAME, OUT = a[:7]
RES = int(os.environ.get("RT_RES", "1080")); FPS = int(os.environ.get("RT_FPS", "16"))
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import character_kit as kit                                        # noqa: E402

sc = bpy.context.scene; sc.render.fps = FPS
rig = bpy.data.objects["rig"]; char = bpy.data.objects["hero"]; pb = rig.pose.bones
zs = [(char.matrix_world @ v.co).z for v in char.data.vertices]; H = max(zs) - min(zs)

d = json.load(open(LAM)); names = d["names"]
frames = d["frames"]
W = np.array([[float(fr.get("weights", fr)[k] if isinstance(fr.get("weights", fr), dict) else fr["weights"][i])
               for i, k in enumerate(names)] for fr in frames], dtype=np.float32) if isinstance(frames[0], dict) else np.array(frames, dtype=np.float32)
src_fps = float(d.get("metadata", {}).get("fps", 30))
vis = np.load(VIS); blink = np.load(BLINK)
n = min(len(vis), int(os.environ.get("RT_FRAMES", "100000")))
def ch(k):
    if k not in names:
        return np.zeros(n)
    c = W[:, names.index(k)]
    idx = np.clip((np.arange(n) * src_fps / FPS).astype(int), 0, len(c) - 1)
    return c[idx]
jaw = np.clip(0.55 * ch("jawOpen") / max(1e-3, ch("jawOpen").max()) + 0.45 * np.maximum(ch("mouthLowerDownLeft"), ch("mouthLowerDownRight")) / max(1e-3, np.maximum(ch("mouthLowerDownLeft"), ch("mouthLowerDownRight")).max()), 0, 1)
smile = np.maximum(ch("mouthSmileLeft"), ch("mouthSmileRight")); brow_up = ch("browInnerUp"); brow_dn = np.maximum(ch("browDownLeft"), ch("browDownRight"))
def smooth(x, k=3):
    return np.convolve(np.pad(x, (k, k), mode='edge'), np.ones(2 * k + 1) / (2 * k + 1), mode='valid')
jaw = smooth(jaw, 1)

# material: cel + face variants (painted in this mesh's own atlas)
img = None
for m in char.data.materials:
    if m and m.use_nodes:
        for nd in m.node_tree.nodes:
            if nd.type == 'TEX_IMAGE' and nd.image: img = nd.image
if img is not None and char.data.uv_layers:
    char.data.materials.clear(); char.data.materials.append(kit.cel_material("hero", img, char.data.uv_layers[0].name))
ctrl = kit.enable_face_variants(char, FNAME, FDIR)

# stage
for o in list(sc.objects):
    if o.type in ('LIGHT', 'CAMERA'): bpy.data.objects.remove(o, do_unlink=True)
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", 'SUN')); sun.data.energy = 3.4; sun.data.color = (1.0, 0.94, 0.86)
sun.rotation_euler = (math.radians(56), 0, math.radians(30)); sc.collection.objects.link(sun)
fl = bpy.data.objects.new("f", bpy.data.lights.new("f", 'SUN')); fl.data.energy = 1.0; fl.data.color = (0.74, 0.82, 1.0)
fl.rotation_euler = (math.radians(68), 0, math.radians(-135)); sc.collection.objects.link(fl)
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.60, 0.66, 1)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); cam.data.lens = float(os.environ.get("RT_LENS", "70"))
sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = 'BLENDER_EEVEE_NEXT'; sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = sc.render.resolution_y = RES
try:
    sc.eevee.taa_render_samples = 96; sc.eevee.use_shadows = True
except Exception: pass                                              # noqa: BLE001
meta = bpy.data.objects.get("metarig")
if meta: meta.hide_render = True
head_z = min(zs) + float(os.environ.get("RT_HEAD", "0.79")) * H     # centre between eyes and mouth, not on the hair
ctr = mathutils.Vector((0, 0, head_z))

# animate
rig.animation_data_clear()
for b in pb:
    b.rotation_mode = 'XYZ'; b.rotation_euler = (0, 0, 0); b.location = (0, 0, 0)
for side in ("L", "R"):
    pb["upper_arm_parent." + side]["IK_FK"] = 1.0
keys = ("m1", "m2", "m3", "m4", "m5")
for i in range(n):
    f = i + 1; t = i / FPS
    pb["jaw_master"].rotation_euler = (math.radians(24) * float(jaw[i]), 0, 0)
    pb["jaw_master"].keyframe_insert("rotation_euler", frame=f)
    col = int(vis[i]); sel = None if col == 0 else "m%d" % col
    for k in keys:
        ctrl[k].default_value = 1.0 if k == sel else 0.0; ctrl[k].keyframe_insert("default_value", frame=f)
    ctrl["blink"].default_value = float(blink[i]); ctrl["blink"].keyframe_insert("default_value", frame=f)
    for ename, v in (("e_smile", smile[i]), ("e_surprise", brow_up[i]), ("e_angry", brow_dn[i])):
        if ename in ctrl:
            ctrl[ename].default_value = float(min(1.0, v * 1.4)); ctrl[ename].keyframe_insert("default_value", frame=f)
    # body: breath, sway, a nod that follows the jaw envelope
    tb = 2 * math.pi * 0.22 * t; ts = 2 * math.pi * 0.07 * t
    pb["chest"].rotation_euler = (0.02 * math.sin(tb), 0, 0.012 * math.sin(ts)); pb["chest"].keyframe_insert("rotation_euler", frame=f)
    pb["head"].rotation_euler = (0.05 * float(jaw[i]) + 0.01 * math.sin(tb), 0.03 * math.sin(ts * 1.3), 0.06 * math.sin(ts))
    pb["head"].keyframe_insert("rotation_euler", frame=f)
    pb["neck"].rotation_euler = (0.02 * float(jaw[i]), 0, 0.03 * math.sin(ts)); pb["neck"].keyframe_insert("rotation_euler", frame=f)
    for side, sg in (("L", 1), ("R", -1)):
        pb["upper_arm_fk." + side].rotation_euler = (0.02 * math.sin(tb + sg), 0, 0); pb["upper_arm_fk." + side].keyframe_insert("rotation_euler", frame=f)
nt = ctrl["_tree"]
if nt.animation_data and nt.animation_data.action:
    cont = {ctrl[k].path_from_id("default_value") for k in keys + ("blink",)}
    for fc in nt.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'CONSTANT' if fc.data_path in cont else 'BEZIER'
# camera: slow drift, rig faces -Y so the camera sits at -Y
for i in range(n):
    f = i + 1; u = i / max(1, n - 1)
    ang = math.radians(-12 + 24 * u); dd = 0.62 * H
    cam.location = (ctr.x + dd * math.sin(ang), ctr.y - dd * math.cos(ang), ctr.z + 0.015 * H)
    cam.rotation_euler = (ctr - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
    cam.keyframe_insert("location", frame=f); cam.keyframe_insert("rotation_euler", frame=f)
sc.frame_start, sc.frame_end = 1, n
sc.render.filepath = os.path.join(OUT, "t_"); sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(animation=True)
print("RT_DONE", OUT, n, "frames; jaw max %.2f" % float(jaw.max()), flush=True)
