"""
DEFORMATION GATE — the acceptance test the asset spec calls for and we never ran.

Transferred skin weights can look right in a neutral pose and collapse the moment a
joint bends. This poses the extremes that break first and renders a contact sheet, so
a bad skin is caught before an episode is rendered rather than after.

Poses, one per panel: neutral, shoulder to 90, elbow to 90, knee to 90, head turned 45.

Run:
  blender -b --factory-startup --python deform_gate.py -- <rigged.glb> <name> <height> <out.png>
"""
import sys
import os
import math
import bpy
import mathutils

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import character_kit as kit                                    # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
glb, name, height, out_png = argv[0], argv[1], float(argv[2]), argv[3]
TMP = "/workspace/loopwork/deform_gate"
os.makedirs(TMP, exist_ok=True)

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
char, rig = kit.load_rigged_character(glb, name, height=height)

sun = bpy.data.objects.new("sun", bpy.data.lights.new("s", 'SUN'))
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(55), 0, math.radians(35))
sc.collection.objects.link(sun)
wd = bpy.data.worlds.new("w")
sc.world = wd
wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.56, 0.60, 1)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("c"))
sc.collection.objects.link(cam)
sc.camera = cam
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x, sc.render.resolution_y = 520, 760

# frame the whole figure from the front
zs = [(char.matrix_world @ v.co).z for v in char.data.vertices]
mx, mn = max(zs), min(zs)
mid = (mx + mn) / 2
cam.data.lens = 50
cam.location = (0, 3.2, mid)   # kit characters face +Y; from -Y this framed the back
cam.rotation_euler = (mathutils.Vector((0, 0, mid)) - cam.location).to_track_quat('-Z', 'Y').to_euler()

# GATE_ANGLE lets the same battery run at the range animation actually uses (~30 deg) as
# well as at the extreme (90). A rig can be perfectly serviceable for a walk and still
# shear at 90, so the extreme alone is not a verdict.
A = float(os.environ.get("GATE_ANGLE", "90"))
POSES = [
    ("neutral", []),
    ("shoulder", [("arm.L", 'Z', A), ("arm.R", 'Z', -A)]),
    ("elbow", [("fore.L", 'X', -A), ("fore.R", 'X', -A)]),
    ("knee", [("shin.L", 'X', A), ("shin.R", 'X', A)]),
    ("head", [("head", 'Z', A * 0.5)]),
]

bpy.context.view_layer.objects.active = rig
rendered = []
for tag, rots in POSES:
    bpy.ops.object.mode_set(mode='POSE')
    for pb in rig.pose.bones:
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler = (0, 0, 0)
    missing = []
    for bone, axis, deg in rots:
        pb = rig.pose.bones.get(bone)
        if pb is None:
            missing.append(bone)
            continue
        idx = "XYZ".index(axis)
        e = [0.0, 0.0, 0.0]
        e[idx] = math.radians(deg)
        pb.rotation_euler = e
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.update()
    path = os.path.join(TMP, "%s_%s.png" % (name, tag))
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    rendered.append(path)
    print("GATE", name, tag, "missing" if missing else "ok", missing, flush=True)

# contact sheet
sys.path.append("/workspace/venv/lib/python3.11/site-packages")
from PIL import Image, ImageDraw                              # noqa: E402
ims = [Image.open(p).convert("RGB") for p in rendered]
w, h = ims[0].size
sheet = Image.new("RGB", (w * len(ims), h), (30, 30, 34))
d = ImageDraw.Draw(sheet)
for i, (im, (tag, _)) in enumerate(zip(ims, POSES)):
    sheet.paste(im, (i * w, 0))
    d.text((i * w + 8, 8), tag, fill=(255, 240, 120))
sheet.save(out_png)
print("GATE_DONE", out_png, flush=True)
