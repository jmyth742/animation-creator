"""
RETOPOLOGY for the cast (the stage we built for props and skipped for characters).

The leads are marching-cubes AI meshes: dense, irregular triangles. That topology is
the proven root cause of two failures — the faces would not sharpen beyond a point,
and inverted-hull outlines came out blotchy because a uniform normal offset crosses
the surface wherever local curvature exceeds it.

remesh_asset.py cannot be used here: it drops the UVs, which is harmless for props
(they wear world-space projected textures) and fatal for characters (their whole
look lives in a painted UV atlas). So this script keeps the texture:

  1. import the painted GLB, join, clean (weld, degenerate, consistent normals);
  2. QuadriFlow to a quad budget -> clean loops, even density;
  3. Smart UV unwrap the new mesh;
  4. Cycles EMIT bake of the ORIGINAL texture from the source mesh onto the new UVs
     (selected-to-active with a cage), so the painted look survives the retopology;
  5. export <name>_retopo.glb + <name>_retopo_base.png.

Run:
  blender -b --factory-startup --python retopo_character.py -- <painted.glb> <name> [faces=15000] [px=2048]
Then: reweight_retopo.py to put it back on the UniRig skeleton.
"""
import sys
import os
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
glb, name = argv[0], argv[1]
budget = int(argv[2]) if len(argv) > 2 else 15000
px = int(argv[3]) if len(argv) > 3 else 2048
PROPS = "/workspace/text-to-video/series/tir-na-nog-legend/meshes/props"

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)

bpy.ops.import_scene.gltf(filepath=glb)
parts = [o for o in sc.objects if o.type == 'MESH']
for o in sc.objects:
    o.select_set(False)
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
if len(parts) > 1:
    bpy.ops.object.join()
src = bpy.context.view_layer.objects.active
src.name = name + "_src"

# the source texture: the painted atlas we must not lose
tex_img = None
for m in src.data.materials:
    if m and m.use_nodes:
        for nd in m.node_tree.nodes:
            if nd.type == 'TEX_IMAGE' and nd.image:
                tex_img = nd.image
                break
print("RETOPO src", name, "faces", len(src.data.polygons), "tex", tex_img.size[:] if tex_img else None, flush=True)

# the source must EMIT its texture, so the bake captures albedo with no lighting
emat = bpy.data.materials.new(name + "_emit")
emat.use_nodes = True
nt = emat.node_tree
nt.nodes.clear()
uvn = nt.nodes.new("ShaderNodeUVMap")
uvn.uv_map = src.data.uv_layers[0].name
tx = nt.nodes.new("ShaderNodeTexImage")
tx.image = tex_img
nt.links.new(uvn.outputs["UV"], tx.inputs["Vector"])
em = nt.nodes.new("ShaderNodeEmission")
out = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(tx.outputs["Color"], em.inputs["Color"])
nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
src.data.materials.clear()
src.data.materials.append(emat)

# --- the retopologised copy
tgt = src.copy()
tgt.data = src.data.copy()
tgt.name = name + "_retopo"
sc.collection.objects.link(tgt)
bpy.ops.object.select_all(action='DESELECT')
tgt.select_set(True)
bpy.context.view_layer.objects.active = tgt

bpy.context.view_layer.update()      # dimensions are stale on a freshly linked copy, and a
                                     # stale value picks too coarse a voxel (128k instead of 467k)
raw = len(tgt.data.polygons)
# QuadriFlow REFUSES a non-manifold mesh ("needs to be manifold and have face normals
# that point in a consistent direction") and silently returns FINISHED having changed
# nothing. AI meshes are never manifold: coincident shells, open edges. Voxel-remesh
# first — guaranteed watertight and manifold, and fusing the shells is itself a fix,
# since coincident surfaces are what made the outline hull poke through. A FINE voxel
# keeps the detail; QuadriFlow then reduces it to an even quad budget, so the result is
# both cleaner AND lighter than the original (Freestyle cost scales with face count).
vox = tgt.modifiers.new("vox", 'REMESH')
vox.mode = 'VOXEL'
vox.voxel_size = max(src.dimensions) / 280.0
vox.adaptivity = 0.0
vox.use_smooth_shade = True
bpy.ops.object.modifier_apply(modifier="vox")
import bmesh
_bm = bmesh.new(); _bm.from_mesh(tgt.data)
_nm = len([e for e in _bm.edges if not e.is_manifold]); _bm.free()
print("RETOPO voxel", round(vox.voxel_size, 5), "faces", raw, "->", len(tgt.data.polygons),
      "nonmanifold", _nm, flush=True)
bpy.ops.object.select_all(action='DESELECT')
tgt.select_set(True); bpy.context.view_layer.objects.active = tgt
before_qf = len(tgt.data.polygons)
bpy.ops.object.quadriflow_remesh(mode='FACES', target_faces=budget,
                                 use_preserve_sharp=False, use_preserve_boundary=False, seed=0)
kind = "quadriflow" if len(tgt.data.polygons) != before_qf else "QUADRIFLOW-NOOP"
if kind == "QUADRIFLOW-NOOP":
    dec = tgt.modifiers.new("dec2", 'DECIMATE')
    dec.ratio = min(1.0, budget * 2 / max(1, len(tgt.data.polygons)))
    bpy.ops.object.modifier_apply(modifier="dec2")
    kind = "decimate-fallback"
print("RETOPO remesh", kind, "faces", raw, "->", len(tgt.data.polygons), flush=True)

# --- fresh UVs on the new topology
while tgt.data.uv_layers:
    tgt.data.uv_layers.remove(tgt.data.uv_layers[0])
tgt.data.uv_layers.new(name="UVMap")
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.005)
bpy.ops.object.mode_set(mode='OBJECT')

# --- bake the painted atlas onto them
baked = bpy.data.images.new(name + "_retopo_base", px, px, alpha=False)
bmat = bpy.data.materials.new(name + "_baked")
bmat.use_nodes = True
nt2 = bmat.node_tree
nt2.nodes.clear()
tgt_tex = nt2.nodes.new("ShaderNodeTexImage")
tgt_tex.image = baked
nt2.nodes.active = tgt_tex
em2 = nt2.nodes.new("ShaderNodeEmission")
out2 = nt2.nodes.new("ShaderNodeOutputMaterial")
nt2.links.new(tgt_tex.outputs["Color"], em2.inputs["Color"])
nt2.links.new(em2.outputs["Emission"], out2.inputs["Surface"])
tgt.data.materials.clear()
tgt.data.materials.append(bmat)

sc.render.engine = 'CYCLES'
sc.cycles.samples = 1
try:
    sc.cycles.device = 'GPU'
except Exception:                                           # noqa: BLE001
    pass
sc.render.bake.use_selected_to_active = True
sc.render.bake.cage_extrusion = 0.02
sc.render.bake.max_ray_distance = 0.04
sc.render.bake.margin = 16
sc.render.bake.use_clear = True

bpy.ops.object.select_all(action='DESELECT')
src.select_set(True)
tgt.select_set(True)
bpy.context.view_layer.objects.active = tgt          # active = bake target
bpy.ops.object.bake(type='EMIT')

dst_png = os.path.join(PROPS, name + "_retopo_base.png")
baked.filepath_raw = dst_png
baked.file_format = 'PNG'
baked.save()
print("RETOPO baked", dst_png, flush=True)

# --- export the clean mesh alone
bpy.data.objects.remove(src, do_unlink=True)
bpy.ops.object.select_all(action='DESELECT')
tgt.select_set(True)
bpy.context.view_layer.objects.active = tgt
dst_glb = os.path.join(PROPS, name + "_retopo.glb")
bpy.ops.export_scene.gltf(filepath=dst_glb, use_selection=True)
print("RETOPO_DONE", dst_glb, "faces", len(tgt.data.polygons), flush=True)
