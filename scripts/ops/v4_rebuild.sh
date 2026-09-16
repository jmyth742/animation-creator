#!/bin/bash
# Rebuild ep2 + ep3 blends with the seam weld (load default) and LAM blink events
# BEFORE their v4 renders start; then queue ep1's rebuild + re-render after ep3.
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender
log(){ echo "[v4rb $(date +%H:%M:%S)] $*"; }
export CHAR_NORMALFIX=0 FILM_RIG=unirig FILM_BLINK=lam
$B -b --factory-startup --python scripts/blender3d/build_film2.py -- $W/film2_audio $R/film2_first_snow.blend $W/film2_shots.json < /dev/null > $W/v4rb_build2.log 2>&1 &
$B -b --factory-startup --python scripts/blender3d/build_film3.py -- $W/film3_audio $R/film3_farewell_cliff.blend $W/film3_shots.json < /dev/null > $W/v4rb_build3.log 2>&1 &
wait
for N in 2 3; do log "ep$N blend: $(grep -c 'FILM SCENE SAVED' $W/v4rb_build$N.log) weld=$(grep -c '^SHELLCULL' $W/v4rb_build$N.log) $(grep -m1 Traceback $W/v4rb_build$N.log)"; done
log "REBUILD DONE"
