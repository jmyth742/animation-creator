"""
'The Farewell Cliff' (Episode 3) — the legend's turn, on the cliff stage.

Builds the scene .blend AND writes shots.json (the edit as data):
walk-in, meeting, five lines with viseme faces, silent beats, and a
closing walk toward the hall together under a crane-back.

Run: blender -b --factory-startup --python build_film3.py -- \
       <audio_dir> <out.blend> <shots.json>
"""
import json
import math
import pathlib
import sys
import bpy
import numpy as np

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import cliff_set                                               # noqa: E402
import character_kit as kit                                    # noqa: E402

audio_dir, out_blend, shots_out = sys.argv[-3:]
MESHES = "/workspace/text-to-video/series/tir-na-nog-legend/meshes"
import os
FPS = int(os.environ.get("FILM_FPS", 16))
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

NP = (0.4, 16.2)       # Niamh stops here, a step behind him
OP = (2.0, 17.5)       # Oisin at the cliff edge
EDGE = (2.0, 21.0)     # what he looks at: the sea


def floor_z(x, y):
    return cliff_set.FLOOR_Z
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

cliff_set.build_set(sc)

CAST = os.environ.get("FILM_CAST", "mv")     # mv = Hunyuan-mv meshes, cg = CharacterGen meshes (Day-2 verdict)
if os.environ.get("FILM_RIG", "numpy") == "unirig":
    # Day-5: UniRig-skinned cast (real skeletons + skin weights), same animators
    ON, NN = ("cg_oisin", "cg_niamh") if CAST == "cg" else ("oisin_mv", "niamh_mv")
    oisin, orig = kit.load_rigged_character(f"{MESHES}/props/{ON}_rigged.glb", ON, height=1.75)
    niamh, nrig = kit.load_rigged_character(f"{MESHES}/props/{NN}_rigged.glb", NN, height=1.68, skirt=True)
else:
    oisin = kit.load_character(f"{MESHES}/props/oisin_mv_painted.glb", "oisin_mv")
    orig = kit.rig_character(oisin, "oisin_mv")
    niamh = kit.load_character(f"{MESHES}/props/niamh_mv_painted.glb", "niamh_mv", height=1.68)
    nrig = kit.rig_character(niamh, "niamh_mv")
FS = os.environ.get("FILM_FACE_SUFFIX", "")     # e.g. _flat -> <name>_flat_face_*.png (flattened palette A/B)
octrl = kit.enable_face_variants(oisin, oisin.name + FS, f"{MESHES}/props")
nctrl = kit.enable_face_variants(niamh, niamh.name + FS, f"{MESHES}/props")

# ── performances ─────────────────────────────────────────────────────
def her_xy(f):
    if f >= WALK_END:
        return NP
    t = (f - 1) / (WALK_END - 1)
    e = t if t < 0.9 else 0.9 + (t - 0.9) * 0.5
    return (-3.0 + (NP[0] + 3.0) * e, -2.0 + (NP[1] + 2.0) * e)
def walk_in(t):
    f = 1 + t * (WALK_END - 1)
    x, y = her_xy(f)
    x2, y2 = her_xy(min(WALK_END, f + 1))
    h = math.pi + math.atan2(-(x2 - x), max(1e-4, y2 - y))
    return (x, y, floor_z(x, y), h)
def walk_pair(p0, p1):
    pts = kit.plan_path(p0, p1, cliff_set.OBSTACLES)
    print("path", p0, "->", p1, "via", len(pts), "points:", pts)
    return kit.path_fn_from_points(pts, floor_z, ease_end=False)
nhead = math.pi + math.atan2(-(OP[0] - NP[0]), OP[1] - NP[1])      # she faces him
ohead = math.pi + math.atan2(-(NP[0] - OP[0]), NP[1] - OP[1])      # he faces her
osea = math.pi + math.atan2(-(EDGE[0] - OP[0]), EDGE[1] - OP[1])   # he faces the sea
kit.apply_walk(nrig, walk_in, 1, WALK_END, fps=FPS, stride_hz=1.2)
# the acting: speakers gesture on their lines, listeners react
o_g, n_g = [], []
for i, (L, f0) in enumerate(zip(lines, starts)):
    fmid = f0 + L["frames"] // 2
    fend = f0 + L["frames"]
    if L["who"] == "oisin":
        o_g.append((f0 + 6, fmid + 8, "lean_in" if i == 2 else "nod"))
        n_g.append((fend - 10, fend + 12, "look_away" if i == 2 else "nod"))
    else:
        n_g.append((f0 + 6, fmid + 8, "hand_raise" if i == 3 else "shake" if i == 1 else "nod"))
        o_g.append((fend - 10, fend + 12, "nod"))
    n_g.append((fend + 2, fend + 18, "weight_shift"))
kit.apply_idle(orig, 1, WALK_END, (OP[0], OP[1], floor_z(*OP)), osea, fps=FPS,
               look_at_fn=lambda f: EDGE, gestures=[])
kit.apply_idle(orig, WALK_END + 1, WALK2_START - 1, (OP[0], OP[1], floor_z(*OP)), ohead, fps=FPS,
               look_at_fn=lambda f: NP, gestures=o_g)
kit.apply_idle(nrig, WALK_END + 1, WALK2_START - 1, (NP[0], NP[1], floor_z(*NP)),
               nhead, fps=FPS, look_at_fn=lambda f: OP, gestures=n_g)
# the leaving: he walks east along the edge toward the way down; she stays and watches
kit.apply_walk(orig, walk_pair(OP, (14.0, 18.2)), WALK2_START, FRAMES, fps=FPS, stride_hz=1.15)
kit.apply_idle(nrig, WALK2_START, FRAMES, (NP[0], NP[1], floor_z(*NP)), nhead, fps=FPS,
               look_at_fn=lambda f: (OP[0] + (14.0 - OP[0]) * (f - WALK2_START) / max(1, FRAMES - WALK2_START), 18.0),
               gestures=[])
# faces: baseline closed+blinks over everything, then the lines
rigs = {"oisin": (orig, octrl), "niamh": (nrig, nctrl)}
for who, (r, fc) in rigs.items():
    kit.apply_talk_tex(r, fc, [0.0] * FRAMES, 1, fps=FPS)
for L, f0 in zip(lines, starts):
    # FILM_VIS_SUFFIX / FILM_ENV_SUFFIX (e.g. "_lam") select alternative
    # per-line viseme/envelope arrays for A/Bs; fall back to the plain ones
    VS, ES = os.environ.get("FILM_VIS_SUFFIX", ""), os.environ.get("FILM_ENV_SUFFIX", "")
    env_p = pathlib.Path(f"{audio_dir}/l{L['i']}_env{ES}.npy")
    env = np.load(env_p if env_p.exists() else f"{audio_dir}/l{L['i']}_env.npy")
    vis_p = pathlib.Path(f"{audio_dir}/l{L['i']}_vis{VS}.npy")
    if not vis_p.exists():
        vis_p = pathlib.Path(f"{audio_dir}/l{L['i']}_vis.npy")
    vis = np.load(vis_p) if vis_p.exists() else None
    r, fc = rigs[L["who"]]
    kit.apply_talk_tex(r, fc, env, f0, fps=FPS, blinks=False, visemes=vis)
    # FILM_BLINK=lam: real blink EVENTS from the LAM curves replace the fixed
    # cadence during the line (l<i>_blink_lam.npy, 1 = lids closed)
    bl_p = pathlib.Path(f"{audio_dir}/l{L['i']}_blink_lam.npy")
    if os.environ.get("FILM_BLINK", "") == "lam" and bl_p.exists():
        bl = np.load(bl_p)
        for k, on in enumerate(bl):
            fc["blink"].default_value = 1.0 if on else 0.0
            fc["blink"].keyframe_insert("default_value", frame=f0 + k)

# ── the edit, as data ────────────────────────────────────────────────
Z = cliff_set.FLOOR_Z
def _c(cam, tgt, lens):
    return {"cam": "%.2f,%.2f,%.2f" % (cam[0], cam[1], Z + cam[2]), "tgt": "%.2f,%.2f,%.2f" % (tgt[0], tgt[1], Z + tgt[2]), "lens": lens}
CLOSE_N = _c((0.88, 17.90, 1.62), (0.40, 16.20, 1.57), 55)     # 3/4 front, cliff edge behind her
CLOSE_O = _c((1.52, 15.82, 1.62), (2.00, 17.50, 1.57), 55)     # 3/4 front, the sea behind him
TWO = _c((6.0, 14.0, 1.45), (1.0, 17.0, 1.35), 50)
shots = [
    {"name": "s01_est", "f0": 1, "f1": 110, **_c((-30, 44, -1.5), (2, 17, 0.4), 30), "move": "orbit:16"},   # from over the sea: cliff face, the pair small on top
    {"name": "s02_walk", "f0": 111, "f1": 196, **_c((-5.5, 4.0, 1.3), (0, 8, 1.2), 42), "move": "pan"},
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
                      "move": "static", **(CLOSE_O if L["who"] == "niamh" else CLOSE_N)})
    else:
        shots.append({"name": f"s0{4+i}", "f0": j, "f1": f1, **_push(c)})
    if i == 2:                       # the silent beat, held wide
        shots.append({"name": "s07_beat", "f0": f1 + 1,
                      "f1": f1 + BEAT_MID, **_c((-6.0, 12.0, 1.5), (1.0, 17.0, 1.4), 40), "move": "static"})
shots.append({"name": "s10_beat", "f0": shots[-1]["f1"] + 1,
              "f1": WALK2_START - 1, "move": "static", **TWO})
shots.append({"name": "s11_away", "f0": WALK2_START, "f1": FRAMES,
              **_c((-3.0, 14.0, 1.5), (8.0, 18.0, 1.4), 32), "move": "crane:2.4"})
json.dump({"fps": FPS, "frames": FRAMES,
           "line_starts": starts, "shots": shots},
          open(shots_out, "w"), indent=1)

bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("FILM SCENE SAVED", FRAMES, "frames,", len(shots), "shots")
