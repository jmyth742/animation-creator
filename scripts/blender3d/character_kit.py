"""
Reusable character machinery for the virtual studio.

load_character(mesh_path, name)      -> textured, smooth, normalised mesh
rig_character(char, name)            -> 14-bone armature (incl. jaw),
                                        deterministic numpy skinning
apply_walk(rig, path_fn, f0, f1)     -> articulated gait along path_fn(t)
apply_idle(rig, f0, f1, look_at_fn)  -> breathing idle, head tracking
apply_talk(rig, envelope, f0)        -> jaw + head driven by an audio
                                        amplitude envelope (one value/frame)
"""
import math
import bpy
import numpy as np
import mathutils

HEIGHT = {"default": 1.75}


def _weld_shells(char, name):
    import os
    if os.environ.get("CHAR_SHELLCULL", "1") not in ("", "0"):   # default: weld seams (the "700 shells" were unshared marching-cubes seams), cull shells < N faces
        # AI meshes come with hundreds of loose shells (hair strands, crumbs):
        # merge coincident verts, then delete shells with fewer than N faces.
        # Kills interior line dashes and stray normal-transfer targets.
        import bmesh
        N = int(os.environ.get("CHAR_SHELLCULL", "1"))
        bm = bmesh.new(); bm.from_mesh(char.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0008)
        bm.faces.ensure_lookup_table()
        seen = set(); removed = 0; shells = 0
        for f0 in bm.faces:
            if f0.index in seen: continue
            comp = []; stack = [f0]
            while stack:
                f = stack.pop()
                if f.index in seen: continue
                seen.add(f.index); comp.append(f)
                for e in f.edges:
                    for g in e.link_faces:
                        if g.index not in seen: stack.append(g)
            shells += 1
            if len(comp) < N:
                bmesh.ops.delete(bm, geom=comp, context='FACES'); removed += len(comp)
                bm.faces.ensure_lookup_table()
        bm.to_mesh(char.data); bm.free(); char.data.update()
        print("SHELLCULL", name, "shells", shells, "faces removed", removed, "faces left", len(char.data.polygons))



def cel_material(name, img, uv_name):
    """The cast's cel shader. CEL_STYLE selects the look (EEVEE, Shader-to-RGB):
      classic (default): two tones, shadow = 0.55 grey multiply (the v4 masters)
      anime: three tones with the shadow hue-shifted toward violet on the albedo
             itself (darkened shadows read as mud), a narrow mid-band at the
             terminator, a stepped Fresnel rim on the lit side, a specular pip.
    Anime knobs: CEL_SHADOW_HUE (0.08 = +29 deg), CEL_SHADOW_VAL (0.62),
    CEL_MID_WIDTH (0.08), CEL_RIM (0 = off; 0.35 tested), CEL_SPEC (0 = off; 0.25 tested)."""
    import os
    style = os.environ.get("CEL_STYLE", "anime")   # judged 21 Sep: hue-shifted three-tone is the default; "classic" = the v4 look
    cmat = bpy.data.materials.new(f"{name}_mat"); cmat.use_nodes = True
    ct = cmat.node_tree; ct.nodes.clear(); N = ct.nodes.new; L = ct.links.new
    cuv = N("ShaderNodeUVMap"); cuv.uv_map = uv_name
    ctx = N("ShaderNodeTexImage"); ctx.image = img; L(cuv.outputs["UV"], ctx.inputs["Vector"])
    diff = N("ShaderNodeBsdfDiffuse"); torgb = N("ShaderNodeShaderToRGB"); L(diff.outputs["BSDF"], torgb.inputs["Shader"])
    ramp = N("ShaderNodeValToRGB"); ramp.color_ramp.interpolation = 'CONSTANT'; L(torgb.outputs["Color"], ramp.inputs["Fac"])
    cem = N("ShaderNodeEmission"); cou = N("ShaderNodeOutputMaterial"); L(cem.outputs["Emission"], cou.inputs["Surface"])
    if style != "anime":
        ramp.color_ramp.elements[0].color = (0.55, 0.55, 0.6, 1)
        ramp.color_ramp.elements[1].position = 0.5; ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
        mix = N("ShaderNodeMixRGB"); mix.blend_type = 'MULTIPLY'; mix.inputs["Fac"].default_value = 1.0
        L(ramp.outputs["Color"], mix.inputs["Color1"]); L(ctx.outputs["Color"], mix.inputs["Color2"]); L(mix.outputs["Color"], cem.inputs["Color"])
        return cmat
    hue = float(os.environ.get("CEL_SHADOW_HUE", "0.08")); val = float(os.environ.get("CEL_SHADOW_VAL", "0.62"))
    midw = float(os.environ.get("CEL_MID_WIDTH", "0.08")); rimk = float(os.environ.get("CEL_RIM", "0")); speck = float(os.environ.get("CEL_SPEC", "0"))   # judged 21 Sep: rim/spec wash the faces; off by default
    hsv = N("ShaderNodeHueSaturation"); hsv.inputs["Hue"].default_value = 0.5 + hue; hsv.inputs["Saturation"].default_value = 1.15; hsv.inputs["Value"].default_value = val
    L(ctx.outputs["Color"], hsv.inputs["Color"])
    mid = N("ShaderNodeMixRGB"); mid.blend_type = 'MIX'; mid.inputs["Fac"].default_value = 0.5
    L(hsv.outputs["Color"], mid.inputs["Color1"]); L(ctx.outputs["Color"], mid.inputs["Color2"])
    t0 = 0.42; t1 = t0 + midw
    e = ramp.color_ramp.elements; e[0].position = 0.0; e[0].color = (0, 0, 0, 1); e[1].position = t0; e[1].color = (0.5, 0.5, 0.5, 1)
    e2 = ramp.color_ramp.elements.new(t1); e2.color = (1, 1, 1, 1)
    sep = N("ShaderNodeSeparateColor"); L(ramp.outputs["Color"], sep.inputs["Color"])
    ge0 = N("ShaderNodeMath"); ge0.operation = 'GREATER_THAN'; ge0.inputs[1].default_value = 0.25; L(sep.outputs["Red"], ge0.inputs[0])
    ge1 = N("ShaderNodeMath"); ge1.operation = 'GREATER_THAN'; ge1.inputs[1].default_value = 0.75; L(sep.outputs["Red"], ge1.inputs[0])
    m1 = N("ShaderNodeMixRGB"); L(ge0.outputs["Value"], m1.inputs["Fac"]); L(hsv.outputs["Color"], m1.inputs["Color1"]); L(mid.outputs["Color"], m1.inputs["Color2"])
    m2 = N("ShaderNodeMixRGB"); L(ge1.outputs["Value"], m2.inputs["Fac"]); L(m1.outputs["Color"], m2.inputs["Color1"]); L(ctx.outputs["Color"], m2.inputs["Color2"])
    cur = m2.outputs["Color"]
    if rimk > 0:
        fr = N("ShaderNodeFresnel"); fr.inputs["IOR"].default_value = 1.45
        step = N("ShaderNodeMath"); step.operation = 'GREATER_THAN'; step.inputs[1].default_value = 0.62; L(fr.outputs["Fac"], step.inputs[0])
        gate = N("ShaderNodeMath"); gate.operation = 'MULTIPLY'; L(step.outputs["Value"], gate.inputs[0]); L(ge0.outputs["Value"], gate.inputs[1])
        amt = N("ShaderNodeMath"); amt.operation = 'MULTIPLY'; amt.inputs[1].default_value = rimk; L(gate.outputs["Value"], amt.inputs[0])
        rim = N("ShaderNodeMixRGB"); rim.blend_type = 'ADD'; L(amt.outputs["Value"], rim.inputs["Fac"]); L(cur, rim.inputs["Color1"]); rim.inputs["Color2"].default_value = (1.0, 0.86, 0.70, 1)
        cur = rim.outputs["Color"]
    if speck > 0:
        gl = N("ShaderNodeBsdfGlossy"); gl.inputs["Roughness"].default_value = 0.25
        g2 = N("ShaderNodeShaderToRGB"); L(gl.outputs["BSDF"], g2.inputs["Shader"])
        gsep = N("ShaderNodeSeparateColor"); L(g2.outputs["Color"], gsep.inputs["Color"])
        gs = N("ShaderNodeMath"); gs.operation = 'GREATER_THAN'; gs.inputs[1].default_value = 0.55; L(gsep.outputs["Red"], gs.inputs[0])
        ga = N("ShaderNodeMath"); ga.operation = 'MULTIPLY'; ga.inputs[1].default_value = speck; L(gs.outputs["Value"], ga.inputs[0])
        sp = N("ShaderNodeMixRGB"); sp.blend_type = 'ADD'; L(ga.outputs["Value"], sp.inputs["Fac"]); L(cur, sp.inputs["Color1"]); sp.inputs["Color2"].default_value = (1, 1, 1, 1)
        cur = sp.outputs["Color"]
    L(cur, cem.inputs["Color"])
    return cmat

def load_character(mesh_path, name, height=1.75):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=mesh_path)
    parts = [o for o in bpy.context.scene.objects
             if o.type == 'MESH' and o not in before]
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    if len(parts) > 1:
        bpy.ops.object.join()
    char = bpy.context.view_layer.objects.active
    char.name = name
    for poly in char.data.polygons:
        poly.use_smooth = True
    import os
    _weld_shells(char, name)
    # CHAR_HERO_SUBSURF=N: hero-head subdivision for close-ups (face_mesh_ab_*.png:
    # level 1 softens hair/cheek silhouettes a little, level 2 adds nothing; the
    # face texture is the real limit). Goes BEFORE the normal transfer so the
    # transfer sees the smooth surface. Off by default (4x faces per level).
    _hs = int(__import__("os").environ.get("CHAR_HERO_SUBSURF", "0") or 0)
    if _hs > 0:
        _sm = char.modifiers.new("hero", 'SUBSURF'); _sm.levels = _hs; _sm.render_levels = _hs
    if os.environ.get("CHAR_YAW"):
        # bake a yaw into the mesh data (CharacterGen meshes face +Y; the kit
        # and probe_face expect the face toward -Y)
        char.data.transform(mathutils.Matrix.Rotation(math.radians(float(os.environ["CHAR_YAW"])), 4, 'Z'))
        char.data.update()
    if os.environ.get("CHAR_NORMALFIX", "0") not in ("", "0"):
        # anime-industry normal editing, automated: copy custom normals
        # from a blurred proxy so the shading terminator ignores lumps
        proxy = char.copy()
        proxy.data = char.data.copy()
        proxy.name = char.name + "_nproxy"
        bpy.context.scene.collection.objects.link(proxy)
        pm = proxy.modifiers.new("blur", 'SMOOTH')
        pm.factor = 1.0
        pm.iterations = 60
        dg = bpy.context.evaluated_depsgraph_get()
        pe = proxy.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(pe)
        old = proxy.data
        proxy.modifiers.clear()
        proxy.data = me
        dt = char.modifiers.new("normals", 'DATA_TRANSFER')
        dt.object = proxy
        dt.use_loop_data = True
        dt.data_types_loops = {'CUSTOM_NORMAL'}
        # POLYINTERP_NEAREST interpolates the proxy's normals across the
        # face instead of snapping to one polygon: no pixel-scale grain
        dt.loop_mapping = ('POLYINTERP_NEAREST'
                           if os.environ.get("CHAR_NORMALFIX_INTERP", "1") == "1"
                           else 'NEAREST_POLYNOR')
        proxy.hide_render = True
        proxy.hide_viewport = True
    if os.environ.get("CHAR_SMOOTH", "0") not in ("", "0"):
        # kill the marching-cubes lumps without touching UVs: heavy
        # Laplacian relaxation applied as a modifier stack
        m1 = char.modifiers.new("desilt", 'SMOOTH')
        m1.factor = 0.9
        m1.iterations = int(os.environ.get("CHAR_SMOOTH"))
        m2 = char.modifiers.new("recover", 'CORRECTIVE_SMOOTH')
        m2.factor = 0.5
        m2.iterations = 10
        m2.smooth_type = 'LENGTH_WEIGHTED'

    # painted texture through a two-tone cel ramp
    img = None
    for m in char.data.materials:
        if m and m.use_nodes:
            for nd in m.node_tree.nodes:
                if nd.type == 'TEX_IMAGE' and nd.image:
                    img = nd.image
    mn = mathutils.Vector((1e9,) * 3)
    mx = mathutils.Vector((-1e9,) * 3)
    for c in char.bound_box:
        w = char.matrix_world @ mathutils.Vector(c)
        mn = mathutils.Vector(map(min, mn, w))
        mx = mathutils.Vector(map(max, mx, w))
    s = height / (mx.z - mn.z)
    char.scale = (char.scale[0] * s,) * 3
    char.location = (-(mn.x + mx.x) / 2 * s, -(mn.y + mx.y) / 2 * s, -mn.z * s)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    if img is not None:
        char.data.materials.clear()
        char.data.materials.append(cel_material(name, img, char.data.uv_layers[0].name))
    return char


BONES = {
    "hips": ((0, 0, 0.95), (0, 0, 1.15), None),
    "spine": ((0, 0, 1.15), (0, 0, 1.45), "hips"),
    "head": ((0, 0, 1.45), (0, 0, 1.75), "spine"),
    # jaw: from mid-head forward/down over the chin (mesh faces -Y)
    "jaw": ((0, -0.02, 1.52), (0, -0.11, 1.47), "head"),
}
for sgn, side in ((1, "L"), (-1, "R")):
    BONES[f"thigh.{side}"] = ((0.10 * sgn, 0, 0.95), (0.11 * sgn, 0, 0.50), "hips")
    BONES[f"shin.{side}"] = ((0.11 * sgn, 0, 0.50), (0.12 * sgn, 0, 0.08), f"thigh.{side}")
    BONES[f"foot.{side}"] = ((0.12 * sgn, 0, 0.08), (0.12 * sgn, -0.17, 0.02), f"shin.{side}")
    BONES[f"arm.{side}"] = ((0.20 * sgn, 0, 1.42), (0.26 * sgn, 0, 1.05), "spine")
    BONES[f"fore.{side}"] = ((0.26 * sgn, 0, 1.05), (0.30 * sgn, 0, 0.75), f"arm.{side}")


def rig_character(char, name):
    arm = bpy.data.armatures.new(f"{name}_rig")
    rig = bpy.data.objects.new(f"{name}_rig", arm)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    for nm, (h, t, par) in BONES.items():
        b = arm.edit_bones.new(nm)
        b.head, b.tail = h, t
        if par:
            b.parent = arm.edit_bones[par]
    bpy.ops.object.mode_set(mode='OBJECT')

    # deterministic nearest-segment skinning (bone heat fails silently on
    # marching-cubes meshes — measured, not assumed)
    n = len(char.data.vertices)
    co = np.empty(n * 3)
    char.data.vertices.foreach_get("co", co)
    P = co.reshape(-1, 3)
    names = [nm for nm in BONES if nm != "jaw"]
    D = np.empty((n, len(names)))
    for bi, nm in enumerate(names):
        a = np.array(BONES[nm][0], dtype=float)
        b = np.array(BONES[nm][1], dtype=float)
        ab = b - a
        tt = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
        D[:, bi] = np.linalg.norm(P - (a + tt[:, None] * ab), axis=1)
    order = np.argsort(D, axis=1)
    near2 = order[:, :2]
    d2 = np.take_along_axis(D, near2, axis=1)
    w = np.exp(-d2 / 0.05)
    w /= w.sum(axis=1, keepdims=True)
    crisp = d2[:, 1] - d2[:, 0] > 0.10
    w[crisp, 0], w[crisp, 1] = 1.0, 0.0
    # everything above the neck is RIGIDLY the head's: segment-distance
    # skinning puts frontal face flesh in the head/spine blend zone, so a
    # head turn dragged the mouth 60% of the way and face cards drifted
    H = P[:, 2].max()
    head_region = P[:, 2] > 0.872 * H
    hbi = names.index("head")
    w[head_region, 0], w[head_region, 1] = 1.0, 0.0
    near2[head_region, 0] = hbi
    groups = {nm: char.vertex_groups.new(name=nm) for nm in names}
    Q = 64
    for k in (0, 1):
        qw = np.round(w[:, k] * Q) / Q
        for bi, nm in enumerate(names):
            sel = near2[:, k] == bi
            for lvl in np.unique(qw[sel]):
                if lvl > 0:
                    idx = np.where(sel & (qw == lvl))[0]
                    groups[nm].add(idx.tolist(), float(lvl), 'ADD')

    # jaw region: lower-front slice of the head, blended from the head group
    jaw_g = char.vertex_groups.new(name="jaw")
    jz0, jz1 = 1.44, 1.56
    jsel = np.where((P[:, 2] > jz0) & (P[:, 2] < jz1) & (P[:, 1] < -0.01))[0]
    for i in jsel:
        f = 1.0 - abs(P[i, 2] - 1.48) / 0.08
        if f > 0:
            jaw_g.add([int(i)], min(0.85, float(f)), 'ADD')

    char.parent = rig
    mod = char.modifiers.new("rig", 'ARMATURE')
    mod.object = rig
    return rig


def _key_all(rig, f):
    rig.keyframe_insert("location", frame=f)
    rig.keyframe_insert("rotation_euler", frame=f)


def plan_path(p0, p1, obstacles, clearance=0.55):
    """Waypoints from p0 to p1 that detour around circular obstacles
    [(x, y, r), ...]. Greedy tangential detours — good enough for a set,
    deterministic, and it never walks through a tree again."""
    pts = [np.array(p0, dtype=float)]
    goal = np.array(p1, dtype=float)
    for _ in range(12):
        cur = pts[-1]
        seg = goal - cur
        L = np.linalg.norm(seg)
        d = seg / L
        hit = None
        for (ox, oy, r) in sorted(obstacles, key=lambda o: np.linalg.norm(
                np.array(o[:2]) - cur)):
            oc = np.array((ox, oy)) - cur
            t = float(np.clip(oc @ d, 0, L))
            close = cur + d * t
            dist = np.linalg.norm(np.array((ox, oy)) - close)
            R = r + clearance
            if dist < R and 0.05 < t < L - 0.05:
                hit = (ox, oy, R, close, dist)
                break
        if hit is None:
            break
        ox, oy, R, close, dist = hit
        away = close - np.array((ox, oy))
        n = np.linalg.norm(away)
        away = away / n if n > 1e-6 else np.array((d[1], -d[0]))
        pts.append(np.array((ox, oy)) + away * (R + 0.15))
    pts.append(goal)
    return [tuple(p) for p in pts]


def path_fn_from_points(pts, floor_fn, ease_end=True):
    """A walk path_fn over waypoints, arc-length parameterised."""
    P = [np.array(p) for p in pts]
    segs = [np.linalg.norm(P[i + 1] - P[i]) for i in range(len(P) - 1)]
    total = sum(segs)

    def fn(t):
        e = t if not ease_end or t < 0.9 else 0.9 + (t - 0.9) * 0.5
        dist = e * total
        for i, L in enumerate(segs):
            if dist <= L or i == len(segs) - 1:
                a, b = P[i], P[i + 1]
                u = 0.0 if L < 1e-6 else min(1.0, dist / L)
                x, y = a + (b - a) * u
                dxy = b - a
                h = math.pi + math.atan2(-dxy[0], max(1e-4, dxy[1]))                     if abs(dxy[1]) > 1e-4 else                     math.pi + math.atan2(-dxy[0], dxy[1] + 1e-4)
                return (float(x), float(y), floor_fn(float(x), float(y)), h)
            dist -= L
        x, y = P[-1]
        return (float(x), float(y), floor_fn(float(x), float(y)), math.pi)
    return fn


def apply_walk(rig, path_fn, f0, f1, fps=16, stride_hz=1.45):
    """path_fn(t in 0..1) -> (x, y, z, heading_rad)."""
    pb = rig.pose.bones
    for b in pb:
        b.rotation_mode = 'XYZ'
    for f in range(f0, f1 + 1):
        t = (f - f0) / max(1, f1 - f0)
        bpy.context.scene.frame_set(f)
        ph = 2 * math.pi * stride_hz * (f - f0) / fps
        x, y, z, heading = path_fn(t)
        sway = 0.028 * math.sin(ph)
        bob = 0.030 - 0.030 * abs(math.cos(ph))
        rig.location = (x + sway, y, z + bob)
        rig.rotation_euler = (0, 0, heading)
        _key_all(rig, f)
        for side, sgn in (("L", 1), ("R", -1)):
            sl = math.sin(ph) * sgn
            swing = max(0.0, -math.sin(ph + 0.55) * sgn)
            dip = 0.12 * max(0.0, math.sin(ph - 0.3) * sgn)
            pb[f"thigh.{side}"].rotation_euler = (0.50 * sl + 0.06, 0, 0)
            pb[f"shin.{side}"].rotation_euler = (0.95 * swing ** 1.3 + dip, 0, 0)
            pb[f"foot.{side}"].rotation_euler = (
                -0.35 * max(0.0, math.sin(ph - 2.4) * sgn) + 0.25 * swing, 0, 0)
            pb[f"arm.{side}"].rotation_euler = (-0.38 * sl, 0, sgn * 0.06)
            pb[f"fore.{side}"].rotation_euler = (-0.20 - 0.22 * max(0.0, -sl), 0, 0)
            for nm in ("thigh", "shin", "foot", "arm", "fore"):
                pb[f"{nm}.{side}"].keyframe_insert("rotation_euler", frame=f)
        pb["hips"].rotation_euler = (0, 0.10 * math.sin(ph), 0.09 * math.sin(ph))
        pb["spine"].rotation_euler = (0.06, -0.07 * math.sin(ph), -0.12 * math.sin(ph))
        pb["head"].rotation_euler = (-0.04, -0.03 * math.sin(ph), 0.04 * math.sin(ph))
        for nm in ("hips", "spine", "head"):
            pb[nm].keyframe_insert("rotation_euler", frame=f)


# gesture offsets: (head_x, head_z, spine_x, spine_z, armR_x, foreR_x,
#                    hips_y) each a function of phase u in 0..1
GESTURES = {
    "nod": lambda u: (0.14 * math.sin(u * math.pi * 2) * math.sin(u * math.pi),
                      0, 0, 0, 0, 0, 0),
    "shake": lambda u: (0, 0.10 * math.sin(u * math.pi * 3) * math.sin(u * math.pi),
                        0, 0, 0, 0, 0),
    "hand_raise": lambda u: (0, 0, 0, 0,
                             -0.85 * math.sin(u * math.pi),
                             -0.55 * math.sin(u * math.pi), 0),
    "look_away": lambda u: (0.03 * math.sin(u * math.pi),
                            -0.38 * math.sin(u * math.pi), 0, 0, 0, 0, 0),
    "lean_in": lambda u: (0.04 * math.sin(u * math.pi), 0,
                          0.10 * math.sin(u * math.pi), 0, 0, 0, 0),
    "weight_shift": lambda u: (0, 0, 0, 0.05 * math.sin(u * math.pi),
                               0, 0, 0.12 * math.sin(u * math.pi)),
}


def apply_idle(rig, f0, f1, pos, heading, fps=16, look_at_fn=None,
               gestures=None):
    """Standing idle: breath, sway, head tracking — plus scheduled gestures
    [(fa, fb, kind)] blended in with a sine envelope so nothing pops."""
    pb = rig.pose.bones
    for b in pb:
        b.rotation_mode = 'XYZ'
    gestures = gestures or []
    for f in range(f0, f1 + 1):
        bpy.context.scene.frame_set(f)
        tb = 2 * math.pi * 0.22 * (f - f0) / fps          # breath
        ts = 2 * math.pi * 0.07 * (f - f0) / fps          # slow sway
        g = [0.0] * 7
        for (fa, fb, kind) in gestures:
            if fa <= f <= fb and kind in GESTURES:
                u = (f - fa) / max(1, fb - fa)
                for k, v in enumerate(GESTURES[kind](u)):
                    g[k] += v
        rig.location = pos
        rig.rotation_euler = (0, 0, heading)
        _key_all(rig, f)
        pb["spine"].rotation_euler = (0.03 + 0.015 * math.sin(tb) + g[2],
                                      0.01 * math.sin(ts), g[3])
        look = 0.0
        if look_at_fn is not None:
            tx, ty = look_at_fn(f)
            target_heading = math.pi + math.atan2(-(tx - pos[0]), ty - pos[1])
            look = target_heading - heading
            look = math.atan2(math.sin(look), math.cos(look))
            look = max(-0.35, min(0.35, look))
        pb["head"].rotation_euler = (-0.01 + 0.01 * math.sin(tb) + g[0], 0,
                                     0.7 * look + g[1])
        pb["hips"].rotation_euler = (0, g[6], 0)
        pb["hips"].keyframe_insert("rotation_euler", frame=f)
        for side, sgn in (("L", 1), ("R", -1)):
            ax = 0.02 * math.sin(tb + sgn) + (g[4] if side == "R" else 0)
            fx = -0.15 + (g[5] if side == "R" else 0)
            pb[f"arm.{side}"].rotation_euler = (ax, 0, sgn * 0.05)
            pb[f"fore.{side}"].rotation_euler = (fx, 0, 0)
            pb[f"arm.{side}"].keyframe_insert("rotation_euler", frame=f)
            pb[f"fore.{side}"].keyframe_insert("rotation_euler", frame=f)
        for nm in ("spine", "head"):
            pb[nm].keyframe_insert("rotation_euler", frame=f)


def apply_talk(rig, envelope, f0, nod=True):
    """Jaw opens with the audio envelope (one 0..1 value per frame)."""
    pb = rig.pose.bones
    pb["jaw"].rotation_mode = 'XYZ'
    for i, a in enumerate(envelope):
        f = f0 + i
        bpy.context.scene.frame_set(f)
        pb["jaw"].rotation_euler = (0.38 * float(a), 0, 0)
        pb["jaw"].keyframe_insert("rotation_euler", frame=f)
        if nod:
            pb["head"].rotation_euler = (
                -0.02 + 0.05 * float(a) * math.sin(i * 0.9), 0,
                pb["head"].rotation_euler[2])
            pb["head"].keyframe_insert("rotation_euler", frame=f)


# ── the face system: viseme mouth card + blink lids ──────────────────
def _closest_uv_color(char, point):
    """Sample the painted texture at the vertex nearest a 3D point."""
    img = None
    for m in char.data.materials:
        for nd in m.node_tree.nodes:
            if nd.type == 'TEX_IMAGE' and nd.image:
                img = nd.image
    if img is None:
        return (0.8, 0.65, 0.55)
    n = len(char.data.vertices)
    co = np.empty(n * 3)
    char.data.vertices.foreach_get("co", co)
    P = co.reshape(-1, 3)
    vi = int(np.argmin(np.linalg.norm(P - np.array(point), axis=1)))
    uvl = char.data.uv_layers[0]
    for loop in char.data.loops:
        if loop.vertex_index == vi:
            u, v = uvl.data[loop.index].uv
            w, h = img.size
            x = min(w - 1, int(u * w)); y = min(h - 1, int(v * h))
            px = img.pixels[(y * w + x) * 4:(y * w + x) * 4 + 3]
            return tuple(px)
    return (0.8, 0.65, 0.55)


def probe_face(char):
    """Face anchors from a frontness scan: the nose is the most forward
    point of the centre-line; the chin is where the profile recedes below
    it. Works on cartoon heads where fixed ratios lie (hair fringes were
    being mistaken for noses)."""
    n = len(char.data.vertices)
    co = np.empty(n * 3)
    char.data.vertices.foreach_get("co", co)
    P = co.reshape(-1, 3)
    H = P[:, 2].max()

    def front_y(z, hw=0.03, dz=0.009):
        band = P[(np.abs(P[:, 0]) < hw) & (np.abs(P[:, 2] - z) < dz)]
        return float(band[:, 1].min()) if len(band) else None

    zs = [0.86 * H + i * (0.975 * H - 0.86 * H) / 44 for i in range(45)]
    prof = [(z, front_y(z)) for z in zs]
    prof = [(z, y) for z, y in prof if y is not None]
    lo, hi = 0.885 * H, 0.965 * H
    cand = [(z, y) for z, y in prof if lo < z < hi]
    nose_z, nose_y = min(cand, key=lambda t: t[1])
    chin_z = 0.885 * H
    for z, y in sorted(prof, reverse=True):
        if z < nose_z and y > nose_y + 0.028:
            chin_z = z
            break
    mouth_z = chin_z + 0.45 * (nose_z - chin_z)
    mouth_y = (front_y(mouth_z) or nose_y) - 0.005
    eye_z = nose_z + 0.55 * (nose_z - mouth_z)
    eband = P[(np.abs(P[:, 2] - eye_z) < 0.015) & (P[:, 1] < nose_y + 0.08)]
    half_w = np.percentile(np.abs(eband[:, 0]), 92) if len(eband) else 0.07
    eye_x = 0.42 * half_w
    eye_y = (front_y(eye_z, hw=0.08) or nose_y) - 0.002
    cheek = (0.6 * eye_x, (front_y(mouth_z, hw=0.08) or nose_y) + 0.008,
             mouth_z + 0.4 * (eye_z - mouth_z))
    return {"mouth": (0.0, mouth_y, mouth_z),
            "eye_L": (eye_x, eye_y, eye_z),
            "eye_R": (-eye_x, eye_y, eye_z),
            "cheek": cheek,
            "scale": (nose_z - chin_z)}


def _viseme_strip(name, skin, lip):
    """6-column mouth strip drawn with numpy: closed, small, mid, open,
    wide-ee, round-oo. Skin-toned plate behind each mouth hides the painted
    static lips underneath."""
    C, R = 128, 128
    W = C * 6
    px = np.zeros((R, W, 4), dtype=np.float32)
    yy, xx = np.mgrid[0:R, 0:C]
    cx, cy = C / 2, R / 2
    dark = (0.09, 0.05, 0.05)
    teeth = (0.93, 0.90, 0.86)

    def ell(col, w, h, oy=0):
        return (((xx - cx) / (w * C / 2)) ** 2
                + ((yy - (cy + oy)) / (h * R / 2)) ** 2) <= 1.0

    shapes = [
        ("closed", 0.0, 0.0), ("small", 0.30, 0.14), ("mid", 0.42, 0.30),
        ("open", 0.52, 0.48), ("ee", 0.66, 0.20), ("oo", 0.26, 0.34)]
    for i, (nm, w, h) in enumerate(shapes):
        s = px[:, i * C:(i + 1) * C]
        plate = ell(i, 0.88, 0.72)
        s[plate] = (*skin, 1.0)
        if nm == "closed":
            line = ell(i, 0.46, 0.075)
            s[line] = (*lip, 1.0)
        else:
            outer = ell(i, w + 0.10, h + 0.10)
            inner = ell(i, w, h)
            s[outer] = (*lip, 1.0)
            s[inner] = (*dark, 1.0)
            if nm in ("open", "ee"):
                tband = inner & (yy < cy - h * R * 0.18)
                s[tband] = (*teeth, 1.0)
    img = bpy.data.images.new(name, W, R, alpha=True)
    img.pixels = px[::-1].ravel().tolist()
    img.pack()
    return img


def add_face(char, rig, name, calib=None):
    """Mouth card + blink lids, bone-bound to the head. Returns controls.

    calib: optional dict {mouth_z, eye_z, eye_x} measured once from a rest
    render — hair overhangs defeat every geometric nose heuristic, so a
    5-minute human calibration beats a clever probe (measured twice)."""
    anchors = probe_face(char)
    if calib:
        n = len(char.data.vertices)
        co = np.empty(n * 3)
        char.data.vertices.foreach_get("co", co)
        P = co.reshape(-1, 3)

        def front_y(z, hw=0.026, dz=0.012):
            band = P[(np.abs(P[:, 0]) < hw) & (np.abs(P[:, 2] - z) < dz)]
            return float(band[:, 1].min()) if len(band) else -0.1

        mz, ez, ex = calib["mouth_z"], calib["eye_z"], calib["eye_x"]
        anchors["mouth"] = (0.0, front_y(mz) - 0.005, mz)
        anchors["eye_L"] = (ex, front_y(ez, hw=0.06) - 0.003, ez)
        anchors["eye_R"] = (-ex, front_y(ez, hw=0.06) - 0.003, ez)
        anchors["scale"] = calib.get("scale", 2.2 * (ez - mz))
    # chin first — it matches the mouth surround exactly; warmth search
    # only rescues beard-dark chins (Oisin)
    m = anchors["mouth"]; ex = anchors["eye_L"][0]
    chin = _closest_uv_color(char, (0.0, m[1] + 0.004,
                                    m[2] - 0.030))[:3]
    if sum(chin) / 3 > 0.30 and chin[0] > chin[2]:
        skin = chin
        cands = []
    else:
        cands = [anchors["cheek"],
             (0.35 * ex, m[1] + 0.006, m[2]),
             (-0.35 * ex, m[1] + 0.006, m[2]),
             (0.0, m[1] + 0.004, m[2] - 0.45 * anchors["scale"]),
             (0.5 * ex, m[1] + 0.008, (m[2] + anchors["eye_L"][2]) / 2)]
    best = -9
    if cands:
        skin = (0.8, 0.65, 0.55)
    for c in cands:
        col = _closest_uv_color(char, c)[:3]
        warm = col[0] * 1.4 - col[2] + 0.6 * sum(col) / 3
        if warm > best:
            best, skin = warm, col
    lip = tuple(c * 0.55 for c in skin[:3])
    strip = _viseme_strip(f"{name}_visemes", skin, lip)
    S = anchors["scale"]

    def card(cname, pos, w, h, image=None, color=None):
        bpy.ops.mesh.primitive_plane_add(size=1)
        ob = bpy.context.object
        ob.name = cname
        ob.scale = (w, h, 1)
        ob.rotation_euler = (math.radians(90), 0, math.radians(180))
        ob.location = pos
        m = bpy.data.materials.new(cname)
        m.use_nodes = True
        m.blend_method = 'CLIP'
        nt = m.node_tree
        nt.nodes.clear()
        em = nt.nodes.new("ShaderNodeEmission")
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        if image is not None:
            tc = nt.nodes.new("ShaderNodeTexCoord")
            mp = nt.nodes.new("ShaderNodeMapping")
            mp.inputs["Scale"].default_value = (1 / 6, 1, 1)
            tx = nt.nodes.new("ShaderNodeTexImage")
            tx.image = image
            tx.extension = 'CLIP'
            mixa = nt.nodes.new("ShaderNodeMixShader")
            tr = nt.nodes.new("ShaderNodeBsdfTransparent")
            nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
            nt.links.new(mp.outputs["Vector"], tx.inputs["Vector"])
            nt.links.new(tx.outputs["Color"], em.inputs["Color"])
            nt.links.new(tx.outputs["Alpha"], mixa.inputs["Fac"])
            nt.links.new(tr.outputs["BSDF"], mixa.inputs[1])
            nt.links.new(em.outputs["Emission"], mixa.inputs[2])
            nt.links.new(mixa.outputs["Shader"], out.inputs["Surface"])
            ctrl = mp
        else:
            em.inputs["Color"].default_value = (*color, 1)
            nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
            ctrl = None
        ob.data.materials.append(m)
        con = ob.constraints.new('CHILD_OF')
        con.target = rig
        con.subtarget = "head"
        # cards are placed in REST space: add_face must run before any
        # performance keyframes, with the rig untransformed
        con.inverse_matrix = rig.data.bones["head"].matrix_local.inverted()
        return ob, ctrl

    ex = abs(anchors["eye_L"][0])
    mw = 1.35 * ex
    mouth, mctrl = card(f"{name}_mouth",
                        anchors["mouth"], mw, mw, image=strip)
    lids = []
    ew = 1.05 * ex
    for side in ("L", "R"):
        lid, _ = card(f"{name}_lid{side}", anchors[f"eye_{side}"],
                      ew, ew * 0.7, color=skin)
        lid.scale = (0.001, 0.001, 1)
        lids.append(lid)
    return {"mouth_ctrl": mctrl, "mouth": mouth, "lids": lids,
            "lid_size": (ew, ew * 0.7)}


def apply_talk_face(rig, face, envelope, f0, fps=16, blink_period=3.4, blinks=True):
    """Viseme card + subtle jaw from the envelope; deterministic blinks."""
    pb = rig.pose.bones
    pb["jaw"].rotation_mode = 'XYZ'
    mp = face["mouth_ctrl"]
    total = len(envelope)

    def set_col(col, f):
        mp.inputs["Location"].default_value = (col / 6.0, 0, 0)
        mp.inputs["Location"].keyframe_insert("default_value", frame=f)

    for i, a in enumerate(envelope):
        f = f0 + i
        a = float(a)
        if a < 0.04:
            col = 0
        elif a < 0.25:
            col = 1
        elif a < 0.48:
            col = 5 if (i // 3) % 4 == 2 else 2
        elif a < 0.72:
            col = 3
        else:
            col = 4
        set_col(col, f)
        bpy.context.scene.frame_set(f)
        pb["jaw"].rotation_euler = (0.15 * a, 0, 0)
        pb["jaw"].keyframe_insert("rotation_euler", frame=f)
    # snap between visemes — no sliding strip
    nt = face["mouth"].data.materials[0].node_tree
    if nt.animation_data and nt.animation_data.action:
        for fc in nt.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'CONSTANT'
    # blinks: two closed frames on a fixed cadence
    if not blinks:
        return
    lw, lh = face["lid_size"]
    for lid in face["lids"]:
        lid.scale = (0.001, 0.001, 1)
        lid.keyframe_insert("scale", frame=f0)
        for t0 in np.arange(f0 + 9, f0 + total, blink_period * fps):
            b = int(t0)
            for f, on in ((b - 1, False), (b, True), (b + 1, True), (b + 2, False)):
                lid.scale = (lw, lh, 1) if on else (0.001, 0.001, 1)
                lid.keyframe_insert("scale", frame=f)
        if lid.animation_data and lid.animation_data.action:
            for fc in lid.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = 'CONSTANT'


# ── texture-space face animation (replaces the card system) ──────────
def enable_face_variants(char, name, faces_dir):
    """Swap the single texture for a keyframable 7-way switch:
    base / m1..m5 visemes / blink. Returns the mix inputs to drive."""
    mat = char.data.materials[0]
    nt = mat.node_tree
    tex = [n for n in nt.nodes if n.type == 'TEX_IMAGE'][0]
    # glb exports (UniRig) leave the Vector input unlinked = default UV map
    uv_from = tex.inputs["Vector"].links[0].from_socket if tex.inputs["Vector"].links else None
    color_to = [ln.to_socket for ln in tex.outputs["Color"].links]
    nt.nodes.remove(tex)
    imgs = {}
    for key in ("base", "m1", "m2", "m3", "m4", "m5", "blink"):
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(f"{faces_dir}/{name}_face_{key}.png")
        node.image.pack()
        if uv_from is not None:
            nt.links.new(uv_from, node.inputs["Vector"])
        imgs[key] = node
    ctrl = {}
    cur = imgs["base"].outputs["Color"]
    for key in ("m1", "m2", "m3", "m4", "m5", "blink"):
        mix = nt.nodes.new("ShaderNodeMixRGB")
        mix.inputs["Fac"].default_value = 0.0
        nt.links.new(cur, mix.inputs["Color1"])
        nt.links.new(imgs[key].outputs["Color"], mix.inputs["Color2"])
        cur = mix.outputs["Color"]
        ctrl[key] = mix.inputs["Fac"]
    for sock in color_to:
        nt.links.new(cur, sock)
    ctrl["_tree"] = nt
    return ctrl


def apply_talk_tex(rig, ctrl, envelope, f0, fps=16, blinks=True,
                   blink_period=3.4, visemes=None):
    """Drive the texture switch from Rhubarb visemes when given (phoneme
    accurate), else from the audio envelope; subtle jaw from the envelope
    either way."""
    pb = rig.pose.bones
    pb["jaw"].rotation_mode = 'XYZ'
    keys = ("m1", "m2", "m3", "m4", "m5")
    for i, a in enumerate(envelope):
        f = f0 + i
        a = float(a)
        if visemes is not None:
            col = int(visemes[i]) if i < len(visemes) else 0
            sel = None if col == 0 else f"m{col}"
        elif a < 0.04:
            sel = None
        elif a < 0.25:
            sel = "m1"
        elif a < 0.48:
            sel = "m5" if (i // 3) % 4 == 2 else "m2"
        elif a < 0.72:
            sel = "m3"
        else:
            sel = "m4"
        for k in keys:
            ctrl[k].default_value = 1.0 if k == sel else 0.0
            ctrl[k].keyframe_insert("default_value", frame=f)
        bpy.context.scene.frame_set(f)
        pb["jaw"].rotation_euler = (0.30 * a, 0, 0)   # was 0.13: unreadable at 3/4
        pb["jaw"].keyframe_insert("rotation_euler", frame=f)
    if blinks:
        total = len(envelope)
        ctrl["blink"].default_value = 0.0
        ctrl["blink"].keyframe_insert("default_value", frame=f0)
        for t0 in np.arange(f0 + 11, f0 + total, blink_period * fps):
            b = int(t0)
            for f, on in ((b - 1, 0.0), (b, 1.0), (b + 1, 1.0), (b + 2, 0.0)):
                ctrl["blink"].default_value = on
                ctrl["blink"].keyframe_insert("default_value", frame=f)
    nt = ctrl["_tree"]
    if nt.animation_data and nt.animation_data.action:
        for fc in nt.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'CONSTANT'


# ── UniRig-rigged cast (Day 5): real skin weights, same animators ────────
def load_rigged_character(glb_path, name, height=1.75, yaw_deg=None, skirt=False):
    """Import a UniRig-rigged GLB and rename its (unnamed) bones to the kit
    convention via the geometric mapper, so apply_walk / apply_idle /
    apply_talk_tex drive it unchanged. Adds the kit's 'jaw' bone + weights.
    Returns (char_mesh, rig). Scales the rig so the character is `height`."""
    import sys as _sys
    _sys.path.insert(0, "/workspace/text-to-video/scripts/day4")
    from rig_map import map_unirig
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=glb_path)
    new = [o for o in bpy.context.scene.objects if o not in before]
    rig = [o for o in new if o.type == 'ARMATURE'][0]
    meshes = [o for o in new if o.type == 'MESH' and any(m.type == 'ARMATURE' for m in o.modifiers)]
    char = meshes[0]
    for o in new:
        if o.type == 'MESH' and o is not char:
            bpy.data.objects.remove(o, do_unlink=True)
    rig.name, char.name = f"{name}_rig", name
    _weld_shells(char, name)     # same seam weld as the numpy path (skin weights survive: they live on the kept verts)
    # CHAR_HERO_SUBSURF=N: hero-head subdivision for close-ups (face_mesh_ab_*.png:
    # level 1 softens hair/cheek silhouettes a little, level 2 adds nothing; the
    # face texture is the real limit). Goes BEFORE the normal transfer so the
    # transfer sees the smooth surface. Off by default (4x faces per level).
    _hs = int(__import__("os").environ.get("CHAR_HERO_SUBSURF", "0") or 0)
    if _hs > 0:
        _sm = char.modifiers.new("hero", 'SUBSURF'); _sm.levels = _hs; _sm.render_levels = _hs
    _img = None
    for m in char.data.materials:
        if m and m.use_nodes:
            for nd in m.node_tree.nodes:
                if nd.type == 'TEX_IMAGE' and nd.image: _img = nd.image
    if _img is not None and char.data.uv_layers:
        char.data.materials.clear(); char.data.materials.append(cel_material(name, _img, char.data.uv_layers[0].name))
    roles = map_unirig(rig); H = roles.pop("_height")
    ren = {"hips": "hips", "spine0": "spine", "L_upperleg": "thigh.L", "L_lowerleg": "shin.L", "L_foot": "foot.L",
           "R_upperleg": "thigh.R", "R_lowerleg": "shin.R", "R_foot": "foot.R",
           "L_upperarm": "arm.L", "L_forearm": "fore.L", "R_upperarm": "arm.R", "R_forearm": "fore.R"}
    ren["head" if "head" in roles else "neck"] = "head"
    for role, kit_name in ren.items():
        if role in roles:
            b = rig.data.bones[roles[role]]
            vg = char.vertex_groups.get(b.name)
            b.name = kit_name
            if vg: vg.name = kit_name
    for pb in rig.pose.bones:
        pb.rotation_mode = 'XYZ'
    # T-POSE rigs (CharacterGen): the animators set arm rotations absolutely
    # for an A-pose rest, so bake an A-pose in: pose the upper arms down,
    # apply the armature deform to the mesh, re-add it, apply pose as rest.
    bpy.context.view_layer.update()
    def _dir(bn):
        b = rig.data.bones[bn]; return (rig.matrix_world.to_3x3() @ (b.tail_local - b.head_local)).normalized()
    if "arm.L" in rig.data.bones and "arm.R" in rig.data.bones and abs(_dir("arm.L").z) < 0.45 and abs(_dir("arm.R").z) < 0.45:
        for bn in ("arm.L", "arm.R"):
            d = _dir(bn); side = 1 if d.x > 0 else -1
            want = mathutils.Vector((0.30 * side, 0.0, -1.0)).normalized()      # ~17 deg off vertical
            q = d.rotation_difference(want)                                       # world swing
            pb = rig.pose.bones[bn]
            R_rest = (rig.matrix_world @ rig.data.bones[bn].matrix_local).to_3x3()
            pb.rotation_mode = 'QUATERNION'
            pb.rotation_quaternion = (R_rest.inverted() @ q.to_matrix() @ R_rest).to_quaternion()
        bpy.context.view_layer.update()
        bpy.context.view_layer.objects.active = char
        mod = [m for m in char.modifiers if m.type == 'ARMATURE'][0]
        bpy.ops.object.modifier_apply(modifier=mod.name)
        newmod = char.modifiers.new("rig", 'ARMATURE'); newmod.object = rig
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='POSE'); bpy.ops.pose.armature_apply(selected=False); bpy.ops.object.mode_set(mode='OBJECT')
        for pb in rig.pose.bones: pb.rotation_mode = 'XYZ'
        print("TPOSE->APOSE baked for", name)
    # the animators put the ARMATURE ORIGIN on the floor (kit convention);
    # UniRig's origin is mid-body — shift bones and mesh so the feet sit at z=0
    bpy.context.view_layer.update()
    M_mesh_to_rig = rig.matrix_world.inverted() @ char.matrix_world
    zs = [(M_mesh_to_rig @ v.co).z for v in char.data.vertices]
    feet = min(zs)
    if abs(feet) > 1e-4:
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='EDIT')
        for eb in rig.data.edit_bones:
            eb.head.z -= feet; eb.tail.z -= feet
        bpy.ops.object.mode_set(mode='OBJECT')
        inv = M_mesh_to_rig.to_3x3().inverted()
        d = inv @ mathutils.Vector((0, 0, feet))
        for v in char.data.vertices:
            v.co -= d
        bpy.context.view_layer.update()
    # scale to height from the MESH extent (bone extents ignore hair/boots)
    zs_m = [(M_mesh_to_rig @ v.co).z for v in char.data.vertices]
    Hm = max(zs_m) - min(zs_m)
    s = height / Hm
    rig.scale = (s, s, s)
    # FACING: UniRig exports flip inconsistently per mesh, and the animators
    # overwrite the armature object's rotation every frame — so the yaw must be
    # BAKED into bones + mesh. Detect facing from the foot -> toe bones and
    # rotate the rest so the toes point along KIT_FACING (+Y: what apply_walk /
    # apply_idle headings assume, measured on the film). yaw_deg overrides.
    rig.rotation_mode = 'XYZ'     # glTF armatures import in QUATERNION mode: the animators' rotation_euler would be ignored
    KIT_FACING = math.radians(-90.0)   # toes along -Y (verified on the film: +Y turned every close-up away)
    yaw = None
    if yaw_deg is None:
        fwd = mathutils.Vector((0, 0, 0))
        for fn in ("foot.L", "foot.R"):
            if fn in rig.data.bones:
                fb = rig.data.bones[fn]; toe = fb.children[0] if fb.children else fb
                d = rig.matrix_world.to_3x3() @ (toe.tail_local - toe.head_local); d.z = 0
                if d.length > 1e-6: fwd += d.normalized()
        if fwd.length > 1e-6:
            yaw = KIT_FACING - math.atan2(fwd.y, fwd.x)
            print("FACING", name, "toes ->", (round(fwd.x, 2), round(fwd.y, 2)), "baked yaw", round(math.degrees(yaw), 1))
    elif yaw_deg:
        yaw = math.radians(yaw_deg)
    if yaw:
        Rz = mathutils.Matrix.Rotation(yaw, 4, 'Z')
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='EDIT')
        for eb in rig.data.edit_bones:
            eb.head = Rz @ eb.head; eb.tail = Rz @ eb.tail; eb.roll = eb.roll   # roll is relative: unchanged
        bpy.ops.object.mode_set(mode='OBJECT')
        Rm = M_mesh_to_rig.inverted() @ Rz @ M_mesh_to_rig
        char.data.transform(Rm); char.data.update()
    bpy.context.view_layer.update()
    # jaw: child of head, lower-front head slice weighted like rig_character
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    hb = rig.data.edit_bones["head"]
    jb = rig.data.edit_bones.new("jaw")
    jb.head = hb.head.copy(); jb.tail = hb.head + mathutils.Vector((0, -0.12 * H / height, -0.06 * H / height))
    jb.parent = hb
    bpy.ops.object.mode_set(mode='OBJECT')
    n = len(char.data.vertices); co = np.empty(n * 3); char.data.vertices.foreach_get("co", co); P = co.reshape(-1, 3)
    P = P @ np.array(char.matrix_world.to_3x3()).T + np.array(char.matrix_world.translation)
    zmax, zmin = P[:, 2].max(), P[:, 2].min(); Hm = zmax - zmin
    jaw_g = char.vertex_groups.new(name="jaw")
    jz0, jz1 = zmin + 0.86 * Hm, zmin + 0.92 * Hm
    ymid = np.median(P[:, 1])
    jsel = np.where((P[:, 2] > jz0) & (P[:, 2] < jz1) & (P[:, 1] < ymid - 0.02 * Hm))[0]
    for i in jsel:
        f = 1.0 - abs(P[i, 2] - (jz0 + jz1) / 2) / (0.5 * (jz1 - jz0))
        if f > 0: jaw_g.add([int(i)], min(0.85, float(f)), 'ADD')
    if skirt:
        # DRESS FIX: vertices below the hips that sit OUTSIDE the legs' envelope
        # are skirt cloth — UniRig weights them to the legs and every stride
        # tents the skirt. Hand their leg weights to the hips (it then swings
        # as a rigid bell; good enough for cel).
        leg_names = [n for n in ("thigh.L", "thigh.R", "shin.L", "shin.R", "foot.L", "foot.R") if n in char.vertex_groups]
        hips_g = char.vertex_groups["hips"]; leg_idx = {char.vertex_groups[n].index: n for n in leg_names}
        hips_z = (rig.matrix_world @ rig.data.bones["hips"].head_local).z
        legs = [rig.data.bones[n] for n in ("thigh.L", "thigh.R") if n in rig.data.bones]
        lx = [(rig.matrix_world @ b.head_local).x for b in legs]; cx = sum(lx) / len(lx) if lx else 0.0
        r_leg = 0.11 * height
        moved = 0
        for v in char.data.vertices:
            w = char.matrix_world @ v.co
            if w.z >= hips_z: continue
            # lateral distance from the nearest leg axis (legs ~vertical in rest)
            dl = min(abs(w.x - x) for x in lx) if lx else abs(w.x - cx)
            dy = abs(w.y - (rig.matrix_world @ rig.data.bones["hips"].head_local).y)
            if dl > r_leg or dy > r_leg:
                tot = 0.0
                for g in v.groups:
                    if g.group in leg_idx: tot += g.weight
                if tot > 0:
                    for g in v.groups:
                        if g.group in leg_idx: char.vertex_groups[leg_idx[g.group]].remove([v.index])
                    hips_g.add([v.index], tot, 'ADD'); moved += 1
        print("SKIRT", name, "verts moved to hips", moved)
    for poly in char.data.polygons: poly.use_smooth = True
    bpy.context.view_layer.update()
    zmin_w = min((char.matrix_world @ v.co).z for v in char.data.vertices)
    print("RIGGED", name, "bones", len(rig.data.bones), "renamed", [k for k in ren.values() if k in rig.data.bones], "jaw verts", len(jsel), "feet z", round(zmin_w, 3))
    return char, rig


def add_outline_hull(char, px, cam, res_y, name="hull"):
    """INVERTED HULL outlines (what Arc System Works ship) instead of Freestyle.

    A SEPARATE shell object, not a Solidify on the character: the cast carry edited
    custom split normals for the cel terminator, and expanding along those pokes the
    shell through the surface in patches. So the shell is a duplicate whose custom
    normals are CLEARED and shading smoothed -- the research's "second set of smoothed
    normals, separate from the lighting normals" -- displaced along those, with its
    faces flipped and a black backface-culled material, so only the far side survives
    and reads as a line ringing the silhouette.

    Width is compensated for camera DISTANCE and FOV so `px` is on-screen pixels in any
    shot: world = px/res_y * 2*dist*tan(fov/2). The shell keeps the character's armature
    modifier, so it deforms with the animation.
    """
    import math
    sc = bpy.context.scene
    hull = char.copy(); hull.data = char.data.copy(); hull.name = char.name + "_hull"
    sc.collection.objects.link(hull)
    # the shell gets its OWN smoothed normals
    for md in list(hull.modifiers):
        if md.type in ('DATA_TRANSFER', 'SUBSURF', 'SOLIDIFY'):
            hull.modifiers.remove(md)
    bpy.ops.object.select_all(action='DESELECT')
    hull.select_set(True); bpy.context.view_layer.objects.active = hull
    try:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    except RuntimeError:
        pass
    for poly in hull.data.polygons:
        poly.use_smooth = True
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.flip_normals()
    bpy.ops.object.mode_set(mode='OBJECT')

    m = bpy.data.materials.new(name + "_line")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.03, 0.02, 0.04, 1)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(em.outputs[0], out.inputs[0])
    m.use_backface_culling = True          # only the shell's far side = the ring
    hull.data.materials.clear(); hull.data.materials.append(m)

    d = (char.matrix_world.translation - cam.matrix_world.translation).length
    fov = 2.0 * math.atan(cam.data.sensor_width / (2.0 * cam.data.lens))

    # A constant on-screen width is only right while the figure fills the frame. On a wide
    # the same 4 px eats a 60 px-tall figure and the character renders as a dark blob
    # (review/retopo_ab_s11_away.png). So cap the line at a fraction of the subject's own
    # on-screen height: the line stays a line at every distance.
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    ys = []
    for corner in char.bound_box:
        co = world_to_camera_view(sc, cam, char.matrix_world @ mathutils.Vector(corner))
        ys.append(co.y)
    screen_h = max(1.0, (max(ys) - min(ys)) * res_y)        # figure height in pixels
    _os = __import__("os")
    # Below a certain size a hull cannot be a line: the figure is thinner than twice the
    # offset, so the shell's far side shows through and fills it in as a dark mass
    # (review/retopo_ab_s11_away.png). Freestyle draws almost nothing on a distant figure
    # either, so skip the outline entirely there rather than fake it.
    if screen_h < float(_os.environ.get("CHAR_HULL_MIN", "300")):
        print("HULL skip", char.name, "screen_h %.0f" % screen_h, flush=True)
        return None
    eff = min(px, max(0.8, screen_h * float(_os.environ.get("CHAR_HULL_FRAC", "0.018"))))
    thick = (eff / max(res_y, 1)) * 2.0 * max(d, 0.1) * math.tan(fov / 2.0)

    dsp = hull.modifiers.new(name, 'DISPLACE')
    dsp.direction = 'NORMAL'
    dsp.mid_level = 0.0
    dsp.strength = -thick          # normals are flipped, so push outward = negative
    hull.visible_shadow = False
    print("HULL", char.name, "px", px, "eff %.2f" % eff, "screen_h %.0f" % screen_h, "thickness %.4f" % thick, flush=True)
    return hull
