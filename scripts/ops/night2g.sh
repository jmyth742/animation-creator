#!/bin/bash
# The repaired closes are re-cut to the authored shot length and installed.
# The rc_ takes already exist, so this only re-times them -- no re-rendering.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "night2[ef]\.s[h]" > /dev/null; do sleep 180; done
log "night2e/f finished"

for E in 13 14 15 12; do
  log "=== re-time ep$E repaired closes to the authored length ==="
  $PY scripts/repair_dialogue_closes.py tir-na-nog-legend --episode $E 2>&1 | tail -12
  log "=== install into ep$E ==="
  $PY scripts/install_repaired_closes.py tir-na-nog-legend --episode $E 2>&1 | tail -10
  log "=== re-stitch ep$E ==="
  $PY scripts/showrunner.py produce tir-na-nog-legend --episode $E \
      --quality final --upscale --resume 2>&1 | tail -8
done

log "=== final stream check across every episode ==="
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
log "NIGHT2G DONE"
