"""
VISEME SHAPE KEYS on a mesh that already HAS a mouth.

Generating the character mid-speech gives real mouth topology — a lip ring with a recess
behind it — so there is nothing to cut. The base pose is open, which is the right basis:
closing a mouth by bringing existing lips together deforms far more convincingly than
tearing an opening into a sealed surface.

Keys built: mouth_closed, mouth_small, mouth_mid, mouth_wide (ee), mouth_round (oo).
Each moves the lip ring only, weighted so the effect fades out into the cheeks.

  blender -b --factory-startup --python viseme_keys.py -- <mesh.glb> <calib.json> <height> <out.glb>
Env: VK_R (0.055) mouth radius, VK_FALLOFF (1.6)
"""
import bpy, sys, os, json, math, mathutils
sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
os.environ["CHAR_NORMALFIX"] = "0"
import character_kit as kit

a = sys.argv[sys.argv.index("--") + 1:]
glb, calib_p, height, out_p = a[0], a[1], float(a[2]), a[3]
R = float(os.environ.get("VK_R", "0.055"))
FALL = float(os.environ.get("VK_FALLOFF", "1.6"))
cal = json.load(open(calib_p))

sc = bpy.context.scene
for o in list(sc.objects):
    bpy.data.objects.remove(o, do_unlink=True)
ch = kit.load_character(glb, "v", height=height)
wm = ch.matrix_world
MX, MZ = cal.get("face_x", 0.0), cal["mouth_z"]

co = [wm @ v.co for v in ch.data.vertices]
band = [c for c in co if abs(c.x - MX) < R and abs(c.z - MZ) < R]
front_y = min(c.y for c in band) if band else min(c.y for c in co)
centre = mathutils.Vector((MX, front_y, MZ))
print("VK centre %.4f %.4f %.4f  r=%.3f" % (centre.x, centre.y, centre.z, R), flush=True)

# weight each vertex by distance from the mouth, so lips move fully and cheeks barely
idx_w = {}
for i, c in enumerate(co):
    d = ((c.x - centre.x) ** 2 + ((c.z - centre.z) / 0.75) ** 2) ** 0.5
    if d < R * FALL and c.y < centre.y + R * 1.2:
        idx_w[i] = max(0.0, 1.0 - (d / (R * FALL)) ** 2)
print("VK affected verts:", len(idx_w), flush=True)
if len(idx_w) < 20:
    sys.exit("VK FAILED: too few verts near the mouth — raise VK_R")

if ch.data.shape_keys is None:
    ch.shape_key_add(name="Basis", from_mix=False)
basis = [v.co.copy() for v in ch.data.vertices]

# (vertical scale about the mouth centre, horizontal scale, lip-seam pull)
SHAPES = {
    "mouth_closed": (0.05, 0.95, 1.0),   # lips together: the resting state for speech
    "mouth_small":  (0.35, 0.90, 0.5),
    "mouth_mid":    (0.70, 1.00, 0.2),
    "mouth_wide":   (0.45, 1.35, 0.3),   # ee
    "mouth_round":  (0.85, 0.65, 0.1),   # oo
}
for nm, (vs_, hs, seam) in SHAPES.items():
    sk = ch.shape_key_add(name=nm, from_mix=False)
    for i, w in idx_w.items():
        p = wm @ basis[i]
        dz = p.z - centre.z
        dx = p.x - centre.x
        # Compute the FULLY deformed position, then blend toward it by the falloff weight.
        # Scaling the factor by the weight instead (the first version) meant the lip ring,
        # at w~0.6, only ever received ~60% of the movement, so "closed" never closed.
        fz = centre.z + dz * vs_
        fz = fz + (centre.z - fz) * seam
        fx = centre.x + dx * hs
        nz = p.z + (fz - p.z) * w
        nx = p.x + (fx - p.x) * w
        sk.data[i].co = wm.inverted() @ mathutils.Vector((nx, p.y, nz))
print("VK keys:", [k.name for k in ch.data.shape_keys.key_blocks], flush=True)

bpy.ops.object.select_all(action='DESELECT')
ch.select_set(True)
bpy.context.view_layer.objects.active = ch
bpy.ops.export_scene.gltf(filepath=out_p, use_selection=True, export_morph=True)
print("VK_DONE", out_p, flush=True)
