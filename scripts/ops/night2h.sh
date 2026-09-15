#!/bin/bash
# night2g hit a variable-shadowing crash after its first close in each
# episode, so almost nothing was re-timed. This redoes it with the fix.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "night2g\.s[h]" > /dev/null; do sleep 120; done
log "night2g finished"

for E in 13 14 15 12; do
  log "=== ep$E · re-time, install, re-stitch ==="
  $PY scripts/repair_dialogue_closes.py tir-na-nog-legend --episode $E 2>&1 | tail -8
  $PY scripts/install_repaired_closes.py tir-na-nog-legend --episode $E 2>&1 | tail -10
  $PY scripts/showrunner.py produce tir-na-nog-legend --episode $E \
      --quality final --upscale --resume 2>&1 | tail -6
done

log "=== final check across every episode ==="
$PY - <<'PYX'
import sys; sys.path.insert(0,'scripts')
import showrunner as sr
from pathlib import Path
for e in (12,13,14,15,16):
    f = Path(f"output/tir-na-nog-legend/ep{e:02d}/ep{e:02d}_final.mp4")
    if f.exists():
        st = sorted(sr._streams(f))
        print(f"  ep{e}: {sr._get_video_duration(f):6.1f}s {st} "
              f"{'OK' if 'audio' in st else 'MISSING AUDIO'}")
PYX
$PY scripts/build_shorts_pack.py 2>&1 | tail -3
cd /workspace && rm -f shorts_pack.tar.gz && tar czf shorts_pack.tar.gz shorts_pack \
  && ls -l shorts_pack.tar.gz | awk '{printf "  shorts_pack.tar.gz %.0f MB\n",$5/1048576}'
log "NIGHT2H DONE"
