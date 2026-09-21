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
if len(args) <= 8 and os.environ.get("FILM_RES"):      # e.g. FILM_RES=1664x960
    rx, ry = os.environ["FILM_RES"].lower().split("x")
    sc.render.resolution_x, sc.render.resolution_y = int(rx), int(ry)
    sc.render.resolution_percentage = 100
if os.environ.get("FILM_SAMPLES"):
    sc.eevee.taa_render_samples = int(os.environ["FILM_SAMPLES"])
if os.environ.get("FILM_LINES", "0") not in ("", "0"):
    # drawn outlines on the CAST only — the single loudest "drawn by an
    # adult" cue in cel animation
    sc.render.use_freestyle = True
    # FILM_LINES is the EFFECTIVE stroke width in pixels: the scene unit thickness
    # multiplies the linestyle thickness, so the unit stays 1.0 (2.0x2.0 at 480p was
    # 4 px; 4.0x4.0 at 960p was 16 px — twice too heavy relative to frame)
    sc.render.line_thickness = 1.0
    vl = sc.view_layers[0]
    vl.use_freestyle = True
    fs = vl.freestyle_settings
    # Freestyle is CPU-bound and walks the WHOLE set each frame: cull what
    # the camera cannot see (measured: the dominant per-frame cost)
    fs.use_culling = True
    while fs.linesets:
        fs.linesets.remove(fs.linesets[0])
    ls = fs.linesets.new("cast")
    # FILM_LINE_MODE=ext: outer contour only (no interior lump marks)
    ext = os.environ.get("FILM_LINE_MODE", "sil") == "ext"
    ls.select_silhouette = not ext
    ls.select_external_contour = ext
    ls.select_border = False
    # crease edges on AI meshes = black scribbles (day1 grids); default off
    ls.select_crease = os.environ.get("FILM_LINE_CREASE", "0") == "1"
    ls.select_by_collection = True
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
    # drop stroke chains shorter than N px: kills the residual hatching
    minlen = float(os.environ.get("FILM_LINE_MINLEN", "6"))
    if minlen > 0:
        ls.linestyle.use_length_min = True
        ls.linestyle.length_min = minlen
if os.environ.get("CHAR_NORMALFIX", "0") == "1":
    # normal editing at RENDER time (build_film keyframes 1000+ frames and
    # would re-evaluate a build-time transfer on every one): copy custom
    # normals from a heavily smoothed proxy of each cast mesh
    for ob in list(sc.objects):
        nm = ob.name.lower()
        if ob.type != 'MESH' or not any(k in nm for k in ("oisin", "niamh")) or nm.endswith("_nproxy"):
            continue
        if any(m.type == 'DATA_TRANSFER' for m in ob.modifiers):
            continue
        proxy = ob.copy(); proxy.data = ob.data.copy(); proxy.name = ob.name + "_nproxy"
        proxy.animation_data_clear(); proxy.modifiers.clear(); proxy.parent = None
        proxy.matrix_world = ob.matrix_world.copy()
        sc.collection.objects.link(proxy)
        pm = proxy.modifiers.new("blur", 'SMOOTH'); pm.factor = 1.0; pm.iterations = 60
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(proxy.evaluated_get(dg))
        proxy.modifiers.clear(); proxy.data = me
        dt = ob.modifiers.new("normals", 'DATA_TRANSFER')
        dt.object = proxy; dt.use_loop_data = True; dt.data_types_loops = {'CUSTOM_NORMAL'}
        dt.loop_mapping = 'POLYINTERP_NEAREST'
        # the transfer must see the REST mesh: put it before the armature deform
        for _ in range(len(ob.modifiers)):
            bpy.context.view_layer.objects.active = ob
            if ob.modifiers[0].name == "normals":
                break
            bpy.ops.object.modifier_move_up(modifier="normals")
        proxy.hide_render = True; proxy.hide_viewport = True
        print("NORMALFIX applied to", ob.name)
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

# PER-SHOT PAINTED WORLD. A set built with painter.py carries a painter camera
# and materials that sample the concept plate through a UV Project modifier.
# One fixed painter camera only serves shots near it (review/env_painted_*_probes.png:
# everything else streaks), so each shot re-projects from ITS OWN camera at the
# middle frame: static shots are exactly the plate + occlusion + cast; moves get
# real parallax near the mid frame. The plate is chosen by the shot's heading
# against the set's master heading (master / side / reverse / closer), or FILM_PLATE.
pc = bpy.data.objects.get("painter_cam")
if pc is not None and os.environ.get("FILM_PAINTER", "shot") == "shot":
    fm = (f0 + f1) // 2
    sc.frame_set(fm)
    master_dir = mathutils.Vector(pc.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1)))
    pc.matrix_world = co.matrix_world.copy()
    pc.data.type = 'PERSP'; pc.data.lens = cam.lens
    pc.data.sensor_width = cam.sensor_width; pc.data.sensor_fit = cam.sensor_fit
    ratio = sc.render.resolution_x / sc.render.resolution_y
    plate = os.environ.get("FILM_PLATE")
    mats = [m for m in bpy.data.materials if m.get("painter_projected")]
    cur = next((nd.image for m in mats for nd in m.node_tree.nodes if nd.type == 'TEX_IMAGE' and nd.image), None)
    shot_dir = mathutils.Vector(co.matrix_world.to_3x3() @ mathutils.Vector((0, 0, -1)))
    a, b = master_dir.xy.normalized(), shot_dir.xy.normalized()
    ang = math.degrees(math.acos(max(-1.0, min(1.0, a.dot(b)))))
    if not plate and cur is not None:
        setup = "master" if ang < 50 else ("side" if ang < 130 else "reverse")
        if setup == "master" and cam.lens >= 60: setup = "closer"
        folder = os.path.dirname(os.path.abspath(bpy.path.abspath(cur.filepath)))
        stem = os.path.basename(cur.filepath).replace("_4x.png", "").replace(".png", "")
        season = stem[len("master"):] if stem.startswith("master") else ""      # '' or '_winter'
        for cand in (f"{folder}/{setup}{season}_4x.png", f"{folder}/{setup}{season}.png"):
            if os.path.exists(cand): plate = cand; break
        else:
            setup = stem   # no such setup in this season: keep the set's own plate
        print("PAINTER shot heading %.0f deg off master -> %s" % (ang, setup))
    if plate and cur is not None and os.path.abspath(bpy.path.abspath(cur.filepath)) != os.path.abspath(plate):
        img = bpy.data.images.load(plate)
        for m in mats:
            for nd in m.node_tree.nodes:
                if nd.type == 'TEX_IMAGE': nd.image = img
        cur = img
    for ob in sc.objects:
        for md in ob.modifiers:
            if md.type != 'UV_PROJECT' or not md.projectors[0].object: continue
            pname = md.projectors[0].object.name          # by name: RNA wrappers are never `is`
            if pname == pc.name:
                md.aspect_x = ratio; md.aspect_y = 1.0
            elif pname == "painter_master" and ang < 50:
                # a 'fixed' surface (the lake) near the master heading: the per-shot projection is
                # exact there, and the fixed one would sit offset beside it (q9 est probe)
                md.projectors[0].object = pc; md.aspect_x = ratio; md.aspect_y = 1.0
    print("PAINTER per-shot projection from frame", fm, "plate", os.path.basename(cur.filepath) if cur else None)

# FILM_HULL=<px>: inverted-hull outlines instead of Freestyle (GPU, not ~15 s/frame CPU;
# width compensated for distance+FOV so it is constant on screen). Set FILM_LINES=0 with it.
_hull = float(os.environ.get("FILM_HULL", "0") or 0)
if _hull > 0:
    sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
    import character_kit as _kit
    sc.frame_set((f0 + f1) // 2)
    for _ob in list(sc.objects):          # snapshot: the shells are added while iterating
        if _ob.type == "MESH" and not _ob.hide_render and not _ob.name.endswith(("_nproxy", "_hull")) and any(n in _ob.name for n in ("oisin", "niamh", "cg_")):
            _kit.add_outline_hull(_ob, _hull, co, sc.render.resolution_y)

sc.frame_start, sc.frame_end = f0, f1
sc.frame_step = int(os.environ.get("FILM_STEP", "1") or 1)   # probes: every Nth frame
sc.render.filepath = outdir + "/frame_"
sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(animation=True)
print("ANGLE FILMED", move)
