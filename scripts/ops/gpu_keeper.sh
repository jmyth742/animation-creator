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

log "keeper started"
while true; do
  if ! busy; then
    job=$(ls $Q/*.sh 2>/dev/null | sort | head -1)
    if [ -z "${job:-}" ]; then refill; job=$(ls $Q/*.sh 2>/dev/null | sort | head -1); fi
    if [ -n "${job:-}" ]; then
      log "RUN $(basename $job)"
      mv "$job" "$job.running" 2>/dev/null && bash "$job.running" >> $LOG 2>&1
      mv "$job.running" "$Q/done/$(basename $job).$(date +%H%M%S)" 2>/dev/null
      log "DONE $(basename $job)"
    fi
  fi
  sleep 45
done
