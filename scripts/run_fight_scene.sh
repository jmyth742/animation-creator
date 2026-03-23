#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Anime Fight Scene — 4 clips × 5 seconds ==="
echo ""

OUTPUT_DIR="ComfyUI/output/video"

for i in 1 2 3 4; do
    echo "--- Generating clip $i/4 ---"
    python scripts/comfyui_api_gen.py "workflows/fight_scene_clip${i}.json"
    echo ""
done

echo "=== All clips generated. Stitching with ffmpeg... ==="

# Find the most recent fight_clip files
CONCAT_FILE=$(mktemp /tmp/fight_concat_XXXX.txt)
for i in 1 2 3 4; do
    # Get the latest file matching the prefix
    LATEST=$(ls -t "${OUTPUT_DIR}/fight_clip${i}"*.mp4 2>/dev/null | head -1)
    if [ -z "$LATEST" ]; then
        echo "ERROR: Could not find output for clip $i"
        exit 1
    fi
    echo "file '$(realpath "$LATEST")'" >> "$CONCAT_FILE"
    echo "  Clip $i: $LATEST"
done

FINAL="${OUTPUT_DIR}/fight_scene_final.mp4"
ffmpeg -y -f concat -safe 0 -i "$CONCAT_FILE" -c copy "$FINAL" 2>/dev/null

rm "$CONCAT_FILE"

echo ""
echo "=== Done! Final video: $FINAL ==="
echo "    Duration: ~20 seconds (4 × 5s clips)"
echo "    Resolution: 480×320"
