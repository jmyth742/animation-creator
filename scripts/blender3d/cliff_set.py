"""
The FAREWELL CLIFF stage (Episode 3): a grass headland ending in a cliff face
over the sea, a seastack offshore, a bent tree at the edge, rocks, and the boat
waiting on the shore below. Shelf top is FLOOR_Z; the sea is at SEA_Z.
build_set(sc) -> None. floor_fn(x, y) -> FLOOR_Z. OBSTACLES for plan_path.
"""
import math
import bpy
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
    # PAINTED BACKDROP: the location's concept plate on a far cyclorama behind
    # the geometry the cast stands on — sky, sea and horizon come from the
    # painting, the shelf/cliff/props stay real for contact and parallax.
    import os as _os
    plate_path = _os.environ.get("SET_PLATE", "/workspace/text-to-video/series/tir-na-nog-legend/sets/farewell_cliff/master.png")
    if _os.path.exists(plate_path) and _os.environ.get("SET_BACKDROP", "1") not in ("", "0"):
        img = bpy.data.images.load(plate_path)
        # a wide, tall curved wall 90 m out, facing the stage; UVs stretched so
        # the plate's horizon (~45% up the image) lands at the camera's eye line
        bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=95.0, depth=120.0, location=(0, 40, FLOOR_Z + 30), end_fill_type='NOTHING')
        cyc = bpy.context.object; cyc.name = "backdrop"; cyc.scale = (1, 0.75, 1)
        # keep the far half only (y > 40): delete near faces
        import bmesh
        bm = bmesh.new(); bm.from_mesh(cyc.data)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if (cyc.matrix_world @ f.calc_center_median()).y < 55], context='FACES')
        bm.to_mesh(cyc.data); bm.free(); cyc.data.update()
        # cylindrical UVs: u from angle, v from height
        uvl = cyc.data.uv_layers.new(name="UVMap"); import math as _m
        for poly in cyc.data.polygons:
            for li in poly.loop_indices:
                co = cyc.data.vertices[cyc.data.loops[li].vertex_index].co
                ang = _m.atan2(co.x, co.y)           # 0 straight ahead
                uvl.data[li].uv = (0.5 + ang / 1.9, (co.z + 60.0) / 120.0 * 0.9 + 0.05)
        bm_mat = bpy.data.materials.new("backdrop"); bm_mat.use_nodes = True; nt = bm_mat.node_tree; nt.nodes.clear()
        tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = img; tx.extension = 'EXTEND'
        em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Strength"].default_value = 1.0; out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(tx.outputs["Color"], em.inputs["Color"]); nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        cyc.data.materials.append(bm_mat)
        for poly in cyc.data.polygons: poly.use_smooth = True
        # the sea plane takes the plate's sea colour so the two meet
        print("BACKDROP plate", plate_path.split("/")[-2])
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
    ob.name = "headland"; ob.scale = (18, 12, 3); ob.data.materials.append(grass); _uv_scale(ob, 22)
    # the cliff face: three staggered rock slabs, not one flat wall
    for i, (x, y, sx, sy, sz, rz) in enumerate([(-7, 20.6, 8, 0.9, 5.6, 0.05), (4, 20.3, 9, 1.1, 5.8, -0.07), (13, 20.8, 7, 0.8, 5.4, 0.12)]):
        bpy.ops.mesh.primitive_cube_add(location=(x, y, -1)); ob = bpy.context.object
        ob.name = f"cliff{i}"; ob.scale = (sx, sy, sz); ob.rotation_euler = (0.06 * (i - 1), 0, rz)
        ob.data.materials.append(rocktex); _uv_scale(ob, 6)
    bpy.ops.mesh.primitive_cube_add(location=(24, 6, FLOOR_Z - 3.5)); ob = bpy.context.object
    ob.name = "shoulder"; ob.scale = (7, 14, 3); ob.rotation_euler.z = 0.2; ob.data.materials.append(grass); _uv_scale(ob, 12)
    bpy.ops.mesh.primitive_plane_add(size=260, location=(0, 70, SEA_Z)); ob = bpy.context.object
    ob.name = "sea"; ob.data.materials.append(sea); _uv_scale(ob, 1)
    # a shingle shore at the cliff foot, where the boat waits
    bpy.ops.mesh.primitive_cube_add(location=(6, 24, SEA_Z + 0.15)); ob = bpy.context.object
    ob.name = "shore"; ob.scale = (7, 3.5, 0.3); ob.data.materials.append(rocktex); _uv_scale(ob, 1)
    set_assets.place(f"{PROPS}/benttree_painted.glb", "bent", (5.5, 16), 4.2, rot_z=0.6, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/seastack_painted.glb", "stack", (-14, 38), 9.5, floor_fn=lambda x, y: SEA_Z)
    set_assets.place(f"{PROPS}/seastack_painted.glb", "stack2", (26, 40), 6.5, rot_z=1.9, floor_fn=lambda x, y: SEA_Z)
    set_assets.place(f"{PROPS}/rock_painted.glb", "r1", (-4, 14), 1.1, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/rock_v2_painted.glb", "r2", (-8.5, 8), 0.9, rot_z=2.1, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/stones_painted.glb", "st1", (9, 10), 0.7, rot_z=0.8, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/bush_painted.glb", "b1", (-12, 12), 1.3, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/boat_painted.glb", "boat", (7.5, 24.5), 1.4, rot_z=0.35, floor_fn=lambda x, y: SEA_Z + 0.3)
    sun = bpy.data.lights.new("sun", "SUN"); sun.energy = 4.0; sun.color = (1.0, 0.84, 0.62)
    so = bpy.data.objects.new("sun", sun); so.rotation_euler = (math.radians(70), 0, math.radians(60))
    sc.collection.objects.link(so)
    print("CLIFF SET BUILT")
