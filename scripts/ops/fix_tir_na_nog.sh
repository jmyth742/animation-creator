#!/bin/bash
# fix_tir_na_nog.sh — restore the classic episodes to the first-set look.
#
# Two diagnosed regressions (session 2026-09-02):
#   1. Dialogue closes seeded from __inplace composites: drifted identity
#      (blue eyes), translucent halo, cropped foreheads.   ep13-18
#   2. Wides/two-shots seeded from gen__ plates forged with the muted winter
#      palette and photoreal drift: murky, hazy, not cel.  ep15-17
#
# This re-forges every affected plate with the fixed generator, then
# re-renders exactly the affected shots per episode, worst-first, and
# re-runs the post chain. Winter chapters wait until the classics are done
# (user call: finish Tir na nOg before the next show).
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }

log "waiting for the winter chain to finish"
while pgrep -f "showrunner.py produce tir-na-nog-legend --episode 1[89]" > /dev/null; do sleep 120; done
while pgrep -f "winter[12]\.sh" > /dev/null; do sleep 60; done
log "winter chain done"

log "=== 1. re-forge plates with warm palettes + hard cel style ==="
$PY scripts/gen_real_plates.py tir-na-nog-legend --only \
gen__valley_wide_oisin,gen__valley_wide_niamh,gen__valley_twoshot,gen__cliff_wide_oisin,gen__cliff_wide_niamh,gen__cliff_twoshot,gen__path_twoshot,gen__path_wide_oisin,gen__sun_wide_oisin,gen__sun_wide_rider \
  2>&1 | tail -12
$PY scripts/gen_real_plates.py tir-na-nog-legend --only \
gen__valley_close_oisin,gen__valley_close_niamh,gen__winter_close_oisin,gen__winter_close_niamh,gen__cliff_close_oisin,gen__cliff_close_niamh,gen__ruin_close_oisin,gen__ruin_close_niamh \
  2>&1 | tail -10

log "=== 2. point repaired closes at the new plates ==="
$PY - <<'PYEOF'
import json, pathlib
gen = pathlib.Path("series/tir-na-nog-legend/sets/_generated")
for f in sorted(pathlib.Path("series/tir-na-nog-legend/episodes").glob("ep*.json")):
    ep = json.load(open(f)); n = 0
    for s in ep["scenes"]:
        want = s.get("reference_image_wanted")
        if want and (gen / f"{want}.png").exists():
            s["reference_image"] = str((gen / f"{want}.png").resolve())
            n += 1
    if n:
        json.dump(ep, open(f, "w"), indent=1, ensure_ascii=False)
        print(f"  {f.name}: {n} closes re-pointed")
PYEOF

Q=ComfyUI/output/video/tir-na-nog-legend/_quarantine_drift
mkdir -p $Q
redo_ep(){
  E=$1; shift
  log "=== ep$E: re-render $* ==="
  for s in "$@"; do
    mv ComfyUI/output/video/tir-na-nog-legend/ep${E}_${s}_*.mp4 $Q/ 2>/dev/null
  done
  $PY scripts/showrunner.py produce tir-na-nog-legend --episode $E --quality final --upscale --resume 2>&1 | tail -15
  $PY scripts/add_camera_to_episode.py tir-na-nog-legend --episode $E 2>&1 | tail -3
  $PY scripts/showrunner.py produce tir-na-nog-legend --episode $E --quality final --upscale --resume 2>&1 | tail -4
  $PY scripts/master_audio.py tir-na-nog-legend --episode $E 2>&1 | tail -3
  $PY scripts/episode_qc.py tir-na-nog-legend --episode $E 2>&1 | tail -8
}

# worst first. closes = identity drift, wides = muted photoreal plates.
redo_ep 16 s03 s06 s07 s08 s10 s12  s02 s04 s05 s09 s11
redo_ep 17 s03 s05 s06 s07 s09 s10 s12  s02 s04 s08 s11
redo_ep 15 s05 s06 s08 s09 s10 s11 s12  s02 s03 s04 s07 s13 s14
redo_ep 14 s15
redo_ep 13 s09
# winter chapters last (user call: classics first). Re-forge the drifted
# winter wides (the twoshot is clean cel and stays), then redo composite
# closes + muted valley/winter wides in ch1 and ch2.
log "=== re-forge winter wides under the hardened style ==="
$PY scripts/gen_real_plates.py tir-na-nog-legend --only \
gen__winter_wide_empty,gen__winter_wide_oisin,gen__winter_wide_niamh,gen__winter_first_flake \
  2>&1 | tail -6
redo_ep 18 s03 s05  s02 s04 s06 s07 s14 s15 s17
redo_ep 19 s01 s02 s06 s12 s14
log "FIX TIR NA NOG DONE — review, then queue winter ch3+ writing"
