#!/bin/bash
# v6 masters: RETOPOLOGISED cast (clean quad topology, re-skinned on the same UniRig skeleton,
# HD faces rebaked into the new UV space) + painted worlds (per-shot plate projection, 4x plates), camera-projected HD faces (_hd variants),
# UniRig cast, LAM blinks, anime cel shader; 1664x960, 8 px lines. One episode after another, export after each.
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender
log(){ echo "[v6 $(date +%H:%M:%S)] $*"; }
EPS=${EPS:-"1 2 3"}
for EP in $EPS; do
  case $EP in
    1) SCRIPT=build_film.py;  AUD=film_audio;  BL=film_nine_waterfalls_v6.blend; JS=film_shots_v6.json;  TAG=filmV6;  TITLE="The Nine Waterfalls"; OUT=nine_waterfalls_v6.mp4;;
    2) SCRIPT=build_film2.py; AUD=film2_audio; BL=film2_first_snow_v6.blend;     JS=film2_shots_v6.json; TAG=film2V6; TITLE="The First Snow";       OUT=first_snow_v6.mp4;;
    3) SCRIPT=build_film3.py; AUD=film3_audio; BL=film3_farewell_cliff_v6.blend; JS=film3_shots_v6.json; TAG=film3V6; TITLE="The Farewell Cliff";   OUT=farewell_cliff_v6.mp4;;
  esac
  CHAR_NORMALFIX=0 FILM_RIG=unirig FILM_BLINK=lam FILM_MESH_SUFFIX=_retopo FILM_FACE_SUFFIX=_retopo_hd $B -b --factory-startup --python scripts/blender3d/$SCRIPT -- $W/$AUD $R/$BL $W/$JS < /dev/null > $W/v6_build$EP.log 2>&1
  log "ep$EP blend: saved=$(grep -c 'FILM SCENE SAVED' $W/v6_build$EP.log) painter=$(grep -c 'PAINTER projected' $W/v6_build$EP.log) $(grep -m1 -A3 Traceback $W/v6_build$EP.log | tail -1)"
  [ -f $R/$BL ] || { log "ep$EP build FAILED — skipping"; continue; }
  # integration recipe (21 Sep): the cast breathe the plate's air, are grounded by a contact
  # patch, are keyed from the plate's own light direction, and wear a tinted rather than
  # near-black line. Line width follows the 480p->960p doubling, so 2.4 becomes 4.8.
  case $EP in
    1) SUN="52,118";;      # summer valley: sun high and behind-left, as the plate paints it
    2) SUN="45,120";;      # winter valley: same geometry, flatter light
    3) SUN="26,96";;       # farewell cliff: low sun over the sea
  esac
  export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=4.8 FILM_LINE_MINLEN=40 FILM_LINE_CREASE=0 FILM_RES=1664x960
  export FILM_INTEGRATE=0.22 CHAR_HAZE_SAT=0.3 FILM_CONTACT=1 SET_SUN="$SUN"
  export FILM_LINE_TINT="0.14,0.09,0.12" FILM_LINE_ALPHA=0.82
  export CHAR_AO=0.35                      # designed shadow shapes from the baked AO map
  export FILM_COMPLINE=0.75 FILM_COMPLINE_Z=0   # interior fold lines; Freestyle keeps the contour
  unset CHAR_SMOOTH
  # shot language: cap the tightest lenses, pull back, guard the foreground. Data-only,
  # applied to the emitted shot list, so the scene itself is untouched.
  /workspace/venv/bin/python scripts/blender3d/shot_language.py $W/$JS $W/sl_$JS >> $W/v6_build$EP.log 2>&1 && JS=sl_$JS
  bash scripts/ops/render_episode.sh $JS $BL $TAG "$TITLE" $AUD $R/$OUT 3; rm -rf $W/$TAG $W/$TAG.*.log
  [ -f $R/$OUT ] && ffmpeg -v error -y -i $R/$OUT -c:v libx264 -crf 23 -preset medium -pix_fmt yuv420p -c:a aac -movflags +faststart ${OUT%.mp4}_web.mp4 2>/dev/null && mv ${OUT%.mp4}_web.mp4 $R/ 
  log "ep$EP master: $(ls -la $R/$OUT 2>/dev/null | awk '{print $5}') bytes"
  bash /workspace/export_outcomes.sh 2>&1 | tail -1
done
log "V6 MASTERS DONE"
