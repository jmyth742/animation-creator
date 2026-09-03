"""Niamh speaks: over-the-shoulder dialogue shot, jaw driven by the line."""
import sys
import math
import bpy
import numpy as np

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import valley_set                                              # noqa: E402
import character_kit as kit                                    # noqa: E402

env_path, out_blend = sys.argv[-2:]
MESHES = "/workspace/text-to-video/series/tir-na-nog-legend/meshes"
env = np.load(env_path)
FPS, FRAMES = 16, len(env) + 12          # a beat before and after the line

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

NP = (-1.55, 8.0, 0.0)          # her mark by the cross
OP = (0.15, 6.9, 0.0)           # his mark, facing her

niamh = kit.load_character(f"{MESHES}/niamh_painted.glb", "niamh", height=1.68)
nrig = kit.rig_character(niamh, "niamh")
oisin = kit.load_character(f"{MESHES}/oisin_painted.glb", "oisin")
orig = kit.rig_character(oisin, "oisin")

import json
def _calib(who):
    f = pathlib_Path = f"{MESHES}/{who}_face.json"
    import os
    return json.load(open(f)) if os.path.exists(f) else None
nface = kit.add_face(niamh, nrig, "niamh", calib=_calib("niamh"))
oface = kit.add_face(oisin, orig, "oisin", calib=_calib("oisin"))

nhead = math.pi + math.atan2(-(OP[0] - NP[0]), OP[1] - NP[1])
ohead = math.pi + math.atan2(-(NP[0] - OP[0]), NP[1] - OP[1])
kit.apply_idle(nrig, 1, FRAMES, NP, nhead, fps=FPS,
               look_at_fn=lambda f: (OP[0], OP[1]))
kit.apply_idle(orig, 1, FRAMES, OP, ohead, fps=FPS,
               look_at_fn=lambda f: (NP[0], NP[1]))
kit.apply_talk_face(nrig, nface, env, 7, fps=FPS)
kit.apply_talk_face(orig, oface, [0.0] * (FRAMES - 1), 1, fps=FPS)  # blinks only

bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("TALK SCENE SAVED", FRAMES, "frames")
