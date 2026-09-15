"""
Film the studio with a camera that exists IN the scene: static frame,
tracking pan, dolly, orbit or crane — all keyframed, all deterministic.

Run: blender -b --factory-startup <studio.blend> --python film.py -- \
     <outdir> <cam x,y,z> <target x,y,z> [lens] [f0] [f1] [move] [args]

  move = static                       hold the frame
         pan                          fixed position, rotate to TRACK the
                                      character (target arg ignored per-frame)
         dolly:x2,y2,z2               glide position → x2,y2,z2, keep aim
         orbit:degrees                circle the target by N degrees
         crane:dz                     rise/fall by dz metres while aiming
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
move = args[6] if len(args) > 6 else "static"
if len(args) > 8:
    bpy.context.scene.render.resolution_x = int(args[7])
    bpy.context.scene.render.resolution_y = int(args[8])

import os
sc = bpy.context.scene
if os.environ.get("FILM_SAMPLES"):
    sc.eevee.taa_render_samples = int(os.environ["FILM_SAMPLES"])
if os.environ.get("FILM_LINES"):
    # drawn outlines on the CAST only — the single loudest "drawn by an
    # adult" cue in cel animation
    sc.render.use_freestyle = True
    sc.render.line_thickness = float(os.environ.get("FILM_LINES", "1.4"))
    vl = sc.view_layers[0]
    vl.use_freestyle = True
    fs = vl.freestyle_settings
    while fs.linesets:
        fs.linesets.remove(fs.linesets[0])
    ls = fs.linesets.new("cast")
    ls.select_silhouette = True
    ls.select_border = False
    ls.select_crease = True
    ls.select_by_group = True
    grp = bpy.data.collections.get("cast_lines")
    if grp is None:
        grp = bpy.data.collections.new("cast_lines")
        sc.collection.children.link(grp)
        for ob in sc.objects:
            nm = ob.name.lower()
            if ob.type == 'MESH' and any(k in nm for k in
                                         ("oisin", "niamh", "char")):
                grp.objects.link(ob)
    ls.collection = grp
    ls.linestyle.thickness = float(os.environ.get("FILM_LINES", "1.4"))
    ls.linestyle.color = (0.06, 0.04, 0.05)
cam = bpy.data.cameras.new("shotcam")
cam.lens = lens
if os.environ.get("FILM_DOF"):
    cam.dof.use_dof = True
    cam.dof.aperture_fstop = float(os.environ["FILM_DOF"])
co = bpy.data.objects.new("shotcam", cam)
sc.collection.objects.link(co)
sc.camera = co
p0 = mathutils.Vector(tuple(float(v) for v in campos.split(",")))
t0 = mathutils.Vector(tuple(float(v) for v in tgt.split(",")))
rig = bpy.data.objects.get("rig")

def aim(pos, target):
    d = target - pos
    return d.to_track_quat('-Z', 'Y').to_euler()

def char_at(f):
    sc.frame_set(f)
    return rig.matrix_world.translation + mathutils.Vector((0, 0, 1.2)) \
        if rig else t0

for f in range(f0, f1 + 1):
    t = (f - f0) / max(1, f1 - f0)
    e = t * t * (3 - 2 * t)
    if move == "pan":
        pos, target = p0, char_at(f)
    elif move.startswith("dolly:"):
        p1 = mathutils.Vector(tuple(float(v) for v in move[6:].split(",")))
        pos, target = p0.lerp(p1, e), t0
    elif move.startswith("orbit:"):
        ang = math.radians(float(move[6:])) * e
        rel = p0 - t0
        rot = mathutils.Matrix.Rotation(ang, 4, 'Z')
        pos, target = t0 + (rot @ rel), t0
    elif move.startswith("crane:"):
        dz = float(move[6:])
        pos = p0 + mathutils.Vector((0, 0, dz * e))
        target = t0
    else:
        pos, target = p0, t0
    sc.frame_set(f)
    co.location = pos
    co.rotation_euler = aim(pos, target)
    co.keyframe_insert("location")
    co.keyframe_insert("rotation_euler")
    if cam.dof.use_dof:
        cam.dof.focus_distance = (target - mathutils.Vector(pos)).length
        cam.dof.keyframe_insert("focus_distance")

sc.frame_start, sc.frame_end = f0, f1
sc.render.filepath = outdir + "/frame_"
sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(animation=True)
print("ANGLE FILMED", move)
