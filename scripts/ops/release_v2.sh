#!/bin/bash
# Release package v2: ep3 SRT + metadata, 3-episode pilot, 60 s trailer v2 cut from the masters.
# Waits for the Episode 3 master. Sources: the 480p verdict masters (v3cast, v3cast, v1).
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review; V=/workspace/venv/bin/python
log(){ echo "[release $(date +%H:%M:%S)] $*"; }
until [ -s $R/farewell_cliff_v1.mp4 ] && ! ps -eo args | grep -q "[e]p3_v2master.sh"; do sleep 60; done
E1=$R/nine_waterfalls_v3cast.mp4; E2=$R/first_snow_v3cast.mp4; E3=$R/farewell_cliff_v1.mp4
log "1: ep3 subtitles + metadata"
$V - <<'PY'
import json
FPS = 16
def ts(sec):
    h = int(sec // 3600); m = int(sec % 3600 // 60); s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")
d = json.load(open("/workspace/loopwork/film3_shots.json")); lines = json.load(open("/workspace/loopwork/film3_audio/lines.json"))
srt = []
for k, (L, f0) in enumerate(zip(lines, d["line_starts"]), start=1):
    a = (f0 - 1) / FPS + 5.0 / FPS; b = a + L["seconds"]
    srt.append(f"{k}\n{ts(a)} --> {ts(b)}\n{L['who'].title()}: {L['text']}\n")
open("/workspace/review/farewell_cliff.srt", "w").write("\n".join(srt))
open("/workspace/review/metadata_farewell_cliff.md", "w").write("""# Tir na nOg — The Farewell Cliff (Episode 3)

## Description
There is a boat on the shore that was not there yesterday. Oisin looks west, and Niamh lets him go — with one warning: do not let your feet touch that ground.

Episode 3 of the Tir na nOg series — the legend's turn, on the cliff above the sea.

#animation #indieanimation #blender #irishmythology #tirnanog

## Tags
animation, blender, irish mythology, tir na nog, oisin, niamh, embarr, animated short, celtic
""")
print("  srt + metadata written")
PY
log "2: pilot v2 — three episodes back to back"
for F in $E1 $E2 $E3; do ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate -select_streams v:0 -of csv=p=0 $F; done | sort | uniq -c
printf "file '%s'\nfile '%s'\nfile '%s'\n" $E1 $E2 $E3 > $W/pilot2.txt
ffmpeg -v error -y -f concat -safe 0 -i $W/pilot2.txt -c:v libx264 -pix_fmt yuv420p -crf 20 -c:a aac -b:a 192k -ar 48000 $R/pilot_v2_ep1_ep2_ep3.mp4 && log "pilot_v2_ep1_ep2_ep3.mp4 ($(ffprobe -v error -show_entries format=duration -of csv=p=0 $R/pilot_v2_ep1_ep2_ep3.mp4)s)"
log "3: trailer v2 — moments from all three masters (global frame -> seconds, +5-frame card)"
$V - <<'PY' > $W/trailer2_cut.txt
import json
FPS = 16.0
picks = [("nine_waterfalls_v3cast", "film_shots.json", "s01_est", 0.6, 0.98), ("first_snow_v3cast", "film2_shots.json", "s01_est", 0.6, 0.98),
         ("farewell_cliff_v1", "film3_shots.json", "s01_est", 0.78, 0.99), ("nine_waterfalls_v3cast", "film_shots.json", "s02_walk", 0.1, 0.9),
         ("farewell_cliff_v1", "film3_shots.json", "s03_meet", 0.0, 1.0), ("first_snow_v3cast", "film2_shots.json", "s05", 0.2, 0.6),
         ("nine_waterfalls_v3cast", "film_shots.json", "s04", 0.2, 0.55), ("farewell_cliff_v1", "film3_shots.json", "s07b", 0.0, 0.8),
         ("first_snow_v3cast", "film2_shots.json", "s07_beat", 0.0, 1.0), ("nine_waterfalls_v3cast", "film_shots.json", "s07a", 0.3, 0.8),
         ("farewell_cliff_v1", "film3_shots.json", "s05", 0.25, 0.7), ("first_snow_v3cast", "film2_shots.json", "s11_away", 0.3, 0.8),
         ("nine_waterfalls_v3cast", "film_shots.json", "s10_beat", 0.0, 1.0), ("farewell_cliff_v1", "film3_shots.json", "s11_away", 0.2, 0.95)]
for master, sj, name, a, z in picks:
    d = json.load(open(f"/workspace/loopwork/{sj}")); s = [x for x in d["shots"] if x["name"] == name][0]
    # the assembled film plays shots in list order with edit-order frames = cumulative; use cumulative offsets
    off = 5; t0 = None
    for x in d["shots"]:
        n = x["f1"] - x["f0"] + 1
        if x["name"] == name: t0 = off; break
        off += n
    n = s["f1"] - s["f0"] + 1
    print(master, round((t0 + a * n) / FPS, 3), round((z - a) * n / FPS, 3))
PY
i=0; ARGS=""; FC=""
while read M T0 DUR; do i=$((i+1)); ffmpeg -nostdin -v error -y -ss $T0 -t $DUR -i $R/$M.mp4 -an -c:v libx264 -pix_fmt yuv420p -crf 18 $W/tr2_$i.mp4; ARGS="$ARGS -i $W/tr2_$i.mp4"; FC="$FC[$((i-1))]"; done < $W/trailer2_cut.txt
FONT=/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf
ffmpeg -v error -y $ARGS -f lavfi -t 60 -i "anoisesrc=colour=brown:amplitude=0.03,lowpass=f=260" -filter_complex "${FC}concat=n=$i:v=1:a=0,colorbalance=rh=0.06:gh=0.02:bh=-0.08,vignette=PI/5.2,drawtext=fontfile=$FONT:text='TIR NA NOG':fontcolor=white:fontsize=58:x=(w-text_w)/2:y=h*0.42:enable='lt(t,3.5)':alpha='if(lt(t,1),t,if(lt(t,2.8),1,3.5-t))',drawtext=fontfile=$FONT:text='THREE EPISODES':fontcolor=white:fontsize=34:x=(w-text_w)/2:y=h*0.56:enable='between(t,1.2,3.5)'[v]" -map "[v]" -map $i:a -shortest -c:v libx264 -pix_fmt yuv420p -crf 19 -c:a aac $R/trailer_v2.mp4 && log "trailer_v2.mp4 ($(ffprobe -v error -show_entries format=duration -of csv=p=0 $R/trailer_v2.mp4)s)"
rm -f $W/tr2_*.mp4
bash /workspace/export_outcomes.sh 2>&1 | tail -1
log "RELEASE V2 DONE"
