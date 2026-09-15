#!/bin/bash
# Insurance behind night3: a new episode written to the grammar, so the card
# has work even if the ep05-11 pass runs faster than estimated.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "night3\.s[h]" > /dev/null; do sleep 180; done
log "night3 finished"

log "=== gates ==="
$PY scripts/selftest.py > /tmp/e17_self.log 2>&1 || { log "SELFTEST FAILED"; exit 1; }
$PY scripts/preflight.py tir-na-nog-legend --episode 17 > /tmp/e17_pre.log 2>&1 || { log "PREFLIGHT FAILED"; tail -20 /tmp/e17_pre.log; exit 1; }
log "gates passed"

log "=== ep17 The Asking (13 shots) ==="
$PY scripts/showrunner.py produce tir-na-nog-legend --episode 17 --quality final --upscale 2>&1 | tail -50
$PY scripts/verify_render.py tir-na-nog-legend --episode 17 2>&1 | tail -16
log "=== camera pass ==="
$PY scripts/add_camera_to_episode.py tir-na-nog-legend --episode 17 2>&1 | tail -5
$PY scripts/showrunner.py produce tir-na-nog-legend --episode 17 --quality final --upscale --resume 2>&1 | tail -8
$PY scripts/shot_inspector.py tir-na-nog-legend --episode 17 --measure 2>&1 | tail -2

log "=== final stream check ==="
$PY - <<'PYX'
import sys; sys.path.insert(0,'scripts')
import showrunner as sr
from pathlib import Path
for e in range(5,18):
    f = Path(f"output/tir-na-nog-legend/ep{e:02d}/ep{e:02d}_final.mp4")
    if f.exists():
        st = sorted(sr._streams(f))
        print(f"  ep{e:02d}: {sr._get_video_duration(f):6.1f}s {st} "
              f"{'OK' if 'audio' in st else 'MISSING AUDIO'}")
PYX
log "NIGHT3B DONE"
