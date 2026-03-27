#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════
# Prepare a character dataset for LoRA training
#
# Usage:
#   bash runpod/prepare_dataset.sh /path/to/raw/images my_character "ohwx woman"
#
# This script:
#   1. Creates the dataset directory structure
#   2. Resizes images to training resolution
#   3. Generates caption templates (you'll need to refine them)
# ═══════════════════════════════════════════════════════════════════

INPUT_DIR="${1:?Usage: prepare_dataset.sh /path/to/images character_name trigger_word}"
CHARACTER_NAME="${2:?Usage: prepare_dataset.sh /path/to/images character_name trigger_word}"
TRIGGER="${3:?Usage: prepare_dataset.sh /path/to/images character_name trigger_word}"

VOLUME="/workspace"
DATASET_DIR="$VOLUME/datasets/$CHARACTER_NAME"
mkdir -p "$DATASET_DIR"

echo "═══════════════════════════════════════════════"
echo "  Preparing dataset: $CHARACTER_NAME"
echo "  Trigger word: $TRIGGER"
echo "  Input: $INPUT_DIR"
echo "  Output: $DATASET_DIR"
echo "═══════════════════════════════════════════════"

COUNT=0
for img in "$INPUT_DIR"/*.{png,jpg,jpeg,webp} 2>/dev/null; do
    [ -f "$img" ] || continue
    COUNT=$((COUNT + 1))
    BASENAME=$(printf "%s_%03d" "$CHARACTER_NAME" "$COUNT")
    EXT="${img##*.}"

    # Copy/resize image
    ffmpeg -y -i "$img" -vf "scale='if(gt(iw,960),960,iw)':'if(gt(ih,960),960,ih)':force_original_aspect_ratio=decrease" \
        "$DATASET_DIR/${BASENAME}.png" 2>/dev/null

    # Generate caption template
    cat > "$DATASET_DIR/${BASENAME}.txt" << EOF
$TRIGGER, [DESCRIBE POSE/ACTION], [DESCRIBE EXPRESSION], [DESCRIBE CLOTHING], [DESCRIBE BACKGROUND/SETTING]
EOF

    echo "  Processed: $(basename "$img") → ${BASENAME}.png"
done

# Handle videos if present
for vid in "$INPUT_DIR"/*.mp4 2>/dev/null; do
    [ -f "$vid" ] || continue
    COUNT=$((COUNT + 1))
    BASENAME=$(printf "%s_%03d" "$CHARACTER_NAME" "$COUNT")

    cp "$vid" "$DATASET_DIR/${BASENAME}.mp4"

    cat > "$DATASET_DIR/${BASENAME}.txt" << EOF
$TRIGGER, [DESCRIBE ACTION/MOTION], [DESCRIBE SCENE], [DESCRIBE CAMERA MOVEMENT]
EOF

    echo "  Copied video: $(basename "$vid") → ${BASENAME}.mp4"
done

echo ""
echo "═══════════════════════════════════════════════"
echo "  Dataset prepared: $COUNT files"
echo "  Location: $DATASET_DIR"
echo "═══════════════════════════════════════════════"

# ── Auto-captioning with Florence-2 (optional) ─────────────────────
AUTO_CAPTION="${4:-auto}"  # "auto", "skip", or "only"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ "$AUTO_CAPTION" = "skip" ]; then
    echo ""
    echo "  Auto-captioning skipped (pass 'auto' as 4th arg to enable)."
    echo ""
    echo "  MANUAL CAPTIONING:"
    echo "  1. Edit captions in $DATASET_DIR/*.txt"
    echo "     Replace [PLACEHOLDERS] with actual descriptions."
    echo "     Keep the trigger word '$TRIGGER' at the start of each."
elif command -v python3 &>/dev/null && python3 -c "import transformers" 2>/dev/null; then
    echo ""
    echo "  Running Florence-2 auto-captioning..."
    python3 "$SCRIPT_DIR/scripts/auto_caption.py" "$DATASET_DIR" \
        --trigger "$TRIGGER" --force
    echo ""
    echo "  Captions generated! Review and refine in $DATASET_DIR/*.txt"
    echo "  Tip: captions should describe visual appearance, not personality."
else
    echo ""
    echo "  Florence-2 not available (install: pip install transformers)."
    echo "  To auto-caption later:"
    echo "    python scripts/auto_caption.py $DATASET_DIR --trigger \"$TRIGGER\" --force"
    echo ""
    echo "  MANUAL CAPTIONING:"
    echo "  1. Edit captions in $DATASET_DIR/*.txt"
    echo "     Replace [PLACEHOLDERS] with actual descriptions."
    echo "     Keep the trigger word '$TRIGGER' at the start of each."
fi

echo ""
echo "  Aim for 15-30 images with varied:"
echo "     - Poses (standing, sitting, walking, close-up)"
echo "     - Expressions (smiling, serious, surprised)"
echo "     - Angles (front, side, 3/4 view)"
echo "     - Lighting (indoor, outdoor, warm, cool)"
echo ""
echo "  When captions are ready, train:"
echo "     bash runpod/train_lora.sh $DATASET_DIR $CHARACTER_NAME"
echo "═══════════════════════════════════════════════"
