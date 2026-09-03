"""
'The Nine Waterfalls' — a complete talk-piece short on one timeline.

Builds the scene .blend AND writes shots.json (the edit as data):
walk-in, meeting, five lines with viseme faces, silent beats, and a
closing walk toward the hall together under a crane-back.

Run: blender -b --factory-startup --python build_film.py -- \
       <audio_dir> <out.blend> <shots.json>
"""
import json
import math
import sys
import bpy
import numpy as np

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import valley_set                                              # noqa: E402
import character_kit as kit                                    # noqa: E402

audio_dir, out_blend, shots_out = sys.argv[-3:]
MESHES = "/workspace/text-to-video/series/tir-na-nog-legend/meshes"
FPS = 16
lines = json.load(open(f"{audio_dir}/lines.json"))

# ── the schedule, computed from real line lengths ────────────────────
WALK_END = 200
GAP, BEAT_MID, BEAT_END = 20, 44, 36
starts, f = [], 246
for i, L in enumerate(lines):
    starts.append(f)
    f += L["frames"] + GAP
    if i == 2:
        f += BEAT_MID                # the silence before the turn
WALK2_START = f - GAP + BEAT_END
FRAMES = WALK2_START + 200

NP = (-1.55, 8.0)
OP = (0.15, 6.9)


def floor_z(x, y):
    r = math.hypot(x, y - 20)
    return 0.35 * math.sin(x * 0.35) * math.cos(y * 0.3) * min(1, r / 8)


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

oisin = kit.load_character(f"{MESHES}/oisin_painted.glb", "oisin")
orig = kit.rig_character(oisin, "oisin")
niamh = kit.load_character(f"{MESHES}/niamh_painted.glb", "niamh", height=1.68)
nrig = kit.rig_character(niamh, "niamh")
octrl = kit.enable_face_variants(oisin, "oisin", f"{MESHES}/faces")
nctrl = kit.enable_face_variants(niamh, "niamh", f"{MESHES}/faces")

# ── performances ─────────────────────────────────────────────────────
def his_xy(f):
    if f >= WALK_END:
        return OP
    t = (f - 1) / (WALK_END - 1)
    e = t if t < 0.9 else 0.9 + (t - 0.9) * 0.5
    return (0.85 + (OP[0] - 0.85) * e, -6.0 + (OP[1] + 6.0) * e)


def walk_in(t):
    f = 1 + t * (WALK_END - 1)
    x, y = his_xy(f)
    x2, y2 = his_xy(min(WALK_END, f + 1))
    h = math.pi + math.atan2(-(x2 - x), max(1e-4, y2 - y))
    return (x, y, floor_z(x, y), h)


def walk_pair(p0, p1):
    pts = kit.plan_path(p0, p1, valley_set.OBSTACLES)
    print("path", p0, "->", p1, "via", len(pts), "points:", pts)
    return kit.path_fn_from_points(pts, floor_z, ease_end=False)


nhead = math.pi + math.atan2(-(OP[0] - NP[0]), OP[1] - NP[1])
ohead = math.pi + math.atan2(-(NP[0] - OP[0]), NP[1] - OP[1])

kit.apply_walk(orig, walk_in, 1, WALK_END, fps=FPS)
kit.apply_idle(orig, WALK_END + 1, WALK2_START - 1,
               (OP[0], OP[1], floor_z(*OP)), ohead, fps=FPS,
               look_at_fn=lambda f: NP)
kit.apply_idle(nrig, 1, WALK2_START - 1, (NP[0], NP[1], floor_z(*NP)),
               nhead, fps=FPS, look_at_fn=lambda f: his_xy(f))
kit.apply_walk(orig, walk_pair(OP, (4.6, 16.5)), WALK2_START, FRAMES,
               fps=FPS, stride_hz=1.15)
kit.apply_walk(nrig, walk_pair(NP, (3.0, 17.3)), WALK2_START, FRAMES,
               fps=FPS, stride_hz=1.2)

# faces: baseline closed+blinks over everything, then the lines
rigs = {"oisin": (orig, octrl), "niamh": (nrig, nctrl)}
for who, (r, fc) in rigs.items():
    kit.apply_talk_tex(r, fc, [0.0] * FRAMES, 1, fps=FPS)
for L, f0 in zip(lines, starts):
    env = np.load(f"{audio_dir}/l{L['i']}_env.npy")
    r, fc = rigs[L["who"]]
    kit.apply_talk_tex(r, fc, env, f0, fps=FPS, blinks=False)

# ── the edit, as data ────────────────────────────────────────────────
CLOSE_N = {"cam": "1.2,6.85,1.8", "tgt": "-1.55,8.05,1.45", "lens": 45}
CLOSE_O = {"cam": "-2.2,6.0,1.62", "tgt": "-0.45,7.25,1.57", "lens": 55}
TWO = {"cam": "5.5,7.6,1.45", "tgt": "-0.8,7.5,1.35", "lens": 50}
shots = [
    {"name": "s01_est", "f0": 1, "f1": 110, "cam": "-14,-6,5",
     "tgt": "0,10,1.5", "lens": 30, "move": "orbit:26"},
    {"name": "s02_walk", "f0": 111, "f1": 196, "cam": "-4.2,0.5,1.3",
     "tgt": "0,2,1.2", "lens": 42, "move": "pan"},
    {"name": "s03_meet", "f0": 197, "f1": starts[0] - 1, "move": "static", **TWO},
]
def _push(c):
    """A barely-perceptible push-in: 6% of the way to the subject."""
    cam = [float(v) for v in c["cam"].split(",")]
    tgt = [float(v) for v in c["tgt"].split(",")]
    p1 = [cam[k] + 0.06 * (tgt[k] - cam[k]) for k in range(3)]
    return {**c, "move": "dolly:%.3f,%.3f,%.3f" % tuple(p1)}


for i, (L, f0) in enumerate(zip(lines, starts)):
    f1 = f0 + L["frames"] + (GAP // 2)
    c = CLOSE_N if L["who"] == "niamh" else CLOSE_O
    j = f0 + 7                       # J-cut: hear the voice, then see the face
    if i == 3:                       # the long line: cut to her listening
        cut = f0 + int(L["frames"] * 0.62)
        shots.append({"name": f"s0{4+i}a", "f0": j, "f1": cut, **_push(c)})
        shots.append({"name": f"s0{4+i}b", "f0": cut + 1, "f1": f1,
                      "move": "static", **CLOSE_N})
    else:
        shots.append({"name": f"s0{4+i}", "f0": j, "f1": f1, **_push(c)})
    if i == 2:                       # the silent beat, held wide
        shots.append({"name": "s07_beat", "f0": f1 + 1,
                      "f1": f1 + BEAT_MID, "cam": "0.0,3.6,1.5",
                      "tgt": "-0.7,7.5,1.4", "lens": 40, "move": "static"})
shots.append({"name": "s10_beat", "f0": shots[-1]["f1"] + 1,
              "f1": WALK2_START - 1, "move": "static", **TWO})
shots.append({"name": "s11_away", "f0": WALK2_START, "f1": FRAMES,
              "cam": "0.2,2.8,1.5", "tgt": "3.6,15.5,1.6", "lens": 32,
              "move": "crane:2.6"})
json.dump({"fps": FPS, "frames": FRAMES,
           "line_starts": starts, "shots": shots},
          open(shots_out, "w"), indent=1)

bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("FILM SCENE SAVED", FRAMES, "frames,", len(shots), "shots")
