"""
Stage the rigged cast INSIDE a depth-projected concept plate: the plate becomes
a displaced terrain (scene_from_image's method), the characters stand on it at
the plate's own scale, lit to match the plate. One still per call.
Run: blender -b --factory-startup --python stage_on_plate.py -- \
      <plate.png> <depth.png> <outdir> <tag> [cast_y=9.0] [cam_y=1.6]
"""
import sys, os, math
import bpy, mathutils, numpy as np
sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import character_kit as kit
args = sys.argv[sys.argv.index("--") + 1:]
plate_path, depth_path, outdir, tag = args[:4]
CAST_Y = float(args[4]) if len(args) > 4 else 9.0
CAM_Y = float(args[5]) if len(args) > 5 else 1.6
os.makedirs(outdir, exist_ok=True)
P = "/workspace/text-to-video/series/tir-na-nog-legend/meshes/props"
sc = bpy.context.scene
for ob in list(sc.objects): bpy.data.objects.remove(ob, do_unlink=True)
sc.render.engine = 'BLENDER_EEVEE_NEXT'; sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x, sc.render.resolution_y = 1248, 720

# ---- plate terrain (same construction as scene_from_image: vertices on camera rays)
plate = bpy.data.images.load(plate_path); depth = bpy.data.images.load(depth_path)
PW, PH = plate.size; DW, DH = depth.size
dpx = np.array(depth.pixels[:], dtype=np.float32).reshape(DH, DW, 4)[:, :, 0]
GRID = (208, 120); DEPTH_RANGE = 26.0; NEAR = 2.0
cam = bpy.data.cameras.new("cam"); cam.lens = 35; cam.sensor_width = 36
camo = bpy.data.objects.new("cam", cam); camo.location = (0, 0, CAM_Y); camo.rotation_euler = (math.radians(90), 0, 0)
sc.collection.objects.link(camo); sc.camera = camo
aspect = PW / PH; hw = 18.0 / cam.lens / 2 * 1.0   # half tan of horizontal FOV (36mm sensor)
def depth_at(u, v):
    x = min(DW - 1, int(u * (DW - 1))); y = min(DH - 1, int((1 - v) * (DH - 1)))
    return float(dpx[DH - 1 - y, x])
verts, faces, uvs = [], [], []
gx, gy = GRID
for j in range(gy + 1):
    for i in range(gx + 1):
        u, v = i / gx, j / gy
        d = depth_at(u, v)                       # 1 = near (Depth-Anything convention: bright = near)
        dist = NEAR + (1.0 - d) * DEPTH_RANGE
        x = (u - 0.5) * 2 * hw * dist; z = CAM_Y + (v - 0.5) * 2 * hw / aspect * dist
        verts.append((x, dist, z)); uvs.append((u, v))
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
# ground height under the cast: sample the terrain at (x=0, y=CAST_Y)
zs = [vz for (vx, vy, vz) in verts if abs(vx) < 1.5 and abs(vy - CAST_Y) < 1.5]
ground = float(np.median(zs)) if zs else 0.0
print("STAGE ground z at y=%.1f: %.2f" % (CAST_Y, ground))

# ---- cast, lit like the plate (warm key from the plate's bright side, cool fill)
for who, h, x, yaw in (("niamh_mv", 1.68, -0.55, 25), ("oisin_mv", 1.75, 0.65, -25)):
    ch, rig = kit.load_rigged_character(f"{P}/{who}_rigged.glb", who, height=h, skirt=(who.startswith("niamh")))
    rig.location = (x, CAST_Y, ground); rig.rotation_euler = (0, 0, math.radians(yaw))
sun = bpy.data.objects.new('sun', bpy.data.lights.new('s', 'SUN')); sun.data.energy = 3.2; sun.data.color = (1.0, 0.88, 0.70)
sun.rotation_euler = (math.radians(55), 0, math.radians(-35)); sc.collection.objects.link(sun)
fill = bpy.data.objects.new('fill', bpy.data.lights.new('f', 'SUN')); fill.data.energy = 0.8; fill.data.color = (0.75, 0.85, 1.0)
fill.rotation_euler = (math.radians(60), 0, math.radians(150)); sc.collection.objects.link(fill)
wd = bpy.data.worlds.new('w'); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes['Background'].inputs['Color'].default_value = (0.75, 0.80, 0.85, 1)
sc.render.filepath = f"{outdir}/{tag}.png"; bpy.ops.render.render(write_still=True)
print("STAGE DONE", sc.render.filepath)
