#!/usr/bin/env bash
# Rebuild every cut made before the two timeline fixes. CPU only.
set -u
cd /workspace/text-to-video
export CUDA_VISIBLE_DEVICES=""
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }
D=/workspace/review/wow/deliver

say "the four-movement film"
$PY scripts/assemble_film.py $S --episodes ep06,ep05,ep08,ep07,ep09 \
  --reactions --post --look subtle --title "Tir na nOg" \
  --subtitle "a folk tale in four movements" -o /workspace/review/post/film_v4.mp4 \
  && cp /workspace/review/post/film_v4.mp4 $D/

say "the prelude"
$PY scripts/assemble_film.py $S --episodes ep10 --reactions --post --look subtle \
  --title "The Woman on the White Horse" --subtitle "a prelude" \
  -o /workspace/review/post/prelude_v2.mp4 \
  && cp /workspace/review/post/prelude_v2.mp4 $D/

say "foley + motif over the resynced four-movement cut"
$PY scripts/mix_with_foley.py $S --episodes ep06,ep05,ep08,ep07,ep09 \
  --source /workspace/review/post/film_v4.mp4 \
  -o /workspace/review/post/film_sound_v2.mp4 \
  && cp /workspace/review/post/film_sound_v2.mp4 $D/

say "verify every deliverable"
for f in $D/*.mp4; do
  V=$(ffprobe -v error -select_streams v:0 -show_entries stream=duration -of csv=p=0 "$f")
  A=$(ffprobe -v error -select_streams a:0 -show_entries stream=duration -of csv=p=0 "$f")
  echo "  $(basename $f)  v=$V a=$A"
done
say "done"
