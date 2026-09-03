"""
Phase-1 proof: rebuild ep16 s11 (walk-away wide) deterministically.

The AI plate seeds the 3D world: the FLUX valley master is camera-projected
as the entire visible environment (window-mapped emission), so the background
is pixel-identical to the validated plate. A low-poly cloaked figure with a
keyframed walk cycle supplies what diffusion cannot: real locomotion.

Run:  blender -b --factory-startup --python trial_walkaway.py -- <plate> <outdir>
"""
import sys
import math
import bpy

plate_path, outdir = sys.argv[-2], sys.argv[-1]

FPS, FRAMES = 16, 81           # 5.06s, matches CLIP_LENGTHS long
RES = (832, 480)

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)

sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.render.resolution_x, sc.render.resolution_y = RES
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, FRAMES
sc.render.filepath = outdir + "/frame_"
sc.render.image_settings.file_format = 'PNG'
sc.view_settings.view_transform = 'Standard'   # plate colours pass through
sc.render.use_motion_blur = False   # cel animation has none — EEVEE's default
                                    # blur smeared the walk into a ghost

# ── camera ───────────────────────────────────────────────────────────
cam = bpy.data.cameras.new("cam"); cam.lens = 35
camo = bpy.data.objects.new("cam", cam)
camo.location = (0, -14, 1.6)
camo.rotation_euler = (math.radians(90), 0, 0)
sc.collection.objects.link(camo); sc.camera = camo

# ── the plate IS the set: window-projected emission backdrop ─────────
img = bpy.data.images.load(plate_path)
mat = bpy.data.materials.new("plate"); mat.use_nodes = True
nt = mat.node_tree; nt.nodes.clear()
tc = nt.nodes.new("ShaderNodeTexCoord")
tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img
em = nt.nodes.new("ShaderNodeEmission")
out = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(tc.outputs["Window"], tex.inputs["Vector"])
nt.links.new(tex.outputs["Color"], em.inputs["Color"])
nt.links.new(em.outputs["Emission"], out.inputs["Surface"])

bpy.ops.mesh.primitive_plane_add(size=120, location=(0, 40, 20),
                                 rotation=(math.radians(90), 0, 0))
backdrop = bpy.context.object
backdrop.data.materials.append(mat)

# ── toon figure: cloak, head, arms, legs, inverted-hull outline ──────
def flat_mat(name, rgb):
    m = bpy.data.materials.new(name); m.use_nodes = True
    t = m.node_tree; t.nodes.clear()
    e = t.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*rgb, 1)
    o = t.nodes.new("ShaderNodeOutputMaterial")
    t.links.new(e.outputs["Emission"], o.inputs["Surface"])
    return m

cloak_m = flat_mat("cloak", (0.055, 0.115, 0.062))  # reads mid-green in sRGB
skin_m = flat_mat("skin", (0.85, 0.66, 0.50))
hair_m = flat_mat("hair", (0.16, 0.12, 0.09))
line_m = flat_mat("line", (0.02, 0.02, 0.02))

root = bpy.data.objects.new("root", None)
sc.collection.objects.link(root)

def part(name, prim, mat_, loc, scale, rot=(0, 0, 0)):
    getattr(bpy.ops.mesh, prim)(location=(0, 0, 0))
    ob = bpy.context.object
    ob.name = name; ob.scale = scale
    ob.location = loc; ob.rotation_euler = rot
    ob.data.materials.append(mat_)
    ob.parent = root
    return ob

# cloaked body: cone torso reads as a travelling cloak at distance
body = part("body", "primitive_cone_add", cloak_m, (0, 0, 0.62),
            (0.34, 0.30, 0.62))
head = part("head", "primitive_uv_sphere_add", cloak_m, (0, 0, 1.38),
            (0.15, 0.15, 0.17))          # hooded — cloak colour from behind
armL = part("armL", "primitive_cylinder_add", cloak_m, (0.20, 0, 0.85),
            (0.055, 0.055, 0.30), rot=(0, math.radians(6), 0))
armR = part("armR", "primitive_cylinder_add", cloak_m, (-0.20, 0, 0.85),
            (0.055, 0.055, 0.30), rot=(0, -math.radians(6), 0))
legL = part("legL", "primitive_cylinder_add", hair_m, (0.12, 0, 0.22),
            (0.06, 0.06, 0.26))
legR = part("legR", "primitive_cylinder_add", hair_m, (-0.12, 0, 0.22),
            (0.06, 0.06, 0.26))

# soft blob shadow, the limited-animation way
bpy.ops.mesh.primitive_circle_add(fill_type='NGON', location=(0, 0, 0.01))
blob = bpy.context.object
blob.scale = (0.42, 0.30, 1)
bm = flat_mat("blob", (0.05, 0.09, 0.06))
bm.blend_method = 'BLEND'
bm.node_tree.nodes["Emission"].inputs["Strength"].default_value = 0.9
blob.data.materials.append(bm)
blob.parent = root

# ── the walk: travel + bob + limb swing, all keyframed ───────────────
# path runs away from camera and slightly left, like the plate's path
for f in range(1, FRAMES + 1):
    t = (f - 1) / (FRAMES - 1)
    sc.frame_set(f)
    root.location = (0.8 - 2.6 * t, -6.5 + 11.5 * t, 0)
    root.rotation_euler = (0, 0, math.radians(8))
    root.keyframe_insert("location")
    root.keyframe_insert("rotation_euler")
    phase = t * FRAMES / 12 * 2 * math.pi          # ~1.3 steps/second
    bob = 0.035 * abs(math.sin(phase))
    body.location.z = 0.62 + bob; body.keyframe_insert("location")
    head.location.z = 1.38 + bob; head.keyframe_insert("location")
    for ob, sgn in ((armL, 1), (armR, -1)):
        ob.rotation_euler.x = sgn * 0.18 * math.sin(phase)
        ob.keyframe_insert("rotation_euler")
    for ob, sgn in ((legL, -1), (legR, 1)):
        ob.rotation_euler.x = sgn * 0.6 * math.sin(phase)
        ob.keyframe_insert("rotation_euler")

bpy.ops.render.render(animation=True)
print("TRIAL RENDER COMPLETE")
