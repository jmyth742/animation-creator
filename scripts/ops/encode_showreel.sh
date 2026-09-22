#!/usr/bin/env bash
# Label the showreel frames and encode one continuous mp4.
# Usage: encode_showreel.sh <framedir> <out.mp4> [fps] "clip1 clip2 ..."
set -eu
SRC=$1; OUT=$2; FPS=${3:-20}; CLIPS=${4:-}
WORK=$(mktemp -d /workspace/loopwork/enc.XXXX)
/workspace/venv/bin/python - "$SRC" "$WORK" "$CLIPS" <<'PY'
import sys, os, glob
from PIL import Image, ImageDraw, ImageFont
src, work, clips = sys.argv[1], sys.argv[2], sys.argv[3].split()
if not clips:
    clips = sorted(d for d in os.listdir(src) if os.path.isdir(os.path.join(src, d)))
def font(sz):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()
CAP = {"walk": "WALK  -  hips travel, weight transfer",
       "turn": "TURN  -  root rotation through the spine",
       "wave": "WAVE  -  shoulder and elbow range",
       "point": "POINT  -  arm extension, held pose",
       "run":  "RUN  -  full stride, both feet airborne",
       "idle": "IDLE  -  breathing and weight shift"}
n = 0
for c in clips:
    fs = sorted(glob.glob(os.path.join(src, c, "f_*.png")))
    if not fs:
        continue
    big, small = font(26), font(18)
    for i, f in enumerate(fs):
        im = Image.open(f).convert("RGB")
        w, h = im.size
        d = ImageDraw.Draw(im, "RGBA")
        d.rectangle([0, h - 56, w, h], fill=(18, 18, 22, 190))
        d.text((16, h - 46), CAP.get(c, c.upper()), font=big, fill=(248, 240, 210))
        d.text((w - 210, h - 42), "UniRig skeleton / MoMask clip", font=small, fill=(170, 180, 195))
        n += 1
        im.save(os.path.join(work, "s_%05d.png" % n))
    print("labelled", c, len(fs))
print("TOTAL", n)
PY
ffmpeg -y -loglevel error -framerate "$FPS" -i "$WORK/s_%05d.png" \
  -c:v libx264 -pix_fmt yuv420p -crf 17 -preset slow -movflags +faststart "$OUT"
rm -rf "$WORK"
ls -la "$OUT"
