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
    # headland shelf (top at FLOOR_Z), cliff face, sea
    rocktex = valley_set.toon_tex("crt", "rocktex.png", tile=6.0, shadow_mult=0.55) if __import__("os").path.exists(valley_set.TEX + "/rocktex.png") else rock
    def _uv_scale(ob, k):
        # primitive cubes map each face to the full 0-1 texture: retile so a
        # 36 m face does not turn the grass into one giant blade
        uv = ob.data.uv_layers.active
        if uv:
            for l in uv.data: l.uv = (l.uv[0] * k, l.uv[1] * k)
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
    ob.name = "sea"; ob.data.materials.append(sea)
    # a shingle shore at the cliff foot, where the boat waits
    bpy.ops.mesh.primitive_cube_add(location=(6, 24, SEA_Z + 0.15)); ob = bpy.context.object
    ob.name = "shore"; ob.scale = (7, 3.5, 0.3); ob.data.materials.append(rock)
    set_assets.place(f"{PROPS}/benttree_painted.glb", "bent", (5.5, 16), 4.2, rot_z=0.6, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/seastack_painted.glb", "stack", (-9, 34), 9.5, floor_fn=lambda x, y: SEA_Z)
    set_assets.place(f"{PROPS}/seastack_painted.glb", "stack2", (18, 44), 6.5, rot_z=1.9, floor_fn=lambda x, y: SEA_Z)
    set_assets.place(f"{PROPS}/rock_painted.glb", "r1", (-4, 14), 1.1, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/rock_v2_painted.glb", "r2", (-8.5, 8), 0.9, rot_z=2.1, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/stones_painted.glb", "st1", (9, 10), 0.7, rot_z=0.8, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/bush_painted.glb", "b1", (-12, 12), 1.3, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/boat_painted.glb", "boat", (7.5, 24.5), 1.4, rot_z=0.35, floor_fn=lambda x, y: SEA_Z + 0.3)
    sun = bpy.data.lights.new("sun", "SUN"); sun.energy = 4.0; sun.color = (1.0, 0.84, 0.62)
    so = bpy.data.objects.new("sun", sun); so.rotation_euler = (math.radians(70), 0, math.radians(60))
    sc.collection.objects.link(so)
    print("CLIFF SET BUILT")
