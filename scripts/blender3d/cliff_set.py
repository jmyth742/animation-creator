"""
The FAREWELL CLIFF stage (Episode 3): a grass headland ending in a cliff face
over the sea, a seastack offshore, a bent tree at the edge, rocks, and the boat
waiting on the shore below. Shelf top is FLOOR_Z; the sea is at SEA_Z.
build_set(sc) -> None. floor_fn(x, y) -> FLOOR_Z. OBSTACLES for plan_path.
"""
import math
import bpy, mathutils
import valley_set
import set_assets

FLOOR_Z = 4.5
SEA_Z = -5.5
OBSTACLES = [(-4.0, 14.0, 1.2), (5.5, 16.0, 1.4), (-8.5, 8.0, 1.1)]
PROPS = "/workspace/text-to-video/series/tir-na-nog-legend/meshes/props"

def floor_fn(x, y):
    return FLOOR_Z

def build_set(sc):
    grass = valley_set.toon_tex("cg", "grasstex.png", tile=1.6) if __import__("os").path.exists(valley_set.TEX + "/grasstex.png") else valley_set.toon("cg", (0.24, 0.40, 0.20))
    rock = valley_set.toon("cr", (0.35, 0.36, 0.38), shadow_mult=0.5)
    sea = valley_set.toon_tex("cs", "watertex.png", tile=14.0, shadow_mult=0.85) if __import__("os").path.exists(valley_set.TEX + "/watertex.png") else valley_set.toon("cs", (0.15, 0.30, 0.40), shadow_mult=0.8)
    sky = bpy.data.worlds.new("w"); sc.world = sky; sky.use_nodes = True
    sky.node_tree.nodes["Background"].inputs["Color"].default_value = (0.62, 0.70, 0.82, 1)
    # PAINTED WORLD (hybrid set, painter.py): the concept plate projected onto
    # near geometry + a far dome from a painter camera (pose h, calibrated in
    # review/env_painter_calib.png); film.py re-projects per shot from the shot
    # camera. SET_PLATE overrides the plate, SET_BACKDROP=0 = primitives.
    import painter
    P = painter.setup(sc, "/workspace/text-to-video/series/tir-na-nog-legend/sets/farewell_cliff/master.png",
                      (-17.0, -12.0, 8.0), (7.0, 20.0, 4.8))
    PLATE = P.plate if P is not None else None
    def painted(name, fallback, sat=1.0, val=1.0, shade=True, flat=None):
        return fallback if P is None else P.painted(name, fallback, sat, val, shade, flat)
    if P is not None:
        P.dome(sc, (0, 30, FLOOR_Z))
    # headland shelf (top at FLOOR_Z), cliff face, sea
    rocktex = valley_set.toon_tex("crt", "rocktex.png", tile=6.0, shadow_mult=0.55) if __import__("os").path.exists(valley_set.TEX + "/rocktex.png") else rock
    for mat in (rocktex, grass, sea):
        # images are sampled by XY: vertical faces streak. Box projection.
        if mat.use_nodes:
            for nd in mat.node_tree.nodes:
                if nd.type == 'TEX_IMAGE':
                    nd.projection = 'BOX'; nd.projection_blend = 0.25
    def _uv_scale(ob, k):
        # toon_tex samples OBJECT-local coordinates: bake the object scale into
        # the mesh so a 36 m slab tiles like the valley floor (unscaled grid)
        bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.ops.mesh.primitive_cube_add(location=(0, 8, FLOOR_Z - 3)); ob = bpy.context.object
    ob.name = "headland"; ob.scale = (10.5, 8, 3); ob.location.x = 7.5; ob.location.y = 12.0; ob.data.materials.append(painted("p_grass", grass)); _uv_scale(ob, 22)
    def _top_grass(ob):
        # the TOP the cast walks on tiles the plate's own grass (reads as grass from every camera);
        # the sides keep the projected rock. Master plate: headland grass at u 0.66-0.80, v 0.42-0.50.
        if P is None: return
        ob.data.materials.append(P.tiled("p_grass_tile", (0.72, 0.36, 0.86, 0.44), size_m=5.0))
        for poly in ob.data.polygons: poly.material_index = 1 if poly.normal.z > 0.5 else 0
    # round the far (sea-side) corners into the plate's promontory
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='DESELECT'); bpy.ops.object.mode_set(mode='OBJECT')
    for v in ob.data.vertices: v.select = (v.co.y > 12.0 + 7.0)
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.bevel(offset=7.0, segments=6, affect='VERTICES'); bpy.ops.object.mode_set(mode='OBJECT')
    _top_grass(ob)   # after the bevel: the new corner faces get their index too
    # the cliff face: three staggered rock slabs, not one flat wall
    for i, (x, y, sx, sy, sz, rz) in enumerate([(-1, 20.6, 3, 0.9, 5.6, 0.05), (4, 20.3, 9, 1.1, 5.8, -0.07), (13, 20.8, 7, 0.8, 5.4, 0.12)]):
        bpy.ops.mesh.primitive_cube_add(location=(x, y, -1)); ob = bpy.context.object
        ob.name = f"cliff{i}"; ob.scale = (sx, sy, sz); ob.rotation_euler = (0.06 * (i - 1), 0, rz)
        ob.data.materials.append(painted("p_rock", rocktex, sat=0.85, val=0.95)); _uv_scale(ob, 6)
    # the cliff FOOT: the plate's rock bulges toward the viewer at the base; a
    # lower, forward slab catches those pixels on a near-vertical face instead
    # of letting them streak across the sea plane (env_painter_proj_check.png)
    bpy.ops.mesh.primitive_cube_add(location=(7.5, 18.6, SEA_Z - 0.5)); ob = bpy.context.object
    ob.name = "cliff_foot"; ob.scale = (10.5, 1.6, 2.6); ob.rotation_euler = (0.35, 0, 0.03)
    ob.data.materials.append(painted("p_foot", rocktex, sat=0.85, val=0.95, flat=(0.30, 0.31, 0.27))); _uv_scale(ob, 6)
    bpy.ops.mesh.primitive_cube_add(location=(24, 6, FLOOR_Z - 3.5)); ob = bpy.context.object
    ob.name = "shoulder"; ob.scale = (7, 9, 3); ob.location.y = 8.0; ob.rotation_euler.z = 0.2; ob.data.materials.append(painted("p_grass2", grass)); _uv_scale(ob, 12); _top_grass(ob)
    bpy.ops.mesh.primitive_plane_add(size=260, location=(0, 60, SEA_Z)); ob = bpy.context.object
    ob.name = "sea"; ob.data.materials.append(painted("p_sea", sea, sat=1.05, flat=(0.17, 0.39, 0.36, 0.02, 0.09))); _uv_scale(ob, 1)
    # a shingle shore at the cliff foot, where the boat waits
    bpy.ops.mesh.primitive_cube_add(location=(6, 24, SEA_Z + 0.15)); ob = bpy.context.object
    ob.name = "shore"; ob.scale = (7, 3.5, 0.3); ob.data.materials.append(painted("p_shore", rocktex, sat=0.85, val=0.95, flat=(0.30, 0.31, 0.27))); _uv_scale(ob, 1)
    if P is None:   # the plate paints the bent tree; the prop doubled it (env_painted_ep3q_probes.png)
        set_assets.place(f"{PROPS}/benttree_painted.glb", "bent", (5.5, 16), 4.2, rot_z=0.6, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/seastack_painted.glb", "stack", (-14, 38), 9.5, floor_fn=lambda x, y: SEA_Z)
    set_assets.place(f"{PROPS}/seastack_painted.glb", "stack2", (26, 40), 6.5, rot_z=1.9, floor_fn=lambda x, y: SEA_Z)
    # props live on the PAINTED headland (x > 3 from the painter's side); west of it the plate paints sea
    set_assets.place(f"{PROPS}/rock_painted.glb", "r1", (6, 13), 1.1, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/rock_v2_painted.glb", "r2", (11, 9), 0.9, rot_z=2.1, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/stones_painted.glb", "st1", (9, 10), 0.7, rot_z=0.8, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/bush_painted.glb", "b1", (14, 12), 1.3, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/boat_painted.glb", "boat", (7.5, 24.5), 1.4, rot_z=0.35, floor_fn=lambda x, y: SEA_Z + 0.3)
    sun = bpy.data.lights.new("sun", "SUN"); sun.energy = 4.0; sun.color = (1.0, 0.84, 0.62)
    so = bpy.data.objects.new("sun", sun); so.rotation_euler = (math.radians(70), 0, math.radians(60))
    sc.collection.objects.link(so)
    if P is not None: P.project_all(sc)
    print("CLIFF SET BUILT")
