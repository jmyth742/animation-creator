#!/usr/bin/env bash
# =============================================================================
# Dataset Preparation Helper
# Extracts character portraits from your existing project to use as training data
#
# Usage: bash scripts/prepare_dataset.sh <project-slug> <type>
#   type: "characters" — extract all canonical character portraits
#         "style"      — extract scene references + episode frames as style refs
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRAINING_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$TRAINING_DIR")"

SLUG="${1:?Usage: prepare_dataset.sh <project-slug> <type>}"
TYPE="${2:?Usage: prepare_dataset.sh <project-slug> characters|style}"

SERIES_DIR="$PROJECT_DIR/series/$SLUG"
COMFYUI_OUTPUT="$PROJECT_DIR/ComfyUI/output"

if [ ! -d "$SERIES_DIR" ]; then
    echo "Error: Series directory not found: $SERIES_DIR"
    echo "Available series:"
    ls "$PROJECT_DIR/series/" 2>/dev/null || echo "  (none)"
    exit 1
fi

case "$TYPE" in
    characters)
        DATASET_DIR="$TRAINING_DIR/datasets/characters_$SLUG"
        mkdir -p "$DATASET_DIR"

        echo "Extracting character portraits from $SLUG..."
        count=0

        # Find canonical character images (char_*.png in series dir)
        for img in "$SERIES_DIR"/char_*.png; do
            [ -f "$img" ] || continue
            name=$(basename "$img" .png)
            cp "$img" "$DATASET_DIR/${name}.png"

            # Create a placeholder caption from the bible.json if available
            if [ -f "$SERIES_DIR/bible.json" ]; then
                # Extract character visual description from bible
                char_id=$(echo "$name" | sed 's/char_//')
                python3 -c "
import json, sys
with open('$SERIES_DIR/bible.json') as f:
    bible = json.load(f)
for c in bible.get('characters', []):
    if str(c.get('id')) == '$char_id':
        visual = c.get('visual_description', c.get('description', ''))
        char_name = c.get('name', '')
        print(f'{char_name}, {visual}')
        break
" > "$DATASET_DIR/${name}.txt" 2>/dev/null || echo "Character portrait" > "$DATASET_DIR/${name}.txt"
            else
                echo "Character portrait" > "$DATASET_DIR/${name}.txt"
            fi

            count=$((count + 1))
            echo "  Extracted: $name"
        done

        # Also grab reference images from ComfyUI output
        for img in "$COMFYUI_OUTPUT/refs/"*"$SLUG"*.png; do
            [ -f "$img" ] || continue
            name=$(basename "$img" .png)
            cp "$img" "$DATASET_DIR/${name}.png"
            echo "Reference image for $SLUG" > "$DATASET_DIR/${name}.txt"
            count=$((count + 1))
        done

        echo ""
        echo "Extracted $count images to: $DATASET_DIR"
        echo ""
        echo "IMPORTANT: Review and edit the .txt caption files!"
        echo "Good captions are critical for LoRA quality."
        echo "Format: 'trigger_word, detailed visual description of the character'"
        ;;

    style)
        DATASET_DIR="$TRAINING_DIR/datasets/style_$SLUG"
        mkdir -p "$DATASET_DIR"

        echo "Extracting style references from $SLUG..."
        count=0

        # Grab scene references
        for img in "$COMFYUI_OUTPUT/refs/"*.png; do
            [ -f "$img" ] || continue
            name=$(basename "$img" .png)
            cp "$img" "$DATASET_DIR/${name}.png"
            echo "Animated scene reference, stylized" > "$DATASET_DIR/${name}.txt"
            count=$((count + 1))
        done

        # Grab continuity frames (end frames from episodes)
        for img in "$SERIES_DIR/continuity/"*.png; do
            [ -f "$img" ] || continue
            name=$(basename "$img" .png)
            cp "$img" "$DATASET_DIR/continuity_${name}.png"
            echo "Animated scene frame, stylized" > "$DATASET_DIR/continuity_${name}.txt"
            count=$((count + 1))
        done

        echo ""
        echo "Extracted $count images to: $DATASET_DIR"
        echo ""
        echo "IMPORTANT: Review and edit the .txt caption files!"
        echo "Describe the visual style you want the LoRA to learn."
        ;;

    *)
        echo "Unknown type: $TYPE"
        echo "Usage: prepare_dataset.sh <project-slug> characters|style"
        exit 1
        ;;
esac
