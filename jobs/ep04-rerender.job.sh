# ─────────────────────────────────────────────────────────────────────
#  ep04, re-rendered with two prompt fixes
#
#  The first pass regressed on coherence: roughly seven of seventeen shots
#  came back as different people in modern interiors. Two causes, both in
#  how the prompt was built rather than in the models:
#
#    1. build_scene_prompt SKIPPED the location entirely for close-up
#       dialogue. With no setting specified the model invents one, so
#       "tight close-up, lips visible" produced studio portraits. Close-ups
#       now carry a short out-of-focus setting cue.
#    2. The shot descriptions used crew shorthand -- "facing SCREEN RIGHT",
#       "brow to chin" -- which a diffusion model does not parse. Rewritten
#       as plain description.
#
#  Keeps everything that worked: authored shot lengths as a floor, tight
#  dialogue framing (which won the lip-sync test), timeline audio, music.
# ─────────────────────────────────────────────────────────────────────
SERIES="tir-na-nog-legend"

NEEDS_COMFY=1
step "park-v1" '
    V=ComfyUI/output/video/tir-na-nog-legend
    mkdir -p $V/ep04-v1
    for f in $V/ep04_s*.mp4; do [ -f "$f" ] && mv "$f" $V/ep04-v1/; done
    echo "parked $(ls $V/ep04-v1/*.mp4 2>/dev/null | wc -l) clips from the first pass"'

step "preflight" "python scripts/preflight.py $SERIES --episode 4"

step "render" "python scripts/showrunner.py produce $SERIES --episode 4 \
                   --quality good --optimization balanced --no-char-loras"

NEEDS_COMFY=0
step "finish" "python scripts/refresh_subtitles.py $SERIES --episode 4 \
                   --music music.mp3 --interpolate 3"

step "publish" "
    mkdir -p /workspace/review/drama
    cp output/$SERIES/ep04/ep04_final.mp4       /workspace/review/drama/ep04_v2_fixed.mp4
    cp output/$SERIES/ep04/ep04_final_48fps.mp4 /workspace/review/drama/ep04_v2_fixed_48fps.mp4 2>/dev/null || true
    ls -lh /workspace/review/drama/"

step "contact-sheet" '
    D=/workspace/review/drama; V=ComfyUI/output/video/tir-na-nog-legend
    T=$(mktemp -d); i=1
    for f in $(ls $V/ep04_s*.mp4 | sort); do
        d=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$f")
        ffmpeg -v error -y -ss $(python3 -c "print(f\"{$d/2:.2f}\")") -i "$f" \
            -frames:v 1 "$T/$(printf %02d $i).png"; i=$((i+1))
    done
    ffmpeg -v error -y -framerate 1 -pattern_type glob -i "$T/*.png" \
        -vf "scale=400:231,tile=6x3:margin=5:padding=4:color=black" -frames:v 1 \
        $D/ep04_v2_contact.png && echo "contact sheet built"
    rm -rf $T'
