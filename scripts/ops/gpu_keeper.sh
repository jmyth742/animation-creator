#!/bin/bash
# GPU KEEPER — the card is the meter that runs, so it must never idle.
#
# Watches for an idle GPU and immediately starts the next job from the queue. When the
# queue empties it refills itself from a rotating backlog of quality experiments, so the
# card keeps working through conversation, overnight, and any gap between tasks.
#
#   queue:  /workspace/loopwork/queue/NN_name.sh   (name order = priority, low first)
#   done:   /workspace/loopwork/queue/done/
#   log:    /workspace/loopwork/gpu_keeper.log
#
# Add work by dropping a numbered script in the queue. Never kill a running job to jump
# the line — queue the new work with a lower number instead.
set -u
Q=/workspace/loopwork/queue
LOG=/workspace/loopwork/gpu_keeper.log
STATE=/workspace/loopwork/keeper_cycle
mkdir -p $Q/done
log(){ echo "[keeper $(date +%F\ %H:%M:%S)] $*" >> $LOG; }

busy() {
  # any Blender render, or anything queued in ComfyUI, counts as the GPU being spoken for
  [ "$(ps -eo args | grep -c '[b]lender42/blender -b')" -gt 0 ] && return 0
  local n
  n=$(curl -s -m 3 http://127.0.0.1:8188/queue 2>/dev/null | /workspace/venv/bin/python -c \
      "import sys,json;d=json.load(sys.stdin);print(len(d.get('queue_running',[]))+len(d.get('queue_pending',[])))" 2>/dev/null)
  [ "${n:-0}" -gt 0 ]
}

refill() {
  # A rotating set of experiments that always leaves something worth running. Rewritten
  # 2026-09-23 around the finding that RETOPOLOGY BEFORE UniRig is what decides whether a
  # character rigs at all: the rotation now pushes candidates through retopo -> rig ->
  # reel and judges them, instead of repairing weights after the fact.
  local c=$(( $(cat $STATE 2>/dev/null || echo 0) ))
  echo $(( (c + 1) % 6 )) > $STATE
  local P=series/tir-na-nog-legend/meshes/props
  case $c in
    0) cat > $Q/70_retopo_sweep.sh <<'J'
cd /workspace/text-to-video
P=series/tir-na-nog-legend/meshes/props
# any textured candidate without a retopologised counterpart gets one
for SRC in $P/st_*_tex.glb $P/*_hy.glb; do
  [ -s "$SRC" ] || continue
  BASE=$(basename "$SRC" .glb); TAG="rt_${BASE}"
  [ -s "$P/${TAG}_retopo.glb" ] && continue
  /workspace/blender42/blender -b --factory-startup --python scripts/blender3d/retopo_character.py -- \
    "$SRC" "$TAG" 15000 2048 || true
  break        # one per pass: retopology is slow and the queue should stay responsive
done
J
       ;;
    1) cat > $Q/71_rig_sweep.sh <<'J'
cd /workspace/text-to-video
P=series/tir-na-nog-legend/meshes/props
for M in $P/*_retopo.glb; do
  [ -s "$M" ] || continue
  BASE=$(basename "$M" _retopo.glb)
  [ -s "$P/${BASE}_rigged.glb" ] && continue
  # the kit's own fitted skeleton, not the auto-rigger: see memory kit-rig-fit
  KRF_APOSE=0 /workspace/blender42/blender -b --factory-startup --python scripts/blender3d/kit_rig_fit.py -- \
    "$M" "$P/${BASE}_rigged.glb" 1.6 || true
  break
done
J
       ;;
    2) cat > $Q/72_reel_sweep.sh <<'J'
cd /workspace/text-to-video
P=series/tir-na-nog-legend/meshes/props
for M in $P/cand_*_rigged.glb; do
  [ -s "$M" ] || continue
  BASE=$(basename "$M" _rigged.glb)
  OUT=/workspace/review/MOTION_${BASE}.mp4
  [ -s "$OUT" ] && continue
  rm -rf /workspace/loopwork/proc_$BASE
  PS_RES=768 /workspace/blender42/blender -b --factory-startup --python scripts/blender3d/proc_showcase.py -- \
    "$M" /workspace/loopwork/proc_$BASE 1.6 || true
  bash scripts/ops/encode_showreel.sh /workspace/loopwork/proc_$BASE "$OUT" 20 "walk turn idle close" || true
  break
done
bash /workspace/export_outcomes.sh 2>&1 | tail -1
J
       ;;
    3) cat > $Q/73_gate_sweep.sh <<'J'
cd /workspace/text-to-video
P=series/tir-na-nog-legend/meshes/props
for M in $P/cand_*_rigged.glb; do
  [ -s "$M" ] || continue
  BASE=$(basename "$M" _rigged.glb)
  [ -s "/workspace/review/deform_${BASE}_60.png" ] && continue
  for A in 35 60 90; do
    GATE_ANGLE=$A /workspace/blender42/blender -b --factory-startup --python scripts/blender3d/deform_gate.py -- \
      "$M" "$BASE" 1.6 /workspace/review/deform_${BASE}_${A}.png || true
  done
  break
done
J
       ;;
    4) cat > $Q/74_texture_upsample.sh <<'J'
cd /workspace/text-to-video
P=series/tir-na-nog-legend/meshes/props
for M in $P/cand_*_retopo.glb; do
  [ -s "$M" ] || continue
  BASE=$(basename "$M" _retopo.glb)
  [ -s "$P/${BASE}_hi.glb" ] && continue
  FRONT=$P/${BASE}_retopo_base.png
  [ -s "$FRONT" ] || continue
  TEXHY_FACES=90000 /workspace/venv/bin/python -u scripts/blender3d/texture_hy3d.py \
    "$M" "$FRONT" "$P/${BASE}_hi.glb" || true
  break
done
J
       ;;
    5) cat > $Q/75_export.sh <<'J'
cd /workspace/text-to-video
bash /workspace/export_outcomes.sh 2>&1 | tail -2
J
       ;;
  esac
  log "refilled backlog (cycle $c)"
}

# DISK GUARD. When /workspace hits its quota every write silently produces a ZERO-BYTE
# file — including the job scripts this keeper generates. On 21 Sep that turned the loop
# into a 600-iteration spin on empty scripts with the GPU idle all night. `df` lies about
# this quota, so the only reliable test is to actually write.
space_ok() {
  dd if=/dev/zero of=/workspace/.keeper_probe bs=1M count=300 >/dev/null 2>&1
  local rc=$?
  rm -f /workspace/.keeper_probe
  return $rc
}

reclaim() {
  log "DISK FULL — reclaiming"
  find /workspace/loopwork -maxdepth 1 -name "*.log" -size +20M -delete 2>/dev/null
  # frame dumps whose video was already assembled, and probe frames older than a day
  find /workspace/loopwork -maxdepth 1 -type d \( -name "show_ep*" -o -name "sw_*" -o -name "sw2_*" \
       -o -name "probe_*" -o -name "allshots_*" \) -mmin +120 -exec rm -rf {} + 2>/dev/null
  find /workspace/loopwork -maxdepth 1 -type d -name "film*V*" -mmin +120 -exec rm -rf {} + 2>/dev/null
  log "reclaimed; free-space test $(space_ok && echo OK || echo STILL-FULL)"
}

# VRAM GUARD. ComfyUI keeps FLUX resident (~11.7 GB of a 24 GB card) between jobs, and
# a resident model is not a leak -- but Hunyuan texture paint and UniRig both want ~10 GB,
# so a queued job can OOM while the card looks half free. Ask ComfyUI to drop its models
# before handing the card to anything else; it reloads them on its next prompt.
free_comfy() {
  curl -s -m 10 -X POST http://127.0.0.1:8188/free \
       -H 'Content-Type: application/json' \
       -d '{"unload_models": true, "free_memory": true}' >/dev/null 2>&1 || true
  sleep 4
}

vram_free_mb() {
  local t u
  read t u < <(nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits | tr ',' ' ')
  echo $(( ${t:-0} - ${u:-0} ))
}

log "keeper started"
FAILS=0
while true; do
  if ! busy; then
    if ! space_ok; then
      reclaim
      if ! space_ok; then log "DISK STILL FULL — holding, not generating work"; sleep 300; continue; fi
    fi
    job=$(ls $Q/*.sh 2>/dev/null | sort | head -1)
    if [ -z "${job:-}" ]; then refill; job=$(ls $Q/*.sh 2>/dev/null | sort | head -1); fi
    # never run an empty script: that is the signature of a disk-full write
    if [ -n "${job:-}" ] && [ ! -s "$job" ]; then
      log "SKIP $(basename $job) — empty (disk was full when written)"
      rm -f "$job"; FAILS=$((FAILS+1))
      if [ $FAILS -ge 3 ]; then log "3 empty jobs in a row — backing off 10 min"; sleep 600; FAILS=0; fi
      sleep 30; continue
    fi
    if [ -n "${job:-}" ]; then
      # jobs whose name says they need the card to themselves get ComfyUI's memory back
      case "$(basename $job)" in
        *apose*|*rig*|*texture*|*tex*|*hy3d*|*upsample*|*momask*|*motion*) free_comfy ;;
      esac
      log "RUN $(basename $job) (vram free $(vram_free_mb) MB)"
      T0=$(date +%s)
      mv "$job" "$job.running" 2>/dev/null && bash "$job.running" >> $LOG 2>&1
      EL=$(( $(date +%s) - T0 ))
      mv "$job.running" "$Q/done/$(basename $job).$(date +%H%M%S)" 2>/dev/null
      log "DONE $(basename $job) in ${EL}s"
      # a real job takes minutes; instant completion means it failed
      if [ $EL -lt 5 ]; then
        FAILS=$((FAILS+1))
        log "WARNING $(basename $job) returned in ${EL}s — treating as failed ($FAILS in a row)"
        if [ $FAILS -ge 3 ]; then log "3 instant failures — backing off 10 min"; sleep 600; FAILS=0; fi
      else
        FAILS=0
      fi
    fi
  fi
  sleep 45
done
