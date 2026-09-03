"""
Film the studio from any angle: a camera is just a parameter now.

Run: blender -b --factory-startup <studio.blend> --python film.py -- \
       <outdir> <cam_x,y,z> <target_x,y,z> [lens] [f_start] [f_end]
"""
import sys
import math
import bpy
import mathutils

args = sys.argv[sys.argv.index("--") + 1:]
outdir, campos, tgt = args[0], args[1], args[2]
lens = float(args[3]) if len(args) > 3 else 35.0
f0 = int(args[4]) if len(args) > 4 else 1
f1 = int(args[5]) if len(args) > 5 else 81

sc = bpy.context.scene
cam = bpy.data.cameras.new("shotcam")
cam.lens = lens
co = bpy.data.objects.new("shotcam", cam)
co.location = tuple(float(v) for v in campos.split(","))
target = mathutils.Vector(tuple(float(v) for v in tgt.split(",")))
d = target - co.location
co.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
sc.collection.objects.link(co)
sc.camera = co
sc.frame_start, sc.frame_end = f0, f1
sc.render.filepath = outdir + "/frame_"
sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(animation=True)
print("ANGLE FILMED", campos)
