#!/usr/bin/env python3
"""
THE IMPROVEMENT LOOP (v2). Called by the GPU keeper whenever the queue is empty; writes
exactly one job, so the card never idles -- and every job must be able to CHANGE something.

v1 rotated the same sweeps forever: 131 walk sweeps that scored identically (the slide
metric was never measured), 88 copies of the same A/B sheets, and a cast search that
re-evaluated the same candidates hourly. Two days of a busy card and nothing moved.

v2 rules
  - every experiment is keyed on the inputs it depends on (walk defaults, adopted cast,
    adopted plate, scene defaults). Once run for those inputs it is SETTLED and not run
    again until an input changes.
  - walk knobs REFINE: the sweep narrows around the current value until the step is below
    its minimum or the score shows no signal; then the knob is settled.
  - substantive work comes first: a face rig for a newly adopted cast, the geometry-first
    plate (scored by depth agreement), scene fit (scored by foot float and on-path time),
    a master re-render whenever anything was adopted (with the scene-fit audit on the result).
  - the open-ended cast search is the fallback, with fresh seeds, when everything is settled.
  - review/IMPROVE_STATUS.md is rewritten after every job: adopted, settled, duty cycle.

State: /workspace/loopwork/improve/state.json   Ledger: review/IMPROVE_LEDGER.md
"""
import json, os, sys, time, random, hashlib, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

W = "/workspace/loopwork"; Q = W + "/queue"; ST = W + "/improve/state.json"
REPO = "/workspace/text-to-video"; R = "/workspace/review"; RG = W + "/rigify"
P = "series/tir-na-nog-legend/meshes/props"
os.makedirs(W + "/improve", exist_ok=True)
st = json.load(open(ST)) if os.path.exists(ST) else {}
for k, v in {"cycle": 0, "defaults_ver": 0, "masters_ver": "", "plate_ver": 0, "plate_rounds": 0, "memo": {}, "knobs": {},
             "adopted": {"oisin": ["st_chibi3_oisin_m7302", 0.73], "niamh": ["st_chibi3_niamh_m7302", 0.74]}}.items():
    st.setdefault(k, v)
st["cycle"] += 1

def env_file(p):
    d = {}
    if os.path.exists(p):
        for l in open(p):
            if "=" in l and not l.startswith("#"): k, v = l.strip().split("=", 1); d[k] = v
    return d
walk_def = env_file(REPO + "/configs/walk_defaults.env"); scene_def = env_file(REPO + "/configs/scene_defaults.env")
def rstrip_tex(n): return n[:-4] if n.endswith("_tex") else n     # the textured glb's name; rigs and faces carry the base name
ao, an = rstrip_tex(st["adopted"]["oisin"][0]), rstrip_tex(st["adopted"]["niamh"][0])
scene_sig = hashlib.md5(json.dumps(scene_def, sort_keys=True).encode()).hexdigest()[:6]
inputs_ver = "d%d|%s|%s|p%d|s%s" % (st["defaults_ver"], ao, an, st["plate_ver"], scene_sig)
st["inputs_ver"] = inputs_ver
short = hashlib.md5(inputs_ver.encode()).hexdigest()[:6]

def fresh(key, ver=None): return st["memo"].get(key, {}).get("ver") != (ver or inputs_ver)
def mark(key, ver=None, result="queued"): st["memo"][key] = {"ver": ver or inputs_ver, "result": result, "at": time.strftime("%F %H:%M")}

def cast_env():
    """FILM_RIGIFY_O/N for the adopted cast when their face rigs exist; the film loader's
    defaults (oisin4/niamh4) otherwise."""
    e = []
    for who, name in (("O", ao), ("N", an)):
        if os.path.exists("%s/%s_face.blend" % (RG, name)): e.append("FILM_RIGIFY_%s=%s/%s_face.blend" % (who, RG, name))
    return " ".join(e)
HEAD = ("cd %s\nset -a; . configs/walk_defaults.env; [ -f configs/scene_defaults.env ] && . configs/scene_defaults.env; set +a\n"
        "LEDGER=%s/IMPROVE_LEDGER.md; export %s\n" % (REPO, R, cast_env() or "IMPROVE_CYCLE=%d" % st["cycle"]))
TAIL = "\n/workspace/venv/bin/python scripts/ops/improve_status.py > /dev/null 2>&1\nbash /workspace/export_outcomes.sh 2>&1 | tail -1\n"
MASTER_ENV = ('export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=4.8 FILM_LINE_MINLEN=40 FILM_LINE_CREASE=0 FILM_RES=1664x960 '
              'FILM_INTEGRATE=0.22 CHAR_HAZE_SAT=0.3 FILM_CONTACT=1 SET_SUN="52,118" FILM_LINE_TINT="0.14,0.09,0.12" FILM_LINE_ALPHA=0.82 CHAR_AO=0.35 FILM_STEP_ANIM=2 FILM_FILL=0.6')
BUILD_ENV = "CHAR_NORMALFIX=0 FILM_RIG=rigify FILM_BLINK=lam FILM_VIS_SUFFIX=_lam FILM_ENV_SUFFIX=_lam"
PROBES = ('"s02_walk -4.2,0.5,1.3 0,2,1.2 42 160 pan" "s03_meet 5.5,7.6,1.45 -0.8,7.5,1.35 50 221 static" "s11_away 0.2,2.8,1.5 3.6,15.5,1.6 32 1150 crane:2.6"')


def x_cast_face():
    """A newly adopted cast member has a body rig but no face rig: build it (the film
    loader needs <name>_face.blend and the cand_<name>_kit face variants) before anything
    downstream can use the adoption."""
    for name in (ao, an):
        if os.path.exists("%s/%s.blend" % (RG, name)) and not os.path.exists("%s/%s_face.blend" % (RG, name)) and fresh("cast_face_" + name, name):
            mark("cast_face_" + name, name)
            lip = "0.45,0.30,0.16" if "oisin" in name else "0.62,0.30,0.30"
            return "cast_face", HEAD + """
# cast_face: face rig + painted visemes for the adopted %s
C=%s; P=%s; RG=%s; B=/workspace/blender42/blender
[ -s $P/cand_${C}_retopo.glb ] || exit 0
RF_FACE=1 $B -b --python scripts/blender3d/rigify_fit.py -- $P/cand_${C}_retopo.glb $RG/${C}_face 1.6 || exit 0
FCG_EYE=0.44 FCG_MOUTH=${FCG_MOUTH:-0.195} FCG_EYEX=0.40 $B -b --factory-startup --python scripts/blender3d/face_calib_geom.py -- $P/cand_${C}_retopo.glb 1.6 $P/cand_${C}_kit_face.json
CHAR_NORMALFIX=0 FP_MOUTH_PLATE=${FP_MOUTH_PLATE:-1.5} $B -b --factory-startup --python scripts/blender3d/face_paint.py -- --keep-eyes $P/cand_${C}_retopo.glb $P/cand_${C}_kit_face.json 1.6 $P cand_${C}_kit "%s"
A=/workspace/loopwork/film_audio; rm -rf $RG/face_cand_${C}_kit
RT_RES=720 RT_FRAMES=40 RT_HEAD=0.74 RT_LENS=85 $B -b $RG/${C}_face.blend --python scripts/blender3d/rigify_talk.py -- /workspace/loopwork/day3/film_audio/l0.json $A/l0_vis_lam.npy $A/l0_blink_lam.npy $A/l0.wav $P cand_${C}_kit $RG/face_cand_${C}_kit > /dev/null 2>&1
N=$(ls $RG/face_cand_${C}_kit/t_*.png 2>/dev/null | wc -l)
echo "- $(date +%%F\\ %%H:%%M) cast_face: $C face rig $([ -s $RG/${C}_face.blend ] && echo built || echo FAILED), talk probe $N frames" >> $LEDGER
""" % (name, name, P, RG, lip)
    return None


def x_plate_flux():
    """Geometry-first plate, FLUX route, for each painted set (valley, winter valley, cliff):
    three denoise levels x three ControlNet strengths per round, scored by ground-band depth
    agreement AND CLIP style against that set's own look; adopted into configs/scene_defaults.env
    only if it beats the old plate's geometry while passing the style gate. Three rounds per set."""
    U = REPO + "/ComfyUI/models/unet/flux1-dev-Q8_0.gguf"; C = REPO + "/ComfyUI/models/controlnet/flux_union_pro2.safetensors"
    if not (os.path.exists(U) and os.path.getsize(U) > 12e9 and os.path.exists(C) and os.path.getsize(C) > 3e9): return None
    from improve_sets import SETS, PROMPTS
    for name, cfg in SETS.items():
        if not (os.path.exists(cfg["guide"]) and os.path.exists(REPO + "/ComfyUI/input/" + cfg["init"])): continue
        rk = "flux_rounds" if name == "valley" else "flux_rounds_" + name
        rnd = st.get(rk, 0)
        if rnd >= 3: continue
        st[rk] = rnd + 1; mark("plate_flux_%s_r%d" % (name, rnd), "g2")
        stem = "r%d_cn" % (10 + rnd) if name == "valley" else "r%d_%s_cn" % (10 + rnd, name)
        return "plate_flux", HEAD + """
# plate_flux %s round %d: FLUX-dev + depth ControlNet, 9 plates, ground agreement + style scored
curl -s -m 10 -X POST http://127.0.0.1:8188/free -H 'Content-Type: application/json' -d '{"unload_models": true, "free_memory": true}' >/dev/null 2>&1; sleep 4
for CN in 0.5 0.7 0.9; do
  PG_PROMPT=%s PF_CN=$CN PF_SEED=%d PF_GUIDE=%s PF_GUIDE_COMFY=%s PF_INIT_COMFY=%s PF_STYLE_REF=%s /workspace/venv/bin/python scripts/blender3d/plate_flux_depth.py /workspace/loopwork/geo/%s${CN}_flux 0.6 0.75 0.9 2>&1 | grep -E "^PF agreement|Traceback|Error"
done
/workspace/venv/bin/python scripts/ops/improve_score.py plate_geo %d %s
""" % (name, rnd, json.dumps(PROMPTS[name]), 6100 + rnd * 7, cfg["guide"], cfg["comfy_guide"], cfg["init"], cfg["style_ref"], stem, 10 + rnd, name)
    return None


def x_plate_shots():
    """SETUPS REVIEW-ONLY (9 Oct): adopted side/closer plates kept drifting the hall (green block,
    gothic gold, a white disc) at style scores the gate accepted; the master plate projected from
    every shot camera is consistent. Candidates are still generated to review/SETUPS_candidates
    for a human pick, never adopted -- the scorer is called in review mode.
    Per-shot setups (side, reverse, closer) of each adopted master plate: the renderer swaps
    them in by shot heading, so every angle of a place must be the same place. Each is painted
    from its own geometry guide, img2img from the setup's init, style-judged against the set's
    adopted master. Two rounds per master; seeds move with the plate version so a redo gives new
    candidates. Valley setups are <setup>_geo, winter ones <setup>_winter_geo (film.py's naming)."""
    from improve_sets import PROMPTS
    S = REPO + "/series/tir-na-nog-legend/sets/tir_na_nog/"
    for c in ("side", "reverse", "closer"):
        if not os.path.exists(W + "/geo/valley2_%s_depth.png" % c): return None
    for setname, master, suffix in (("valley", S + "master_geo.png", "_geo"), ("winter", S + "master_winter_geo.png", "_winter_geo")):
        if not os.path.exists(master): continue
        mver = hashlib.md5(open(master, "rb").read(65536)).hexdigest()[:8]
        rk = "shots_rounds" if setname == "valley" else "shots_rounds_winter"
        if st.get(rk + "_for") != mver: st[rk] = 0; st[rk + "_for"] = mver        # a new master: redo its setups
        rnd = st.get(rk, 0)
        if rnd >= 1: continue                                   # one round of candidates per master is enough for a pick
        st[rk] = rnd + 1; mark("plate_shots_%s_%s_r%d" % (setname, mver, rnd), "g2")
        seed = 7100 + rnd * 11 + st["plate_ver"] * 101
        body = HEAD + "# plate_shots %s round %d: side / reverse / closer painted from their own geometry guides\n" % (setname, rnd)
        body += "curl -s -m 10 -X POST http://127.0.0.1:8188/free -H 'Content-Type: application/json' -d '{\"unload_models\": true, \"free_memory\": true}' >/dev/null 2>&1; sleep 4\n"
        for c in ("side", "reverse", "closer"):
            init = "geo_init_%s.png" % c if setname == "valley" else "geo_init_winter.png"
            body += ("for CN in 0.6 0.8; do PG_PROMPT=%s PF_CN=$CN PF_SEED=%d PF_GUIDE=/workspace/loopwork/geo/valley2_%s_depth.png PF_GUIDE_COMFY=geo_depth2_%s.png PF_INIT_COMFY=%s "
                     "PF_STYLE_REF=%s /workspace/venv/bin/python scripts/blender3d/plate_flux_depth.py "
                     "/workspace/loopwork/geo/ps%d_%s%s_cn${CN} 0.55 0.7 2>&1 | grep -E '^PF agreement|Traceback|Error'; done\n") % (json.dumps(PROMPTS[setname]), seed, c, c, init, master, rnd, c, suffix, )
        body += "PS_REVIEW_ONLY=1 /workspace/venv/bin/python scripts/ops/improve_score.py plate_shots %d %s\n" % (rnd, suffix)
        return "plate_shots", body
    return None


def x_plate_hires():
    """Refine every adopted plate at 2016x1152 (FLUX img2img, low denoise, depth held): the
    projector's _4x must out-resolve a 1664x960 frame, and a Lanczos upscale of 1344x768 does
    not. Once per adopted plate; scored on sharpness with the picture held (style >= 0.95)."""
    from improve_sets import SETS, PROMPTS
    S = REPO + "/series/tir-na-nog-legend/sets/"
    targets = []
    if "SET_PLATE" in scene_def:
        targets.append(("valley_master", scene_def["SET_PLATE"], W + "/geo/valley2_depth.png", "valley"))
        for c in ("side", "reverse", "closer"):
            if os.path.exists(S + "tir_na_nog/%s_geo.png" % c): targets.append(("valley_" + c, S + "tir_na_nog/%s_geo.png" % c, W + "/geo/valley2_%s_depth.png" % c, "valley"))
    if "SET_PLATE_WINTER" in scene_def: targets.append(("winter_master", scene_def["SET_PLATE_WINTER"], W + "/geo/valley2_depth.png", "winter"))
    if "SET_PLATE_CLIFF" in scene_def: targets.append(("cliff_master", scene_def["SET_PLATE_CLIFF"], W + "/geo/cliff2_depth.png", "cliff"))
    for tag, plate, guide, setname in targets:
        key = "plate_hires_" + tag; ver = hashlib.md5(open(plate, "rb").read(65536)).hexdigest()[:8]
        if not fresh(key, ver): continue
        mark(key, ver)
        return "plate_hires", HEAD + """
# plate_hires %s: refine the adopted plate at 2016x1152, depth held, picture held
curl -s -m 10 -X POST http://127.0.0.1:8188/free -H 'Content-Type: application/json' -d '{"unload_models": true, "free_memory": true}' >/dev/null 2>&1; sleep 4
PG_PROMPT=%s PF_W=2016 PF_H=1152 PF_CN=0.5 PF_END=0.5 PF_STEPS=20 PF_SEED=6177 PF_GUIDE=%s PF_INIT_PATH=%s PF_STYLE_REF=%s /workspace/venv/bin/python scripts/blender3d/plate_flux_depth.py /workspace/loopwork/geo/hr_%s_cn0.5 0.25 0.35 0.45 2>&1 | grep -E "^PF agreement|Traceback|Error"
/workspace/venv/bin/python scripts/ops/improve_score.py plate_hires %s %s
""" % (tag, json.dumps(PROMPTS[setname]), guide, plate, plate, tag, tag, plate)
    return None


def x_plate_geo():
    """Geometry-first plate: paint the valley conditioned on the real set's depth, three
    strengths x three ControlNet weights per round, scored by Depth-Anything agreement with
    the geometry. Three rounds (fresh seeds), then settled until the geometry changes."""
    if st["plate_rounds"] >= 3 or not os.path.exists(W + "/geo/valley_depth.png"): return None
    rnd = st["plate_rounds"]; st["plate_rounds"] += 1; mark("plate_geo_r%d" % rnd, "g1")
    return "plate_geo", HEAD + """
# plate_geo round %d: 9 plates, agreement-scored, best adopted as the candidate plate if it beats the old one
curl -s -m 10 -X POST http://127.0.0.1:8188/free -H 'Content-Type: application/json' -d '{"unload_models": true, "free_memory": true}' >/dev/null 2>&1; sleep 4
for CN in 0.6 0.8 1.0; do
  HF_HOME=/workspace/hf_cache PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True PG_CN=$CN PG_SEED=%d /workspace/venv/bin/python scripts/blender3d/plate_from_geometry.py \\
    /workspace/loopwork/geo/valley_depth.png series/tir-na-nog-legend/sets/tir_na_nog/master_4x.png /workspace/loopwork/geo/r%d_cn${CN} 0.55 0.75 0.9 2>&1 | grep -E "^PG agreement|Traceback|Error"
done
/workspace/venv/bin/python scripts/ops/improve_score.py plate_geo %d
""" % (rnd, 6100 + rnd * 7, rnd, rnd)


def x_scene_fit():
    """Scene fit per valley episode: build it at three relief gains with its plate and the
    cast, audit foot float and on-path time, adopt the best gain for THAT episode's key,
    render three probe shots. Keyed on cast + that episode's plate."""
    from improve_sets import EPISODES
    for ep in (1, 2):
        e = EPISODES[ep]; gk = e.get("gain", "SET_RELIEF_GAIN")
        sf_ver = "%s|%s|%s" % (ao, an, scene_def.get(e["plate"], "-"))
        if not fresh("scene_fit_ep%d" % ep, sf_ver): continue
        mark("scene_fit_ep%d" % ep, sf_ver)
        env = "unset SET_PLATE SET_RELIEF_NPY SET_RELIEF_GAIN; export IMPROVE_EP=%d " % ep + " ".join(
            (["SET_PLATE=%s" % scene_def[e["plate"]]] if e["plate"] in scene_def else []) +
            (["SET_RELIEF_NPY=%s" % scene_def[e["npy"]]] if e["npy"] and e["npy"] in scene_def else []))
        return "scene_fit", HEAD + """
# scene_fit episode %d @ %s: relief gain sweep, audited
W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender; EP=%d
%s
for G in 0.4 0.6 0.8; do
  %s SET_RELIEF_GAIN=$G $B -b --python scripts/blender3d/%s -- $W/%s $R/sf${EP}_g$G.blend $W/sf${EP}_shots_g$G.json < /dev/null > $W/improve/sf${EP}_build_g$G.log 2>&1
  grep -q "FILM SCENE SAVED" $W/improve/sf${EP}_build_g$G.log || continue
  $B -b $R/sf${EP}_g$G.blend --python scripts/blender3d/scene_fit_audit.py -- $W/sf${EP}_shots_g$G.json $W/improve/sf${EP}_audit_g$G > $W/improve/sf${EP}_g$G.txt 2>&1
done
/workspace/venv/bin/python scripts/ops/improve_score.py scene_fit %d %s $EP
BEST=$(cat $W/improve/sf${EP}_best 2>/dev/null); [ -n "$BEST" ] || exit 0
%s; export CHAR_NORMALFIX=0 FILM_LINES=2.4 FILM_LINE_MINLEN=20 FILM_RES=832x480
for S in %s; do set -- $S; rm -rf $W/improve/sfp${EP}_$1
  $B -b --factory-startup $R/sf${EP}_g$BEST.blend --python scripts/blender3d/film.py -- $W/improve/sfp${EP}_$1 "$2" "$3" $4 $5 $5 "$6" 832 480 < /dev/null > $W/improve/sfp${EP}_$1.log 2>&1 &
done; wait
/workspace/venv/bin/python - <<'EOF'
from PIL import Image, ImageDraw; import glob, os
ep = os.environ.get("IMPROVE_EP", "1")
ims=[Image.open(sorted(glob.glob('/workspace/loopwork/improve/sfp%%s_%%s/*.png'%%(ep,n)))[0]).convert('RGB') for n in ('s02_walk','s03_meet','s11_away') if glob.glob('/workspace/loopwork/improve/sfp%%s_%%s/*.png'%%(ep,n))]
if ims:
    w,h=ims[0].size; s=Image.new('RGB',(w*len(ims),h+24),'black'); [s.paste(im,(i*w,24)) for i,im in enumerate(ims)]
    ImageDraw.Draw(s).text((8,5),'scene fit ep%%s %s gain '%%ep+open('/workspace/loopwork/improve/sf%%s_best'%%ep).read().strip(),fill='white'); s.save('/workspace/review/SCENE_FIT_ep%%s_%s.png'%%ep)
EOF
cp $R/sf${EP}_g$BEST.blend $R/film${EP}_nw_loop.blend 2>/dev/null; [ "$EP" = 1 ] && cp $R/sf1_g$BEST.blend $R/film_nw_loop.blend
""" % (ep, sf_ver, ep, env, BUILD_ENV, e["script"], e["audio"], st["cycle"], gk, MASTER_ENV, PROBES, short, short)
    return None


def x_walk():
    """One knob, refined around the current value; the scorer narrows the step or settles it."""
    ranges = {"RW_STRIDE": (0.40, 0.76, 0.04, 0.01), "RW_DROP": (0.03, 0.10, 0.01, 0.0025), "RW_ARM_OUT": (2, 22, 4, 1)}
    for k, (lo, hi, step, mins) in ranges.items():
        kb = st["knobs"].setdefault(k, {"lo": lo, "hi": hi, "step": step, "min": mins, "done": False})
        if kb["done"] or not fresh("walk_" + k): continue
        cur = float(walk_def.get(k, (lo + hi) / 2)); s = kb["step"]
        vals = sorted(set(round(min(hi, max(lo, cur + i * s)), 4) for i in (-2, -1, 0, 1, 2)))
        mark("walk_" + k)
        return "walk", HEAD + """
# walk: refine %s around %s (step %s) on the benchmark rig; a win is adopted, no win halves the step
RG=/workspace/loopwork/rigify; B=$RG/oisin4.blend
OUT=/workspace/loopwork/improve/walk_%s_%d.txt; : > $OUT
for V in %s; do echo "== %s=$V ==" >> $OUT
  %s=$V /workspace/blender42/blender -b $B --python $RG/gate_metrics.py 2>&1 | grep -E "^(WM  *[0-9]+ |RW foot)" >> $OUT
done
/workspace/venv/bin/python scripts/ops/improve_score.py walk %s $OUT
""" % (k, cur, s, k, st["cycle"], " ".join("%g" % v for v in vals), k, k, k)
    return None


def x_ab(kind):
    knobs = {"craft": [("FILM_FILL", ["0", "0.6", "1.2"]), ("FILM_LINES", ["3.2", "4.8", "6.4"]), ("CHAR_AO", ["0", "0.35", "0.6"]), ("FILM_INTEGRATE", ["0", "0.22", "0.4"]), ("FILM_LINE_ALPHA", ["0.6", "0.82", "1.0"])],
             "face": [("FP_MOUTH_PLATE", ["1.2", "1.5", "1.9"]), ("FCG_MOUTH", ["0.17", "0.195", "0.22"])]}[kind]
    for k, vals in knobs:
        if not fresh("%s_%s" % (kind, k)): continue
        mark("%s_%s" % (kind, k))
        if kind == "craft":
            bl = R + "/film_nw_loop.blend" if os.path.exists(R + "/film_nw_loop.blend") else R + "/film_nw_rigify_cast4.blend"
            return "craft", HEAD + """
# craft: A/B %s on a close-up and a wide shot (once per input set)
BL=%s; [ -s $BL ] || exit 0
%s
for V in %s; do for S in "close -2.0,7.4,1.48 0.0,6.95,1.44 55 317" "ots 1.612,6.670,1.694 -1.550,8.050,1.326 42 300" "wide 5.5,7.6,1.45 -0.8,7.5,1.35 50 221"; do
  set -- $S; D=/workspace/loopwork/improve/craft_%s_${V}_$1; rm -rf $D
  %s=$V /workspace/blender42/blender -b --factory-startup $BL --python scripts/blender3d/film.py -- $D "$2" "$3" $4 $5 $5 static 1248 720 < /dev/null > $D.log 2>&1 &
done; done; wait
/workspace/venv/bin/python scripts/ops/improve_score.py craft %s "%s"
""" % (k, bl, MASTER_ENV, " ".join(vals), k, k, k, " ".join(vals))
        return "face", HEAD + """
# face: A/B %s on the lead's close-up, jaw-open frames (once per input set)
P=%s; RG=/workspace/loopwork/rigify; A=/workspace/loopwork/film_audio
for V in %s; do
  N=cand_oisin4_%s_${V//./}
  FCG_EYE=0.44 FCG_MOUTH=${FCG_MOUTH:-0.195} FCG_EYEX=0.40 %s=$V /workspace/blender42/blender -b --factory-startup --python scripts/blender3d/face_calib_geom.py -- $P/cand_oisin4_retopo.glb 1.6 $P/${N}_face.json > /dev/null 2>&1
  CHAR_NORMALFIX=0 FP_MOUTH_PLATE=${FP_MOUTH_PLATE:-1.5} %s=$V /workspace/blender42/blender -b --factory-startup --python scripts/blender3d/face_paint.py -- --keep-eyes $P/cand_oisin4_retopo.glb $P/${N}_face.json 1.6 $P $N "0.45,0.30,0.16" > /dev/null 2>&1
  rm -rf $RG/face_$N
  RT_RES=720 RT_FRAMES=40 RT_HEAD=0.74 RT_LENS=85 /workspace/blender42/blender -b $RG/oisin4_face.blend --python scripts/blender3d/rigify_talk.py -- /workspace/loopwork/day3/film_audio/l0.json $A/l0_vis_lam.npy $A/l0_blink_lam.npy $A/l0.wav $P $N $RG/face_$N > /dev/null 2>&1
done
/workspace/venv/bin/python scripts/ops/improve_score.py face %s "%s"
""" % (k, P, " ".join(vals), k, k, k, k, " ".join(vals))
    return None


def ep_inputs(ep):
    from improve_sets import EPISODES
    e = EPISODES[ep]
    keys = [e["plate"], e["npy"], e.get("gain", "SET_RELIEF_GAIN")]
    return "d%d|%s|%s|" % (st["defaults_ver"], ao, an) + "|".join("%s=%s" % (k, scene_def.get(k, "-")) for k in keys if k)


def x_episode():
    """Something was adopted since the last masters of an episode: re-render that episode with
    everything current, audit it, and record the numbers. Nothing is overwritten -- the output
    carries the inputs hash. Episode 1 first, then 2 and 3 (they take their own plates)."""
    from improve_sets import EPISODES
    masters = st.setdefault("masters", {})
    for ep in (1, 2, 3):
        e = EPISODES[ep]; iv = ep_inputs(ep)
        if masters.get(str(ep)) == iv: continue
        # an episode without a geometry plate of its own still re-renders when the cast or walk changed
        masters[str(ep)] = iv; st["masters_ver"] = iv
        h = hashlib.md5(iv.encode()).hexdigest()[:6]
        gk = e.get("gain", "SET_RELIEF_GAIN")
        env = "unset SET_PLATE SET_RELIEF_NPY SET_RELIEF_GAIN; export " + " ".join(
            (["SET_PLATE=%s" % scene_def[e["plate"]]] if e["plate"] in scene_def else []) +
            (["SET_RELIEF_NPY=%s" % scene_def[e["npy"]]] if e["npy"] and e["npy"] in scene_def else []) +
            (["SET_RELIEF_GAIN=%s" % scene_def[gk]] if gk in scene_def else []))
        return "episode", HEAD + """
# episode %d @ %s -> %s_loop_%s.mp4
W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender; H=%s; EPO=%s
%s
%s $B -b --python scripts/blender3d/%s -- $W/%s $R/film${EPO}_loop_$H.blend $W/film${EPO}_shots_loop_$H.json < /dev/null > $W/improve/ep%d_build_$H.log 2>&1
grep -q "FILM SCENE SAVED" $W/improve/ep%d_build_$H.log || { echo "- $(date +%%F\ %%H:%%M) episode %d @ $H: BUILD FAILED" >> $LEDGER; exit 0; }
$B -b $R/film${EPO}_loop_$H.blend --python scripts/blender3d/scene_fit_audit.py -- $W/film${EPO}_shots_loop_$H.json $W/improve/ep%d_audit_$H > $W/improve/ep%d_audit_$H.txt 2>&1 || true
%s; export SET_SUN="%s"
/workspace/venv/bin/python scripts/blender3d/shot_language.py $W/film${EPO}_shots_loop_$H.json $W/sl_film${EPO}_shots_loop_$H.json > /dev/null 2>&1
rm -rf $W/filmL${EPO}$H $W/filmL${EPO}$H.*.log
bash scripts/ops/render_episode.sh sl_film${EPO}_shots_loop_$H.json film${EPO}_loop_$H.blend filmL${EPO}$H "%s" %s $R/%s_loop_$H.mp4 6 > $W/improve/ep%d_render_$H.log 2>&1
[ -f $R/%s_loop_$H.mp4 ] && ffmpeg -v error -y -i $R/%s_loop_$H.mp4 -c:v libx264 -crf 23 -preset medium -pix_fmt yuv420p -c:a aac -movflags +faststart $R/%s_loop_${H}_web.mp4
rm -rf $W/filmL${EPO}$H
echo "- $(date +%%F\ %%H:%%M) episode %d @ $H (%s): $([ -f $R/%s_loop_${H}_web.mp4 ] && echo rendered %s_loop_${H}_web.mp4 || echo RENDER FAILED); $(grep -h '^SF' $W/improve/ep%d_audit_$H.txt | tr '\n' ';')" >> $LEDGER
""" % (ep, iv, e["out"], h, h, "" if ep == 1 else str(ep), env.rstrip(" export"), BUILD_ENV, e["script"], e["audio"], ep, ep, ep, ep, ep,
       MASTER_ENV, e["sun"], e["title"], e["audio"], e["out"], ep, e["out"], e["out"], e["out"], ep, iv, e["out"], e["out"], ep)
    return None


def x_cast():
    seed = 20000 + st["cycle"] * 10 + random.randint(0, 9)
    return "cast", HEAD + """
# cast (fallback search): three fresh candidates per lead, hands scored; auto-adopt on a clear win
P=%s; RG=/workspace/loopwork/rigify
for WHO in oisin niamh; do for K in 0 1 2; do
  SEED=$((%d + K)); TAG=${WHO}_m$SEED
  [ -s $P/st_chibi3_${TAG}.glb ] && continue
  POSE_MODE=apose OPEN_MOUTH=1 TEST_SEED=$SEED /workspace/venv/bin/python -u scripts/blender3d/style_test.py chibi3 $TAG 2>&1 | tail -1
  [ -s $P/st_chibi3_${TAG}.glb ] && /workspace/blender42/blender -b --factory-startup --python scripts/blender3d/mesh_turntable.py -- $P/st_chibi3_${TAG}.glb /workspace/review/library_${TAG}.png $TAG > /dev/null 2>&1
done; done
/workspace/venv/bin/python scripts/blender3d/pick_hands.py $P 'st_chibi3_*_m*.glb' > /workspace/review/hand_scores.txt 2>&1
/workspace/venv/bin/python scripts/ops/improve_score.py cast %d
""" % (P, seed, st["cycle"])


for fn in (x_cast_face, x_plate_flux, x_plate_shots, x_plate_hires, x_plate_geo, x_scene_fit, x_walk, x_episode, lambda: x_ab("craft"), lambda: x_ab("face"), x_cast):
    r = fn()
    if r: break
exp, body = r
json.dump(st, open(ST, "w"), indent=1)
job = "%s/90_improve_%s_%04d.sh" % (Q, exp, st["cycle"])
open(job, "w").write(body + TAIL)
print("IMPROVE wrote", os.path.basename(job), "inputs", inputs_ver)
