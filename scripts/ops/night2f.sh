#!/bin/bash
# After night2e: the three improvements.
#   1 plates for the two locations that had none
#   2 re-render the two-shots WITH character LoRAs, to fix the approximate
#     likeness that a generated plate cannot carry on its own
#   3 (the stream gate is already in showrunner and needs no GPU)
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "night2e\.s[h]" > /dev/null; do sleep 180; done
log "night2e finished"

log "=== 1/3 · plates for storm_cliffs and stormy_sea ==="
$PY scripts/gen_real_plates.py tir-na-nog-legend 2>&1 | grep -vE "Running|Queued" | tail -8

log "=== 2/3 · two-shots re-rendered with character LoRAs ==="
# ep15 and ep16 are the episodes with real two-shots in them.
for E in 15 16; do
  log "  ep$E"
  $PY scripts/upgrade_wides.py tir-na-nog-legend --episode $E 2>&1 | tail -14
  $PY scripts/showrunner.py produce tir-na-nog-legend --episode $E \
      --quality final --upscale --resume 2>&1 | tail -8
done

log "=== 3/3 · verify every episode kept its streams ==="
$PY - <<'PYX'
import sys; sys.path.insert(0,'scripts')
import showrunner as sr
from pathlib import Path
for e in (12,13,14,15,16):
    f = Path(f"output/tir-na-nog-legend/ep{e:02d}/ep{e:02d}_final.mp4")
    if f.exists():
        st = sorted(sr._streams(f))
        ok = "OK " if "audio" in st and "video" in st else "MISSING AUDIO"
        print(f"  ep{e}: {st}  {ok}")
PYX

log "=== repackage ==="
$PY scripts/build_shorts_pack.py 2>&1 | tail -4
cd /workspace && rm -f shorts_pack.tar.gz && tar czf shorts_pack.tar.gz shorts_pack \
  && ls -l shorts_pack.tar.gz | awk '{printf "  shorts_pack.tar.gz %.0f MB\n",$5/1048576}'
log "NIGHT2F DONE"
