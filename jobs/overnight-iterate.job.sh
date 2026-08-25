# ─────────────────────────────────────────────────────────────────────
#  Overnight iteration — roughly 9 hours, unattended
#
#    1. wait for ep03 (the cohesive 480p baseline) and the lip-sync test
#    2. score the four lip-sync variants objectively and pick a winner
#    3. render ep04 with the winning S2V step count -- ep04 already frames
#       every dialogue shot tight and applies the 180-degree rule
#    4. finish it on measured offsets, with music and 48fps
#    5. assemble a side-by-side of ep03 vs ep04 for the morning
#
#  720p is deliberately absent: it cost 2.75x and came back smoother, not
#  sharper. Resolution was not the lip-sync lever.
# ─────────────────────────────────────────────────────────────────────
SERIES="tir-na-nog-legend"
SR="python scripts/showrunner.py"

NEEDS_COMFY=0
step "wait-prereqs" '
    for J in .jobs/drama-ep03 .jobs/lipsync-test .jobs/overnight-quality; do
        [ -d "$J" ] || continue
        while true; do
            s=$(cat "$J/state" 2>/dev/null || echo unknown)
            p=$(cat "$J/pid" 2>/dev/null)
            if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then sleep 180; continue; fi
            [ "$s" = "running" ] && { sleep 180; continue; }
            echo "$(basename $J): $s"; break
        done
    done'

step "score-lipsync" "python scripts/score_lipsync.py || echo 'scoring failed — ep04 will use 25 steps'"

NEEDS_COMFY=1
step "render-ep04" '
    W=/workspace/review/lipsync/winner.json
    STEPS=25
    if [ -f "$W" ]; then
        STEPS=$(python3 -c "import json;print(json.load(open(\"$W\"))[\"steps\"])" 2>/dev/null || echo 25)
    fi
    echo "rendering ep04 with S2V steps=$STEPS"
    # --quality maps to step counts; pick the preset matching the winner
    Q=good; [ "$STEPS" = "40" ] && Q=final
    python scripts/showrunner.py produce tir-na-nog-legend --episode 4 \
        --quality $Q --optimization balanced --no-char-loras'

NEEDS_COMFY=0
step "finish-ep04" "python scripts/refresh_subtitles.py $SERIES --episode 4 \
                        --music music.mp3 --interpolate 3"

step "publish" "
    mkdir -p /workspace/review/drama
    cp output/$SERIES/ep03/ep03_final.mp4       /workspace/review/drama/ep03_baseline.mp4 2>/dev/null || true
    cp output/$SERIES/ep03/ep03_final_48fps.mp4 /workspace/review/drama/ep03_baseline_48fps.mp4 2>/dev/null || true
    cp output/$SERIES/ep04/ep04_final.mp4       /workspace/review/drama/ep04_coverage.mp4 2>/dev/null || true
    cp output/$SERIES/ep04/ep04_final_48fps.mp4 /workspace/review/drama/ep04_coverage_48fps.mp4 2>/dev/null || true
    cp /workspace/review/lipsync/winner.json    /workspace/review/drama/ 2>/dev/null || true
    ls -lh /workspace/review/drama/"

step "compare" '
    D=/workspace/review/drama
    for e in ep03_baseline ep04_coverage; do
        F=$D/$e.mp4
        [ -f "$F" ] || continue
        d=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$F")
        n=1
        rm -f /tmp/cmp_${e}_*.png
        for k in 1 2 3 4 5 6; do
            t=$(python3 -c "print(f\"{$d*$k/7:.2f}\")")
            ffmpeg -v error -y -ss $t -i "$F" -frames:v 1 -vf scale=320:-1 /tmp/cmp_${e}_$k.png
        done
        ffmpeg -v error -y -i /tmp/cmp_${e}_1.png -i /tmp/cmp_${e}_2.png -i /tmp/cmp_${e}_3.png \
               -i /tmp/cmp_${e}_4.png -i /tmp/cmp_${e}_5.png -i /tmp/cmp_${e}_6.png \
               -filter_complex "[0:v][1:v][2:v][3:v][4:v][5:v]hstack=6" $D/${e}_strip.png
    done
    ls -1 $D/*.png 2>/dev/null'
