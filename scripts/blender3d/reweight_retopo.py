"""
Put a retopologised character back on its UniRig skeleton, keeping the known-good rig.

Re-running UniRig on the new mesh would give a different skeleton and invalidate every
retargeted MoMask action. Instead the existing rig is kept and only the skin moves: the
vertex groups are transferred from the old skinned mesh onto the new topology by nearest
interpolated face, which is exactly what the groups describe (a smooth field over the
surface), so the clean mesh inherits the deformation that was already tuned.

Run:
  blender -b --factory-startup --python reweight_retopo.py -- <name>
Reads  <props>/<name>_rigged.glb and <props>/<name>_retopo.glb
Writes <props>/<name>_retopo_rigged.glb
"""
import sys
import os
import bpy

name = sys.argv[sys.argv.index("--") + 1]
PROPS = "/workspace/text-to-video/series/tir-na-nog-legend/meshes/props"
sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)

# --- the rig, with its skinned mesh
bpy.ops.import_scene.gltf(filepath=os.path.join(PROPS, name + "_rigged.glb"))
rig = next(o for o in sc.objects if o.type == 'ARMATURE')
old = max((o for o in sc.objects if o.type == 'MESH'), key=lambda o: len(o.data.polygons))
old.name = name + "_old"
print("REWEIGHT rig", rig.name, "bones", len(rig.data.bones), "old mesh faces", len(old.data.polygons), flush=True)

# --- the clean mesh
before = set(sc.objects)
bpy.ops.import_scene.gltf(filepath=os.path.join(PROPS, name + "_retopo.glb"))
new = max((o for o in sc.objects if o not in before and o.type == 'MESH'), key=lambda o: len(o.data.polygons))
new.name = name + "_retopo"
for o in list(sc.objects):
    if o not in before and o.type != 'MESH' and o is not new:
        bpy.data.objects.remove(o, do_unlink=True)

# --- align the clean mesh onto the skinned one (the two GLBs need not share a transform)
bpy.context.view_layer.update()


def bbox(o):
    cs = [o.matrix_world @ v.co for v in o.data.vertices]
    lo = [min(c[i] for c in cs) for i in range(3)]
    hi = [max(c[i] for c in cs) for i in range(3)]
    return lo, hi


olo, ohi = bbox(old)
nlo, nhi = bbox(new)
osz = max(ohi[i] - olo[i] for i in range(3))
nsz = max(nhi[i] - nlo[i] for i in range(3))
s = osz / nsz if nsz else 1.0
new.scale = [v * s for v in new.scale]
bpy.context.view_layer.update()
nlo, nhi = bbox(new)
for i in range(3):
    new.location[i] += ((olo[i] + ohi[i]) / 2) - ((nlo[i] + nhi[i]) / 2)
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='DESELECT')
new.select_set(True)
bpy.context.view_layer.objects.active = new
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
print("REWEIGHT aligned scale %.4f" % s, flush=True)

# --- weights: old skinned mesh -> new topology
# the MODIFIER, not bpy.ops.object.data_transfer: the operator's layers_select_src
# only accepts ACTIVE/NAME/INDEX, so it cannot copy every vertex group in one pass.
bpy.ops.object.select_all(action='DESELECT')
new.select_set(True)
bpy.context.view_layer.objects.active = new
for vg in list(new.vertex_groups):
    new.vertex_groups.remove(vg)
dt = new.modifiers.new("dt", 'DATA_TRANSFER')
dt.object = old
dt.use_vert_data = True
dt.data_types_verts = {'VGROUP_WEIGHTS'}
dt.vert_mapping = 'POLYINTERP_NEAREST'
dt.layers_vgroup_select_src = 'ALL'
dt.layers_vgroup_select_dst = 'NAME'
bpy.ops.object.datalayout_transfer(modifier=dt.name)     # create the groups on the target
bpy.ops.object.modifier_apply(modifier=dt.name)          # then fill them
got = len(new.vertex_groups)
print("REWEIGHT vertex groups", got, flush=True)
if got == 0:
    sys.exit("REWEIGHT FAILED: no vertex groups transferred")

# --- bind to the armature
for md in list(new.modifiers):
    new.modifiers.remove(md)
new.parent = rig
new.matrix_parent_inverse = rig.matrix_world.inverted()
amod = new.modifiers.new("Armature", 'ARMATURE')
amod.object = rig

bpy.data.objects.remove(old, do_unlink=True)
bpy.ops.object.select_all(action='SELECT')
dst = os.path.join(PROPS, name + "_retopo_rigged.glb")
bpy.ops.export_scene.gltf(filepath=dst, use_selection=True)
print("REWEIGHT_DONE", dst, "faces", len(new.data.polygons), "groups", got, flush=True)
