"""
BIND A/B — the same rigged GLB loaded under different skinning options, posed
identically, rendered side by side. The question it answers: is the arm damage
coming from UniRig's predicted weights, from the A-pose bake that runs through
them, or from neither.

Each variant renders: rest (front), rest (3/4), and an arms-down walk-ish pose.

  blender -b --factory-startup --python bind_ab.py -- <rigged.glb> <out.png> [height=1.6]
Variants are chosen by BIND_AB, a comma list of label=ENV;ENV settings, e.g.
  BIND_AB="raw=CHAR_WSMOOTH:0|CHAR_CSMOOTH:0,smooth=CHAR_WSMOOTH:0.5,auto=CHAR_REBIND:auto"
"""
import sys, os, math
import bpy, mathutils

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
argv = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT = argv[0], argv[1]
H = float(argv[2]) if len(argv) > 2 else 1.6
SPEC = os.environ.get("BIND_AB", "raw=CHAR_WSMOOTH:0|CHAR_CSMOOTH:0,smooth=CHAR_WSMOOTH:0.5,auto=CHAR_REBIND:auto|CHAR_WSMOOTH:0.5")
TMP = "/workspace/loopwork/bind_ab"
os.makedirs(TMP, exist_ok=True)

POSES = [("rest_front", 0.0, []),
         ("rest_34", 38.0, []),
         ("stride", 20.0, [("thigh.L", 'X', -32), ("thigh.R", 'X', 30), ("shin.L", 'X', 18),
                           ("arm.L", 'X', 26), ("arm.R", 'X', -26), ("fore.L", 'X', -22), ("fore.R", 'X', -22)])]

sc = bpy.context.scene
rows = []
for chunk in SPEC.split(","):
    label, _, envs = chunk.partition("=")
    for kv in envs.split("|"):
        if not kv:
            continue
        k, _, v = kv.partition(":")
        os.environ[k] = v
    # defaults for anything the variant did not set
    os.environ.setdefault("CHAR_WSMOOTH", "0.5")
    os.environ.setdefault("CHAR_CSMOOTH", "0.45")
    for ob in list(sc.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)
    import importlib
    import character_kit as kit
    importlib.reload(kit)
    char, rig = kit.load_rigged_character(GLB, "ab", height=H)

    sun = bpy.data.objects.new("s", bpy.data.lights.new("s", 'SUN')); sun.data.energy = 3.2
    sun.rotation_euler = (math.radians(58), 0, math.radians(35)); sc.collection.objects.link(sun)
    fl = bpy.data.objects.new("f", bpy.data.lights.new("f", 'SUN')); fl.data.energy = 1.1
    fl.rotation_euler = (math.radians(70), 0, math.radians(-140)); sc.collection.objects.link(fl)
    wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
    wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.56, 0.59, 0.64, 1)
    cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); cam.data.lens = 60
    sc.collection.objects.link(cam); sc.camera = cam
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.view_settings.view_transform = 'Standard'
    sc.render.resolution_x = sc.render.resolution_y = 560

    shots = []
    for tag, yaw, rots in POSES:
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='POSE')
        for pb in rig.pose.bones:
            pb.rotation_mode = 'XYZ'
            pb.rotation_euler = (0, 0, 0)
        for bone, axis, deg in rots:
            pb = rig.pose.bones.get(bone)
            if pb is None:
                continue
            e = [0.0, 0.0, 0.0]; e["XYZ".index(axis)] = math.radians(deg)
            pb.rotation_euler = e
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.update()
        ctr = mathutils.Vector((0, 0, H * 0.5))
        a = math.radians(yaw); d = 2.05 * H
        cam.location = (ctr.x + d * math.sin(a), ctr.y - d * math.cos(a), ctr.z + 0.06 * H)
        cam.rotation_euler = (ctr - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
        pth = os.path.join(TMP, "%s_%s.png" % (label, tag))
        sc.render.filepath = pth
        bpy.ops.render.render(write_still=True)
        shots.append(pth)
    rows.append((label, shots))
    print("AB variant done", label, flush=True)

sys.path.append("/workspace/venv/lib/python3.11/site-packages")
from PIL import Image, ImageDraw                                # noqa: E402
cell = Image.open(rows[0][1][0]).size
sheet = Image.new("RGB", (cell[0] * len(POSES), cell[1] * len(rows)), (26, 26, 30))
d = ImageDraw.Draw(sheet)
for r, (label, shots) in enumerate(rows):
    for c, p in enumerate(shots):
        sheet.paste(Image.open(p).convert("RGB"), (c * cell[0], r * cell[1]))
    d.text((8, r * cell[1] + 8), label, fill=(255, 235, 120))
sheet.save(OUT)
print("AB_DONE", OUT, flush=True)
