"""
RIG DIAGNOSTIC SHEET — what is actually going on under the skin.

Three things, from four angles each:
  row 1  the character as it renders
  row 2  the same frame with the SKELETON drawn over it (x-ray), bones coloured by
         chain: spine green, left arm red, right arm orange, left leg blue, right leg cyan
  row 3  the same mesh coloured by which bone owns each vertex, so a shoulder whose
         geometry is claimed by the wrong bone is visible directly

  blender -b --factory-startup --python rig_diagnostic.py -- <rigged.glb> <out.png> [height=1.6]
Env: RD_POSE  rest (default) | stride
     RD_RES   per-panel pixels (560)
"""
import sys, os, math, colorsys
import bpy, bmesh, mathutils

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
sys.path.insert(0, "/workspace/text-to-video/scripts/day4")
import character_kit as kit                                        # noqa: E402
from rig_map import map_unirig                                     # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT = a[0], a[1]
H = float(a[2]) if len(a) > 2 else 1.6
RES = int(os.environ.get("RD_RES", "560"))
POSE = os.environ.get("RD_POSE", "rest")
TMP = "/workspace/loopwork/rig_diag"
os.makedirs(TMP, exist_ok=True)
VIEWS = [("front", 0.0), ("three_quarter", 40.0), ("left", 90.0), ("back", 180.0)]

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
char, rig = kit.load_rigged_character(GLB, "diag", height=H)
roles = map_unirig(rig); roles.pop("_height")

if POSE == "stride":
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')
    for pb in rig.pose.bones:
        pb.rotation_mode = 'XYZ'; pb.rotation_euler = (0, 0, 0)
    for bone, axis, deg in (("thigh.L", 'X', -30), ("thigh.R", 'X', 28), ("shin.L", 'X', 16),
                            ("arm.L", 'X', 24), ("arm.R", 'X', -24)):
        pb = rig.pose.bones.get(bone)
        if pb:
            e = [0.0, 0.0, 0.0]; e["XYZ".index(axis)] = math.radians(deg); pb.rotation_euler = e
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.context.view_layer.update()

# ---------------------------------------------------------------- chain colours
CHAIN = {}
def _mark(role_prefix, col):
    for r, bn in roles.items():
        if r.startswith(role_prefix):
            CHAIN[bn] = col
_mark("spine", (0.25, 0.95, 0.35)); _mark("hips", (0.95, 0.95, 0.25))
_mark("neck", (0.25, 0.95, 0.35)); _mark("head", (0.35, 1.0, 0.65))
_mark("L_upper", (0.0, 0.0, 0.0))     # placeholder, overwritten below
for r, bn in roles.items():
    if r.startswith("L_") and ("arm" in r or "hand" in r or "clav" in r):
        CHAIN[bn] = (1.0, 0.18, 0.18)
    elif r.startswith("R_") and ("arm" in r or "hand" in r or "clav" in r):
        CHAIN[bn] = (1.0, 0.62, 0.10)
    elif r.startswith("L_") and ("leg" in r or "foot" in r or "toe" in r):
        CHAIN[bn] = (0.25, 0.45, 1.0)
    elif r.startswith("R_") and ("leg" in r or "foot" in r or "toe" in r):
        CHAIN[bn] = (0.25, 0.9, 1.0)

# ---------------------------------------------------------------- bone sticks
def build_sticks():
    obs = []
    for pb in rig.pose.bones:
        head = rig.matrix_world @ pb.head
        tail = rig.matrix_world @ pb.tail
        v = tail - head
        L = v.length
        if L < 1e-4:
            continue
        me = bpy.data.meshes.new("b_" + pb.name)
        bm = bmesh.new()
        r = max(0.004, min(0.016, 0.10 * L))
        bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=r, radius2=r * 0.35, depth=L)
        bm.to_mesh(me); bm.free()
        ob = bpy.data.objects.new("b_" + pb.name, me)
        sc.collection.objects.link(ob)
        ob.location = (head + tail) / 2
        ob.rotation_mode = 'QUATERNION'
        ob.rotation_quaternion = mathutils.Vector((0, 0, 1)).rotation_difference(v.normalized())
        col = CHAIN.get(pb.name, (0.85, 0.85, 0.9))
        m = bpy.data.materials.new("m_" + pb.name)
        m.use_nodes = True
        nt = m.node_tree; nt.nodes.clear()
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (col[0], col[1], col[2], 1)
        e.inputs["Strength"].default_value = 1.0
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(e.outputs["Emission"], o.inputs["Surface"])
        me.materials.append(m)
        obs.append(ob)
        # a ball at every joint, so a chain that jumps is obvious
        jm = bpy.data.meshes.new("j_" + pb.name)
        bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r * 2.1)
        bm.to_mesh(jm); bm.free()
        jo = bpy.data.objects.new("j_" + pb.name, jm)
        sc.collection.objects.link(jo); jo.location = head
        jm.materials.append(m)
        obs.append(jo)
    return obs

# ---------------------------------------------------------------- weight colours
def weight_colours():
    """Per-vertex colour = the colour of the bone with the largest weight."""
    me = char.data
    if not me.color_attributes:
        me.color_attributes.new(name="wcol", type='FLOAT_COLOR', domain='POINT')
    ca = me.color_attributes["wcol"]
    gi_to_name = {vg.index: vg.name for vg in char.vertex_groups}
    # unmapped bones get a NEUTRAL grey, never a hue. Giving them golden-ratio hues once
    # painted an unmapped spine bone bright red and made it look like the arm owned the
    # whole chest, which sent an hour of work at the wrong problem.
    palette = {}
    for i, (gi, nm) in enumerate(sorted(gi_to_name.items())):
        palette[gi] = CHAIN.get(nm, (0.45, 0.45, 0.48))
    counts = {}
    for v in me.vertices:
        best, bw = None, -1.0
        for g in v.groups:
            if g.weight > bw:
                bw, best = g.weight, g.group
        c = palette.get(best, (0.5, 0.5, 0.5))
        ca.data[v.index].color = (c[0], c[1], c[2], 1.0)
        counts[best] = counts.get(best, 0) + 1
    role_of = {bn: r for r, bn in roles.items()}
    print("OWNERSHIP (vertices dominated by each bone)")
    for gi, cnt in sorted(counts.items(), key=lambda kv: -kv[1])[:18]:
        nm = gi_to_name.get(gi, "?")
        print("   %-10s %-12s %6d  %5.1f%%" % (nm, role_of.get(nm, "-"), cnt, 100.0 * cnt / len(me.vertices)))
    m = bpy.data.materials.new("wmat")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    at = nt.nodes.new("ShaderNodeVertexColor"); at.layer_name = "wcol"
    e = nt.nodes.new("ShaderNodeEmission")
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(at.outputs["Color"], e.inputs["Color"])
    nt.links.new(e.outputs["Emission"], o.inputs["Surface"])
    return m

# ---------------------------------------------------------------- stage
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", 'SUN')); sun.data.energy = 3.2
sun.rotation_euler = (math.radians(58), 0, math.radians(35)); sc.collection.objects.link(sun)
fl = bpy.data.objects.new("f", bpy.data.lights.new("f", 'SUN')); fl.data.energy = 1.1
fl.rotation_euler = (math.radians(70), 0, math.radians(-140)); sc.collection.objects.link(fl)
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.20, 0.21, 0.24, 1)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); cam.data.lens = 60
sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = sc.render.resolution_y = RES
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGBA'

zs = [(char.matrix_world @ v.co).z for v in char.data.vertices]
ctr = mathutils.Vector((0, 0, (min(zs) + max(zs)) / 2))
DIST = 1.95 * H


def place(yaw):
    r = math.radians(yaw)
    cam.location = (ctr.x + DIST * math.sin(r), ctr.y - DIST * math.cos(r), ctr.z + 0.04 * H)
    cam.rotation_euler = (ctr - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()


def render(tag):
    sc.render.filepath = os.path.join(TMP, tag)
    bpy.ops.render.render(write_still=True)
    return os.path.join(TMP, tag + ".png")


shots = {"skin": [], "bones": [], "weights": []}
sc.render.film_transparent = False
for name, yaw in VIEWS:
    place(yaw)
    shots["skin"].append(render("skin_" + name))

sticks = build_sticks()
for o in sticks:
    o.hide_render = True
char.hide_render = True
sc.render.film_transparent = True
for o in sticks:
    o.hide_render = False
for name, yaw in VIEWS:
    place(yaw)
    shots["bones"].append(render("bones_" + name))

for o in sticks:
    o.hide_render = True
char.hide_render = False
sc.render.film_transparent = False
orig = list(char.data.materials)
wm = weight_colours()
char.data.materials.clear(); char.data.materials.append(wm)
for name, yaw in VIEWS:
    place(yaw)
    shots["weights"].append(render("w_" + name))

# ---------------------------------------------------------------- sheet
sys.path.append("/workspace/venv/lib/python3.11/site-packages")
from PIL import Image, ImageDraw, ImageFont                        # noqa: E402
def font(sz):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()
f1, f2 = font(20), font(15)
rows = [("skin", "as rendered"), ("bones", "skeleton x-ray"), ("weights", "bone that owns each vertex")]
W = RES * len(VIEWS)
sheet = Image.new("RGB", (W, RES * len(rows) + 34 * len(rows) + 30), (16, 16, 20))
d = ImageDraw.Draw(sheet)
y = 0
for key, label in rows:
    d.text((10, y + 8), label, font=f1, fill=(255, 232, 120))
    y += 30
    for i, p in enumerate(shots[key]):
        im = Image.open(p).convert("RGBA")
        if key == "bones":
            base = Image.open(shots["skin"][i]).convert("RGBA")
            dim = Image.new("RGBA", base.size, (0, 0, 0, 90))
            base = Image.alpha_composite(base, dim)
            im = Image.alpha_composite(base, im)
        sheet.paste(im.convert("RGB"), (i * RES, y))
        d.text((i * RES + 8, y + 6), VIEWS[i][0], font=f2, fill=(210, 220, 235))
    y += RES + 4
d.text((10, y + 4), "spine green   hips yellow   L arm red   R arm orange   L leg blue   R leg cyan",
       font=f2, fill=(190, 200, 215))
sheet.save(OUT)
print("RIGDIAG_DONE", OUT, flush=True)
