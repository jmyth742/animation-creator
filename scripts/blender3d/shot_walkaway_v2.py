"""
The first pure-3D shot: the generated character walks through the generated
scene. Everything on screen came from two AI images.

  plate  ──depth──►  displaced terrain (scene_from_image approach)
  sheet  ──Hunyuan3D──►  mesh ──auto-weight armature──► walk cycle

Run: blender -b --factory-startup --python shot_walkaway_v2.py -- \
       <plate> <depth> <mesh.glb> <sheet> <outdir>
"""
import sys
import math
import bpy
import mathutils

plate_path, depth_path, mesh_path, sheet_path, outdir = sys.argv[-5:]

FPS, FRAMES = 16, 81
RES = (832, 480)
DEPTH_RANGE, NEAR = 26.0, 2.0
GRID = (416, 240)

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.render.resolution_x, sc.render.resolution_y = RES
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, FRAMES
sc.render.use_motion_blur = False
sc.view_settings.view_transform = 'Standard'
sc.render.filepath = outdir + "/frame_"
sc.render.image_settings.file_format = 'PNG'

cam = bpy.data.cameras.new("cam"); cam.lens = 35
camo = bpy.data.objects.new("cam", cam)
camo.location = (0, 0, 0)
camo.rotation_euler = (math.radians(90), 0, 0)
sc.collection.objects.link(camo); sc.camera = camo

# ── terrain from plate + depth (same construction as scene_from_image) ──
def frustum(y):
    w = y * 36.0 / 35.0
    return w, w * RES[1] / RES[0]

dimg = bpy.data.images.load(depth_path)
dw, dh = dimg.size
dpx = list(dimg.pixels)

def depth_at(u, v):
    x = min(dw - 1, int(u * (dw - 1)))
    y = min(dh - 1, int(v * (dh - 1)))
    return NEAR + (1.0 - dpx[(y * dw + x) * 4]) * DEPTH_RANGE

nx, ny = GRID
verts, faces = [], []
for j in range(ny + 1):
    for i in range(nx + 1):
        u, v = i / nx, j / ny
        yd = depth_at(u, v)
        fw, fh = frustum(yd)
        verts.append(((u - 0.5) * fw, yd, (v - 0.5) * fh))
for j in range(ny):
    for i in range(nx):
        a = j * (nx + 1) + i
        faces.append((a, a + 1, a + nx + 2, a + nx + 1))
tmesh = bpy.data.meshes.new("terrain")
tmesh.from_pydata(verts, [], faces)
uvl = tmesh.uv_layers.new()
for poly in tmesh.polygons:
    for li in poly.loop_indices:
        vi = tmesh.loops[li].vertex_index
        uvl.data[li].uv = (vi % (nx + 1) / nx, vi // (nx + 1) / ny)
tob = bpy.data.objects.new("terrain", tmesh)
sc.collection.objects.link(tob)
pimg = bpy.data.images.load(plate_path)
pmat = bpy.data.materials.new("plate"); pmat.use_nodes = True
nt = pmat.node_tree; nt.nodes.clear()
tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = pimg
em = nt.nodes.new("ShaderNodeEmission")
ou = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(tx.outputs["Color"], em.inputs["Color"])
nt.links.new(em.outputs["Emission"], ou.inputs["Surface"])
tmesh.materials.append(pmat)

# ── the character ────────────────────────────────────────────────────
bpy.ops.import_scene.gltf(filepath=mesh_path)
parts = [o for o in sc.objects if o.type == 'MESH' and o.name != "terrain"]
for o in sc.objects:
    o.select_set(False)
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
if len(parts) > 1:
    bpy.ops.object.join()
char = bpy.context.view_layer.objects.active
char.name = "oisin"

# normalise: feet on z=0, height 1.75m, facing -Y (as imported)
mn = mathutils.Vector((1e9,) * 3); mx = mathutils.Vector((-1e9,) * 3)
for c in char.bound_box:
    w = char.matrix_world @ mathutils.Vector(c)
    mn = mathutils.Vector(map(min, mn, w)); mx = mathutils.Vector(map(max, mx, w))
H = 1.75
s = H / (mx.z - mn.z)
char.scale = (char.scale[0] * s,) * 3
char.location = (-(mn.x + mx.x) / 2 * s, -(mn.y + mx.y) / 2 * s, -mn.z * s)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# colour by projecting the sheet from the front (planar map on x/z);
# crude, but at wide distance it reads as costume rather than clay
uv = char.data.uv_layers.new(name="proj")
mn2 = mathutils.Vector((1e9,) * 3); mx2 = mathutils.Vector((-1e9,) * 3)
for v in char.data.vertices:
    mn2 = mathutils.Vector(map(min, mn2, v.co))
    mx2 = mathutils.Vector(map(max, mx2, v.co))
for poly in char.data.polygons:
    for li in poly.loop_indices:
        co = char.data.vertices[char.data.loops[li].vertex_index].co
        u = (co.x - mn2.x) / (mx2.x - mn2.x)
        w = (co.z - mn2.z) / (mx2.z - mn2.z)
        if w > 0.84:
            # the camera sees his BACK all shot: head samples the sheet's
            # hair pixels, not the face (single-view projection has no back)
            uv.data[li].uv = (0.50 + u * 0.07, 0.908)
        else:
            # sheet margins: figure occupies roughly x 28–72%, y 5–95%
            uv.data[li].uv = (0.28 + u * 0.44, 0.05 + w * 0.90)
simg = bpy.data.images.load(sheet_path)
cmat = bpy.data.materials.new("charmat"); cmat.use_nodes = True
ct = cmat.node_tree; ct.nodes.clear()
cuv = ct.nodes.new("ShaderNodeUVMap"); cuv.uv_map = "proj"
ctx = ct.nodes.new("ShaderNodeTexImage"); ctx.image = simg
cem = ct.nodes.new("ShaderNodeEmission")
cou = ct.nodes.new("ShaderNodeOutputMaterial")
ct.links.new(cuv.outputs["UV"], ctx.inputs["Vector"])
ct.links.new(ctx.outputs["Color"], cem.inputs["Color"])
ct.links.new(cem.outputs["Emission"], cou.inputs["Surface"])
char.data.materials.clear()
char.data.materials.append(cmat)

# ── armature: simple biped, auto weights ─────────────────────────────
arm = bpy.data.armatures.new("rig")
rig = bpy.data.objects.new("rig", arm)
sc.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='EDIT')

def bone(name, head, tail, parent=None):
    b = arm.edit_bones.new(name)
    b.head, b.tail = head, tail
    if parent:
        b.parent = arm.edit_bones[parent]
    return b

bone("hips", (0, 0, 0.95), (0, 0, 1.15))
bone("spine", (0, 0, 1.15), (0, 0, 1.45), "hips")
bone("head", (0, 0, 1.45), (0, 0, 1.75), "spine")
for sgn, side in ((1, "L"), (-1, "R")):
    bone(f"thigh.{side}", (0.10 * sgn, 0, 0.95), (0.11 * sgn, 0, 0.50), "hips")
    bone(f"shin.{side}", (0.11 * sgn, 0, 0.50), (0.12 * sgn, 0, 0.05), f"thigh.{side}")
    bone(f"arm.{side}", (0.20 * sgn, 0, 1.42), (0.26 * sgn, 0, 1.05), "spine")
    bone(f"fore.{side}", (0.26 * sgn, 0, 1.05), (0.30 * sgn, 0, 0.75), f"arm.{side}")
bpy.ops.object.mode_set(mode='OBJECT')

for o in sc.objects:
    o.select_set(False)
char.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type='ARMATURE_AUTO')

# ── glue the walk to the terrain surface ─────────────────────────────
def ground_z(x, y):
    """z of the terrain surface under world point (x, y): scan pixel rows
    from the bottom of the image until the reprojected depth passes y."""
    for jv in range(0, 1000):
        v = jv / 1000
        u = min(1.0, max(0.0, x / (y * 36.0 / 35.0) + 0.5))
        yd = depth_at(u, v)
        if yd >= y:
            return (v - 0.5) * frustum(yd)[1]
    return 0.0


# ── the walk ─────────────────────────────────────────────────────────
STRIDE_HZ = 1.45
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='POSE')
pb = rig.pose.bones
for f in range(1, FRAMES + 1):
    t = (f - 1) / (FRAMES - 1)
    sc.frame_set(f)
    ph = 2 * math.pi * STRIDE_HZ * (f - 1) / FPS
    px = 0.55 - 1.45 * t
    py = 5.6 + 8.4 * t
    rig.location = (px, py, ground_z(px, py) + 0.02 * abs(math.sin(ph)))
    # mesh faces -Y; walking away means facing +Y — turn him around,
    # with a slight angle toward the path's drift
    rig.rotation_euler = (0, 0, math.radians(180 + 7))
    rig.keyframe_insert("location"); rig.keyframe_insert("rotation_euler")
    for side, sgn in (("L", 1), ("R", -1)):
        pb[f"thigh.{side}"].rotation_mode = 'XYZ'
        pb[f"thigh.{side}"].rotation_euler = (sgn * 0.45 * math.sin(ph), 0, 0)
        pb[f"thigh.{side}"].keyframe_insert("rotation_euler")
        pb[f"shin.{side}"].rotation_mode = 'XYZ'
        pb[f"shin.{side}"].rotation_euler = (max(0.0, -sgn * 0.9 * math.sin(ph + 0.6)), 0, 0)
        pb[f"shin.{side}"].keyframe_insert("rotation_euler")
        pb[f"arm.{side}"].rotation_mode = 'XYZ'
        pb[f"arm.{side}"].rotation_euler = (-sgn * 0.30 * math.sin(ph), 0, 0)
        pb[f"arm.{side}"].keyframe_insert("rotation_euler")
    pb["spine"].rotation_mode = 'XYZ'
    pb["spine"].rotation_euler = (0.03, 0, 0.05 * math.sin(ph))
    pb["spine"].keyframe_insert("rotation_euler")
bpy.ops.object.mode_set(mode='OBJECT')

bpy.ops.render.render(animation=True)
print("PURE3D SHOT COMPLETE")
