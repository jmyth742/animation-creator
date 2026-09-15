#!/bin/bash
# 14-hour queue: ep2 winter chapter -> hi-res ep1 master -> Shorts ->
# ambience loops -> coverage passes -> trailer material. Best-effort stages.
cd /workspace/text-to-video
S=/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad
V=/workspace/venv/bin/python
B=/workspace/blender42/blender
P=series/tir-na-nog-legend/meshes/props
log(){ echo "[$(date +%H:%M:%S)] STAGE $*"; }

log "0: snow ground texture"
timeout 400 $V scripts/blender3d/prop_sheet.py grasstex $S/unused.png grasstex 0 > /dev/null 2>&1 || true
$V - <<'PY' || true
import pathlib
p = pathlib.Path("scripts/blender3d/prop_sheet.py"); s = p.read_text()
if "snowtex" not in s:
    s = s.replace('''PROPS = {''', '''PROPS = {
    "snowtex": ("Seamless hand-painted fresh snow texture seen from directly "
                "above, soft blue-white with subtle sparkle and gentle drifts, "
                "faint footprint-free surface, fills the whole frame edge to "
                "edge, even light. Painted storybook animation style, no "
                "text, no watermark."),''')
    p.write_text(s)
PY
timeout 400 $V scripts/blender3d/prop_sheet.py snowtex series/tir-na-nog-legend/meshes/textures/snowtex.png || true

log "1: episode 2 audio (script + rhubarb)"
$V scripts/blender3d/film_lines.py $S/film2_audio $S/ep2_script.json
$V - <<'PY'
import json, subprocess
lines = json.load(open("/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/film2_audio/lines.json"))
for L in lines:
    i = L["i"]
    subprocess.run(["/workspace/venv/bin/python", "scripts/blender3d/rhubarb_visemes.py",
                    f"/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/film2_audio/l{i}.wav",
                    f"/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/film2_audio/l{i}_vis.npy",
                    str(L["frames"])], check=True)
print("ep2 viseme tracks done")
PY

log "2: build + render episode 2"
curl -s -X POST http://127.0.0.1:8188/free -H 'Content-Type: application/json' -d '{"unload_models":true,"free_memory":true}' > /dev/null
$B -b --factory-startup --python scripts/blender3d/build_film2.py -- $S/film2_audio /workspace/review/film2_first_snow.blend $S/film2_shots.json 2>&1 | grep -E "DRESSED|FILM SCENE SAVED"
$V - <<'PY' > $S/ep2_render.sh
import json
d = json.load(open("/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/film2_shots.json"))
print("set -e")
prev = 0
for s in d["shots"]:
    f0 = max(s["f0"], prev + 1); prev = s["f1"]
    out = f"/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/film2/{s['name']}"
    print(f"rm -rf {out}; mkdir -p {out}")
    print(f"/workspace/blender42/blender -b --factory-startup /workspace/review/film2_first_snow.blend "
          f"--python /workspace/text-to-video/scripts/blender3d/film.py -- {out} "
          f"\"{s['cam']}\" \"{s['tgt']}\" {s['lens']} {f0} {s['f1']} \"{s['move']}\"")
print("echo EP2_DONE")
PY
bash $S/ep2_render.sh > $S/ep2_render.log 2>&1 && log "2: ep2 shots rendered"
$V scripts/blender3d/assemble_film.py $S /workspace/review/first_snow.mp4 "The First Snow" film2 film2_shots.json film2_audio && \
ffmpeg -v error -y -i /workspace/review/first_snow.mp4 -c:v libx264 -pix_fmt yuv420p -crf 20 -af "loudnorm=I=-14:TP=-1.5:LRA=11" -c:a aac -b:a 192k -ar 48000 $S/fs.mp4 && mv $S/fs.mp4 /workspace/review/first_snow.mp4 && log "2: EPISODE 2 ASSEMBLED"

log "3: hi-res ep1 master (1664x960)"
$V - <<'PY' > $S/hires_render.sh
import json
d = json.load(open("/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/film_shots.json"))
print("set -e")
prev = 0
for s in d["shots"]:
    f0 = max(s["f0"], prev + 1); prev = s["f1"]
    out = f"/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/film_hr/{s['name']}"
    print(f"rm -rf {out}; mkdir -p {out}")
    print(f"/workspace/blender42/blender -b --factory-startup /workspace/review/film_nine_waterfalls.blend "
          f"--python /workspace/text-to-video/scripts/blender3d/film.py -- {out} "
          f"\"{s['cam']}\" \"{s['tgt']}\" {s['lens']} {f0} {s['f1']} \"{s['move']}\" 1664 960")
print("echo HIRES_DONE")
PY
bash $S/hires_render.sh > $S/hires.log 2>&1 && \
$V scripts/blender3d/assemble_film.py $S /workspace/review/nine_waterfalls_1080.mp4 "The Nine Waterfalls" film_hr film_shots.json film_audio && \
ffmpeg -v error -y -i /workspace/review/nine_waterfalls_1080.mp4 -c:v libx264 -pix_fmt yuv420p -crf 19 -af "loudnorm=I=-14:TP=-1.5:LRA=11" -c:a aac -b:a 192k -ar 48000 $S/hr.mp4 && mv $S/hr.mp4 /workspace/review/nine_waterfalls_1080.mp4 && log "3: HI-RES MASTER DONE"

log "4: Shorts (9:16 verticals)"
mkdir -p $S/shorts
i=0
while read NAME BLEND CAM TGT LENS F0 F1; do
  i=$((i+1)); D=$S/shorts/$NAME; rm -rf $D; mkdir -p $D
  $B -b --factory-startup $BLEND --python scripts/blender3d/film.py -- $D "$CAM" "$TGT" $LENS $F0 $F1 static 480 832 > /dev/null 2>&1
  ffmpeg -v error -y -framerate 16 -i $D/frame_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 20 /workspace/review/short_${NAME}.mp4 && log "4: short $NAME"
done <<'SHOTS'
n_line /workspace/review/film_nine_waterfalls.blend 0.5,7.0,1.7 -1.55,8.05,1.5 60 250 360
walkaway /workspace/review/film_nine_waterfalls.blend 0.2,2.8,1.5 3.6,15.5,1.6 32 1090 1250
petals /workspace/review/film_nine_waterfalls.blend -1.0,5.5,1.4 0.6,10,2.2 40 660 760
snow_arrive /workspace/review/film2_first_snow.blend -1.6,4.5,1.6 -0.4,9.0,1.5 40 100 200
snow_line /workspace/review/film2_first_snow.blend -0.9,9.0,1.7 0.6,10.15,1.45 60 250 360
SHOTS

log "5: ambience loops"
for CFG in "valley /workspace/review/film_nine_waterfalls.blend -6,2,1.8 -3,14,2.5" "winter /workspace/review/film2_first_snow.blend 3.5,5,1.9 0.5,12,2.4"; do
  set -- $CFG; NAME=$1; BLEND=$2; CAM=$3; TGT=$4
  D=$S/loop_$NAME; rm -rf $D; mkdir -p $D
  $B -b --factory-startup $BLEND --python scripts/blender3d/film.py -- $D "$CAM" "$TGT" 35 1 1281 static > /dev/null 2>&1
  ffmpeg -v error -y -framerate 16 -i $D/frame_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 21 $S/loop_$NAME.mp4
  ffmpeg -v error -y -stream_loop 22 -i $S/loop_$NAME.mp4 -f lavfi -t 1800 -i "anoisesrc=colour=brown:amplitude=0.03,lowpass=f=260" -c:v copy -c:a aac -shortest /workspace/review/ambience_${NAME}_30min.mp4 && log "5: ambience $NAME"
done

log "6: B-cam coverage of both films (MV cast)"
for FILM in "film_shots.json /workspace/review/film_nine_waterfalls.blend bcam_ep1" "film2_shots.json /workspace/review/film2_first_snow.blend bcam_ep2"; do
  set -- $FILM; SJ=$1; BLEND=$2; TAG=$3
  $V - "$SJ" "$BLEND" "$TAG" <<'PY' > $S/cov_$TAG.sh
import json, sys
sj, blend, tag = sys.argv[1:4]
d = json.load(open(f"/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/{sj}"))
print("set -e")
prev = 0
for s in d["shots"]:
    f0 = max(s["f0"], prev + 1); prev = s["f1"]
    cam = [float(v) for v in s["cam"].split(",")]
    tgt = [float(v) for v in s["tgt"].split(",")]
    cam2 = [cam[0] + 0.3 * (tgt[0] - cam[0]) - 1.1, cam[1] + 0.3 * (tgt[1] - cam[1]) + 0.5, cam[2] + 0.3]
    out = f"/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/{tag}/{s['name']}"
    print(f"mkdir -p {out}")
    print(f"/workspace/blender42/blender -b --factory-startup {blend} "
          f"--python /workspace/text-to-video/scripts/blender3d/film.py -- {out} "
          f"\"{cam2[0]:.2f},{cam2[1]:.2f},{cam2[2]:.2f}\" \"{s['tgt']}\" {min(70, s['lens'] + 8)} {f0} {s['f1']} static")
print(f"echo {tag}_DONE")
PY
  bash $S/cov_$TAG.sh > $S/$TAG.log 2>&1 && log "6: $TAG done"
done

log "7: trailer material — best-moment supercut"
i=0; rm -rf $S/trailseq; mkdir -p $S/trailseq
for CLIP in "$S/film/s01_est 20 60" "$S/film2/s01_est 20 60" "$S/film/s02_walk 130 180" "$S/film2/s07_beat 670 705" "$S/film/s11_away 1150 1230"; do
  set -- $CLIP; D=$1; A=$2; Z=$3
  for f in $(seq $A $Z); do
    FP=$(printf "%s/frame_%04d.png" $D $f)
    [ -f "$FP" ] && { i=$((i+1)); ln -sf $FP $S/trailseq/t_$(printf %05d $i).png; }
  done
done
ffmpeg -v error -y -framerate 16 -i $S/trailseq/t_%05d.png -c:v libx264 -pix_fmt yuv420p -crf 20 /workspace/review/trailer_material.mp4 && log "7: trailer material"
log "NIGHT14 DONE"
