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
import pathlib
import sys
import bpy
import numpy as np

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import valley_set                                              # noqa: E402
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

NP = (-1.55, 8.0)
OP = (0.15, 6.9)


def floor_z(x, y):
    if bpy.data.objects.get("painter_cam"): return 0.0     # painted world: the floor is flat (the plate paints the relief)
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
if os.environ.get("SET_DRESS", "0" if bpy.data.objects.get("painter_cam") else "1") != "0":   # painted world: the plate IS the dressing
    set_assets.dress_valley(sc, floor_z if 'floor_z' in dir() else (lambda x, y: 0.0))

MS = os.environ.get("FILM_MESH_SUFFIX", "")   # _retopo = the clean, re-skinned cast
CAST = os.environ.get("FILM_CAST", "mv")     # mv = Hunyuan-mv meshes, cg = CharacterGen meshes (Day-2 verdict)
RIGIFY_ACTOR = None
if os.environ.get("FILM_RIG", "numpy") == "rigify":
    # BENCHMARK (23 Sep): Oisin as the Rigify-fitted chibi, dropped into the SAME staging,
    # shots and set as the 3 Sep film. Niamh stays on the kit rig. The rig and mesh are
    # appended from the .blend rigify_fit wrote, drivers intact.
    import rigify_anim
    RB = os.environ.get("FILM_RIGIFY_BLEND", "/workspace/loopwork/rigify/chibi_face.blend")
    with bpy.data.libraries.load(RB, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in ("rig", "hero")]
    for ob in dst.objects:
        if ob is not None:
            sc.collection.objects.link(ob)
    orig = bpy.data.objects["rig"]; oisin = bpy.data.objects["hero"]
    orig.name = "oisin_rigify"; oisin.name = "oisin_mv"          # the film's shot data expects oisin_mv
    RIGIFY_ACTOR = rigify_anim.RigifyActor(orig, oisin, fps=FPS)
    print("RIGIFY cast appended from", RB, "height %.2f" % RIGIFY_ACTOR.H, flush=True)
    niamh = kit.load_character(f"{MESHES}/props/niamh_mv_painted.glb", "niamh_mv", height=1.68)
    nrig = kit.rig_character(niamh, "niamh_mv")
elif os.environ.get("FILM_RIG", "numpy") == "unirig":
    # Day-5: UniRig-skinned cast (real skeletons + skin weights), same animators
    ON, NN = ("cg_oisin", "cg_niamh") if CAST == "cg" else ("oisin_mv", "niamh_mv")
    oisin, orig = kit.load_rigged_character(f"{MESHES}/props/{ON}{MS}_rigged.glb", ON, height=1.75)
    niamh, nrig = kit.load_rigged_character(f"{MESHES}/props/{NN}{MS}_rigged.glb", NN, height=1.68, skirt=True)
else:
    oisin = kit.load_character(f"{MESHES}/props/oisin_mv_painted.glb", "oisin_mv")
    orig = kit.rig_character(oisin, "oisin_mv")
    niamh = kit.load_character(f"{MESHES}/props/niamh_mv_painted.glb", "niamh_mv", height=1.68)
    nrig = kit.rig_character(niamh, "niamh_mv")
FS = os.environ.get("FILM_FACE_SUFFIX", "")     # e.g. _flat -> <name>_flat_face_*.png (flattened palette A/B)
octrl = kit.enable_face_variants(oisin, os.environ.get("FILM_RIGIFY_FACE", "cand_chibi_kit") if RIGIFY_ACTOR else oisin.name + FS, f"{MESHES}/props")
nctrl = kit.enable_face_variants(niamh, niamh.name + FS, f"{MESHES}/props")

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

if RIGIFY_ACTOR:
    RIGIFY_ACTOR.walk(1, WALK_END, walk_in)
else:
    kit.apply_walk(orig, walk_in, 1, WALK_END, fps=FPS)
# the acting: speakers gesture on their lines, listeners react
o_g, n_g = [], []
for i, (L, f0) in enumerate(zip(lines, starts)):
    fmid = f0 + L["frames"] // 2
    fend = f0 + L["frames"]
    if L["who"] == "niamh":
        n_g.append((f0 + 6, fmid + 8, "hand_raise" if i == 0 else "shake"
                    if i == 2 else "nod"))
        o_g.append((fend - 10, fend + 12, "nod"))
    else:
        o_g.append((f0 + 6, fmid + 8, "lean_in" if i == 3 else "nod"))
        n_g.append((fend - 10, fend + 12, "nod" if i == 1 else "look_away"))
    o_g.append((fend + 2, fend + 18, "weight_shift"))
if RIGIFY_ACTOR:
    RIGIFY_ACTOR.idle(WALK_END + 1, WALK2_START - 1, (OP[0], OP[1], floor_z(*OP)), ohead,
                      gestures=o_g, look_at_fn=lambda f: NP)
else:
    kit.apply_idle(orig, WALK_END + 1, WALK2_START - 1,
                   (OP[0], OP[1], floor_z(*OP)), ohead, fps=FPS,
                   look_at_fn=lambda f: NP, gestures=o_g)
kit.apply_idle(nrig, 1, WALK2_START - 1, (NP[0], NP[1], floor_z(*NP)),
               nhead, fps=FPS, look_at_fn=lambda f: his_xy(f), gestures=n_g)
if RIGIFY_ACTOR:
    RIGIFY_ACTOR.walk(WALK2_START, FRAMES, walk_pair(OP, (6.6, 16.5)))
else:
    kit.apply_walk(orig, walk_pair(OP, (6.6, 16.5)), WALK2_START, FRAMES,   # up the path toward the hall, clear of the painted lake
                   fps=FPS, stride_hz=1.15)
kit.apply_walk(nrig, walk_pair(NP, (5.0, 17.3)), WALK2_START, FRAMES,
               fps=FPS, stride_hz=1.2)

# faces: baseline closed+blinks over everything, then the lines
rigs = {"oisin": (orig, octrl), "niamh": (nrig, nctrl)}


def talk_tex(r, fc, env, f0, blinks=True, visemes=None):
    """apply_talk_tex for either rig: the kit's version keys pb['jaw'], the Rigify rig
    has jaw_master instead."""
    if r is orig and RIGIFY_ACTOR:
        keys = ("m1", "m2", "m3", "m4", "m5")
        for i, a in enumerate(env):
            f = f0 + i
            col = int(visemes[i]) if visemes is not None and i < len(visemes) else 0
            sel = None if col == 0 else "m%d" % col
            if visemes is None:
                a = float(a); sel = None if a < 0.04 else "m1" if a < 0.25 else "m2" if a < 0.48 else "m3" if a < 0.72 else "m4"
            for k in keys:
                fc[k].default_value = 1.0 if k == sel else 0.0; fc[k].keyframe_insert("default_value", frame=f)
        RIGIFY_ACTOR.talk(f0, [min(1.0, float(a)) for a in env])
        if blinks:
            fc["blink"].default_value = 0.0; fc["blink"].keyframe_insert("default_value", frame=f0)
            for t0 in np.arange(f0 + 11, f0 + len(env), 3.4 * FPS):
                b = int(t0)
                for f, on in ((b - 1, 0.0), (b, 1.0), (b + 1, 1.0), (b + 2, 0.0)):
                    fc["blink"].default_value = on; fc["blink"].keyframe_insert("default_value", frame=f)
        nt = fc["_tree"]
        if nt.animation_data and nt.animation_data.action:
            for fcu in nt.animation_data.action.fcurves:
                for kp in fcu.keyframe_points:
                    kp.interpolation = 'CONSTANT'
    else:
        kit.apply_talk_tex(r, fc, env, f0, fps=FPS, blinks=blinks, visemes=visemes)


for who, (r, fc) in rigs.items():
    talk_tex(r, fc, [0.0] * FRAMES, 1)
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
    talk_tex(r, fc, env, f0, blinks=False, visemes=vis)
    # FILM_BLINK=lam: real blink EVENTS from the LAM curves replace the fixed
    # cadence during the line (l<i>_blink_lam.npy, 1 = lids closed)
    bl_p = pathlib.Path(f"{audio_dir}/l{L['i']}_blink_lam.npy")
    if os.environ.get("FILM_BLINK", "") == "lam" and bl_p.exists():
        bl = np.load(bl_p)
        for k, on in enumerate(bl):
            fc["blink"].default_value = 1.0 if on else 0.0
            fc["blink"].keyframe_insert("default_value", frame=f0 + k)

# ── the edit, as data ────────────────────────────────────────────────
CLOSE_N = {"cam": "1.2,6.85,1.8", "tgt": "-1.55,8.05,1.45", "lens": 45}
CLOSE_O = {"cam": "-2.0,7.4,1.62", "tgt": "0.0,6.95,1.57", "lens": 55}   # 3/4 front on his real head position (was a profile aimed at a stale point)
if RIGIFY_ACTOR:
    _k = RIGIFY_ACTOR.H / 1.75                                      # the chibi's head sits lower
    CLOSE_O = {"cam": "-2.0,7.4,%.2f" % (1.62 * _k), "tgt": "0.0,6.95,%.2f" % (1.57 * _k), "lens": 55}
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
