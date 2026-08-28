#!/usr/bin/env python3
"""
S23 -- the negative-prompt correction, as a real side-by-side.

The manifest carried a pointer ("see ../18_the_negative_that_wasnt/") instead
of a file, so it was the one short in the series with nothing to play. It is
also the one that most needs to be seen rather than described: the claim is
that replacing a hand-built 40-term English negative with WAN's own default
increased motion 1.10x, and 1.10x is small enough that a viewer is entitled to
check it against their own eyes.

Old on top, new below, same shot, same seed, playing together.
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SRC = Path("/workspace/video_assets/18_the_negative_that_wasnt")
DST = Path("/workspace/video_assets/SHORTS_SERIES/S23_the_fix_that_wasnt_the_answer")
W, H, VH = 1080, 1920, 623
SERIF_B = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
MONO, MONO_B = ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf")
BG, INK, DIM, ACC = (13, 14, 17), (233, 230, 221), (132, 129, 123), (140, 165, 220)
TOP_Y, BOT_Y = 300, 300 + VH + 46


def wrap(d, t, f, mw):
    out, cur = [], ""
    for w in t.split():
        s = (cur + " " + w).strip()
        if d.textbbox((0, 0), s, font=f)[2] > mw and cur:
            out.append(cur); cur = w
        else:
            cur = s
    if cur:
        out.append(cur)
    return out


def main():
    old = SRC / "ep11_s04_old_negative.mp4"
    new = SRC / "ep11_s04_new_negative.mp4"
    if not (old.exists() and new.exists()):
        print("  source clips missing")
        return 1
    DST.mkdir(parents=True, exist_ok=True)

    plate = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(plate)
    fv = ImageFont.truetype(MONO_B, 38)
    bw = d.textbbox((0, 0), "SURPRISE", font=fv)[2] + 60
    d.rounded_rectangle([60, 78, 60 + bw, 148], 10, fill=ACC)
    d.text((90, 92), "SURPRISE", font=fv, fill=BG)
    ft = ImageFont.truetype(SERIF_B, 52)
    y = 186
    for ln in wrap(d, "The fix that wasn't the answer", ft, W - 120):
        d.text((60, y), ln, font=ft, fill=INK); y += 62

    fl = ImageFont.truetype(MONO_B, 30)
    d.text((60, TOP_Y - 40), "OLD  40 hand-written English terms", font=fl, fill=DIM)
    d.text((60, TOP_Y + VH + 6), "NEW  WAN's own default negative", font=fl, fill=ACC)

    fn = ImageFont.truetype(MONO_B, 84)
    ny = BOT_Y + 60
    bb = d.textbbox((0, 0), "1.10x", font=fn)
    d.text(((W - (bb[2] - bb[0])) / 2, ny), "1.10x", font=fn, fill=ACC)
    fnote = ImageFont.truetype(MONO, 27)
    ny += 128
    note = ("I found the negative prompt was fighting the motion I wanted and "
            "replaced it. Measured honestly it bought 1.10x, and cost a little "
            "identity. The real answer was elsewhere: silent image-to-video "
            "moves 12.1 against speech-to-video's 5.4.")
    for ln in wrap(d, note, fnote, W - 120)[:7]:
        d.text((60, ny), ln, font=fnote, fill=DIM); ny += 38

    bgp = DST / "_bg.png"
    plate.save(bgp)

    out = DST / "clip.mp4"
    fc = (f"[1:v]scale={W}:{VH}:force_original_aspect_ratio=increase,"
          f"crop={W}:{VH},setpts=PTS-STARTPTS[a];"
          f"[2:v]scale={W}:{VH}:force_original_aspect_ratio=increase,"
          f"crop={W}:{VH},setpts=PTS-STARTPTS[b];"
          f"[0:v][a]overlay=0:{TOP_Y}:shortest=0[t];"
          f"[t][b]overlay=0:{BOT_Y}:shortest=1[v]")
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(bgp),
         "-i", str(old), "-i", str(new), "-filter_complex", fc,
         "-map", "[v]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
         "-r", "16", "-movflags", "+faststart", str(out)],
        capture_output=True, text=True)
    if r.returncode:
        print(f"  ffmpeg: {r.stderr.strip()[:300]}")
        return 1
    for f in (old, new):
        (DST / f.name).write_bytes(f.read_bytes())
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
    print(f"  {out}  {float(dur):.2f}s  {out.stat().st_size / 1048576:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
