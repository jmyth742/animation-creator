#!/bin/bash
# EPISODE 3 resume: build -> probes -> master (audio/visemes/LAM already in loopwork/film3_audio)
# with the UniRig cast -> probes -> 480p verdict master -> export.
set -u; cd /workspace/text-to-video
W=/workspace/loopwork; V=/workspace/venv/bin/python; B=/workspace/blender42/blender; R=/workspace/review; A=$W/film3_audio
log(){ echo "[ep3 $(date +%H:%M:%S)] $*"; }
export HF_HOME=/workspace/hf_cache
log "4: build the cliff film (UniRig cast, restaged-close conventions)"
CHAR_NORMALFIX=0 FILM_RIG=unirig $B -b --factory-startup --python scripts/blender3d/build_film3.py -- $A $R/film3_farewell_cliff.blend $W/film3_shots.json < /dev/null > $W/ep3_build.log 2>&1
log "build: $(grep -c 'FILM SCENE SAVED' $W/ep3_build.log) $(grep -m1 -E 'CLIFF SET|FILM SCENE SAVED' $W/ep3_build.log)"
grep -q "FILM SCENE SAVED" $W/ep3_build.log || { log "BUILD FAILED"; grep -A8 Traceback $W/ep3_build.log | head -12; exit 1; }
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=2.0 FILM_LINE_MINLEN=20 FILM_LINE_CREASE=0
log "5: probes (est, meet, his close, her close)"
probe(){ SHOT=$1; S=$(python3 -c "import json; d=json.load(open('$W/film3_shots.json')); s=[x for x in d['shots'] if x['name']=='$SHOT'][0]; print(s['cam'],s['tgt'],s['lens'],s['f0'],s['f1'],s['move'])"); read C T L F0 F1 M <<< "$S"; FM=$(( (F0+F1)/2 )); D=$W/ep3p_$SHOT; rm -rf $D; mkdir -p $D
  $B -b --factory-startup $R/film3_farewell_cliff.blend --python scripts/blender3d/film.py -- $D "$C" "$T" $L $FM $FM static < /dev/null > $D.log 2>&1; }
probe s01_est & probe s03_meet & probe s04 & probe s05 & wait
ffmpeg -v error -y -i $(ls $W/ep3p_s01_est/*.png) -i $(ls $W/ep3p_s03_meet/*.png) -i $(ls $W/ep3p_s04/*.png) -i $(ls $W/ep3p_s05/*.png) -filter_complex "[0][1]hstack[a];[2][3]hstack[b];[a][b]vstack" $R/day6_ep3_probes.png && log "day6_ep3_probes.png (est | meet over his close | her close)"
bash /workspace/export_outcomes.sh 2>&1 | tail -1
log "6: 480p verdict master"
bash scripts/ops/render_episode.sh film3_shots.json film3_farewell_cliff.blend film3S "The Farewell Cliff" film3_audio $R/farewell_cliff_v1.mp4 3
rm -rf $W/film3S $W/film3S.*.log
bash /workspace/export_outcomes.sh 2>&1 | tail -1
log "EP3 DONE"
