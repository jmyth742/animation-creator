"""Painted asset placement for the valley: import, normalise, ground."""
import math
import bpy
import mathutils

PROPS = "/workspace/text-to-video/series/tir-na-nog-legend/meshes/props"


def place(glb, name, loc, height, rot_z=0.0, floor_fn=None):
    """Import a painted asset, scale to real height, origin at base centre,
    sit it on the terrain. Returns the object or None if the file is absent."""
    import os
    if not os.path.exists(glb):
        return None
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=glb)
    parts = [o for o in bpy.context.scene.objects
             if o.type == 'MESH' and o not in before]
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    if len(parts) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    for poly in ob.data.polygons:
        poly.use_smooth = True
    mn = mathutils.Vector((1e9,) * 3)
    mx = mathutils.Vector((-1e9,) * 3)
    for c in ob.bound_box:
        w = ob.matrix_world @ mathutils.Vector(c)
        mn = mathutils.Vector(map(min, mn, w))
        mx = mathutils.Vector(map(max, mx, w))
    s = height / (mx.z - mn.z)
    ob.scale = (ob.scale[0] * s,) * 3
    z = floor_fn(loc[0], loc[1]) if floor_fn else 0.0
    ob.location = (loc[0] - (mn.x + mx.x) / 2 * s,
                   loc[1] - (mn.y + mx.y) / 2 * s,
                   z - mn.z * s)
    ob.rotation_euler = (0, 0, rot_z)
    # lit like the characters: texture through the two-tone cel ramp
    img = None
    for m in ob.data.materials:
        if m and m.use_nodes:
            for nd in m.node_tree.nodes:
                if nd.type == 'TEX_IMAGE' and nd.image:
                    img = nd.image
    if img is not None:
        mat = bpy.data.materials.new(name + "_cel")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = ob.data.uv_layers[0].name
        tx = nt.nodes.new("ShaderNodeTexImage")
        tx.image = img
        diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
        torgb = nt.nodes.new("ShaderNodeShaderToRGB")
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.interpolation = 'CONSTANT'
        ramp.color_ramp.elements[0].color = (0.55, 0.53, 0.58, 1)
        ramp.color_ramp.elements[1].position = 0.48
        ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
        mix = nt.nodes.new("ShaderNodeMixRGB")
        mix.blend_type = 'MULTIPLY'
        mix.inputs["Fac"].default_value = 1.0
        em = nt.nodes.new("ShaderNodeEmission")
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(uv.outputs["UV"], tx.inputs["Vector"])
        nt.links.new(diff.outputs["BSDF"], torgb.inputs["Shader"])
        nt.links.new(torgb.outputs["Color"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], mix.inputs["Color1"])
        nt.links.new(tx.outputs["Color"], mix.inputs["Color2"])
        nt.links.new(mix.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        ob.data.materials.clear()
        ob.data.materials.append(mat)
    return ob


def dress_valley(sc, floor_fn, winter=False):
    """Swap primitives for painted assets wherever the mesh exists.
    Call AFTER valley_set.build_set; removes the placeholder objects it
    replaces. Returns the list of asset names actually placed."""
    placed = []
    def drop(prefixes):
        for o in list(sc.objects):
            if any(o.name.startswith(p) for p in prefixes):
                bpy.data.objects.remove(o, do_unlink=True)

    # drop the primitives FIRST — the placed asset's own name ("hall_asset")
    # matched the "hall" prefix and the new hall deleted itself
    import os
    if os.path.exists(f"{PROPS}/hall_painted.glb"):
        drop(("hall", "tower", "towerroof", "door", "col", "cren"))
    if place(f"{PROPS}/hall_painted.glb", "hall_asset", (7.5, 26), 9.5,
             rot_z=math.radians(12), floor_fn=floor_fn):
        placed.append("hall")
    tree_spots = [(-3.5, 8, 4.6, 0.3), (3.4, 12, 5.4, 1.8), (-4.8, 16, 4.9, 3.1),
                  (5.5, 18, 4.2, 0.9), (2.8, 30, 5.8, 2.2), (-3.2, 33, 5.0, 4.0),
                  (12, 18, 6.2, 1.4), (-13, 12, 5.4, 5.1)]
    ok = False
    for i, (tx, ty, th, rz) in enumerate(tree_spots):
        VARIANT_MIX = [f"{PROPS}/tree_painted.glb", f"{PROPS}/tree_v2_painted.glb",
                       f"{PROPS}/tree_v3_painted.glb"]
        import os as _os
        cand = VARIANT_MIX[i % len(VARIANT_MIX)]
        if not _os.path.exists(cand):
            cand = f"{PROPS}/tree_painted.glb"
        tglb = f"{PROPS}/snowtree_painted.glb" if winter else cand
        if place(tglb, f"tree_asset{i}", (tx, ty), th,
                 rot_z=rz, floor_fn=floor_fn):
            ok = True
    if ok:
        drop(("trunk0", "trunk1", "trunk2", "trunk3", "trunk4", "trunk5",
              "trunk6", "trunk7", "can"))
        placed.append("trees")
    if place(f"{PROPS}/cross_painted.glb", "cross_asset", (-2.6, 19), 2.6,
             rot_z=math.radians(-15), floor_fn=floor_fn):
        drop(("crossv", "crossh"))
        placed.append("cross")
    rglb = f"{PROPS}/snowrock_painted.glb" if winter else f"{PROPS}/rock_painted.glb"
    for i, (rx, ry, rh, rz) in enumerate([(4.6, 9.5, 0.9, 0.4),
                                          (-5.8, 12.5, 1.1, 2.0),
                                          (9.5, 22, 1.4, 4.2)]):
        if place(rglb, f"rock_asset{i}", (rx, ry), rh,
                 rot_z=rz, floor_fn=floor_fn):
            if i == 0:
                placed.append("rocks")
    for i, (bx, by, bh, bz) in enumerate([(-6.5, 9, 1.3, 1.0),
                                          (6.8, 14.5, 1.5, 3.3),
                                          (-2.0, 25.5, 1.4, 0.2)]):
        bglb = f"{PROPS}/snowbush_painted.glb" if winter else f"{PROPS}/bush_painted.glb"
        if place(bglb, f"bush_asset{i}", (bx, by), bh,
                 rot_z=bz, floor_fn=floor_fn):
            if i == 0:
                placed.append("bushes")
    if place(f"{PROPS}/stones_painted.glb", "stones_asset", (-9.5, 13.5), 2.2,
             rot_z=math.radians(30), floor_fn=floor_fn):
        placed.append("stones")
    if winter and place(f"{PROPS}/frozenwell_painted.glb", "well_asset",
                        (1.9, 9.6), 1.9, rot_z=math.radians(-25),
                        floor_fn=floor_fn):
        placed.append("well")
    print("DRESSED:", placed)
    return placed
