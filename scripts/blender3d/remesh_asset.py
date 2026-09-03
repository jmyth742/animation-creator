"""QuadriFlow remesh per the asset spec: cleanup, budgeted quads, report.
Run: blender -b --python remesh_asset.py -- <painted.glb> <out.glb> <faces>"""
import sys
import bpy

glb, out, budget = sys.argv[-3], sys.argv[-2], int(sys.argv[-1])
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
# stage-4 cleanup: floaters, weld, degenerate faces
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.remove_doubles(threshold=0.0001)
bpy.ops.mesh.dissolve_degenerate()
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode='OBJECT')
raw = len(ob.data.polygons)
if raw > 500000:
    dec = ob.modifiers.new("dec", 'DECIMATE')
    dec.ratio = 150000 / raw
    bpy.ops.object.modifier_apply(modifier="dec")
try:
    bpy.ops.object.quadriflow_remesh(mode='FACES', target_faces=budget,
                                     use_preserve_sharp=True,
                                     use_preserve_boundary=True, seed=0)
    kind = "quadriflow"
except Exception as e:                                     # noqa: BLE001
    dec = ob.modifiers.new("dec2", 'DECIMATE')
    dec.ratio = min(1.0, budget * 2 / max(1, len(ob.data.polygons)))
    bpy.ops.object.modifier_apply(modifier="dec2")
    kind = f"decimate-fallback({e})"
bpy.ops.export_scene.gltf(filepath=out, use_selection=False)
print(f"REMESH_DONE {out} raw={raw} final={len(ob.data.polygons)} via={kind}")
