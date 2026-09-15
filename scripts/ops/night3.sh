#!/bin/bash
# Bring ep05-ep11 up to the current standard, as far as is possible without
# re-authoring them.
#
# 57 of their 66 shots are dialogue -- they were written before the grammar,
# so their "wide shots" all carry lines and all collapsed to close-ups. That
# cannot be fixed by re-rendering: the line has to move to a closer shot or
# the shot has to go silent with the voice laid over, which is a rewrite.
#
# What CAN be fixed without touching the writing, and is worth doing:
#   closes re-seeded in their own location  (57 shots set somewhere at last)
#   a camera on every shot                  (1.43x motion, free)
#   grade + ESRGAN + audio preserved        (the current post chain)
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }

for E in 7 5 6 8 9 11 10; do
  log "=== ep$E ==="
  $PY scripts/modernise_episode.py tir-na-nog-legend --episode $E 2>&1 | tail -30
done

log "=== stream check across the whole series ==="
$PY - <<'PYX'
import sys; sys.path.insert(0,'scripts')
import showrunner as sr
from pathlib import Path
for e in range(5,17):
    f = Path(f"output/tir-na-nog-legend/ep{e:02d}/ep{e:02d}_final.mp4")
    if f.exists():
        st = sorted(sr._streams(f))
        print(f"  ep{e:02d}: {sr._get_video_duration(f):6.1f}s {st} "
              f"{'OK' if 'audio' in st else 'MISSING AUDIO'}")
PYX

log "=== repackage ==="
$PY scripts/build_shorts_pack.py 2>&1 | tail -3
cd /workspace && rm -f shorts_pack.tar.gz && tar czf shorts_pack.tar.gz shorts_pack \
  && ls -l shorts_pack.tar.gz | awk '{printf "  shorts_pack.tar.gz %.0f MB\n",$5/1048576}'
log "NIGHT3 DONE"
