"""Render a rigged CharacterGen lead with its new face variants: base | m3 (open) | blink.
Run: blender -b --factory-startup --python cg_face_check.py -- <rigged.glb> <name> <height> <faces_dir> <out.png>"""
import sys, os, math
import bpy, mathutils
sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import character_kit as kit
args = sys.argv[sys.argv.index("--") + 1:]
glb, name, height, faces_dir, out = args[0], args[1], float(args[2]), args[3], args[4]
sc = bpy.context.scene
for ob in list(sc.objects): bpy.data.objects.remove(ob, do_unlink=True)
char, rig = kit.load_rigged_character(glb, name, height=height, yaw_deg=180)
ctrl = kit.enable_face_variants(char, name, faces_dir)
sun = bpy.data.objects.new('sun', bpy.data.lights.new('s', 'SUN')); sun.data.energy = 3.5
sun.rotation_euler = (math.radians(60), 0, math.radians(25)); sc.collection.objects.link(sun)
wd = bpy.data.worlds.new('w'); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes['Background'].inputs['Color'].default_value = (0.62, 0.60, 0.58, 1)
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = 'BLENDER_EEVEE_NEXT'; sc.view_settings.view_transform = 'Standard'
head = rig.matrix_world @ rig.data.bones["head"].head_local
cam.data.lens = 85; sc.render.resolution_x, sc.render.resolution_y = 430, 430
cam.location = (head.x, head.y - 0.95, head.z + 0.08); tgt = mathutils.Vector((head.x, head.y, head.z + 0.06))
cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
outs = []
for key in ("base", "m3", "blink"):
    for k in ("m1", "m2", "m3", "m4", "m5", "blink"): ctrl[k].default_value = 1.0 if k == key else 0.0
    sc.render.filepath = out.replace(".png", f"_{key}.png"); bpy.ops.render.render(write_still=True); outs.append(sc.render.filepath)
print("CGFACE DONE", outs)
