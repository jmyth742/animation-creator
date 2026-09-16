"""Kit procedural walk driving a UniRig-rigged character (Day-5 integration probe).
Run: blender -b --factory-startup --python rigged_gait_test.py -- <rigged.glb> <name> <height> <outdir> <tag> [frames=48]"""
import sys, os, math
import bpy, mathutils
sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import character_kit as kit
args = sys.argv[sys.argv.index("--") + 1:]
glb, name, height, outdir, tag = args[0], args[1], float(args[2]), args[3], args[4]
N = int(args[5]) if len(args) > 5 else 48
os.makedirs(outdir, exist_ok=True); sc = bpy.context.scene
for ob in list(sc.objects): bpy.data.objects.remove(ob, do_unlink=True)
char, rig = kit.load_rigged_character(glb, name, height=height)
path = kit.path_fn_from_points([(0.0, -1.5), (0.0, 1.5)], lambda x, y: 0.0)
kit.apply_walk(rig, path, 1, N, fps=16)
sc.render.fps = 16
sun = bpy.data.objects.new('sun', bpy.data.lights.new('s', 'SUN')); sun.data.energy = 3.5
sun.rotation_euler = (math.radians(60), 0, math.radians(25)); sc.collection.objects.link(sun)
wd = bpy.data.worlds.new('w'); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes['Background'].inputs['Color'].default_value = (0.62, 0.60, 0.58, 1)
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = 'BLENDER_EEVEE_NEXT'; sc.view_settings.view_transform = 'Standard'
ctr = mathutils.Vector((0, 0, height * 0.5)); d = 2.4 * max(3.0, height) + 1.5; a = math.radians(35)
cam.location = (ctr.x + d * math.sin(a), ctr.y - d * math.cos(a), ctr.z + 0.25 * height)
cam.rotation_euler = (ctr - cam.location).to_track_quat('-Z', 'Y').to_euler()
sc.render.resolution_x, sc.render.resolution_y = 640, 480; sc.frame_start, sc.frame_end = 1, N
sc.render.filepath = f"{outdir}/{tag}_"; sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(animation=True); print("RIGGED GAIT DONE", tag)
