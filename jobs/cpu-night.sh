#!/usr/bin/env bash
# CPU work, running ALONGSIDE the GPU jobs. Nothing here touches the card --
# that rule was learned the hard way when a scoring pass tripled plate times.
set -u
cd /workspace/text-to-video
export CUDA_VISIBLE_DEVICES=""
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }

say "1  foley + motif on the existing cuts"
$PY scripts/mix_with_foley.py $S --episodes ep06,ep05,ep08,ep07,ep09 \
    -o /workspace/review/post/film_sound.mp4 || echo "  skipped"

say "2  re-cut whatever the GPU has finished, every 40 minutes"
# ep11 and the re-rolls land through the night; each pass picks up what exists
# and leaves the previous cut in place if nothing changed.
for i in 1 2 3 4 5 6 7 8; do
  sleep 2400
  if [ -f output/$S/ep11/ep11_designed.mp4 ] && \
     [ ! -f /workspace/review/post/ep11_post.mp4 ]; then
    say "  ep11 has landed — cutting it"
    $PY scripts/assemble_film.py $S --episodes ep11 --reactions --post \
        --title "Three Hundred Summers" --subtitle "the years between" \
        -o /workspace/review/post/ep11_post.mp4 || true
    cp /workspace/review/post/ep11_post.mp4 /workspace/review/wow/deliver/ 2>/dev/null || true
  fi
  $PY scripts/build_video_assets.py >/dev/null 2>&1 || true
  $PY scripts/build_story_cards.py >/dev/null 2>&1 || true
done

say "done"
