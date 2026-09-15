#!/bin/bash
# After night4: the evidence sets for morning judgement. CPU-heavy, cheap.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "night4\.s[h]" > /dev/null; do sleep 180; done
log "night4 finished"

log "=== voice direction A/B pairs (installed nowhere) ==="
$PY scripts/voice_direction.py tir-na-nog-legend 2>&1 | tail -14

log "=== likeness sheet: LoRA two-shots beside the anchors ==="
$PY - <<'PYX' 2>&1 | tail -6
import sys, subprocess
sys.path.insert(0,'scripts')
from pathlib import Path
import showrunner as sr
sr.set_current_series('tir-na-nog-legend')
frames = []
for sid in ("ep15_s04","ep15_s07","ep15_s11","ep16_s05","ep16_s09","ep17_s04","ep17_s08"):
    c = sr.find_latest_clip(sid)
    if not c: continue
    f = f"/tmp/lk_{sid}.png"
    subprocess.run(["ffmpeg","-v","error","-y","-ss","2.5","-i",c,"-frames:v","1","-vf","scale=300:173",f], check=False)
    if Path(f).exists(): frames.append(f)
ref = sr.series_path('tir-na-nog-legend')/'reference_images'
for ch in ("oisin","niamh"):
    p = sr._find_ref(ref, ch, "char")
    if p:
        f = f"/tmp/lk_anchor_{ch}.png"
        subprocess.run(["ffmpeg","-v","error","-y","-i",str(p),"-vf","scale=300:173",f], check=False)
        frames.append(f)
n = len(frames)
args = []
for f in frames: args += ["-i", f]
subprocess.run(["ffmpeg","-v","error","-y",*args,"-filter_complex",
                "".join(f"[{i}]" for i in range(n)) + f"hstack=inputs={n}",
                "/workspace/review/LIKENESS_SHEET.png"], check=False)
print(f"{n} frames -> /workspace/review/LIKENESS_SHEET.png (two-shots then anchors)")
PYX

log "=== inspector pages for the whole current series ==="
for E in 12 13 14 15 16 17; do
  $PY scripts/shot_inspector.py tir-na-nog-legend --episode $E --measure 2>&1 | tail -1
done
log "NIGHT4B DONE"
