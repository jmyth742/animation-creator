#!/bin/bash
# contact_sheet.sh <name> <tag1> <tag2> ... — stitch probe frames into review/<name>.png
set -u; W=/workspace/loopwork; R=/workspace/review
NAME=$1; shift
ARGS=""; N=0
for t in "$@"; do f=$(ls $W/$t/*.png 2>/dev/null | head -1); [ -n "$f" ] && { ARGS="$ARGS -i $f"; N=$((N+1)); }; done
[ $N -lt 2 ] && exit 0
ffmpeg -v error -y $ARGS -filter_complex "hstack=inputs=$N" $R/$NAME.png && echo "sheet $NAME ($N)"
