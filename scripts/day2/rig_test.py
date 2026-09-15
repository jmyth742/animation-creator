"""
Prove a UniRig-rigged GLB animates in Blender: import, report the skeleton,
drive limb bones with a sine 'walk' for 48 frames, render a 3/4 turntable.
Run: blender -b --factory-startup --python rig_test.py -- <rigged.glb> <outdir> <tag>
"""
import sys, os, math
import bpy, mathutils
args = sys.argv[sys.argv.index("--") + 1:]
src, outdir, tag = args[0], args[1], args[2]
os.makedirs(outdir, exist_ok=True)
sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=src)
arms = [o for o in sc.objects if o.type == 'ARMATURE']
meshes = [o for o in sc.objects if o.type == 'MESH']
print("RIG armatures", len(arms), "meshes", len(meshes))
if not arms:
    print("RIG FAIL no armature"); sys.exit(1)
rig = arms[0]
bones = list(rig.pose.bones)
print("RIG bones", len(bones), [b.name for b in bones][:40])
skinned = [m for m in meshes if any(md.type == 'ARMATURE' for md in m.modifiers)]
print("RIG skinned meshes", len(skinned), "vgroups", [len(m.vertex_groups) for m in meshes])
# pick limb-ish bones by name, else the 4 longest chains' second bones
def pick(keys):
    return [b for b in bones if any(k in b.name.lower() for k in keys)]
legs = pick(("leg", "thigh", "hip", "upleg")) or bones[len(bones)//2:len(bones)//2+2]
arms_ = pick(("arm", "shoulder", "clavicle")) or bones[1:3]
print("RIG driving", [b.name for b in legs[:2]], [b.name for b in arms_[:2]])
F0, F1 = 1, 48
for f in range(F0, F1 + 1):
    t = 2 * math.pi * (f - F0) / 24.0
    for i, b in enumerate(legs[:2]):
        b.rotation_mode = 'XYZ'; b.rotation_euler = (math.radians(30) * math.sin(t + i * math.pi), 0, 0)
        b.keyframe_insert("rotation_euler", frame=f)
    for i, b in enumerate(arms_[:2]):
        b.rotation_mode = 'XYZ'; b.rotation_euler = (math.radians(25) * math.sin(t + i * math.pi + math.pi), 0, 0)
        b.keyframe_insert("rotation_euler", frame=f)
# light, world, camera framing the whole rig
sun = bpy.data.objects.new('sun', bpy.data.lights.new('s', 'SUN')); sun.data.energy = 3.5
sun.rotation_euler = (math.radians(60), 0, math.radians(25)); sc.collection.objects.link(sun)
wd = bpy.data.worlds.new('w'); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes['Background'].inputs['Color'].default_value = (0.62, 0.60, 0.58, 1)
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = 'BLENDER_EEVEE_NEXT'; sc.view_settings.view_transform = 'Standard'
dg = bpy.context.evaluated_depsgraph_get()
mn = mathutils.Vector((1e9,)*3); mx = mathutils.Vector((-1e9,)*3)
for m in meshes:
    for c in m.evaluated_get(dg).bound_box:
        wv = m.matrix_world @ mathutils.Vector(c)
        mn = mathutils.Vector(map(min, mn, wv)); mx = mathutils.Vector(map(max, mx, wv))
ctr = (mn + mx) / 2; size = max(mx - mn)
a = math.radians(35)
cam.location = (ctr.x + 2.2*size*math.sin(a), ctr.y - 2.2*size*math.cos(a), ctr.z + 0.15*size)
d = mathutils.Vector(ctr) - cam.location
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
sc.render.resolution_x, sc.render.resolution_y = 480, 600
sc.frame_start, sc.frame_end = F0, F1
sc.render.filepath = f"{outdir}/{tag}_"
sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(animation=True)
print("RIG DONE", tag)
