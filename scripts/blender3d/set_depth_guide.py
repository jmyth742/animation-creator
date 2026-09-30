"""
SET DEPTH GUIDE -- render the REAL set geometry's depth from the painter camera.

The painted-world plates were never designed as sets: they are 640x360 final frames of a
video camera move, upscaled, with no camera model and no defined ground plane. Everything
we do to fit characters into them is guessing geometry after the fact. This turns the order
around: the set's own geometry (valley_set with the painter OFF) is the authority, and its
depth from the painter camera becomes the conditioning image for a depth-controlled plate
generation (plate_from_geometry.py), so the painting conforms to geometry we control.

  blender -b --python set_depth_guide.py -- <out_prefix> [winter]
Writes <out_prefix>_color.png (the primitive set), <out_prefix>_depth.png (near = white,
8-bit, ControlNet convention) at 1664x960 from PAINTER_LOC/PAINTER_TGT, lens 32.
"""
import os, sys, math
import bpy, mathutils
sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
os.environ["SET_BACKDROP"] = "0"           # primitives, no plate: geometry is the authority here
os.environ["SET_RELIEF"] = "0"
import valley_set

argv = sys.argv[sys.argv.index("--") + 1:]
out = argv[0]; winter = len(argv) > 1 and argv[1] == "winter"
NEAR, FAR = float(os.environ.get("DG_NEAR", "4.0")), float(os.environ.get("DG_FAR", "70.0"))

sc = bpy.context.scene
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
valley_set.build_set(sc, winter=winter)
cam_d = bpy.data.cameras.new("guide"); cam_d.lens = 32.0; cam_d.sensor_width = 36
cam = bpy.data.objects.new("guide", cam_d); sc.collection.objects.link(cam)
loc, tgt = mathutils.Vector(valley_set.PAINTER_LOC), mathutils.Vector(valley_set.PAINTER_TGT)
cam.location = loc
cam.rotation_euler = (tgt - loc).to_track_quat('-Z', 'Y').to_euler()
sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = 1664, 960
sc.render.resolution_percentage = 100
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.eevee.taa_render_samples = 8
sc.render.film_transparent = False
if not sc.world: sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.70, 0.92, 1)
sun = bpy.data.lights.new("sun", 'SUN'); sun.energy = 3.0
so = bpy.data.objects.new("sun", sun); sc.collection.objects.link(so)
so.rotation_euler = (math.radians(52), 0, math.radians(118))
vl = sc.view_layers[0]; vl.use_pass_z = True
# the depth is DATA: AgX would lift and flatten it into a uniform grey
sc.view_settings.view_transform = 'Standard'; sc.view_settings.look = 'None'

sc.use_nodes = True
nt = sc.node_tree; nt.nodes.clear()
rl = nt.nodes.new("CompositorNodeRLayers")
comp = nt.nodes.new("CompositorNodeComposite")
nt.links.new(rl.outputs["Image"], comp.inputs["Image"])
# depth: 1/z style ramp so the near ground gets most of the range (what a monocular
# depth model and ControlNet-depth both expect: near bright, far dark, sky black)
mr = nt.nodes.new("CompositorNodeMapRange")
mr.inputs["From Min"].default_value = NEAR; mr.inputs["From Max"].default_value = FAR
mr.inputs["To Min"].default_value = 1.0; mr.inputs["To Max"].default_value = 0.0
mr.use_clamp = True
nt.links.new(rl.outputs["Depth"], mr.inputs["Value"])
gam = nt.nodes.new("CompositorNodeGamma"); gam.inputs["Gamma"].default_value = 0.6
nt.links.new(mr.outputs["Value"], gam.inputs["Image"])
fo = nt.nodes.new("CompositorNodeOutputFile")
fo.base_path = os.path.dirname(out); fo.file_slots[0].path = os.path.basename(out) + "_depth_"
fo.format.file_format = 'PNG'; fo.format.color_mode = 'BW'; fo.format.color_depth = '8'
nt.links.new(gam.outputs["Image"], fo.inputs[0])

sc.render.filepath = out + "_color.png"
bpy.ops.render.render(write_still=True)
# File Output appends the frame number; give it the plain name
import glob, shutil
d = sorted(glob.glob(out + "_depth_*.png"))
if d: shutil.move(d[-1], out + "_depth.png")
print("DEPTH_GUIDE", out + "_color.png", out + "_depth.png", flush=True)
