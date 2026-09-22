"""
MOUTH GEOMETRY — give the head an actual mouth instead of a painted one.

Texture-swapped visemes read as stuck on because they are: the mesh is a closed surface
with a mouth drawn on it. There is no cavity, so there is no depth, and the illusion
fails the moment the head turns.

This cuts a real mouth: open the surface at the calibrated mouth position, extrude the
border inward to make a lined cavity, and build shape keys that move the lip ring. The
result deforms in 3D, holds up off-axis, and is driven by the viseme track we already
have. It is the approach Arc System Works use for stylised faces, and it suits a simple
head far better than a blendshape set transferred from a realistic donor.

  blender -b --factory-startup --python mouth_geo.py -- <mesh.glb> <calib.json> <height> <out.glb>
Env: MOUTH_R (0.035) radius, MOUTH_DEPTH (0.030), MOUTH_ASPECT (0.62 height/width)
"""
import bpy, bmesh, sys, os, json, math, mathutils
sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
os.environ["CHAR_NORMALFIX"] = "0"
import character_kit as kit

a = sys.argv[sys.argv.index("--") + 1:]
glb, calib_p, height, out_p = a[0], a[1], float(a[2]), a[3]
R = float(os.environ.get("MOUTH_R", "0.035"))
DEPTH = float(os.environ.get("MOUTH_DEPTH", "0.030"))
ASPECT = float(os.environ.get("MOUTH_ASPECT", "0.62"))
cal = json.load(open(calib_p))

sc = bpy.context.scene
for o in list(sc.objects):
    bpy.data.objects.remove(o, do_unlink=True)
ch = kit.load_character(glb, "m", height=height)
print("MOUTH mesh faces", len(ch.data.polygons), flush=True)

MX = cal.get("face_x", 0.0)
MZ = cal["mouth_z"]
# the front surface at mouth height
co = [ch.matrix_world @ v.co for v in ch.data.vertices]
band = [c for c in co if abs(c.x - MX) < R and abs(c.z - MZ) < R]
front_y = min(c.y for c in band) if band else min(c.y for c in co)
centre = mathutils.Vector((MX, front_y, MZ))
print("MOUTH centre %.4f %.4f %.4f  r=%.3f" % (centre.x, centre.y, centre.z, R), flush=True)

bpy.ops.object.select_all(action='DESELECT')
ch.select_set(True)
bpy.context.view_layer.objects.active = ch
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ch.data)
bm.faces.ensure_lookup_table()

def inside(p):
    """elliptical mouth footprint on the front of the face"""
    d = ch.matrix_world @ p
    if d.y > centre.y + R * 1.2:          # only the front surface
        return False
    dx = (d.x - centre.x) / R
    dz = (d.z - centre.z) / (R * ASPECT)
    return dx * dx + dz * dz <= 1.0

sel = [f for f in bm.faces if all(inside(v.co) for v in f.verts)]
print("MOUTH faces to open:", len(sel), flush=True)
if not sel:
    print("MOUTH FAILED: no faces inside the footprint — widen MOUTH_R", flush=True)
    sys.exit(1)

bmesh.ops.delete(bm, geom=sel, context='FACES')
bmesh.update_edit_mesh(ch.data)

# the open border becomes the lip ring; extrude it inward to line the cavity
bm = bmesh.from_edit_mesh(ch.data)
border = [e for e in bm.edges if e.is_boundary]
ring = sorted({v for e in border for v in e.verts}, key=lambda v: v.index)
print("MOUTH lip ring verts:", len(ring), flush=True)
res = bmesh.ops.extrude_edge_only(bm, edges=border)
new_v = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
for v in new_v:
    v.co.y += DEPTH                       # inward is +Y (the face looks along -Y)
    v.co.x = centre.x + (v.co.x - centre.x) * 0.45
    v.co.z = centre.z + (v.co.z - centre.z) * 0.45
# cap the back of the cavity so it is not see-through
back = bmesh.ops.contextual_create(bm, geom=[e for e in bm.edges if e.is_boundary])
bmesh.update_edit_mesh(ch.data)
bpy.ops.object.mode_set(mode='OBJECT')
print("MOUTH cavity made, faces now", len(ch.data.polygons), flush=True)

# a dark interior material for the cavity faces
dark = bpy.data.materials.new("mouth_interior")
dark.use_nodes = True
bs = dark.node_tree.nodes.get("Principled BSDF")
if bs:
    bs.inputs["Base Color"].default_value = (0.08, 0.03, 0.04, 1)
    bs.inputs["Roughness"].default_value = 0.9
ch.data.materials.append(dark)
idx = len(ch.data.materials) - 1
wm = ch.matrix_world
# ONLY the faces that actually line the cavity. The first version used a generous radius
# plus a loose depth test and painted the whole beard and jaw dark (review/mouth_geo_chibi.png).
# The cavity faces are the ones set BACK from the face surface, so test depth first.
n_dark = 0
for p in ch.data.polygons:
    c = wm @ p.center
    if c.y > centre.y + DEPTH * 0.25 and (c - centre).length < R * 1.15:
        p.material_index = idx
        n_dark += 1
print("MOUTH interior faces:", n_dark, flush=True)

# shape keys: the lip ring drives the visemes, so the mouth opens in 3D
ring_idx = [v.index for v in ch.data.vertices
            if ((wm @ v.co) - centre).length < R * 1.25]
print("MOUTH shape-key verts:", len(ring_idx), flush=True)
ch.shape_key_add(name="Basis", from_mix=False)
SHAPES = {                                   # (vertical open, horizontal spread)
    "mouth_small": (0.9, 0.80),
    "mouth_mid":   (1.8, 0.95),
    "mouth_open":  (3.0, 1.05),
    "mouth_ee":    (0.7, 1.70),
    "mouth_oo":    (1.9, 0.50),
}
basis = [v.co.copy() for v in ch.data.vertices]
for nm, (vopen, hspread) in SHAPES.items():
    sk = ch.shape_key_add(name=nm, from_mix=False)
    for i in ring_idx:
        p = basis[i]
        w = wm @ p
        dz = w.z - centre.z
        dx = w.x - centre.x
        nz = centre.z + dz * (1.0 + vopen * (1.0 if dz < 0 else 0.35))
        nx = centre.x + dx * hspread
        sk.data[i].co = wm.inverted() @ mathutils.Vector((nx, w.y, nz))
print("MOUTH shape keys:", [k.name for k in ch.data.shape_keys.key_blocks], flush=True)

bpy.ops.object.select_all(action='DESELECT')
ch.select_set(True)
bpy.ops.export_scene.gltf(filepath=out_p, use_selection=True, export_morph=True)
print("MOUTH_DONE", out_p, flush=True)
