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
    # a near-black line is a cut-out cue: nothing in a painted plate is outlined that way.
    # FILM_LINE_TINT gives the line a dark tint of the scene's own shadow colour instead.
    _lt = os.environ.get("FILM_LINE_TINT", "0.06,0.04,0.05")
    ls.linestyle.color = tuple(float(v) for v in _lt.split(","))
    ls.linestyle.alpha = float(os.environ.get("FILM_LINE_ALPHA", "1.0"))
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

_sun = os.environ.get("SET_SUN", "")
if _sun:
    _el, _az = [float(v) for v in _sun.split(",")]
    _n = 0
    for _ob in sc.objects:
        if _ob.type == 'LIGHT' and _ob.data.type == 'SUN' and _ob.name.startswith("sun"):
            _ob.rotation_euler = (math.radians(_el), 0.0, math.radians(_az))
            _n += 1
    print("SET_SUN", _el, _az, "lights", _n, flush=True)

# FILM_INTEGRATE=<haze>: sit the cast IN the plate rather than on it, plus a grade over
# the whole frame. A character against a matte painting reads as a sticker because it is
# more saturated than the painting, shares none of its atmosphere and nothing grounds it.
# Three fixes, all at render time: depth-based haze toward the plate's own mean colour, a
# contact patch under each figure, and one grade + grain over character and painting
# together so they share a single "film".
_integ = float(os.environ.get("FILM_INTEGRATE", "0") or 0)
if _integ > 0:
    sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
    import character_kit as _kit2
    sc.frame_set((f0 + f1) // 2)
    _cast = [o for o in sc.objects if o.type == 'MESH' and not o.name.endswith(("_nproxy", "_hull", "_contact"))
             and any(n in o.name for n in ("oisin", "niamh", "cg_"))]
    _plate = None
    for _m in bpy.data.materials:
        if _m.get("painter_projected") and _m.use_nodes:
            for _nd in _m.node_tree.nodes:
                if _nd.type == 'TEX_IMAGE' and _nd.image:
                    _plate = _nd.image
                    break
        if _plate:
            break
    _kit2.integrate_cast(_cast, co, _plate, haze=_integ)
    if os.environ.get("FILM_CONTACT", "1") not in ("", "0"):
        for _ch in _cast:
            _rig = _ch.parent if _ch.parent and _ch.parent.type == 'ARMATURE' else None
            _kit2.contact_shadow(_ch, _rig, co)
    # one grade over the whole frame: gentle lift + grain, so both layers share a film
    sc.use_nodes = True
    _nt = sc.node_tree
    _nt.nodes.clear()
    _rl = _nt.nodes.new("CompositorNodeRLayers")
    _cur = _nt.nodes.new("CompositorNodeCurveRGB")
    _cur.mapping.curves[3].points[0].location = (0.0, 0.022)      # lift the blacks
    _cur.mapping.curves[3].points[1].location = (1.0, 0.985)
    _cur.mapping.update()
    _nt.links.new(_rl.outputs["Image"], _cur.inputs["Image"])
    _gl = _nt.nodes.new("CompositorNodeGlare")
    _gl.glare_type = 'FOG_GLOW'
    _gl.quality = 'MEDIUM'
    _gl.mix = -0.72
    _gl.threshold = 0.86
    _nt.links.new(_cur.outputs["Image"], _gl.inputs["Image"])
    _comp = _nt.nodes.new("CompositorNodeComposite")
    _nt.links.new(_gl.outputs["Image"], _comp.inputs["Image"])
    sc.render.use_compositing = True
    print("INTEGRATE grade on, haze", _integ, flush=True)

# FILM_PASSES=1 / FILM_COMPLINE=<strength>: multi-pass output and comp-derived line art.
# Freestyle costs ~15 s/frame on the CPU while the GPU idles, it can only draw silhouette
# and contour, and every line change needs a full re-render. Normal- and depth-pass edge
# detection runs on the GPU in the compositor, costs ~nothing, gives INTERIOR lines
# (cloth folds, hair strands, garment breaks) that Freestyle never could, and lets line
# weight vary with depth. Writing multilayer EXR alongside means a later re-grade or
# re-line needs no re-render at all.
_passes = os.environ.get("FILM_PASSES", "0") not in ("", "0")
_cline = float(os.environ.get("FILM_COMPLINE", "0") or 0)
if _passes or _cline > 0:
    _vl = sc.view_layers[0]
    _vl.use_pass_normal = True
    _vl.use_pass_z = True
    _vl.use_pass_cryptomatte_object = True
    _vl.pass_cryptomatte_depth = 6
    if _passes:
        sc.render.image_settings.file_format = 'OPEN_EXR_MULTILAYER'
        sc.render.image_settings.color_depth = '16'
        sc.render.image_settings.exr_codec = 'ZIP'
    if _cline > 0:
        sc.use_nodes = True
        _nt = sc.node_tree
        _nt.nodes.clear()
        _rl = _nt.nodes.new("CompositorNodeRLayers")

        def _edge(sock, normalize, lo, hi):
            """Sobel on a pass -> a 0..1 edge mask."""
            _src = sock
            if normalize:
                _nz = _nt.nodes.new("CompositorNodeNormalize")
                _nt.links.new(sock, _nz.inputs[0]); _src = _nz.outputs[0]
            _f = _nt.nodes.new("CompositorNodeFilter")
            _f.filter_type = 'SOBEL'
            _f.inputs["Fac"].default_value = 1.0
            _nt.links.new(_src, _f.inputs["Image"])
            _bw = _nt.nodes.new("CompositorNodeRGBToBW")
            _nt.links.new(_f.outputs["Image"], _bw.inputs["Image"])
            _mr = _nt.nodes.new("CompositorNodeMapRange")
            _mr.inputs["From Min"].default_value = lo
            _mr.inputs["From Max"].default_value = hi
            _mr.use_clamp = True
            _nt.links.new(_bw.outputs["Val"], _mr.inputs["Value"])
            return _mr.outputs["Value"]

        _nlo = float(os.environ.get("FILM_COMPLINE_NLO", "0.18"))
        _nhi = float(os.environ.get("FILM_COMPLINE_NHI", "0.55"))
        _zlo = float(os.environ.get("FILM_COMPLINE_ZLO", "0.004"))
        _zhi = float(os.environ.get("FILM_COMPLINE_ZHI", "0.030"))
        _en = _edge(_rl.outputs["Normal"], False, _nlo, _nhi)     # folds and creases
        _mx = _nt.nodes.new("CompositorNodeMath"); _mx.operation = 'MAXIMUM'
        _nt.links.new(_en, _mx.inputs[0])
        if os.environ.get("FILM_COMPLINE_Z", "1") not in ("", "0"):
            # The depth edge is the SILHOUETTE. Freestyle draws a crisper one, so when
            # Freestyle is on, leave the contour to it and let the compositor do only what
            # Freestyle cannot: interior folds from the normal pass.
            _ez = _edge(_rl.outputs["Depth"], True, _zlo, _zhi)
            _nt.links.new(_ez, _mx.inputs[1])
        else:
            _mx.inputs[1].default_value = 0.0
        # CAST ONLY. Unmasked, the depth Sobel draws on the dome and across the plate's own
        # painted edges — lines in the sky. A cryptomatte of the cast objects confines the
        # line work to the characters, which is where drawn lines belong.
        _names = [o.name for o in sc.objects if o.type == 'MESH'
                  and not o.name.endswith(("_nproxy", "_hull", "_contact"))
                  and any(n in o.name for n in ("oisin", "niamh", "cg_"))]
        _masked = _mx.outputs["Value"]
        if _names:
            _cm = _nt.nodes.new("CompositorNodeCryptomatteV2")
            _cm.source = 'RENDER'
            _cm.scene = sc
            _cm.layer_name = _vl.name + ".CryptoObject"   # the enum is prefixed by the view layer
            _cm.matte_id = ",".join(_names)
            _nt.links.new(_rl.outputs["Image"], _cm.inputs["Image"])
            _cmul = _nt.nodes.new("CompositorNodeMath"); _cmul.operation = 'MULTIPLY'
            _nt.links.new(_mx.outputs["Value"], _cmul.inputs[0])
            _nt.links.new(_cm.outputs["Matte"], _cmul.inputs[1])
            _masked = _cmul.outputs["Value"]
            print("COMPLINE masked to cast:", _names, flush=True)
        _st = _nt.nodes.new("CompositorNodeMath"); _st.operation = 'MULTIPLY'
        _st.inputs[1].default_value = _cline
        _nt.links.new(_masked, _st.inputs[0])
        _tint = [float(v) for v in os.environ.get("FILM_LINE_TINT", "0.17,0.11,0.13").split(",")]
        _mix = _nt.nodes.new("CompositorNodeMixRGB")
        _mix.blend_type = 'MIX'
        # the compositor MixRGB names both colour sockets "Image", so address them by index
        _mix.inputs[2].default_value = (_tint[0], _tint[1], _tint[2], 1.0)
        _nt.links.new(_rl.outputs["Image"], _mix.inputs[1])
        _nt.links.new(_st.outputs["Value"], _mix.inputs[0])
        _cur = _nt.nodes.new("CompositorNodeCurveRGB")
        _cur.mapping.curves[3].points[0].location = (0.0, 0.022)
        _cur.mapping.curves[3].points[1].location = (1.0, 0.985)
        _cur.mapping.update()
        _nt.links.new(_mix.outputs["Image"], _cur.inputs["Image"])
        # FILM_MATTE=1 also writes the cast matte beside each frame, so a post pass can
        # style the CHARACTERS separately from the painted plate. A global stylisation
        # cannot fix the measured problem (the cast carry about half the detail of the
        # background); it has to be applied where the detail is missing.
        if os.environ.get("FILM_MATTE", "0") not in ("", "0") and _names:
            _mout = _nt.nodes.new("CompositorNodeOutputFile")
            _mout.base_path = outdir
            _mout.file_slots.clear()
            _mout.file_slots.new("matte_")
            _mout.format.file_format = 'PNG'
            _mout.format.color_mode = 'BW'
            _nt.links.new(_cm.outputs["Matte"], _mout.inputs["matte_"])
            print("MATTE output on", flush=True)
        _cmp = _nt.nodes.new("CompositorNodeComposite")
        _nt.links.new(_cur.outputs["Image"], _cmp.inputs["Image"])
        sc.render.use_compositing = True
        print("COMPLINE on strength", _cline, "normal", _nlo, _nhi, "depth", _zlo, _zhi, flush=True)

# FILM_STEP_ANIM=<n>: animate the CAST on twos (or threes). Verified studio practice —
# Arc System Works disable interpolation entirely so every frame is a held pose, and it
# is what makes 3D read as drawn rather than as smoothly interpolated CG. Applied as a
# non-destructive Stepped f-modifier at render time, and only to the cast: the CAMERA
# must keep moving smoothly or the whole frame judders.
_stepn = int(os.environ.get("FILM_STEP_ANIM", "0") or 0)
if _stepn > 1:
    _stepped = 0
    for _ob in sc.objects:
        if _ob.name in ("shotcam", "painter_cam", "painter_master"):
            continue
        if _ob.type not in ('ARMATURE', 'MESH'):
            continue
        for _holder in (_ob, _ob.data, getattr(_ob, "active_material", None)):
            _ad = getattr(_holder, "animation_data", None)
            if not _ad or not _ad.action:
                continue
            for _fcu in _ad.action.fcurves:
                if any(m.type == 'STEPPED' for m in _fcu.modifiers):
                    continue
                _m = _fcu.modifiers.new('STEPPED')
                _m.frame_step = float(_stepn)
                _stepped += 1
    print("STEP ANIM on", _stepn, "curves", _stepped, flush=True)

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
