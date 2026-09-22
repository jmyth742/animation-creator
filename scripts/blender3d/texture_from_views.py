"""
TEXTURE FROM VIEWS — paint a shape-only mesh with the drawings it was built from.

Hunyuan3D's shape pipeline returns geometry with no UVs and no colour. The three sheets
that produced it are, however, exactly the views we need, so the texture can be projected
straight back on: unwrap, aim an orthographic camera along each source axis, project each
drawing, blend them by how squarely each surface faces its camera, and bake one atlas.

The part that decides whether this looks right or like garbage is ALIGNMENT. The drawing
frames the character wherever the image model put it; the mesh is normalised by the
generator. So each camera is fitted by comparing the mesh's rendered silhouette with the
drawing's own alpha silhouette and matching their bounding boxes.

  blender -b --factory-startup --python texture_from_views.py -- <mesh.glb> <front> <left> <back> <out.glb> [px]
"""
import sys, os, math
import bpy, mathutils
sys.path.append("/workspace/venv/lib/python3.11/site-packages")
import numpy as np
from PIL import Image

a = sys.argv[sys.argv.index("--") + 1:]
glb, f_png, l_png, b_png, out_glb = a[0], a[1], a[2], a[3], a[4]
PX = int(a[5]) if len(a) > 5 else 2048
LW = "/workspace/loopwork"

def cutout(path, tag):
    """White-background drawing -> RGBA with the figure isolated, plus its bbox."""
    im = Image.open(path).convert("RGB")
    arr = np.asarray(im, dtype=np.float32) / 255.0
    lum = arr.mean(axis=2)
    # the plate is pure white; anything meaningfully darker is the character
    mask = (lum < 0.93).astype(np.float32)
    # drop stray specks
    ys, xs = np.where(mask > 0.5)
    if len(xs) < 50:
        mask = np.ones_like(mask); ys, xs = np.where(mask > 0.5)
    box = (xs.min(), ys.min(), xs.max(), ys.max())
    rgba = np.dstack([arr, mask])
    p = os.path.join(LW, "cut_%s.png" % tag)
    Image.fromarray((rgba * 255).astype(np.uint8)).save(p)
    return p, box, im.size

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=glb)
ms = [o for o in sc.objects if o.type == 'MESH']
for o in sc.objects:
    o.select_set(False)
for o in ms:
    o.select_set(True)
bpy.context.view_layer.objects.active = ms[0]
if len(ms) > 1:
    bpy.ops.object.join()
ob = bpy.context.view_layer.objects.active
ob.name = "subject"
for p in ob.data.polygons:
    p.use_smooth = True
print("TEXV mesh faces", len(ob.data.polygons), flush=True)

vs = [ob.matrix_world @ v.co for v in ob.data.vertices]
lo = mathutils.Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
hi = mathutils.Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
mid = (lo + hi) / 2
height = hi.z - lo.z

# --- fresh UVs
while ob.data.uv_layers:
    ob.data.uv_layers.remove(ob.data.uv_layers[0])
ob.data.uv_layers.new(name="UVMap")
bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.004)
bpy.ops.object.mode_set(mode='OBJECT')
uv0 = ob.data.uv_layers[0].name

# character faces -Y (verified by the turntable: the -Y camera sees the face).
# its own LEFT is therefore -X.
VIEWS = [("f", mathutils.Vector((0, -1, 0)), f_png),
         ("l", mathutils.Vector((-1, 0, 0)), l_png),
         ("b", mathutils.Vector((0, 1, 0)), b_png)]

sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.view_settings.view_transform = 'Standard'
sc.render.film_transparent = True
sc.render.resolution_x = sc.render.resolution_y = 1024

cams, imgs = {}, {}
for tag, d, png in VIEWS:
    cut, box, isize = cutout(png, tag)
    cd = bpy.data.cameras.new("c" + tag)
    cd.type = 'ORTHO'
    cd.clip_start, cd.clip_end = 0.01, 40.0
    cam = bpy.data.objects.new("c" + tag, cd)
    sc.collection.objects.link(cam)
    cam.location = mid + d * (height * 4.0)
    cam.rotation_euler = (mid - cam.location).to_track_quat('-Z', 'Y').to_euler()
    # ALIGNMENT: fit the ortho scale and vertical shift so the mesh's silhouette matches
    # the drawing's. Without this the texture lands offset and the whole bake is wasted.
    iw, ih = isize
    fig_h = (box[3] - box[1]) / float(ih)          # figure height as a fraction of the plate
    cd.ortho_scale = height / max(fig_h, 1e-3)
    fig_cy = ((box[1] + box[3]) / 2.0) / float(ih) - 0.5
    cam.location.z = mid.z - fig_cy * cd.ortho_scale
    cams[tag] = cam
    img = bpy.data.images.load(cut)
    imgs[tag] = img
    print("TEXV view", tag, "fig_h %.3f ortho %.3f" % (fig_h, cd.ortho_scale), flush=True)

for tag, _d, _p in VIEWS:
    ln = "P_" + tag
    if ln not in ob.data.uv_layers:
        ob.data.uv_layers.new(name=ln)
    md = ob.modifiers.new("p" + tag, 'UV_PROJECT')
    md.uv_layer = ln
    md.projector_count = 1
    md.projectors[0].object = cams[tag]
    md.aspect_x = md.aspect_y = 1.0
    bpy.ops.object.modifier_apply(modifier=md.name)
ob.data.uv_layers.active = ob.data.uv_layers[uv0]

m = bpy.data.materials.new("bake")
m.use_nodes = True
nt = m.node_tree
nt.nodes.clear()
geo = nt.nodes.new("ShaderNodeNewGeometry")
acc_c = acc_w = None
for tag, d, _p in VIEWS:
    uvp = nt.nodes.new("ShaderNodeUVMap"); uvp.uv_map = "P_" + tag
    tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = imgs[tag]; tx.extension = 'CLIP'
    nt.links.new(uvp.outputs["UV"], tx.inputs["Vector"])
    dot = nt.nodes.new("ShaderNodeVectorMath"); dot.operation = 'DOT_PRODUCT'
    # d points FROM the subject TO the camera, so a surface facing that camera has a
    # normal along +d. Negating it here projects each view onto the opposite side —
    # the face ends up on the back of the head.
    dot.inputs[1].default_value = (d.x, d.y, d.z)
    nt.links.new(geo.outputs["Normal"], dot.inputs[0])
    cl = nt.nodes.new("ShaderNodeMath"); cl.operation = 'MAXIMUM'; cl.inputs[1].default_value = 0.0
    nt.links.new(dot.outputs["Value"], cl.inputs[0])
    pw = nt.nodes.new("ShaderNodeMath"); pw.operation = 'POWER'; pw.inputs[1].default_value = float(os.environ.get("TEXV_POWER", "8.0"))
    nt.links.new(cl.outputs["Value"], pw.inputs[0])
    # the plate's alpha keeps white background out of the bake
    wa = nt.nodes.new("ShaderNodeMath"); wa.operation = 'MULTIPLY'
    nt.links.new(pw.outputs["Value"], wa.inputs[0]); nt.links.new(tx.outputs["Alpha"], wa.inputs[1])
    scn = nt.nodes.new("ShaderNodeVectorMath"); scn.operation = 'SCALE'
    nt.links.new(tx.outputs["Color"], scn.inputs[0])
    nt.links.new(wa.outputs["Value"], scn.inputs["Scale"])
    if acc_c is None:
        acc_c, acc_w = scn.outputs["Vector"], wa.outputs["Value"]
    else:
        ad = nt.nodes.new("ShaderNodeVectorMath"); ad.operation = 'ADD'
        nt.links.new(acc_c, ad.inputs[0]); nt.links.new(scn.outputs["Vector"], ad.inputs[1])
        acc_c = ad.outputs["Vector"]
        aw = nt.nodes.new("ShaderNodeMath"); aw.operation = 'ADD'
        nt.links.new(acc_w, aw.inputs[0]); nt.links.new(wa.outputs["Value"], aw.inputs[1])
        acc_w = aw.outputs["Value"]

safe = nt.nodes.new("ShaderNodeMath"); safe.operation = 'MAXIMUM'; safe.inputs[1].default_value = 1e-3
nt.links.new(acc_w, safe.inputs[0])
dv = nt.nodes.new("ShaderNodeCombineXYZ")
for s_ in ("X", "Y", "Z"):
    nt.links.new(safe.outputs["Value"], dv.inputs[s_])
nrm = nt.nodes.new("ShaderNodeVectorMath"); nrm.operation = 'DIVIDE'
nt.links.new(acc_c, nrm.inputs[0]); nt.links.new(dv.outputs["Vector"], nrm.inputs[1])
em = nt.nodes.new("ShaderNodeEmission"); out = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(nrm.outputs["Vector"], em.inputs["Color"])
nt.links.new(em.outputs["Emission"], out.inputs["Surface"])

target = bpy.data.images.new("atlas", PX, PX, alpha=False)
tn = nt.nodes.new("ShaderNodeTexImage"); tn.image = target
nt.nodes.active = tn
ob.data.materials.clear()
ob.data.materials.append(m)

sc.render.engine = 'CYCLES'
sc.cycles.samples = 1
try:
    sc.cycles.device = 'GPU'
except Exception:
    pass
sc.render.bake.use_selected_to_active = False
sc.render.bake.margin = 12
sc.render.bake.use_clear = True
bpy.ops.object.bake(type='EMIT')

png_out = out_glb[:-4] + "_tex.png"
target.filepath_raw = png_out
target.file_format = 'PNG'
target.save()

# ship it as a normal textured material so any viewer shows the colour
m2 = bpy.data.materials.new("painted")
m2.use_nodes = True
nt2 = m2.node_tree
bsdf = nt2.nodes.get("Principled BSDF")
timg = nt2.nodes.new("ShaderNodeTexImage")
timg.image = target
nt2.links.new(timg.outputs["Color"], bsdf.inputs["Base Color"])
bsdf.inputs["Roughness"].default_value = 0.85
if "Metallic" in bsdf.inputs:
    bsdf.inputs["Metallic"].default_value = 0.0
ob.data.materials.clear()
ob.data.materials.append(m2)
bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True)
bpy.ops.export_scene.gltf(filepath=out_glb, use_selection=True)
print("TEXV_DONE", out_glb, png_out, flush=True)
