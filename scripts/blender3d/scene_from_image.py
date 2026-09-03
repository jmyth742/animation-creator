"""
Scene generated FROM AN IMAGE: plate + its depth map -> a displaced 3D
terrain the camera can actually move through.

Every pixel of the plate becomes a vertex pushed to its estimated depth,
textured by the plate itself. The camera then dollies forward with a slight
drift — parallax that no flat backdrop and no diffusion model can give
deterministically.

Run: blender -b --factory-startup --python scene_from_image.py -- \
       <plate.png> <depth.png> <outdir> [push_m] [drift_m]
"""
import sys
import math
import bpy

plate_path, depth_path, outdir = sys.argv[-5], sys.argv[-4], sys.argv[-3]
push, drift = float(sys.argv[-2]), float(sys.argv[-1])

FPS, FRAMES = 16, 81
RES = (832, 480)
GRID = (416, 240)            # one vertex per 2px
DEPTH_RANGE = 26.0           # metres from nearest to farthest pixel
NEAR = 2.0

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.render.resolution_x, sc.render.resolution_y = RES
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, FRAMES
sc.render.use_motion_blur = False
sc.view_settings.view_transform = 'Standard'
sc.render.filepath = outdir + "/frame_"
sc.render.image_settings.file_format = 'PNG'

# camera: 35mm at origin looking +Y
cam = bpy.data.cameras.new("cam"); cam.lens = 35
camo = bpy.data.objects.new("cam", cam)
camo.location = (0, 0, 0)
camo.rotation_euler = (math.radians(90), 0, 0)
sc.collection.objects.link(camo); sc.camera = camo

# view frustum footprint at a given depth for 35mm on a 36mm-wide sensor
def frustum(y):
    w = y * 36.0 / 35.0
    return w, w * RES[1] / RES[0]

# depth image -> per-vertex distance
dimg = bpy.data.images.load(depth_path)
dw, dh = dimg.size
dpx = list(dimg.pixels)      # RGBA floats

def depth_at(u, v):
    x = min(dw - 1, int(u * (dw - 1)))
    y = min(dh - 1, int(v * (dh - 1)))
    near01 = dpx[(y * dw + x) * 4]          # R channel, 1=near
    return NEAR + (1.0 - near01) * DEPTH_RANGE

# build the grid: each vertex sits ON the camera ray through its pixel,
# pushed to its estimated depth -> reprojection is exact from the origin
nx, ny = GRID
verts = []
for j in range(ny + 1):
    for i in range(nx + 1):
        u, v = i / nx, j / ny
        yd = depth_at(u, v)
        fw, fh = frustum(yd)
        verts.append(((u - 0.5) * fw, yd, (v - 0.5) * fh))
faces = []
for j in range(ny):
    for i in range(nx):
        a = j * (nx + 1) + i
        faces.append((a, a + 1, a + nx + 2, a + nx + 1))
mesh = bpy.data.meshes.new("terrain")
mesh.from_pydata(verts, [], faces)
uvl = mesh.uv_layers.new()
for poly in mesh.polygons:
    for li in poly.loop_indices:
        vi = mesh.loops[li].vertex_index
        uvl.data[li].uv = (vi % (nx + 1) / nx, vi // (nx + 1) / ny)
ob = bpy.data.objects.new("terrain", mesh)
sc.collection.objects.link(ob)

img = bpy.data.images.load(plate_path)
mat = bpy.data.materials.new("plate"); mat.use_nodes = True
nt = mat.node_tree; nt.nodes.clear()
tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img
em = nt.nodes.new("ShaderNodeEmission")
out = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(tex.outputs["Color"], em.inputs["Color"])
nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
mesh.materials.append(mat)

# the move: slow push with a slight lateral drift (classic establishing PTZ,
# but with TRUE parallax)
for f in range(1, FRAMES + 1):
    t = (f - 1) / (FRAMES - 1)
    e = t * t * (3 - 2 * t)                  # smoothstep
    camo.location = (drift * e, push * e, 0)
    camo.keyframe_insert("location", frame=f)

bpy.ops.render.render(animation=True)
print("SCENE FROM IMAGE COMPLETE")
