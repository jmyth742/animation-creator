# ─────────────────────────────────────────────────────────────────────
#  Overnight: produce the best cohesive episode we can
#
#  Order matters. ep03 renders first at 480p as the cohesive baseline
#  (one sampler, one guidance, portrait-seeded identity, no cross-family
#  LoRAs). Then, only if the 720p S2V probe actually succeeded, the same
#  episode renders again at 720p so the two can be compared like for like.
#
#  Both passes finish through refresh_subtitles, which now lays audio on
#  MEASURED clip durations -- S2V sizes clips to their audio and clamps at
#  97 frames, so a dialogue shot lands 1-2.5s off its nominal slot and the
#  old nominal-slot timeline put sound and subtitles seconds adrift.
# ─────────────────────────────────────────────────────────────────────
SERIES="tir-na-nog-legend"
SR="python scripts/showrunner.py"

NEEDS_COMFY=0
step "wait-480p" '
    for J in .jobs/drama-ep03 .jobs/s2v-720p-test; do
        [ -d "$J" ] || continue
        while true; do
            s=$(cat "$J/state" 2>/dev/null || echo unknown)
            p=$(cat "$J/pid" 2>/dev/null)
            if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then sleep 180; continue; fi
            [ "$s" = "running" ] && { sleep 180; continue; }
            echo "$(basename $J): $s"; break
        done
    done'

# ─── Rebuild the 480p cut on the corrected timeline ──────────────────
step "finish-480p" "python scripts/refresh_subtitles.py $SERIES --episode 3 \
                        --music music.mp3 --interpolate 3"
step "publish-480p" "
    mkdir -p /workspace/review/drama
    cp output/$SERIES/ep03/ep03_final.mp4       /workspace/review/drama/ep03_480p.mp4
    cp output/$SERIES/ep03/ep03_final_48fps.mp4 /workspace/review/drama/ep03_480p_48fps.mp4 2>/dev/null || true
    cp output/$SERIES/ep03/ep03.srt             /workspace/review/drama/ep03_480p.srt 2>/dev/null || true
    ls -lh /workspace/review/drama/"

# ─── 720p pass, only if the probe proved S2V survives it ─────────────
NEEDS_COMFY=1
step "720p-gate-DISABLED" '
    J=/workspace/review/shot_tests/ep02_s05_resolution.json
    if [ ! -f "$J" ]; then echo "no 720p probe result — skipping the 720p pass"; exit 0; fi
    python3 -c "
import json,sys
d=json.load(open(\"$J\"))
ok=[v for v in d if v[\"variant\"].startswith(\"r720\") and v[\"ok\"]]
print(\"  720p S2V probe:\", \"PASSED\" if ok else \"FAILED\")
sys.exit(0 if ok else 3)
" || { echo "720p not viable on this card — 480p stays the deliverable"; exit 0; }'

step "render-720p-DISABLED" '
    J=/workspace/review/shot_tests/ep02_s05_resolution.json
    if [ -f "$J" ] && python3 -c "
import json,sys; d=json.load(open(\"$J\"))
sys.exit(0 if [v for v in d if v[\"variant\"].startswith(\"r720\") and v[\"ok\"]] else 1)"; then
        V=ComfyUI/output/video/tir-na-nog-legend
        mkdir -p $V/ep03-480p && for f in $V/ep03_s*.mp4; do [ -f "$f" ] && mv "$f" $V/ep03-480p/; done
        python scripts/showrunner.py produce tir-na-nog-legend --episode 3 --quality good \
            --optimization balanced --no-char-loras --resolution 720p
    else
        echo "skipped (720p probe did not pass)"
    fi'

NEEDS_COMFY=0
step "finish-720p-DISABLED" '
    V=ComfyUI/output/video/tir-na-nog-legend
    if ls $V/ep03_s*.mp4 >/dev/null 2>&1; then
        python scripts/refresh_subtitles.py tir-na-nog-legend --episode 3 \
            --music music.mp3 --interpolate 3
        cp output/tir-na-nog-legend/ep03/ep03_final.mp4       /workspace/review/drama/ep03_720p.mp4
        cp output/tir-na-nog-legend/ep03/ep03_final_48fps.mp4 /workspace/review/drama/ep03_720p_48fps.mp4 2>/dev/null || true
    else
        echo "no 720p clips — nothing to finish"
    fi'

step "report" "
    echo '--- deliverables ---'; ls -lh /workspace/review/drama/
    for f in /workspace/review/drama/*.mp4; do
        printf '  %-30s ' \"\$(basename \$f)\"
        ffprobe -v error -select_streams v:0 -show_entries stream=width,height,duration \
            -of csv=p=0 \"\$f\"
    done"
