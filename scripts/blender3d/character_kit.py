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
        cmat = bpy.data.materials.new(f"{name}_mat")
        cmat.use_nodes = True
        ct = cmat.node_tree
        ct.nodes.clear()
        cuv = ct.nodes.new("ShaderNodeUVMap")
        cuv.uv_map = char.data.uv_layers[0].name
        ctx = ct.nodes.new("ShaderNodeTexImage")
        ctx.image = img
        diff = ct.nodes.new("ShaderNodeBsdfDiffuse")
        torgb = ct.nodes.new("ShaderNodeShaderToRGB")
        ramp = ct.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.interpolation = 'CONSTANT'
        ramp.color_ramp.elements[0].color = (0.55, 0.55, 0.6, 1)
        ramp.color_ramp.elements[1].position = 0.5
        ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
        mix = ct.nodes.new("ShaderNodeMixRGB")
        mix.blend_type = 'MULTIPLY'
        mix.inputs["Fac"].default_value = 1.0
        cem = ct.nodes.new("ShaderNodeEmission")
        cou = ct.nodes.new("ShaderNodeOutputMaterial")
        ct.links.new(cuv.outputs["UV"], ctx.inputs["Vector"])
        ct.links.new(diff.outputs["BSDF"], torgb.inputs["Shader"])
        ct.links.new(torgb.outputs["Color"], ramp.inputs["Fac"])
        ct.links.new(ramp.outputs["Color"], mix.inputs["Color1"])
        ct.links.new(ctx.outputs["Color"], mix.inputs["Color2"])
        ct.links.new(mix.outputs["Color"], cem.inputs["Color"])
        ct.links.new(cem.outputs["Emission"], cou.inputs["Surface"])
        char.data.materials.clear()
        char.data.materials.append(cmat)
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


def apply_idle(rig, f0, f1, pos, heading, fps=16, look_at_fn=None):
    """Standing idle: breath, sway — and the head follows look_at_fn(f)."""
    pb = rig.pose.bones
    for b in pb:
        b.rotation_mode = 'XYZ'
    for f in range(f0, f1 + 1):
        bpy.context.scene.frame_set(f)
        tb = 2 * math.pi * 0.22 * (f - f0) / fps          # breath
        ts = 2 * math.pi * 0.07 * (f - f0) / fps          # slow sway
        rig.location = pos
        rig.rotation_euler = (0, 0, heading)
        _key_all(rig, f)
        pb["spine"].rotation_euler = (0.03 + 0.015 * math.sin(tb),
                                      0.01 * math.sin(ts), 0)
        look = 0.0
        if look_at_fn is not None:
            tx, ty = look_at_fn(f)
            look = math.atan2(-(tx - pos[0]), ty - pos[1]) - heading
            look = max(-0.9, min(0.9, math.atan2(math.sin(look), math.cos(look))))
        pb["head"].rotation_euler = (-0.02 + 0.01 * math.sin(tb), 0, 0.8 * look)
        for side, sgn in (("L", 1), ("R", -1)):
            pb[f"arm.{side}"].rotation_euler = (0.02 * math.sin(tb + sgn), 0, sgn * 0.05)
            pb[f"fore.{side}"].rotation_euler = (-0.15, 0, 0)
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
