#!/bin/bash
# GPU utilisation sampler: one line a minute, so the improvement status can show the
# card's REAL duty cycle rather than "a job was running". epoch,util%,mem_MiB
OUT=/workspace/loopwork/gpu_util.csv; echo $$ > /workspace/loopwork/gpu_util.pid
while true; do
  echo "$(date +%s),$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits | tr -d ' ')" >> $OUT
  sleep 60
done
