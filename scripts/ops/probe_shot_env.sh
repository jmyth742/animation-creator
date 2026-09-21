#!/bin/bash
# probe_shot_env.sh <outtag> <shotname> [ENV=VAL ...] — one frame of one shot, current stack
set -u; cd /workspace/text-to-video
TAG=$1; SHOT=$2; shift 2
W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender
JS=$W/shots_night_sl.json; [ -f "$JS" ] || JS=$W/shots_sl3.json
BL=$R/film_night.blend; [ -f "$BL" ] || BL=$R/film_sl.blend
read C T L F0 F1 <<< "$(/workspace/venv/bin/python -c "
import json,sys
d=json.load(open('$JS')); s=[x for x in d['shots'] if x['name']=='$SHOT']
if not s: sys.exit(1)
s=s[0]; print(s['cam'],s['tgt'],s['lens'],s['f0'],s['f1'])")" || exit 0
FM=$(( (F0+F1)/2 )); D=$W/$TAG; rm -rf $D; mkdir -p $D
env "$@" CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINE_TINT="0.14,0.09,0.12" SET_SUN="52,118" \
  FILM_LINE_MINLEN=14 FILM_COMPLINE=0.75 FILM_COMPLINE_Z=0 \
  timeout 700 $B -b --factory-startup $BL --python scripts/blender3d/film.py -- $D "$C" "$T" $L $FM $FM static < /dev/null > $D.log 2>&1
echo "probe $TAG: $(ls $D/*.png 2>/dev/null | wc -l) frame"
