"""
Judgment turntable: one character, one config -> body + face still.
Run: blender -b --factory-startup --python turn_grid.py -- <who|mesh.glb> <height> <outdir> <tag>
Config comes from the character_kit env hooks (CHAR_SMOOTH, CHAR_NORMALFIX)
plus FILM_LINES / FILM_LINE_CREASE / FILM_LINE_MINLEN (same semantics as
film.py). Outputs <outdir>/<tag>_<who>.png and <outdir>/<tag>_<who>_face.png.
"""
import sys, os, math
import bpy, mathutils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import character_kit as kit

args = sys.argv[sys.argv.index("--") + 1:]
who, height, outdir, tag = args[0], float(args[1]), args[2], args[3]
P = "series/tir-na-nog-legend/meshes/props"
# <who> is a cast name (props/<who>_painted.glb) or any .glb path (A/Bs)
mesh_path = who if who.endswith(".glb") else f"{P}/{who}_painted.glb"
if who.endswith(".glb"):
    who = os.path.splitext(os.path.basename(who))[0]
sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
ch = kit.load_character(mesh_path, who, height=height)
if os.environ.get("TURN_YAW"):        # e.g. 180 for meshes that face +Y (CharacterGen)
    ch.rotation_euler.z += math.radians(float(os.environ["TURN_YAW"]))

if os.environ.get("FILM_LINES", "0") not in ("", "0"):
    sc.render.use_freestyle = True
    sc.render.line_thickness = float(os.environ["FILM_LINES"])
    vl = sc.view_layers[0]
    vl.use_freestyle = True
    fs = vl.freestyle_settings
    while fs.linesets:          # factory startup ships a default lineset
        fs.linesets.remove(fs.linesets[0])
    ls = fs.linesets.new("c")
    ls.select_by_collection = False
    ls.linestyle.thickness = float(os.environ["FILM_LINES"])
    # FILM_LINE_MODE=ext: outer contour only (no interior lump marks)
    ext = os.environ.get("FILM_LINE_MODE", "sil") == "ext"
    ls.select_silhouette = not ext
    ls.select_external_contour = ext
    ls.select_border = False
    ls.select_crease = os.environ.get("FILM_LINE_CREASE", "0") == "1"
    ls.linestyle.color = (0.06, 0.04, 0.05)
    minlen = float(os.environ.get("FILM_LINE_MINLEN", "6"))
    if minlen > 0:
        ls.linestyle.use_length_min = True
        ls.linestyle.length_min = minlen

sun = bpy.data.objects.new("sun", bpy.data.lights.new("s", "SUN"))
sun.data.energy = 3.5
sun.data.color = (1.0, 0.85, 0.65)
sun.rotation_euler = (math.radians(60), 0, math.radians(25))
sc.collection.objects.link(sun)
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.62, 0.60, 0.58, 1)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("c"))
sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = "BLENDER_EEVEE_NEXT"
sc.view_settings.view_transform = "Standard"

dg = bpy.context.evaluated_depsgraph_get()
mn = mathutils.Vector((1e9,) * 3); mx = mathutils.Vector((-1e9,) * 3)
for c in ch.evaluated_get(dg).bound_box:
    wv = ch.matrix_world @ mathutils.Vector(c)
    mn = mathutils.Vector(map(min, mn, wv)); mx = mathutils.Vector(map(max, mx, wv))
ctr = (mn + mx) / 2; size = max(mx - mn)

sc.render.resolution_x, sc.render.resolution_y = 380, 470
a = math.radians(35)
cam.location = (ctr.x + 1.9 * size * math.sin(a), ctr.y - 1.9 * size * math.cos(a), ctr.z + 0.1 * size)
d = mathutils.Vector(ctr) - cam.location
cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
sc.render.filepath = f"{outdir}/{tag}_{who}.png"
bpy.ops.render.render(write_still=True)

cam.data.lens = 85
sc.render.resolution_x, sc.render.resolution_y = 430, 430
cam.location = (ctr.x, ctr.y - 0.95, mx.z - 0.13 * size)
d = mathutils.Vector((ctr.x, ctr.y, mx.z - 0.14 * size)) - cam.location
cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
sc.render.filepath = f"{outdir}/{tag}_{who}_face.png"
bpy.ops.render.render(write_still=True)
print("TURN DONE", tag, who)
