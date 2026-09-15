#!/bin/bash
# Render one episode's shots IN PARALLEL (Freestyle is CPU-bound; the box
# has 256 cores), verify every shot frame-for-frame, retry failures once,
# assemble, loudnorm. The character/line stack comes from the environment
# (CHAR_NORMALFIX, FILM_LINES, FILM_LINE_MINLEN ...) exactly as film.py reads it.
#
# Usage: render_episode.sh <shots.json> <blend> <tag> "<title>" <audio_dir> <out.mp4> [parallel]
set -u
cd /workspace/text-to-video
W=/workspace/loopwork; V=/workspace/venv/bin/python; B=/workspace/blender42/blender
F=scripts/blender3d/film.py
SJ=$1; BL=$2; TAG=$3; TITLE=$4; AUD=$5; OUT=$6; PAR=${7:-6}
log(){ echo "[render $(date +%H:%M:%S)] $*"; }

$V - "$SJ" > $W/order_$TAG.txt <<'PY'
import json, sys
d = json.load(open(f"/workspace/loopwork/{sys.argv[1]}"))
prev = 0
for s in d["shots"]:
    f0 = max(s["f0"], prev + 1); prev = s["f1"]
    print(s["name"], s["cam"], s["tgt"], s["lens"], f0, s["f1"], s["move"])
PY

render_shot(){   # NAME CAM TGT LENS F0 F1 MOVE
  NAME=$1; CAM=$2; TGT=$3; LENS=$4; F0=$5; F1=$6; MOVE=$7
  D=$W/$TAG/$NAME; EXP=$((F1 - F0 + 1))
  for ATTEMPT in 1 2; do
    rm -rf $D; mkdir -p $D
    $B -b --factory-startup /workspace/review/$BL --python $F -- $D "$CAM" "$TGT" $LENS $F0 $F1 "$MOVE" \
      < /dev/null > $W/$TAG.$NAME.log 2>&1
    N=$(ls $D/frame_*.png 2>/dev/null | wc -l)
    if [ "$N" -ge "$EXP" ]; then echo "[render $(date +%H:%M:%S)] $TAG/$NAME $N/$EXP ok (try $ATTEMPT)"; return 0; fi
    echo "[render $(date +%H:%M:%S)] $TAG/$NAME FAILED $N/$EXP (try $ATTEMPT): $(grep -m1 -E 'Error|error:' $W/$TAG.$NAME.log | cut -c1-120)"
  done
  return 1
}
export -f render_shot; export W B F TAG BL
log "$TAG: $(wc -l < $W/order_$TAG.txt) shots, $PAR in parallel, stack: NORMALFIX=${CHAR_NORMALFIX:-} LINES=${FILM_LINES:-} MINLEN=${FILM_LINE_MINLEN:-} SMOOTH=${CHAR_SMOOTH:-}"
xargs -P $PAR -L 1 bash -c 'render_shot "$@"' _ < $W/order_$TAG.txt
BAD=0
while read NAME CAM TGT LENS F0 F1 MOVE; do
  N=$(ls $W/$TAG/$NAME/frame_*.png 2>/dev/null | wc -l); [ "$N" -ge $((F1 - F0 + 1)) ] || BAD=$((BAD+1))
done < $W/order_$TAG.txt
if [ "$BAD" != 0 ]; then log "$TAG: $BAD shots short — NOT assembling"; exit 1; fi
$V scripts/blender3d/assemble_film.py $W $OUT "$TITLE" $TAG $SJ $AUD || { log "$TAG: assemble failed"; exit 1; }
ffmpeg -v error -y -i $OUT -c:v libx264 -pix_fmt yuv420p -crf 20 -af "loudnorm=I=-14:TP=-1.5:LRA=11" -c:a aac -b:a 192k -ar 48000 $W/x_$TAG.mp4 && mv $W/x_$TAG.mp4 $OUT
log "$TAG: master $OUT ($(stat -c%s $OUT) bytes, $(ffprobe -v error -show_entries format=duration -of csv=p=0 $OUT)s)"
