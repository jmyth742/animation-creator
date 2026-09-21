"""
AMBIENT OCCLUSION bake -> a designed shadow-shape map for the cel ramp.

The loudest remaining character defect is that a figure reads as a flat mass. A cel ramp
driven only by N.L puts the whole camera-facing side in one band whenever the key is not
frontal, so the cloak, the tunic and the hair become one silhouette with no interior
form.

Arc System Works solve this by painting a per-region offset into the shade threshold by
hand. AO is a very good automatic approximation of the same thing: it is dark exactly
where an artist would paint shadow — under the jaw, inside the hood, between the legs,
in the folds of a cloak, where the hair meets the neck — and it is view-independent, so
it is stable across a whole shot.

This bakes AO into the character's UV space once. `cel_material` reads it through
CHAR_AO and subtracts it from the ramp input, so those regions cross into the shadow
band regardless of where the key light is.

  blender -b --factory-startup --python char_ao_bake.py -- <mesh.glb> <name> [px=2048] [samples=64]

Writes <props>/<name>_ao.png.
"""
import sys
import os
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
glb, name = argv[0], argv[1]
px = int(argv[2]) if len(argv) > 2 else 2048
samples = int(argv[3]) if len(argv) > 3 else 64
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
ob = bpy.context.view_layer.objects.active
ob.name = name
print("AO src", name, "faces", len(ob.data.polygons), "uvs", len(ob.data.uv_layers), flush=True)

if not ob.data.uv_layers:
    sys.exit("AO: mesh has no UVs")

img = bpy.data.images.new(name + "_ao", px, px, alpha=False)
m = bpy.data.materials.new(name + "_aobake")
m.use_nodes = True
nt = m.node_tree
nt.nodes.clear()
diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
out = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(diff.outputs["BSDF"], out.inputs["Surface"])
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = img
nt.nodes.active = tex
ob.data.materials.clear()
ob.data.materials.append(m)

sc.render.engine = 'CYCLES'
sc.cycles.samples = samples
try:
    sc.cycles.device = 'GPU'
except Exception:                                               # noqa: BLE001
    pass
sc.render.bake.margin = 16
sc.render.bake.use_clear = True
sc.render.bake.use_selected_to_active = False

bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.bake(type='AO')

dst = os.path.join(PROPS, name + "_ao.png")
img.filepath_raw = dst
img.file_format = 'PNG'
img.save()
print("AO_DONE", dst, flush=True)
