#!/usr/bin/env bash
# The long night. Runs after the priority experiments, ordered so that the
# things whose ANSWERS change later work come first, and the things that just
# consume GPU come last.
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }

for J in finishall priority; do
  P=$(cat .jobs/pids/$J.pid 2>/dev/null || echo "")
  [ -n "$P" ] && { say "waiting for $J"; while kill -0 "$P" 2>/dev/null; do sleep 60; done; }
done

say "A  ep11 — Three Hundred Summers (7 of 11 shots ask for physical action)"
# The first script written against the finding that 42 of 55 shots were
# talking heads. Whether the bodies actually move is the point.
$PY scripts/selftest.py || exit 1
$PY scripts/preflight.py $S --episode 11 || echo "  preflight warned, continuing"
$PY scripts/validate_workflow.py $S --episode 11 || exit 1
rm -f ComfyUI/output/video/$S/ep11_s*.mp4
$PY scripts/showrunner.py produce $S --episode 11
$PY scripts/design_episode_audio.py $S --episode 11

say "B  re-roll the weakest shots (targeted, not blanket coverage)"
# Coverage showed the benefit is bimodal: re-rolling low-scoring shots captures
# most of it at a fraction of the cost.
$PY scripts/reroll_weak_shots.py $S --worst 8 --takes 2

say "C  stage the location that has never been built"
$PY scripts/build_sets.py setups $S --all
$PY scripts/build_sets.py check $S --threshold 0.55

say "D  1080p everything that does not have it"
for E in 06 07 08 09 10 11; do
  [ -f output/$S/ep$E/ep${E}_1080p.mp4 ] || $PY scripts/upscale_episode.py $S --episode ${E#0} || true
done

say "E  collect"
mkdir -p /workspace/review/wow/deliver
for E in 05 06 07 08 09 10 11; do
  for V in designed 1080p; do
    F=output/$S/ep$E/ep${E}_$V.mp4
    [ -f "$F" ] && cp "$F" /workspace/review/wow/deliver/ep${E}_$V.mp4
  done
done
ls -la /workspace/review/wow/deliver/
say "done"
