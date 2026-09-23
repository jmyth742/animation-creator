"""
Audio-driven talk on a VRM avatar: real blendshapes from the LAM ARKit curves.

Maps the 52 ARKit channels onto whatever expression keys the VRM carries (VRoid names,
Seed-san names, or ARKit names if the model has "perfect sync" shapes), by name matching.
The jaw is a shape key, the blink is a shape key, the brows are shape keys: nothing is
painted, so the head can turn and the mouth still opens.

  blender -b --python vrm_talk.py -- <in.vrm> <lam.json> <wav> <outdir> [frames=110]
Env: VT_RES (900), VT_FPS (16)
"""
import sys, os, math, json
import bpy, mathutils
import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
VRM, LAM, WAV, OUT = a[:4]
NF = int(a[4]) if len(a) > 4 else 110
RES = int(os.environ.get("VT_RES", "900")); FPS = int(os.environ.get("VT_FPS", "16"))
os.makedirs(OUT, exist_ok=True)
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.io_scene_vrm")
sc = bpy.context.scene; sc.render.fps = FPS
for o in list(sc.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.vrm(filepath=VRM)
rig = [o for o in sc.objects if o.type == 'ARMATURE'][0]
meshes = [o for o in sc.objects if o.type == 'MESH']
keys = {}
for m in meshes:
    if m.data.shape_keys:
        for k in m.data.shape_keys.key_blocks:
            keys[k.name] = k
names = {n.lower(): n for n in keys}
print("VT shape keys", len(keys), flush=True)


def find(*cands):
    for c in cands:
        for ln, n in names.items():
            if ln == c.lower():
                return n
    for c in cands:
        for ln, n in names.items():
            if c.lower() in ln:
                return n
    return None


# ARKit channel -> (weight, [candidate key names in priority order])
MAP = {
    "jawOpen":            (1.0, ["jawOpen", "lip_a", "mouth_a", "aa", "A", "mouse_open", "mouth_open"]),
    "mouthFunnel":        (1.0, ["mouthFunnel", "lip_o", "mouth_o", "oh", "O"]),
    "mouthPucker":        (1.0, ["mouthPucker", "lip_u", "mouth_u", "ou", "U"]),
    "mouthStretchLeft":   (0.8, ["mouthStretchLeft", "lip_i", "mouth_i", "ih", "I"]),
    "mouthSmileLeft":     (1.0, ["mouthSmileLeft", "mouth_smile", "face_happy", "happy", "joy"]),
    "mouthFrownLeft":     (0.8, ["mouthFrownLeft", "mouth_sad", "face_sad", "sorrow", "sad"]),
    "eyeBlinkLeft":       (1.0, ["eyeBlinkLeft", "blink_L", "eye_close", "blink"]),
    "eyeBlinkRight":      (1.0, ["eyeBlinkRight", "blink_R", "eye_close", "blink"]),
    "browInnerUp":        (1.0, ["browInnerUp", "eye_brow_up", "brow_up", "surprised"]),
    "browDownLeft":       (1.0, ["browDownLeft", "eye_brow_down", "brow_down", "angry"]),
    "eyeWideLeft":        (0.7, ["eyeWideLeft", "eye_open", "face_surprise", "surprised"]),
    "eyeLookUpLeft":      (0.8, ["eyeLookUpLeft", "look_up", "lookup"]),
    "eyeLookDownLeft":    (0.8, ["eyeLookDownLeft", "look_down", "lookdown"]),
    "eyeLookInLeft":      (0.8, ["eyeLookInLeft", "look_right", "lookright"]),
    "eyeLookOutLeft":     (0.8, ["eyeLookOutLeft", "look_left", "lookleft"]),
}
d = json.load(open(LAM)); an = d["names"]; fr = d["frames"]
W = np.array([f["weights"] for f in fr], dtype=np.float32)
src_fps = float(d.get("metadata", {}).get("fps", 30))
n = min(NF, int(len(W) * FPS / src_fps))
idx = np.clip((np.arange(n) * src_fps / FPS).astype(int), 0, len(W) - 1)
bound = {}
for ch, (gain, cands) in MAP.items():
    if ch not in an:
        continue
    k = find(*cands)
    if k:
        bound.setdefault(k, []).append((gain, W[idx, an.index(ch)]))
print("VT bound", {k: len(v) for k, v in bound.items()}, flush=True)
for k, srcs in bound.items():
    curve = np.clip(sum(g * c for g, c in srcs), 0, 1)
    # normalise the jaw-ish channels so the mouth actually opens: LAM's raw jawOpen peaks ~0.35
    if k == find("lip_a", "mouth_a", "jawOpen", "mouse_open", "aa"):
        curve = np.clip(curve / max(1e-3, np.percentile(curve, 97)), 0, 1)
    kb = keys[k]
    for i in range(n):
        kb.value = float(curve[i]); kb.keyframe_insert("value", frame=i + 1)

# head: breath and a nod on the jaw envelope, on the humanoid head bone
head = next((b for b in rig.pose.bones if b.name.lower() in ("head", "j_bip_c_head")), None)
jawk = find("lip_a", "mouth_a", "jawOpen", "mouse_open", "aa")
env = np.zeros(n)
if jawk and jawk in bound:
    env = np.clip(sum(g * c for g, c in bound[jawk]) / max(1e-3, np.percentile(sum(g * c for g, c in bound[jawk]), 97)), 0, 1)
if head:
    head.rotation_mode = 'XYZ'
    for i in range(n):
        t = i / FPS
        head.rotation_euler = (0.05 * float(env[i]) + 0.01 * math.sin(2 * math.pi * 0.22 * t), 0.03 * math.sin(2 * math.pi * 0.09 * t), 0.06 * math.sin(2 * math.pi * 0.07 * t))
        head.keyframe_insert("rotation_euler", frame=i + 1)

zs = [(m.matrix_world @ v.co).z for m in meshes for v in m.data.vertices]; H = max(zs) - min(zs)
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", 'SUN')); sun.data.energy = 3.2; sun.data.color = (1.0, 0.94, 0.86)
sun.rotation_euler = (math.radians(56), 0, math.radians(30)); sc.collection.objects.link(sun)
fl = bpy.data.objects.new("f", bpy.data.lights.new("f", 'SUN')); fl.data.energy = 1.0; fl.data.color = (0.74, 0.82, 1.0)
fl.rotation_euler = (math.radians(68), 0, math.radians(-135)); sc.collection.objects.link(fl)
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.60, 0.66, 1)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); cam.data.lens = 70; sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = 'BLENDER_EEVEE_NEXT'; sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = sc.render.resolution_y = RES
ctr = mathutils.Vector((0, 0, min(zs) + 0.86 * H))
for i in range(n):
    u = i / max(1, n - 1); ang = math.radians(-12 + 24 * u); dd = 0.55 * H
    cam.location = (ctr.x + dd * math.sin(ang), ctr.y - dd * math.cos(ang), ctr.z + 0.01 * H)
    cam.rotation_euler = (ctr - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
    cam.keyframe_insert("location", frame=i + 1); cam.keyframe_insert("rotation_euler", frame=i + 1)
sc.frame_start, sc.frame_end = 1, n
sc.render.filepath = os.path.join(OUT, "t_"); sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(animation=True)
print("VT_DONE", n, flush=True)
