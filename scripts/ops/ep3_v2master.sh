#!/bin/bash
# Episode 3: build the fixed stage (v2) -> establishing probe -> 480p master -> export
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender; A=$W/film3_audio
log(){ echo "[ep3m $(date +%H:%M:%S)] $*"; }
CHAR_NORMALFIX=0 FILM_RIG=unirig $B -b --factory-startup --python scripts/blender3d/build_film3.py -- $A $R/film3_farewell_cliff.blend $W/film3_shots.json < /dev/null > $W/ep3_build.log 2>&1
log "build: $(grep -c 'FILM SCENE SAVED' $W/ep3_build.log) $(grep -m1 Traceback $W/ep3_build.log)"
grep -q "FILM SCENE SAVED" $W/ep3_build.log || exit 1
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=4.0 FILM_LINE_MINLEN=20 FILM_LINE_CREASE=0
S=$(python3 -c "import json; d=json.load(open('$W/film3_shots.json')); s=[x for x in d['shots'] if x['name']=='s01_est'][0]; print(s['cam'],s['tgt'],s['lens'],s['f0'],s['f1'],s['move'])"); read C T L F0 F1 M <<< "$S"
D=$W/ep3m_est; rm -rf $D; mkdir -p $D; $B -b --factory-startup $R/film3_farewell_cliff.blend --python scripts/blender3d/film.py -- $D "$C" "$T" $L 55 55 static < /dev/null > $D.log 2>&1
cp $(ls $D/*.png | head -1) $R/day6_ep3_establishing.png && log "day6_ep3_establishing.png"
bash /workspace/export_outcomes.sh 2>&1 | tail -1
bash scripts/ops/render_episode.sh film3_shots.json film3_farewell_cliff.blend film3S "The Farewell Cliff" film3_audio $R/farewell_cliff_v1.mp4 3
rm -rf $W/film3S $W/film3S.*.log; bash /workspace/export_outcomes.sh 2>&1 | tail -1
log "EP3 MASTER DONE"
