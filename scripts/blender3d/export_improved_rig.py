"""
Export the rig AS THE PIPELINE ACTUALLY USES IT.

The file UniRig writes is not what gets rendered: the kit loader smooths the predicted
weights, bakes an A-pose into the rest (the mesh is modelled arms-up, and posing from
there is what tore the shoulders), stands the feet on z=0, scales to height, bakes the
facing yaw and adds the jaw bone. This writes that state out so it can be opened and
judged directly.

Note the corrective-smooth modifier is a render-time modifier and does not travel in a
glTF file; everything else here is baked into the geometry and the weights.

  blender -b --factory-startup --python export_improved_rig.py -- <rigged.glb> <out.glb> [height=1.6]
"""
import sys, os
import bpy

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import character_kit as kit                                        # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, DST = argv[0], argv[1]
H = float(argv[2]) if len(argv) > 2 else 1.6

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
char, rig = kit.load_rigged_character(SRC, "hero", height=H)
for m in [m for m in char.modifiers if m.type == 'CORRECTIVE_SMOOTH']:
    char.modifiers.remove(m)
bpy.ops.object.select_all(action='DESELECT')
char.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.export_scene.gltf(filepath=DST, use_selection=True, export_apply=False,
                          export_animations=False, export_format='GLB')
print("EXPORT_DONE", DST, os.path.getsize(DST), flush=True)
