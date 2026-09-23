"""
Face rig check on a Rigify-fitted character with the face rig: lists the face controls,
then renders the neutral face and a battery of poses (jaw open, lids closed, brows up,
brows down, lip corners up, lip corners down, eyes look left) as a sheet.

  blender -b <fit_face.blend> --python rigify_face_check.py -- <out.png>
"""
import sys, os, math
import bpy, mathutils

OUT = sys.argv[sys.argv.index("--") + 1]
sc = bpy.context.scene
rig = bpy.data.objects["rig"]; char = bpy.data.objects["hero"]
pb = rig.pose.bones
names = {b.name for b in pb}
ctrl = sorted(n for n in names if not n.startswith(("DEF-", "ORG-", "MCH-", "VIS_")) and any(
    k in n for k in ("jaw", "lip", "lid", "brow", "eye", "teeth", "tongue", "nose", "chin", "cheek", "mouth")))
print("FC controls", len(ctrl)); print(" ".join(ctrl), flush=True)
TMP = "/workspace/loopwork/rigify/tmp_face"; os.makedirs(TMP, exist_ok=True)
for o in list(sc.objects):
    if o.type in ('LIGHT', 'CAMERA'):
        bpy.data.objects.remove(o, do_unlink=True)
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", 'SUN')); sun.data.energy = 3.0
sun.rotation_euler = (math.radians(55), 0, math.radians(20)); sc.collection.objects.link(sun)
fl = bpy.data.objects.new("f", bpy.data.lights.new("f", 'SUN')); fl.data.energy = 1.2
fl.rotation_euler = (math.radians(70), 0, math.radians(-140)); sc.collection.objects.link(fl)
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.58, 0.62, 1)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); cam.data.lens = 85
sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = 'BLENDER_EEVEE_NEXT'; sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = sc.render.resolution_y = 520
head = rig.matrix_world @ rig.data.bones["DEF-spine.006"].head_local if "DEF-spine.006" in rig.data.bones else None
zs = [(char.matrix_world @ v.co).z for v in char.data.vertices]
ctr = mathutils.Vector((0, 0, min(zs) + 0.87 * (max(zs) - min(zs))))
cam.location = (ctr.x + 0.35, ctr.y - 1.15, ctr.z + 0.02)
cam.rotation_euler = (ctr - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
meta = bpy.data.objects.get("metarig")
if meta: meta.hide_render = True


def has(*c):
    return next((x for x in c if x in names), None)


def reset():
    for b in pb:
        b.rotation_mode = 'XYZ'; b.rotation_euler = (0, 0, 0); b.location = (0, 0, 0); b.scale = (1, 1, 1)


def move(name, dx=0, dy=0, dz=0):
    if name and name in pb:
        pb[name].location = (pb[name].location.x + dx, pb[name].location.y + dy, pb[name].location.z + dz)


def rot(name, rx=0, ry=0, rz=0):
    if name and name in pb:
        pb[name].rotation_euler = (math.radians(rx), math.radians(ry), math.radians(rz))


S = float(os.environ.get("FC_S", "0.012"))      # move size in metres; the face is ~0.45 m tall
JAW = float(os.environ.get("FC_JAW", "18"))
POSES = {
    "neutral": lambda: None,
    "jaw_open": lambda: rot(has("jaw_master"), rx=JAW),
    "lids_closed": lambda: [move(has("lid.T.L.002"), dz=-S * 1.2), move(has("lid.T.R.002"), dz=-S * 1.2),
                            move(has("lid.T.L.001"), dz=-S), move(has("lid.T.R.001"), dz=-S),
                            move(has("lid.T.L.003"), dz=-S), move(has("lid.T.R.003"), dz=-S)],
    "brows_up": lambda: [move(has("brow.T.L.002"), dz=S * 1.5), move(has("brow.T.R.002"), dz=S * 1.5),
                         move(has("brow.T.L.001"), dz=S), move(has("brow.T.R.001"), dz=S),
                         move(has("brow.T.L.003"), dz=S), move(has("brow.T.R.003"), dz=S)],
    "brows_down": lambda: [move(has("brow.T.L.003"), dz=-S * 1.3), move(has("brow.T.R.003"), dz=-S * 1.3),
                           move(has("brow.T.L.002"), dz=-S * 0.6), move(has("brow.T.R.002"), dz=-S * 0.6)],
    "smile": lambda: [move(has("lips.L"), dx=S * 1.2, dz=S), move(has("lips.R"), dx=-S * 1.2, dz=S)],
    "frown": lambda: [move(has("lips.L"), dz=-S), move(has("lips.R"), dz=-S)],
    "look_left": lambda: move(has("eyes", "eye_common"), dx=S * 2.5),
}
panels = []
for tag, fn in POSES.items():
    reset(); fn(); bpy.context.view_layer.update()
    sc.render.filepath = os.path.join(TMP, tag); bpy.ops.render.render(write_still=True)
    panels.append((tag, os.path.join(TMP, tag + ".png")))
sys.path.append("/workspace/venv/lib/python3.11/site-packages")
from PIL import Image, ImageDraw, ImageFont                        # noqa: E402
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
R = 520; cols = 4; rows = (len(panels) + cols - 1) // cols
sheet = Image.new("RGB", (R * cols, (R + 24) * rows), (16, 16, 20)); d = ImageDraw.Draw(sheet)
for i, (tag, p) in enumerate(panels):
    x, y = (i % cols) * R, (i // cols) * (R + 24)
    sheet.paste(Image.open(p).convert("RGB"), (x, y + 24)); d.text((x + 8, y + 4), tag, font=font, fill=(255, 232, 120))
sheet.save(OUT); print("FC_DONE", OUT, flush=True)
