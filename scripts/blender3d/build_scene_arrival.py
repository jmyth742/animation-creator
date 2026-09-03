"""
The first TWO-CHARACTER 3D scene: Niamh waits by the cross, watching;
Oisin walks up the path and stops in front of her.

Run: blender -b --factory-startup --python build_scene_arrival.py -- <out.blend>
"""
import sys
import math
import bpy

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import valley_set                                              # noqa: E402
import character_kit as kit                                    # noqa: E402

out_blend = sys.argv[-1]
MESHES = "/workspace/text-to-video/series/tir-na-nog-legend/meshes"
FPS, FRAMES = 16, 81

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.render.resolution_x, sc.render.resolution_y = 832, 480
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, FRAMES
sc.render.use_motion_blur = False
sc.eevee.use_shadows = True
sc.view_settings.view_transform = 'Standard'

valley_set.build_set(sc)
import set_assets
set_assets.dress_valley(sc, floor_z if 'floor_z' in dir() else (lambda x, y: 0.0))

cam = bpy.data.cameras.new("cam_master"); cam.lens = 35
camo = bpy.data.objects.new("cam_master", cam)
camo.location = (-0.5, -12, 2.2)
camo.rotation_euler = (math.radians(84), 0, 0)
sc.collection.objects.link(camo); sc.camera = camo

# ── Niamh: idle by the cross, watching him come ──────────────────────
NPOS = (-1.55, 8.0, valley_set and 0.0)
npos = (-1.55, 8.0, 0.0)

# ── Oisin: walk up, stop in front of her ─────────────────────────────
STOP = (0.15, 6.9)
START = (0.85, -0.6)
WALK_END = 58


def his_xy(f):
    if f >= WALK_END:
        return STOP
    t = (f - 1) / (WALK_END - 1)
    e = t if t < 0.9 else 0.9 + (t - 0.9) * 0.5      # ease in to the stop
    return (START[0] + (STOP[0] - START[0]) * e,
            START[1] + (STOP[1] - START[1]) * e)


oisin = kit.load_character(f"{MESHES}/oisin_painted.glb", "oisin")
orig = kit.rig_character(oisin, "oisin")
niamh = kit.load_character(f"{MESHES}/niamh_painted.glb", "niamh", height=1.68)
nrig = kit.rig_character(niamh, "niamh")

# her: face his approach, watch him the whole time
nheading = math.pi + math.atan2(-(STOP[0] - npos[0]), STOP[1] - npos[1])
kit.apply_idle(nrig, 1, FRAMES, npos, nheading, fps=FPS,
               look_at_fn=lambda f: his_xy(f))

# him: walk, then settle facing her
def path(t):
    f = 1 + t * (WALK_END - 1)
    x, y = his_xy(f)
    x2, y2 = his_xy(min(WALK_END, f + 1))
    heading = math.pi + math.atan2(-(x2 - x), max(1e-4, y2 - y))
    return (x, y, 0.0, heading)

kit.apply_walk(orig, path, 1, WALK_END, fps=FPS)
face_her = math.pi + math.atan2(-(npos[0] - STOP[0]), npos[1] - STOP[1])
kit.apply_idle(orig, WALK_END + 1, FRAMES, (STOP[0], STOP[1], 0.0),
               face_her, fps=FPS, look_at_fn=lambda f: (npos[0], npos[1]))

bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("ARRIVAL SCENE SAVED", out_blend)
