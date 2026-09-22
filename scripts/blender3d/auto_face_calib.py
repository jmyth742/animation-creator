"""
AUTO FACE CALIBRATION — find the mouth and eyes without a human reading a grid.

Every character so far needed me to render a measured grid and read the mouth position
off it by eye, which blocks any unattended run. On a textured anime head the features
are strongly coloured: the mouth is the saturated red/pink region in the lower face, and
the eyes are the dark saturated pair above it. That is enough to locate them reliably.

Writes <out.json> with mouth_z, eye_z, eye_x, face_x in the loader's coordinate space,
and a marked-up check image so a wrong result is obvious rather than silent.

  blender -b --factory-startup --python auto_face_calib.py -- <mesh.glb> <height> <out.json> [check.png]
"""
import bpy, sys, os, json, math, mathutils
sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
sys.path.append("/workspace/venv/lib/python3.11/site-packages")
os.environ["CHAR_NORMALFIX"] = "0"
import numpy as np
from PIL import Image, ImageDraw
import character_kit as kit

a = sys.argv[sys.argv.index("--") + 1:]
glb, height, out_json = a[0], float(a[1]), a[2]
check = a[3] if len(a) > 3 else None

sc = bpy.context.scene
for o in list(sc.objects):
    bpy.data.objects.remove(o, do_unlink=True)
ch = kit.load_character(glb, "c", height=height)
vs = [ch.matrix_world @ v.co for v in ch.data.vertices]
hi_z = max(v.z for v in vs); lo_z = min(v.z for v in vs)
xs = [v.x for v in vs]; x_c = (min(xs) + max(xs)) / 2
top = hi_z; bot = hi_z - (hi_z - lo_z) * 0.42
span = top - bot
mid = mathutils.Vector((x_c, (min(v.y for v in vs) + max(v.y for v in vs)) / 2, (top + bot) / 2))

k = bpy.data.objects.new("k", bpy.data.lights.new("k", 'SUN')); k.data.energy = 3.0
k.rotation_euler = (math.radians(60), 0, math.radians(15)); sc.collection.objects.link(k)
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.5, 0.52, 1)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); cam.data.type = 'ORTHO'
cam.data.ortho_scale = span
sc.collection.objects.link(cam); sc.camera = cam
cam.location = mid + mathutils.Vector((0, -4, 0))
cam.rotation_euler = (mid - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = sc.render.resolution_y = 700
raw = "/workspace/loopwork/afc_raw.png"
sc.render.filepath = raw
bpy.ops.render.render(write_still=True)

im = Image.open(raw).convert("RGB")
arr = np.asarray(im, dtype=np.float32) / 255.0
H, W, _ = arr.shape
r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
mx = arr.max(axis=2); mn = arr.min(axis=2)
sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
lum = arr @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
face = (xx > W * 0.2) & (xx < W * 0.8)

# MOUTH: saturated red/pink, in the lower half of the framed head
mouth = face & (yy > H * 0.55) & (yy < H * 0.92) & (r > g * 1.25) & (r > b * 1.25) & (sat > 0.25)
# EYES: the WHITE of the eye, not the dark parts. Looking for dark saturated pixels finds
# the eyebrows, which sit above the eyes and are darker than them (review/autocalib_check.png,
# first attempt). Anime eyes have large bright sclera and highlights, and nothing else on
# the face is both that bright and that desaturated.
eyes = face & (yy > H * 0.38) & (yy < H * 0.78) & (lum > 0.82) & (sat < 0.18)
if eyes.sum() < 60:                    # e.g. eyes closed or a very dark design
    eyes = face & (yy > H * 0.38) & (yy < H * 0.78) & (lum < 0.40) & (sat > 0.25)
    print("AFC note: sclera not found, falling back to dark-iris detection", flush=True)

def centroid(mask):
    ys, xs_ = np.where(mask)
    return (None, None) if len(xs_) < 30 else (xs_.mean() / W, ys.mean() / H)

mx_f, my_f = centroid(mouth)
if my_f is None:                       # fall back to anatomy if colour detection fails
    mx_f, my_f = 0.5, 0.72
    print("AFC WARNING: no mouth found by colour, using fallback", flush=True)
ex_f, ey_f = centroid(eyes)
if ey_f is None:
    ex_f, ey_f = 0.5, 0.55
    print("AFC WARNING: no eyes found by colour, using fallback", flush=True)

# eye separation: split the eye mask left/right of centre
ys, xs_ = np.where(eyes)
if len(xs_) > 60:
    l = xs_[xs_ < W * 0.5]; rr = xs_[xs_ >= W * 0.5]
    sep = (rr.mean() - l.mean()) / W / 2 if len(l) > 10 and len(rr) > 10 else 0.10
else:
    sep = 0.10

z_of = lambda f: top - f * span
x_of = lambda f: x_c + (f - 0.5) * span
cal = {"mouth_z": round(z_of(my_f), 4),
       "eye_z": round(z_of(ey_f), 4),
       "eye_x": round(sep * span, 4),
       "face_x": round(x_of(mx_f), 4)}
json.dump(cal, open(out_json, "w"), indent=1)
print("AFC mouth frac %.3f,%.3f  eyes frac %.3f,%.3f  sep %.3f" % (mx_f, my_f, ex_f, ey_f, sep), flush=True)
print("AFC", json.dumps(cal), flush=True)

if check:
    d = ImageDraw.Draw(im)
    d.ellipse([mx_f*W-9, my_f*H-9, mx_f*W+9, my_f*H+9], outline=(255, 40, 40), width=3)
    d.ellipse([(ex_f-sep)*W-9, ey_f*H-9, (ex_f-sep)*W+9, ey_f*H+9], outline=(40, 160, 255), width=3)
    d.ellipse([(ex_f+sep)*W-9, ey_f*H-9, (ex_f+sep)*W+9, ey_f*H+9], outline=(40, 160, 255), width=3)
    im.save(check)
    print("AFC check", check, flush=True)
print("AFC_DONE", flush=True)
