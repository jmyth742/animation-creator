#!/usr/bin/env python3
"""
THE IMPROVEMENT LOOP. Called by the GPU keeper whenever the queue is empty; writes exactly
one job into the queue, so the card is never idle, and every job is an experiment whose
result is recorded in review/IMPROVE_LEDGER.md. Experiments rotate and never run out:
the generative ones take a fresh seed each cycle, the sweeps refine their step.

Experiments
  cast       three new lead candidates, hands scored by geometry; a candidate that beats
             the adopted cast by 10% is retopologised, rigged and gated automatically
  walk       one walk parameter perturbed on the benchmark rig, scored on slide/knee/reach;
             a win is written to configs/walk_defaults.env
  craft      one render variable (line width, AO, haze, line alpha) A/B on a fixed
             close-up and wide shot; sheet for a human pick, logged
  face       mouth plate / lip colour A/B on the close-up; sheet, logged
  episode    when walk defaults changed since the last masters, re-render episode 1

State in /workspace/loopwork/improve/state.json.
"""
import json, os, sys, time, random

W = "/workspace/loopwork"; Q = W + "/queue"; ST = W + "/improve/state.json"
REPO = "/workspace/text-to-video"; R = "/workspace/review"
os.makedirs(W + "/improve", exist_ok=True)
st = json.load(open(ST)) if os.path.exists(ST) else {"cycle": 0, "walk_i": 0, "craft_i": 0, "face_i": 0, "defaults_ver": 0, "masters_ver": 0}
ORDER = ["cast", "walk", "craft", "walk", "face", "cast", "walk", "episode"]
exp = ORDER[st["cycle"] % len(ORDER)]
st["cycle"] += 1
HEAD = "cd %s\nset -a; . configs/walk_defaults.env; set +a\nLEDGER=%s/IMPROVE_LEDGER.md\n" % (REPO, R)
TAIL = "\nbash /workspace/export_outcomes.sh 2>&1 | tail -1\n"

if exp == "cast":
    seed = 20000 + st["cycle"] * 10 + random.randint(0, 9)
    body = HEAD + """
# cast: three fresh candidates per lead, hands scored; auto-adopt on a clear win
P=series/tir-na-nog-legend/meshes/props; RG=/workspace/loopwork/rigify
for WHO in oisin niamh; do for K in 0 1 2; do
  SEED=$((%d + K)); TAG=${WHO}_m$SEED
  [ -s $P/st_chibi3_${TAG}.glb ] && continue
  POSE_MODE=apose OPEN_MOUTH=1 TEST_SEED=$SEED /workspace/venv/bin/python -u scripts/blender3d/style_test.py chibi3 $TAG 2>&1 | tail -1
  [ -s $P/st_chibi3_${TAG}.glb ] && /workspace/blender42/blender -b --factory-startup --python scripts/blender3d/mesh_turntable.py -- $P/st_chibi3_${TAG}.glb /workspace/review/library_${TAG}.png $TAG > /dev/null 2>&1
done; done
/workspace/venv/bin/python scripts/blender3d/pick_hands.py $P 'st_chibi3_*_m*.glb' > /workspace/review/hand_scores.txt 2>&1
/workspace/venv/bin/python scripts/ops/improve_score.py cast %d
""" % (seed, st["cycle"])
elif exp == "walk":
    knobs = [("RW_STRIDE", [0.50, 0.53, 0.56, 0.60, 0.64]), ("RW_DROP", [0.045, 0.055, 0.062, 0.070, 0.080]), ("RW_ARM_OUT", [6, 10, 14, 18])]
    k, vals = knobs[st["walk_i"] % len(knobs)]; st["walk_i"] += 1
    body = HEAD + """
# walk: sweep %s on the benchmark rig, measured, adopt a win into configs/walk_defaults.env
RG=/workspace/loopwork/rigify; B=$RG/oisin4.blend; [ -s $B ] || B=$RG/chibi.blend
OUT=/workspace/loopwork/improve/walk_%s_%d.txt; : > $OUT
for V in %s; do
  echo "== %s=$V ==" >> $OUT
  %s=$V /workspace/blender42/blender -b $B --python /workspace/loopwork/rigify/gate_metrics.py 2>&1 | grep -E "^(WM  *[0-9]+ |RW foot)" >> $OUT
done
/workspace/venv/bin/python scripts/ops/improve_score.py walk %s $OUT
""" % (k, k, st["cycle"], " ".join(str(v) for v in vals), k, k, k)
elif exp == "craft":
    knobs = [("FILM_LINES", ["3.2", "4.8", "6.4"]), ("CHAR_AO", ["0", "0.35", "0.6"]), ("FILM_INTEGRATE", ["0", "0.22", "0.4"]), ("FILM_LINE_ALPHA", ["0.6", "0.82", "1.0"])]
    k, vals = knobs[st["craft_i"] % len(knobs)]; st["craft_i"] += 1
    body = HEAD + """
# craft: A/B %s on a close-up and a wide shot of the latest episode-1 build
BL=/workspace/review/film_nw_rigify_cast4.blend; [ -s $BL ] || exit 0
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=4.8 FILM_LINE_MINLEN=40 FILM_INTEGRATE=0.22 CHAR_HAZE_SAT=0.3 FILM_CONTACT=1 SET_SUN="52,118" FILM_LINE_TINT="0.14,0.09,0.12" FILM_LINE_ALPHA=0.82 CHAR_AO=0.35
for V in %s; do for S in "close -2.0,7.4,1.48 0.0,6.95,1.44 55 317" "wide 5.5,7.6,1.45 -0.8,7.5,1.35 50 221"; do
  set -- $S; D=/workspace/loopwork/improve/craft_%s_${V}_$1; rm -rf $D
  %s=$V /workspace/blender42/blender -b --factory-startup $BL --python scripts/blender3d/film.py -- $D "$2" "$3" $4 $5 $5 static 1248 720 < /dev/null > $D.log 2>&1 &
done; done; wait
/workspace/venv/bin/python scripts/ops/improve_score.py craft %s "%s"
""" % (k, " ".join(vals), k, k, k, " ".join(vals))
elif exp == "face":
    knobs = [("FP_MOUTH_PLATE", ["1.2", "1.5", "1.9"]), ("FCG_MOUTH", ["0.17", "0.195", "0.22"])]
    k, vals = knobs[st["face_i"] % len(knobs)]; st["face_i"] += 1
    body = HEAD + """
# face: A/B %s on the lead's close-up, jaw-open frames
P=series/tir-na-nog-legend/meshes/props; RG=/workspace/loopwork/rigify; A=/workspace/loopwork/film_audio
for V in %s; do
  N=cand_oisin4_%s_${V//./}
  FCG_EYE=0.44 FCG_MOUTH=${FCG_MOUTH:-0.195} FCG_EYEX=0.40 %s=$V /workspace/blender42/blender -b --factory-startup --python scripts/blender3d/face_calib_geom.py -- $P/cand_oisin4_retopo.glb 1.6 $P/${N}_face.json > /dev/null 2>&1
  CHAR_NORMALFIX=0 FP_MOUTH_PLATE=${FP_MOUTH_PLATE:-1.5} %s=$V /workspace/blender42/blender -b --factory-startup --python scripts/blender3d/face_paint.py -- --keep-eyes $P/cand_oisin4_retopo.glb $P/${N}_face.json 1.6 $P $N "0.45,0.30,0.16" > /dev/null 2>&1
  rm -rf $RG/face_$N
  RT_RES=720 RT_FRAMES=40 RT_HEAD=0.74 RT_LENS=85 /workspace/blender42/blender -b $RG/oisin4_face.blend --python scripts/blender3d/rigify_talk.py -- /workspace/loopwork/day3/film_audio/l0.json $A/l0_vis_lam.npy $A/l0_blink_lam.npy $A/l0.wav $P $N $RG/face_$N > /dev/null 2>&1
done
/workspace/venv/bin/python scripts/ops/improve_score.py face %s "%s"
""" % (k, " ".join(vals), k, k, k, k, " ".join(vals))
else:
    if st.get("defaults_ver", 0) <= st.get("masters_ver", 0):
        # nothing changed: fall through to a cast cycle instead of an idle
        st["cycle"] += 1
        json.dump(st, open(ST, "w"))
        os.execv(sys.executable, [sys.executable] + sys.argv)
    st["masters_ver"] = st["defaults_ver"]
    body = HEAD + """
# episode: walk defaults changed since the last masters -> re-render episode 1
W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender
CHAR_NORMALFIX=0 FILM_RIG=rigify FILM_BLINK=lam FILM_VIS_SUFFIX=_lam FILM_ENV_SUFFIX=_lam $B -b --python scripts/blender3d/build_film.py -- $W/film_audio $R/film_nw_rigify_cast4.blend $W/film_shots_rc4.json < /dev/null > $W/imp_build.log 2>&1
grep -q "FILM SCENE SAVED" $W/imp_build.log || exit 0
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=4.8 FILM_LINE_MINLEN=40 FILM_LINE_CREASE=0 FILM_RES=1664x960 FILM_INTEGRATE=0.22 CHAR_HAZE_SAT=0.3 FILM_CONTACT=1 SET_SUN="52,118" FILM_LINE_TINT="0.14,0.09,0.12" FILM_LINE_ALPHA=0.82 CHAR_AO=0.35 FILM_STEP_ANIM=2
/workspace/venv/bin/python scripts/blender3d/shot_language.py $W/film_shots_rc4.json $W/sl_film_shots_rc4.json > /dev/null 2>&1
rm -rf $W/filmIMP $W/filmIMP.*.log
bash scripts/ops/render_episode.sh sl_film_shots_rc4.json film_nw_rigify_cast4.blend filmIMP "The Nine Waterfalls" film_audio $R/nine_waterfalls_rigify_cast4.mp4 6 > $W/imp_render.log 2>&1
[ -f $R/nine_waterfalls_rigify_cast4.mp4 ] && ffmpeg -v error -y -i $R/nine_waterfalls_rigify_cast4.mp4 -c:v libx264 -crf 23 -preset medium -pix_fmt yuv420p -c:a aac -movflags +faststart $R/nine_waterfalls_rigify_cast4_web.mp4
echo "- $(date +%%F\\ %%H:%%M) episode: re-rendered episode 1 with walk defaults v$(cat /workspace/loopwork/improve/defaults_ver 2>/dev/null || echo ?)" >> $LEDGER
"""
json.dump(st, open(ST, "w"), indent=1)
job = "%s/90_improve_%s_%04d.sh" % (Q, exp, st["cycle"])
open(job, "w").write(body + TAIL)
print("IMPROVE wrote", os.path.basename(job))
