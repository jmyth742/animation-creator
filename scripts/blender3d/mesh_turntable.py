"""
MESH TURNTABLE — four views of a mesh on one sheet, for judging a candidate style.

A character sheet shows what the drawing looks like. This shows what the reconstruction
actually kept: whether the arms separated from the torso, whether the fingers survived,
whether the head holds its proportions off-axis, and what the silhouette does when it
turns. Judge this, not the drawing.

  blender -b --factory-startup --python mesh_turntable.py -- <mesh.glb> <out.png> [label]
"""
import sys, os, math
import bpy, mathutils
sys.path.append("/workspace/venv/lib/python3.11/site-packages")
from PIL import Image, ImageDraw

args = sys.argv[sys.argv.index("--") + 1:]
glb, out = args[0], args[1]
label = args[2] if len(args) > 2 else os.path.basename(glb)

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=glb)
ms = [o for o in sc.objects if o.type == 'MESH']
if not ms:
    sys.exit("no mesh in %s" % glb)
for o in sc.objects:
    o.select_set(False)
for o in ms:
    o.select_set(True)
bpy.context.view_layer.objects.active = ms[0]
if len(ms) > 1:
    bpy.ops.object.join()
ob = bpy.context.view_layer.objects.active
for p in ob.data.polygons:
    p.use_smooth = True

vs = [ob.matrix_world @ v.co for v in ob.data.vertices]
lo = mathutils.Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
hi = mathutils.Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
mid = (lo + hi) / 2
span = max(hi.z - lo.z, hi.x - lo.x) * 1.15

# plain matte grey so the FORM is judged, not the texture
m = bpy.data.materials.new("clay")
m.use_nodes = True
nt = m.node_tree
bs = nt.nodes.get("Principled BSDF")
if bs:
    bs.inputs["Base Color"].default_value = (0.62, 0.60, 0.58, 1)
    bs.inputs["Roughness"].default_value = 0.75
    if "Metallic" in bs.inputs:
        bs.inputs["Metallic"].default_value = 0.0
ob.data.materials.clear()
ob.data.materials.append(m)

key = bpy.data.objects.new("key", bpy.data.lights.new("k", 'SUN'))
key.data.energy = 3.0
key.rotation_euler = (math.radians(58), 0, math.radians(35))
sc.collection.objects.link(key)
fill = bpy.data.objects.new("fill", bpy.data.lights.new("f", 'SUN'))
fill.data.energy = 1.1
fill.data.use_shadow = False
fill.rotation_euler = (math.radians(65), 0, math.radians(-120))
sc.collection.objects.link(fill)
wd = bpy.data.worlds.new("w")
sc.world = wd
wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.86, 0.87, 0.89, 1)

cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
cam.data.type = 'ORTHO'
cam.data.ortho_scale = span
sc.collection.objects.link(cam)
sc.camera = cam
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x, sc.render.resolution_y = 500, 720

shots = []
for ang, tag in ((0, "front"), (40, "3/4"), (90, "side"), (180, "back")):
    r = math.radians(ang)
    cam.location = mid + mathutils.Vector((math.sin(r) * -4.0, -math.cos(r) * 4.0, 0.0))
    cam.rotation_euler = (mid - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
    p = "/workspace/loopwork/tt_%s_%s.png" % (os.path.basename(glb)[:-4], tag.replace("/", ""))
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    shots.append((p, tag))

ims = [Image.open(p).convert("RGB") for p, _ in shots]
w, h = ims[0].size
sheet = Image.new("RGB", (w * 4, h + 30), (26, 26, 30))
d = ImageDraw.Draw(sheet)
d.text((8, 8), "%s   verts %d   faces %d" % (label, len(ob.data.vertices), len(ob.data.polygons)),
       fill=(255, 225, 110))
for i, (im, tag) in enumerate(zip(ims, [t for _, t in shots])):
    sheet.paste(im, (i * w, 30))
    d.text((i * w + 8, 34), tag, fill=(40, 40, 40))
sheet.save(out)
print("TURNTABLE_DONE", out, "verts", len(ob.data.vertices), flush=True)
