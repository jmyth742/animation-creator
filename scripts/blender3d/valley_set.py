OBSTACLES = []
"""
The valley as a REAL 3D set — geometry, toon materials, a sun that casts
shadows. Not a projected painting: everything here occludes, receives light,
and can be filmed from any angle.

Import-safe: build_set(sc) constructs the set and returns dict of anchors.
"""
import math
import bpy


def toon(name, rgb, shadow_mult=0.55, gloss=0.0):
    """Two-tone cel material: lit colour / shadow colour, hard boundary."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    torgb = nt.nodes.new("ShaderNodeShaderToRGB")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = 'CONSTANT'
    ramp.color_ramp.elements[0].color = (*[c * shadow_mult for c in rgb], 1)
    ramp.color_ramp.elements[1].position = 0.55
    ramp.color_ramp.elements[1].color = (*rgb, 1)
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(diff.outputs["BSDF"], torgb.inputs["Shader"])
    nt.links.new(torgb.outputs["Color"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


def _obj(name, mesh_op, mat, loc=(0, 0, 0), scale=(1, 1, 1), rot=(0, 0, 0), **kw):
    mesh_op(location=loc, **kw)
    ob = bpy.context.object
    ob.name = name
    ob.scale = scale
    ob.rotation_euler = rot
    if mat:
        ob.data.materials.append(mat)
    return ob


def build_set(sc):
    import random
    rnd = random.Random(6100)

    grass = toon("grass", (0.23, 0.42, 0.18))
    grass_dk = toon("grassdk", (0.16, 0.33, 0.14))
    rock = toon("rock", (0.34, 0.38, 0.33))
    mount = toon("mount", (0.25, 0.36, 0.28))
    water = toon("water", (0.13, 0.33, 0.38), shadow_mult=0.8)
    falls = toon("falls", (0.88, 0.93, 0.95), shadow_mult=0.9)
    path_m = toon("path", (0.58, 0.48, 0.33))
    gold = toon("gold", (0.72, 0.60, 0.25))
    gold_dk = toon("golddk", (0.55, 0.44, 0.16))
    leaf = toon("leaf", (0.14, 0.30, 0.13))
    trunk = toon("trunk", (0.28, 0.20, 0.13))

    # valley floor with gentle relief
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=90, y_subdivisions=90,
                                    size=90, location=(0, 20, 0))
    floor = bpy.context.object
    floor.name = "floor"
    for v in floor.data.vertices:
        r = math.hypot(v.co.x, v.co.y)
        v.co.z = 0.35 * math.sin(v.co.x * 0.35) * math.cos(v.co.y * 0.3) \
            * min(1, r / 8)
    floor.data.materials.append(grass)

    # mountain walls: big displaced cones ringing the back
    for i, (mx, my, h, r) in enumerate([
            (-24, 46, 22, 16), (-9, 52, 26, 18), (9, 54, 24, 17),
            (26, 48, 20, 14), (-36, 34, 17, 12), (38, 36, 18, 13)]):
        _obj(f"mtn{i}", bpy.ops.mesh.primitive_cone_add, mount,
             loc=(mx, my, h * 0.38), scale=(r, r, h),
             vertices=24, radius1=1.0, radius2=0.12)

    # the lake, left of the path
    _obj("lake", bpy.ops.mesh.primitive_circle_add, water,
         loc=(-8, 19, 0.06), scale=(10, 8, 1), fill_type='NGON')

    # waterfall: a stylised ribbon from the mountains into the lake
    _obj("falls", bpy.ops.mesh.primitive_plane_add, falls,
         loc=(-9, 26.5, 4.5), scale=(1.6, 0.1, 4.5),
         rot=(math.radians(90), 0, 0))
    _obj("foam", bpy.ops.mesh.primitive_circle_add, falls,
         loc=(-9, 24.8, 0.12), scale=(2.4, 1.3, 1), fill_type='NGON')

    # the path: a ribbon of flat quads following the walk line
    for i in range(26):
        t = i / 25
        _obj(f"path{i}", bpy.ops.mesh.primitive_plane_add, path_m,
             loc=(0.9 - 2.6 * t + 0.5 * math.sin(t * 5), -4 + 22 * t, 0.05),
             scale=(1.0 - 0.5 * t, 1.3, 1))

    # the golden hall on a rise, right side
    hx, hy = 7.5, 26
    _obj("rise", bpy.ops.mesh.primitive_cylinder_add, grass_dk,
         loc=(hx, hy, 0.5), scale=(9, 7, 0.5))
    _obj("hall", bpy.ops.mesh.primitive_cube_add, gold,
         loc=(hx, hy, 3.4), scale=(5.5, 3.4, 2.4))
    _obj("tower", bpy.ops.mesh.primitive_cube_add, gold,
         loc=(hx + 4.2, hy - 0.6, 4.6), scale=(1.7, 1.7, 3.4))
    _obj("towerroof", bpy.ops.mesh.primitive_cone_add, gold_dk,
         loc=(hx + 4.2, hy - 0.6, 8.8), scale=(2.1, 2.1, 1.5), vertices=8)
    # arched door: dark inset + columns
    _obj("door", bpy.ops.mesh.primitive_cube_add, toon("dark", (0.10, 0.07, 0.05)),
         loc=(hx - 1.5, hy - 3.5, 1.9), scale=(1.1, 0.2, 1.9))
    for dx in (-2.9, -0.1):
        _obj("col", bpy.ops.mesh.primitive_cylinder_add, gold_dk,
             loc=(hx + dx, hy - 3.6, 1.8), scale=(0.28, 0.28, 1.8))
    # crenellations
    for i in range(7):
        _obj("cren", bpy.ops.mesh.primitive_cube_add, gold_dk,
             loc=(hx - 4.8 + i * 1.6, hy - 3.3, 6.1), scale=(0.4, 0.25, 0.3))

    # trees: cone canopies on trunks, scattered but not on the path
    spots = [(-3.5, 8, 1.0), (3.4, 12, 1.3), (-4.8, 16, 1.1), (5.5, 18, 0.9),
             (2.8, 30, 1.4), (-3.2, 33, 1.2), (12, 18, 1.5), (-13, 12, 1.3)]
    global OBSTACLES
    OBSTACLES = [(tx, ty, 1.05 * ts) for tx, ty, ts in spots]
    OBSTACLES.append((-2.6, 19, 0.5))          # the cross
    OBSTACLES.append((7.5, 26, 8.0))           # hall + rise
    OBSTACLES.append((-8, 19, 8.5))            # the lake — nobody wades
    for i, (tx, ty, ts) in enumerate(spots):
        _obj(f"trunk{i}", bpy.ops.mesh.primitive_cylinder_add, trunk,
             loc=(tx, ty, 0.9 * ts), scale=(0.22 * ts, 0.22 * ts, 0.9 * ts))
        _obj(f"can{i}", bpy.ops.mesh.primitive_cone_add, leaf,
             loc=(tx, ty, 2.6 * ts), scale=(1.3 * ts, 1.3 * ts, 1.9 * ts),
             vertices=10)
        _obj(f"can{i}b", bpy.ops.mesh.primitive_cone_add, leaf,
             loc=(tx + 0.2, ty, 3.4 * ts), scale=(0.9 * ts, 0.9 * ts, 1.3 * ts),
             vertices=10)

    # standing cross by the lake (the plate's landmark)
    _obj("crossv", bpy.ops.mesh.primitive_cylinder_add, trunk,
         loc=(-2.6, 19, 1.6), scale=(0.16, 0.16, 1.6))
    _obj("crossh", bpy.ops.mesh.primitive_cylinder_add, trunk,
         loc=(-2.6, 19, 2.4), scale=(0.14, 0.14, 0.8),
         rot=(0, math.radians(90), 0))

    # flowers: tiny bright dots near the camera
    fl = toon("flower", (0.85, 0.80, 0.55), shadow_mult=0.8)
    for i in range(70):
        fx = rnd.uniform(-9, 9); fy = rnd.uniform(-5, 14)
        if abs(fx - (0.9 - 2.6 * ((fy + 4) / 22))) < 1.2:
            continue
        _obj(f"fl{i}", bpy.ops.mesh.primitive_ico_sphere_add, fl,
             loc=(fx, fy, 0.12), scale=(0.07, 0.07, 0.07), subdivisions=1)

    # sky + clouds
    w = bpy.data.worlds.new("sky")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.42, 0.68, 0.88, 1)
    bg.inputs["Strength"].default_value = 1.0
    cloud = toon("cloud", (0.96, 0.97, 0.95), shadow_mult=0.95)
    for i, (cx, cz, cs) in enumerate([(-20, 26, 4), (8, 30, 5), (28, 24, 3.5),
                                      (-4, 33, 3)]):
        _obj(f"cloud{i}", bpy.ops.mesh.primitive_ico_sphere_add, cloud,
             loc=(cx, 60, cz), scale=(cs, cs * 0.5, cs * 0.35), subdivisions=2)

    # the sun — real shadows
    sun = bpy.data.lights.new("sun", 'SUN')
    sun.energy = 3.5
    sun.angle = 0.05
    so = bpy.data.objects.new("sun", sun)
    so.rotation_euler = (math.radians(62), math.radians(-8), math.radians(55))
    sc.collection.objects.link(so)
    return {"grass": grass}
