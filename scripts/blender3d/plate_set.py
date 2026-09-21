"""
A concept plate as a film SET: depth-projected terrain that the existing
build_film cameras and character blocking can use. build(sc, plate, depth,
cam_z=1.6) -> (plate_object, ground_fn). The terrain is built on the rays of
a reference camera at the origin looking +Y (35 mm), so world coordinates
match what stage_on_plate.py used: a character at y=CAST_Y stands where the
plate shows that depth. ground_fn(x, y) samples the terrain height.
"""
import math
import bpy, numpy as np

def build(sc, plate_path, depth_path, cam_z=1.6, grid=(208, 120), depth_range=26.0, near=2.0, lens=35.0):
    plate = bpy.data.images.load(plate_path); depth = bpy.data.images.load(depth_path)
    PW, PH = plate.size; DW, DH = depth.size
    dpx = np.array(depth.pixels[:], dtype=np.float32).reshape(DH, DW, 4)[:, :, 0]
    aspect = PW / PH; hw = 18.0 / lens
    def depth_at(u, v):
        x = min(DW - 1, int(u * (DW - 1))); y = min(DH - 1, int((1 - v) * (DH - 1)))
        return float(dpx[DH - 1 - y, x])
    gx, gy = grid; verts, faces, uvs = [], [], []
    for j in range(gy + 1):
        for i in range(gx + 1):
            u, v = i / gx, j / gy
            dist = near + (1.0 - depth_at(u, v)) * depth_range
            verts.append(((u - 0.5) * 2 * hw * dist, dist, cam_z + (v - 0.5) * 2 * hw / aspect * dist)); uvs.append((u, v))
    for j in range(gy):
        for i in range(gx):
            a = j * (gx + 1) + i; faces.append((a, a + 1, a + gx + 2, a + gx + 1))
    me = bpy.data.meshes.new("plate"); me.from_pydata(verts, [], faces); me.update()
    uvl = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices: uvl.data[li].uv = uvs[me.loops[li].vertex_index]
    ob = bpy.data.objects.new("plate", me); sc.collection.objects.link(ob)
    mat = bpy.data.materials.new("plate"); mat.use_nodes = True; nt = mat.node_tree; nt.nodes.clear()
    tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = plate; em = nt.nodes.new("ShaderNodeEmission"); out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tx.outputs["Color"], em.inputs["Color"]); nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    me.materials.append(mat)
    V = np.array(verts)
    # APRON: beyond the plate's bottom edge the camera sees nothing — extend a
    # ground plane at the plate's near-floor height so blocking can start off-plate
    floor_z = float(np.median(V[(V[:, 1] < near + 0.15 * depth_range), 2]))
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, near + 0.05 * depth_range, floor_z - 0.02)); ap = bpy.context.object; ap.name = "apron"
    apm = bpy.data.materials.new("apron"); apm.use_nodes = True; nt2 = apm.node_tree; nt2.nodes.clear()
    # sample the plate's near-floor colour so the apron matches
    ppx = np.array(plate.pixels[:], dtype=np.float32).reshape(PH, PW, 4)
    band = ppx[int(PH * 0.02):int(PH * 0.10), int(PW * 0.3):int(PW * 0.7), :3].reshape(-1, 3).mean(axis=0)
    em2 = nt2.nodes.new("ShaderNodeEmission"); em2.inputs["Color"].default_value = (*band, 1); out2 = nt2.nodes.new("ShaderNodeOutputMaterial")
    nt2.links.new(em2.outputs["Emission"], out2.inputs["Surface"]); ap.data.materials.append(apm)
    def ground_fn(x, y):
        m = (np.abs(V[:, 0] - x) < 1.2) & (np.abs(V[:, 1] - y) < 1.2)
        return float(np.median(V[m, 2])) if m.any() else 0.0
    ground_fn.floor_z = floor_z
    return ob, ground_fn
