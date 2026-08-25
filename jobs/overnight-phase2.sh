#!/usr/bin/env bash
# Phase 2, chained straight onto phase 1 so the GPU never drains at the
# boundary: a fourth piece, then a 1080p pass over everything.
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
SERIES=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }

# Wait for phase 1 to exit, checking the pidfile rather than matching a
# process name -- `pgrep -f` matches the shell running it and kills sessions.
P1=$(cat .jobs/pids/overnight.pid 2>/dev/null || echo "")
if [ -n "$P1" ]; then
  say "waiting for phase 1 (pid $P1)"
  while kill -0 "$P1" 2>/dev/null; do sleep 20; done
fi

say "A/E  gates for ep08"
$PY scripts/selftest.py || exit 1
$PY scripts/preflight.py $SERIES --episode 8 || exit 1
$PY scripts/validate_workflow.py $SERIES --episode 8 || exit 1

say "B/E  render ep08 — What She Kept"
$PY scripts/showrunner.py produce $SERIES --episode 8
$PY scripts/design_episode_audio.py $SERIES --episode 8

say "C/E  1080p upscale pass (RealESRGAN anime 6B)"
for E in 5 6 7 8; do
  echo "--- ep0$E ---"
  $PY scripts/upscale_episode.py $SERIES --episode $E || echo "  ep0$E upscale skipped"
done

say "D/E  collect"
mkdir -p /workspace/review/wow/deliver
for E in 05 06 07 08; do
  for V in 1080p designed final; do
    F=output/$SERIES/ep$E/ep${E}_$V.mp4
    [ -f "$F" ] && cp "$F" /workspace/review/wow/deliver/ep${E}_$V.mp4
  done
done
ls -la /workspace/review/wow/deliver/

say "E/E  done"
