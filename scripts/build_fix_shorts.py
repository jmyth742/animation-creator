#!/usr/bin/env python3
"""
Before/after shorts: the issue, what it gave, the fix, what it gives now.

The numbered series says what was found. This says it in the only order that
works on a phone:

    1  THE ISSUE     one line, and the number
    2  WHAT IT GAVE  the broken render, playing
    3  THE FIX       one line -- what actually changed
    4  WHAT IT GIVES the fixed render, playing, same shot same seed

Every pair here is the same shot rendered twice with one variable changed, so
the comparison is honest: nothing is cherry-picked from different takes.

Output is 1080x1920 with the clip letterboxed into the middle and the words
above and below, which is the layout that reads at phone size without
upscaling a 480p render to fill the frame.

    build_fix_shorts.py            # all of them
    build_fix_shorts.py --only wide-collapse
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("/workspace/video_assets/FIX_SHORTS")
W, H = 1080, 1920
VID_H = 624                        # 1080x624 is 832x480 scaled to width
SERIF_B = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
MONO, MONO_B = ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf")
BG, INK, DIM = (13, 14, 17), (233, 230, 221), (132, 129, 123)
BAD, GOOD = (214, 96, 88), (120, 190, 130)

R = "/workspace"
FIXES = [
 {"id": "wide-collapse", "number": "0.008 -> 0.953",
  "issue": "Every wide shot with a line in it came back a close-up",
  "gave": "The script says 'the warrior small and alone among the stones'. "
          "Six of eight rendered as a face. All were seeded from a correct "
          "full-body plate.",
  "fix": "Render the wide SILENT and lay the voice over it. The speech model "
         "is a talking-head model and pulls to the face whatever the prompt "
         "says.",
  "before": f"{R}/text-to-video/ComfyUI/output/video/tir-na-nog-legend/ep07_s01_00001_.mp4",
  "after":  f"{R}/review/wide_dialogue/ep07_s01_B_held.mp4"},

 {"id": "location-drift", "number": "wrong place",
  "issue": "The wides were rendering in the wrong location",
  "gave": "A grey mossy ring-fort in the script; a bright green hillside on "
          "screen. The staged character plates carry the character and not "
          "the place.",
  "fix": "Seed silent wides from the LOCATION plate instead of the staged "
         "character plate. p(wide) 0.943 and the right ruin.",
  "before": f"/tmp/ep13_s02_00001_.mp4",
  "after":  f"{R}/text-to-video/ComfyUI/output/video/tir-na-nog-legend/ep13_s02_00001_.mp4"},

 {"id": "close-seed", "number": "0.869 -> 0.880",
  "issue": "The close-ups were set nowhere",
  "gave": "Dialogue seeds from a bare portrait, so it carries the portrait's "
          "background. The wides are a grey ruin, the closes are a teal sea. "
          "Cut together, two different scenes.",
  "fix": "Composite the character INTO the location plate behind a feathered "
         "edge and seed from that. Neither pure direction works: the location "
         "alone stays empty, the portrait alone is placeless.",
  "before": f"{R}/text-to-video/ComfyUI/output/video/tir-na-nog-legend/ep13_s06_00001_.mp4",
  "after":  f"{R}/text-to-video/ComfyUI/output/video/tir-na-nog-legend/inplace_s06_00001_.mp4"},

 {"id": "silent-moves", "number": "5.4 -> 12.1",
  "issue": "The characters would not move",
  "gave": "Whatever verb the prompt used, a talking shot barely moves. "
          "Measured across five verbs the best was 3.85.",
  "fix": "Stop asking a dialogue shot to move. Render movement SILENTLY with "
         "image-to-video. Same character, same walk, 2.2x the motion.",
  "before": f"{R}/video_assets/18_the_negative_that_wasnt/CONTRAST_s2v_walk_5.4.mp4",
  "after":  f"{R}/video_assets/18_the_negative_that_wasnt/CONTRAST_i2v_walk_12.1.mp4"},

 {"id": "negative-prompt", "number": "1.10x",
  "issue": "My negative prompt was fighting the motion I wanted",
  "gave": "Forty hand-written English terms, several of which told the model "
          "to hold still while the prompt asked it to walk.",
  "fix": "Replace it with WAN's own default negative. Honest result: 1.10x "
         "motion and a small identity cost. Real, and not the answer -- "
         "the answer was rendering silently.",
  "before": f"{R}/video_assets/18_the_negative_that_wasnt/ep11_s04_old_negative.mp4",
  "after":  f"{R}/video_assets/18_the_negative_that_wasnt/ep11_s04_new_negative.mp4"},
]


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


def card(tag, tag_col, heading, body, number, dst, num_col=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    ft = ImageFont.truetype(MONO_B, 36)
    bw = d.textbbox((0, 0), tag, font=ft)[2] + 56
    d.rounded_rectangle([60, 150, 60 + bw, 216], 8, fill=tag_col)
    d.text((88, 162), tag, font=ft, fill=BG)
    y = 290
    fh = ImageFont.truetype(SERIF_B, 60)
    for ln in wrap(d, heading, fh, W - 120)[:4]:
        d.text((60, y), ln, font=fh, fill=INK); y += 76
    y += 40
    fb = ImageFont.truetype(MONO, 30)
    for ln in wrap(d, body, fb, W - 120)[:10]:
        d.text((60, y), ln, font=fb, fill=DIM); y += 44
    if number:
        fn = ImageFont.truetype(MONO_B, 88)
        bb = d.textbbox((0, 0), number, font=fn)
        d.text(((W - (bb[2] - bb[0])) / 2, H - 420), number, font=fn,
               fill=num_col or tag_col)
    img.save(dst)
    return dst


def card_clip(png, out, seconds):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(png),
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", str(seconds), "-vf", f"scale={W}:{H},fps=25",
                    "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "96k", "-shortest", str(out)],
                   check=True)
    return out


def labelled_clip(src, label, label_col, out):
    """The render, letterboxed into a vertical frame with a label above."""
    plate = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(plate)
    fl = ImageFont.truetype(MONO_B, 40)
    d.text((60, 520), label, font=fl, fill=label_col)
    bgp = str(Path(out).with_suffix(".bg.png"))
    plate.save(bgp)
    top = 620
    fc = (f"[1:v]scale={W}:{VID_H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{VID_H}:(ow-iw)/2:(oh-ih)/2,setsar=1[v];"
          f"[0:v][v]overlay=0:{top}:shortest=1,fps=25[o]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", bgp,
                    "-i", str(src), "-f", "lavfi", "-i",
                    "anullsrc=r=48000:cl=stereo",
                    "-filter_complex", fc, "-map", "[o]", "-map", "2:a",
                    "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "96k", "-shortest", str(out)],
                   check=True)
    Path(bgp).unlink(missing_ok=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    man = []
    for f in FIXES:
        if a.only and f["id"] != a.only:
            continue
        miss = [k for k in ("before", "after") if not Path(f[k]).exists()]
        if miss:
            print(f"  {f['id']}: missing {miss}, skipping"); continue
        d = OUT / f["id"]; d.mkdir(exist_ok=True)
        parts = []
        parts.append(card_clip(card("THE ISSUE", BAD, f["issue"], f["gave"],
                                    None, d / "1.png"), d / "1.mp4", 5.5))
        parts.append(labelled_clip(f["before"], "WHAT IT GAVE", BAD, d / "2.mp4"))
        parts.append(card_clip(card("THE FIX", GOOD, "What actually changed",
                                    f["fix"], f["number"], d / "3.png", GOOD),
                               d / "3.mp4", 6.0))
        parts.append(labelled_clip(f["after"], "WHAT IT GIVES NOW", GOOD,
                                   d / "4.mp4"))
        lst = d / "parts.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in parts))
        out = d / f"{f['id']}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe",
                        "0", "-i", str(lst), "-c:v", "libx264", "-crf", "20",
                        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
                        str(out)], check=True)
        dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "format=duration", "-of", "csv=p=0", str(out)],
                             capture_output=True, text=True).stdout.strip()
        man.append({"id": f["id"], "seconds": round(float(dur), 1),
                    "number": f["number"], "issue": f["issue"]})
        print(f"  {f['id']:16} {float(dur):5.1f}s  {f['number']}")
        for p in parts:
            Path(p).unlink(missing_ok=True)
        lst.unlink(missing_ok=True)
    (OUT / "manifest.json").write_text(json.dumps(man, indent=2))
    print(f"\n  {len(man)} before/after short(s) in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
