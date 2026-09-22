"""
TALK ON THE RIGGED CHARACTER.

The face chain proved visemes on a static head. This drives the same texture visemes
plus the jaw bone on the RIGGED character while the body is alive underneath, which is
the only configuration the film actually uses: if the lip-sync only reads on a locked-off
head it is not finished.

  blender -b --factory-startup --python talk_rigged.py -- <rigged.glb> <facesdir> <name> \
      <vis.npy> <blink.npy> <outdir> [frames=110] [height=1.6]
Env: TR_RES (720), TR_FPS (16), TR_LENS (85), TR_IDLE (1) body idle under the speech.
"""
import sys, os, math
import bpy, mathutils
import numpy as np

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import character_kit as kit                                        # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
GLB, FACES, NAME, VIS, BLINK, OUT = a[0], a[1], a[2], a[3], a[4], a[5]
NF = int(a[6]) if len(a) > 6 else 110
H = float(a[7]) if len(a) > 7 else 1.6
RES = int(os.environ.get("TR_RES", "720"))
FPS = int(os.environ.get("TR_FPS", "16"))
os.makedirs(OUT, exist_ok=True)

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
char, rig = kit.load_rigged_character(GLB, NAME, height=H)
ctrl = kit.enable_face_variants(char, NAME, FACES)

vis = np.load(VIS)
env = np.clip(np.abs(vis.astype(float)) / max(1.0, float(np.max(np.abs(vis)))), 0, 1) if vis.ndim == 1 else None
visemes = vis if vis.ndim == 1 else None
n = min(NF, len(vis))
# an envelope for the jaw: viseme column magnitude is a fine proxy
envelope = np.array([min(1.0, float(v) / 5.0) for v in vis[:n]])

f0 = 1
if os.environ.get("TR_IDLE", "1") not in ("", "0"):
    kit.apply_idle(rig, f0, f0 + n - 1, (0, 0, 0), 0.0, fps=FPS)
kit.apply_talk_tex(rig, ctrl, envelope, f0, fps=FPS, visemes=visemes, blinks=True)

sun = bpy.data.objects.new("s", bpy.data.lights.new("s", 'SUN'))
sun.data.energy = 3.4; sun.data.color = (1.0, 0.93, 0.85)
sun.rotation_euler = (math.radians(56), 0, math.radians(32))
sc.collection.objects.link(sun)
fl = bpy.data.objects.new("f", bpy.data.lights.new("f", 'SUN'))
fl.data.energy = 1.0; fl.data.color = (0.74, 0.82, 1.0)
fl.rotation_euler = (math.radians(68), 0, math.radians(-135))
sc.collection.objects.link(fl)
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.60, 0.66, 1)

cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
cam.data.lens = float(os.environ.get("TR_LENS", "85"))
sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = sc.render.resolution_y = RES
sc.render.fps = FPS
sc.render.image_settings.file_format = 'PNG'

zs = [(char.matrix_world @ v.co).z for v in char.data.vertices]
head_z = min(zs) + 0.84 * (max(zs) - min(zs))
ctr = mathutils.Vector((0, 0, head_z))
sc.frame_start, sc.frame_end = f0, f0 + n - 1
for i, f in enumerate(range(f0, f0 + n)):
    t = i / max(1, n - 1)
    ang = math.radians(-14 + 26 * t)                 # a slow drift across the face
    d = 0.62 * H
    cam.location = (ctr.x + d * math.sin(ang), ctr.y - d * math.cos(ang), ctr.z + 0.015 * H)
    cam.rotation_euler = (ctr - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_euler", frame=f)
for fc in cam.animation_data.action.fcurves:
    for kp in fc.keyframe_points:
        kp.interpolation = 'LINEAR'
sc.render.filepath = os.path.join(OUT, "t_")
bpy.ops.render.render(animation=True)
print("TALKRIG_DONE", OUT, n, "frames", flush=True)
