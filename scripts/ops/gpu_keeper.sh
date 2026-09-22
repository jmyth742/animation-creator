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
  # A rotating set of experiments that always leaves something worth running. Each writes
  # its own review artifact, so a morning judgement is always possible.
  local c=$(( $(cat $STATE 2>/dev/null || echo 0) ))
  echo $(( (c + 1) % 6 )) > $STATE
  local P=series/tir-na-nog-legend/meshes/props
  case $c in
    0) cat > $Q/50_sweep_ao.sh <<'J'
cd /workspace/text-to-video
for A in 0.15 0.30 0.50; do
  bash scripts/ops/probe_shot_env.sh sw_ao$A s05 CHAR_AO=$A FILM_INTEGRATE=0.22 CHAR_HAZE_SAT=0.3
done
bash scripts/ops/contact_sheet.sh keeper_ao sw_ao0.15 sw_ao0.30 sw_ao0.50
J
       ;;
    1) cat > $Q/50_sweep_line.sh <<'J'
cd /workspace/text-to-video
for L in 1.8 2.4 3.2; do
  bash scripts/ops/probe_shot_env.sh sw_ln$L s05 FILM_LINES=$L CHAR_AO=0.35 FILM_INTEGRATE=0.22
done
bash scripts/ops/contact_sheet.sh keeper_line sw_ln1.8 sw_ln2.4 sw_ln3.2
J
       ;;
    2) cat > $Q/50_sweep_haze.sh <<'J'
cd /workspace/text-to-video
for H in 0.12 0.22 0.34; do
  bash scripts/ops/probe_shot_env.sh sw_hz$H s02_walk FILM_INTEGRATE=$H CHAR_HAZE_SAT=0.3 CHAR_AO=0.35
done
bash scripts/ops/contact_sheet.sh keeper_haze sw_hz0.12 sw_hz0.22 sw_hz0.34
J
       ;;
    3) cat > $Q/50_body_denoise.sh <<'J'
cd /workspace/text-to-video
P=series/tir-na-nog-legend/meshes/props
for D in 0.24 0.40; do
  BODY_TAG=_d$D BODY_SEED=$RANDOM /workspace/blender42/blender -b --factory-startup \
    --python scripts/blender3d/body_project.py -- $P/oisin_mv_retopo.glb oisin_mv_retopo $D \
    >> /workspace/loopwork/gpu_keeper.log 2>&1
done
J
       ;;
    4) cat > $Q/50_face_seed.sh <<'J'
cd /workspace/text-to-video
P=series/tir-na-nog-legend/meshes/props
FACE_HD_SEED=$RANDOM FACE_HD_TAG=_alt CHAR_NORMALFIX=0 /workspace/blender42/blender -b \
  --factory-startup --python scripts/blender3d/face_project_mv.py -- \
  $P/niamh_mv_retopo.glb $P/niamh_mv_face.json 1.68 niamh_mv_retopo 0.55 \
  >> /workspace/loopwork/gpu_keeper.log 2>&1
J
       ;;
    5) cat > $Q/60_probe_all_shots.sh <<'J'
cd /workspace/text-to-video
# a full contact sheet of every shot at current settings: the cheapest way to catch a
# staging or projection regression across a whole episode
W=/workspace/loopwork
for S in $(/workspace/venv/bin/python -c "import json;print(' '.join(x['name'] for x in json.load(open('$W/shots_night_sl.json'))['shots']))" 2>/dev/null); do
  bash scripts/ops/probe_shot_env.sh allshots_$S $S CHAR_AO=0.35 FILM_INTEGRATE=0.22 CHAR_HAZE_SAT=0.3
done
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
      log "RUN $(basename $job)"
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
