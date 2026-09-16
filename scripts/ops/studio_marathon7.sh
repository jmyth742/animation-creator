#!/bin/bash
# DAY 4 (shift 7): the motion library. MoMask (MIT) text->motion->BVH, retargeted
# by rest-pose deltas onto the UniRig rigs (Day-2 win), rendered per motion for
# both leads; acting A/B: procedural gait vs retargeted walk. HY-Motion-Lite
# (24 GB min) does not fit beside anything on this card — noted, not run.
# Launch: bash /workspace/go7.sh
set -u
cd /workspace/text-to-video
W=/workspace/loopwork; V=/workspace/venv/bin/python; B=/workspace/blender42/blender
R=/workspace/review; D4=$W/day4; mkdir -p $D4; E=/workspace/envs/momask; M=/workspace/momask-codes
log(){ echo "[m7 $(date +%H:%M:%S)] $*"; }
export_pass(){ bash /workspace/export_outcomes.sh 2>&1 | tail -1; }
export HF_HOME=/workspace/hf_cache

log "P1: MoMask install (idempotent)"
bash scripts/day4/install_momask.sh > $W/m7_install.log 2>&1; log "P1: $(grep -E '^INSTALL' $W/m7_install.log | tail -1)"
grep -q "INSTALL momask OK" $W/m7_install.log || { log "DAY4 ABORT: MoMask install failed"; tail -15 $W/m7_install.log; exit 1; }

log "P2: generate the motion library (10 prompts x 2 takes) -> BVH @20fps"
cd $M; rm -rf generation/day4
$E/bin/python gen_t2m.py --gpu_id 0 --ext day4 --text_path /workspace/text-to-video/scripts/day4/prompts.txt --repeat_times 2 > $W/m7_gen.log 2>&1 || log "gen_t2m exited non-zero: $(grep -m1 -iE 'error' $W/m7_gen.log | cut -c1-160)"
cd /workspace/text-to-video
find $M/generation/day4 -name '*.bvh' | sort > $D4/bvh_list.txt; log "P2: $(wc -l < $D4/bvh_list.txt) BVH files"
[ -s $D4/bvh_list.txt ] || { log "DAY4 ABORT: no BVH produced"; tail -20 $W/m7_gen.log; exit 1; }
export_pass

log "P3: retarget every motion onto both leads (one take each, the _ik variant), render"
NAMES=(walk sadwalk run idle turn sit kneel point hug wave)
i=0
for D in $(ls -d $M/generation/day4/animations/*/ | sort); do
  NAME=${NAMES[$i]:-m$i}; i=$((i+1))
  BVH=$(ls $D/*repeat0*_ik.bvh 2>/dev/null | head -1); [ -n "$BVH" ] || BVH=$(ls $D/*.bvh | head -1)
  cp "$BVH" $D4/$NAME.bvh
  for WHO in oisin_mv niamh_mv; do
    $B -b --factory-startup --python scripts/day4/retarget.py -- $W/day2/${WHO}_rigged.glb $D4/$NAME.bvh $D4/r_${NAME}_$WHO ${NAME}_$WHO 20 1 < /dev/null > $W/m7_rt_${NAME}_$WHO.log 2>&1 &
  done; wait
  for WHO in oisin_mv niamh_mv; do
    grep -E "^RETARGET (pairs|keyed|DONE)|Error" $W/m7_rt_${NAME}_$WHO.log | head -3 | cut -c1-160
    N=$(ls $D4/r_${NAME}_$WHO/${NAME}_${WHO}_*.png 2>/dev/null | wc -l)
    [ "$N" -gt 0 ] && ffmpeg -v error -y -framerate 20 -i $D4/r_${NAME}_$WHO/${NAME}_${WHO}_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 19 $R/day4_motion_${NAME}_$WHO.mp4 && log "day4_motion_${NAME}_$WHO.mp4 ($N frames)"
  done
done
# contact sheet: frame 40% into each motion, Oisin row over Niamh row
for WHO in oisin_mv niamh_mv; do IN=""; for NAME in "${NAMES[@]}"; do F=$(ls $D4/r_${NAME}_$WHO/*.png 2>/dev/null | sort | awk '{a[NR]=$0} END{print a[int(NR*0.4)+1]}'); [ -n "$F" ] && IN="$IN -i $F"; done
  [ -n "$IN" ] && ffmpeg -v error -y $IN -filter_complex "hstack=inputs=$(echo $IN | grep -o '\-i' | wc -l)" $D4/sheet_$WHO.png; done
[ -f $D4/sheet_oisin_mv.png ] && [ -f $D4/sheet_niamh_mv.png ] && ffmpeg -v error -y -i $D4/sheet_oisin_mv.png -i $D4/sheet_niamh_mv.png -filter_complex vstack $R/day4_motion_library_sheet.png && log "day4_motion_library_sheet.png"
export_pass

log "P4: acting A/B — procedural gait (current) | MoMask walk retargeted"
for CFG in "oisin_mv 1.75" "niamh_mv 1.68"; do set -- $CFG; WHO=$1; H=$2
  $B -b --factory-startup --python scripts/day4/gait_ab.py -- $WHO $H $D4/g_$WHO proc_$WHO 48 < /dev/null > $W/m7_gait_$WHO.log 2>&1
  ffmpeg -v error -y -framerate 16 -i $D4/g_$WHO/proc_${WHO}_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 19 $D4/proc_$WHO.mp4
  [ -f $R/day4_motion_walk_$WHO.mp4 ] && ffmpeg -v error -y -i $D4/proc_$WHO.mp4 -i $R/day4_motion_walk_$WHO.mp4 -filter_complex "[0]scale=640:480[a];[1]scale=640:480[b];[a][b]hstack" -c:v libx264 -pix_fmt yuv420p -crf 19 $R/day4_gait_ab_$WHO.mp4 && log "day4_gait_ab_$WHO.mp4 (procedural | MoMask)"
done
export_pass
for d in $D4/r_*/; do find $d -name "*.png" -delete; done; rm -rf $D4/g_*/   # frame dumps only (keep the .glb rigs)
log "DAY4 DONE — judge: day4_motion_library_sheet.png, day4_motion_*.mp4, day4_gait_ab_*.mp4 — animated rigs for Day 5 in $D4/r_*/*.glb"
