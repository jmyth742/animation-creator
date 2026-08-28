#!/usr/bin/env bash
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }
for J in negab overnightfull movetest walktest shortsbroll; do
  P=$(cat .jobs/pids/$J.pid 2>/dev/null || echo "")
  [ -n "$P" ] && { say "waiting for $J"; while kill -0 "$P" 2>/dev/null; do sleep 60; done; }
done
say "ep12 — The Ride Back (7 of 11 shots are silent movement)"
$PY scripts/selftest.py || exit 1
$PY scripts/preflight.py $S --episode 12 || exit 1
$PY scripts/validate_workflow.py $S --episode 12 || exit 1
rm -f ComfyUI/output/video/$S/ep12_s*.mp4
$PY scripts/showrunner.py produce $S --episode 12
$PY scripts/design_episode_audio.py $S --episode 12
export CUDA_VISIBLE_DEVICES=""
$PY scripts/assemble_film.py $S --episodes ep12 --post --look subtle \
   --title "The Ride Back" --subtitle "movement, written as its own shots" \
   -o /workspace/review/post/ep12_post.mp4
cp /workspace/review/post/ep12_post.mp4 /workspace/review/wow/deliver/ 2>/dev/null
say "done"

say "sampler settings the audit says are wrong"
$PY scripts/sampler_ab.py $S --scene ep11_s02
