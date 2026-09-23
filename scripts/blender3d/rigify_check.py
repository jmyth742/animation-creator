"""
Checks on a Rigify-fitted character: MODE=xray draws the deform bones over the mesh from
four angles; MODE=gate poses the FK controls (shoulder 45, elbow 45, knee 45, head 22)
and renders the panels. Both from the .blend rigify_fit wrote.

  blender -b <fit.blend> --python rigify_check.py -- <mode> <out.png> [angle=45]
"""
import sys, os, math
import bpy, bmesh, mathutils

a = sys.argv[sys.argv.index("--") + 1:]
MODE, OUT = a[0], a[1]
ANG = float(a[2]) if len(a) > 2 else 45.0
sc = bpy.context.scene
rig = bpy.data.objects["rig"]
char = bpy.data.objects["hero"]
TMP = "/workspace/loopwork/rigify/tmp_" + MODE
os.makedirs(TMP, exist_ok=True)

for o in list(sc.objects):
    if o.type in ('LIGHT', 'CAMERA'):
        bpy.data.objects.remove(o, do_unlink=True)
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", 'SUN')); sun.data.energy = 3.2
sun.rotation_euler = (math.radians(58), 0, math.radians(35)); sc.collection.objects.link(sun)
fl = bpy.data.objects.new("f", bpy.data.lights.new("f", 'SUN')); fl.data.energy = 1.1
fl.rotation_euler = (math.radians(70), 0, math.radians(-140)); sc.collection.objects.link(fl)
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.22, 0.23, 0.26, 1)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); cam.data.lens = 60
sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = 'BLENDER_EEVEE_NEXT'; sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = sc.render.resolution_y = 560
sc.render.image_settings.color_mode = 'RGBA'
zs = [(char.matrix_world @ v.co).z for v in char.data.vertices]
H = max(zs) - min(zs)
ctr = mathutils.Vector((0, 0, (max(zs) + min(zs)) / 2))


def place(yaw):
    r = math.radians(yaw); d = 1.95 * H
    cam.location = (ctr.x + d * math.sin(r), ctr.y - d * math.cos(r), ctr.z + 0.04 * H)
    cam.rotation_euler = (ctr - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()


def shot(path):
    sc.render.filepath = path; bpy.ops.render.render(write_still=True); return path + ".png"


sys.path.append("/workspace/venv/lib/python3.11/site-packages")
from PIL import Image, ImageDraw, ImageFont                          # noqa: E402
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)

if MODE == "xray":
    COL = {"spine": (0.3, 0.95, 0.4), "arm": (1, 0.25, 0.25), "hand": (1, 0.6, 0.2), "shoulder": (1, 0.85, 0.2),
           "thigh": (0.3, 0.5, 1), "shin": (0.3, 0.5, 1), "foot": (0.3, 0.9, 1), "toe": (0.3, 0.9, 1)}
    sticks = []
    for pb in rig.pose.bones:
        if not rig.data.bones[pb.name].use_deform:
            continue
        h = rig.matrix_world @ pb.head; t = rig.matrix_world @ pb.tail
        v = t - h
        if v.length < 1e-4:
            continue
        me = bpy.data.meshes.new("b"); bm = bmesh.new()
        r = max(0.004, min(0.014, 0.10 * v.length))
        bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=r, radius2=r * 0.35, depth=v.length)
        bm.to_mesh(me); bm.free()
        ob = bpy.data.objects.new("b", me); sc.collection.objects.link(ob)
        ob.location = (h + t) / 2; ob.rotation_mode = 'QUATERNION'
        ob.rotation_quaternion = mathutils.Vector((0, 0, 1)).rotation_difference(v.normalized())
        key = next((k for k in COL if k in pb.name.replace("DEF-", "")), None)
        c = COL.get(key, (0.85, 0.85, 0.9))
        m = bpy.data.materials.new("m"); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
        e = nt.nodes.new("ShaderNodeEmission"); e.inputs["Color"].default_value = (*c, 1)
        o = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(e.outputs["Emission"], o.inputs["Surface"])
        me.materials.append(m); sticks.append(ob)
    views = [("front", 0), ("three_quarter", 40), ("left", 90), ("back", 180)]
    skin, bones = [], []
    for s_ in sticks: s_.hide_render = True
    sc.render.film_transparent = False
    for nm, yaw in views:
        place(yaw); skin.append(shot(os.path.join(TMP, "skin_" + nm)))
    char.hide_render = True; sc.render.film_transparent = True
    for s_ in sticks: s_.hide_render = False
    for nm, yaw in views:
        place(yaw); bones.append(shot(os.path.join(TMP, "bones_" + nm)))
    R = 560
    sheet = Image.new("RGB", (R * 4, R + 26), (16, 16, 20)); d = ImageDraw.Draw(sheet)
    for i, (nm, _) in enumerate(views):
        base = Image.open(skin[i]).convert("RGBA")
        base = Image.alpha_composite(base, Image.new("RGBA", base.size, (0, 0, 0, 90)))
        im = Image.alpha_composite(base, Image.open(bones[i]).convert("RGBA"))
        sheet.paste(im.convert("RGB"), (i * R, 26)); d.text((i * R + 8, 5), nm, font=font, fill=(255, 232, 120))
    sheet.save(OUT); print("RC_DONE xray", OUT, "deform bones", len(sticks), flush=True)

else:
    names = {pb.name for pb in rig.pose.bones}
    def find(*cands):
        return next((c for c in cands if c in names), None)
    POSES = [
        ("neutral", []),
        ("shoulder", [(find("upper_arm_fk.L", "upper_arm.L"), 'Z', ANG), (find("upper_arm_fk.R", "upper_arm.R"), 'Z', -ANG)]),
        ("elbow", [(find("forearm_fk.L", "forearm.L"), 'X', ANG), (find("forearm_fk.R", "forearm.R"), 'X', ANG)]),
        ("knee", [(find("shin_fk.L", "shin.L"), 'X', ANG), (find("shin_fk.R", "shin.R"), 'X', ANG)]),
        ("head", [(find("head"), 'Z', ANG * 0.5)]),
    ]
    print("RC controls", [p[1][0][0] if p[1] else "-" for p in POSES], flush=True)
    # FK/IK switch to FK on the limbs so the FK controls drive them
    for pb in rig.pose.bones:
        if "IK_FK" in pb.keys():
            pb["IK_FK"] = 1.0
    panels = []
    bpy.context.view_layer.objects.active = rig
    for tag, rots in POSES:
        bpy.ops.object.mode_set(mode='POSE')
        for pb in rig.pose.bones:
            pb.rotation_mode = 'XYZ'; pb.rotation_euler = (0, 0, 0)
        for bone, axis, deg in rots:
            if bone and bone in rig.pose.bones:
                e = [0.0, 0.0, 0.0]; e["XYZ".index(axis)] = math.radians(deg)
                rig.pose.bones[bone].rotation_euler = e
        bpy.ops.object.mode_set(mode='OBJECT'); bpy.context.view_layer.update()
        place(0); panels.append((tag, shot(os.path.join(TMP, "g_" + tag))))
    R = 560
    sheet = Image.new("RGB", (R * len(panels), R + 26), (16, 16, 20)); d = ImageDraw.Draw(sheet)
    for i, (tag, p) in enumerate(panels):
        sheet.paste(Image.open(p).convert("RGB"), (i * R, 26)); d.text((i * R + 8, 5), "%s %g" % (tag, ANG), font=font, fill=(255, 232, 120))
    sheet.save(OUT); print("RC_DONE gate", OUT, flush=True)
