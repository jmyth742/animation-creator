"""
VRM -> kit cast. The drop-in path for modelled anime heads.

VRoid/VRM is the answer to the one thing this pipeline cannot do: an anime face is a
drawing convention (eye scale and spacing, near-absent nose, specific jaw curve) and no
texture resolution, denoise strength or projection scheme recovers it from an
image-to-3D head. A VRM avatar arrives with correct proportions, REAL eye geometry, and
ARKit expression shape keys that our existing LAM Audio2Expression curves drive
directly — which deletes the whole texture-face stack (face_project_mv, face_paint, the
viseme/blink atlas variants and the per-frame image swap).

  blender -b --python vrm_import.py -- <in.vrm> <name> [height=1.75]

Writes <props>/<name>_vrm_rigged.glb, usable with FILM_MESH_SUFFIX=_vrm, and prints the
shape keys found so arkit_bridge.py can be pointed at them instead of the 6-column
viseme reduction.

NOTE: run WITHOUT --factory-startup; the add-on is an extension and factory startup
skips it.
"""
import sys, os, bpy

ADDON = "bl_ext.user_default.io_scene_vrm"
try:
    bpy.ops.preferences.addon_enable(module=ADDON)
except Exception as e:                                          # noqa: BLE001
    sys.exit("VRM add-on not enabled (%s). Install: see docs/PIPELINE_FOR_REVIEW.md" % e)

argv = sys.argv[sys.argv.index("--") + 1:]
src, name = argv[0], argv[1]
height = float(argv[2]) if len(argv) > 2 else 1.75
PROPS = "/workspace/text-to-video/series/tir-na-nog-legend/meshes/props"

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
bpy.ops.import_scene.vrm(filepath=src)

rig = next((o for o in sc.objects if o.type == 'ARMATURE'), None)
meshes = [o for o in sc.objects if o.type == 'MESH']
if rig is None or not meshes:
    sys.exit("VRM import produced no armature/mesh")
print("VRM imported: bones", len(rig.data.bones), "meshes", len(meshes), flush=True)

# VRoid ships a Colliders hierarchy that is not geometry; it confuses joins and exports
for o in list(sc.objects):
    if "collider" in o.name.lower() or "secondary" in o.name.lower():
        bpy.data.objects.remove(o, do_unlink=True)

# VRM humanoid names -> the kit skeleton the animators expect
KIT = {"hips": "hips", "spine": "spine", "chest": "spine", "head": "head",
       "leftUpperLeg": "thigh.L", "rightUpperLeg": "thigh.R",
       "leftLowerLeg": "shin.L", "rightLowerLeg": "shin.R",
       "leftFoot": "foot.L", "rightFoot": "foot.R",
       "leftUpperArm": "arm.L", "rightUpperArm": "arm.R",
       "leftLowerArm": "fore.L", "rightLowerArm": "fore.R"}
ext = getattr(rig.data, "vrm_addon_extension", None)
renamed = 0
if ext is not None:
    for spec, kit_name in KIT.items():
        for human in ("vrm1", "vrm0"):
            h = getattr(ext, human, None)
            if h is None:
                continue
            try:
                bones = h.humanoid.human_bones
                node = getattr(bones, spec, None)
                bn = getattr(getattr(node, "node", None), "bone_name", None) if node else None
                if bn and bn in rig.data.bones and rig.data.bones[bn].name != kit_name:
                    rig.data.bones[bn].name = kit_name
                    renamed += 1
            except Exception:                                   # noqa: BLE001
                pass
print("VRM bones renamed to kit skeleton:", renamed, flush=True)

# one mesh, metallic off (VRoid ships metallic 1 on some materials, which reads wrong
# under a cel ramp), transforms applied, scaled to the kit height
bpy.ops.object.select_all(action='DESELECT')
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
mesh = bpy.context.view_layer.objects.active
mesh.name = name
for m in mesh.data.materials:
    if m and m.use_nodes:
        for nd in m.node_tree.nodes:
            if nd.type == 'BSDF_PRINCIPLED':
                nd.inputs["Metallic"].default_value = 0.0

zs = [(mesh.matrix_world @ v.co).z for v in mesh.data.vertices]
cur = max(zs) - min(zs)
if cur > 0:
    s = height / cur
    rig.scale = (s, s, s)
    bpy.context.view_layer.update()
print("VRM scaled to height %.2f (factor %.3f)" % (height, height / cur if cur else 1), flush=True)

keys = []
if mesh.data.shape_keys:
    keys = [k.name for k in mesh.data.shape_keys.key_blocks]
print("VRM shape keys (%d):" % len(keys), keys[:12], "..." if len(keys) > 12 else "", flush=True)

bpy.ops.object.select_all(action='SELECT')
dst = os.path.join(PROPS, name + "_vrm_rigged.glb")
bpy.ops.export_scene.gltf(filepath=dst, use_selection=True, export_morph=True)
print("VRM_DONE", dst, flush=True)
