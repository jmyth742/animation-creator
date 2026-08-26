#!/usr/bin/env python3
"""
Title and end cards.

The films have neither. Typography is the cheapest production-value signal
there is: a well-set title tells an audience, before a frame of story, that
somebody was paying attention.

Set against black with generous space, letter-spaced small caps for the title
and a quiet serif for everything else. The card fades up from black, holds, and
fades out, so it can be butted straight against the first shot.

    titles.py card --text "Tir na nOg" --sub "a film in four movements" -o t.mp4
    titles.py end  --lines "written and directed by ..." -o e.mp4
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
SERIF_B = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
INK = (232, 228, 218)
DIM = (150, 146, 138)
BG = (10, 12, 14)


def _spaced(s: str, px: int = 6) -> str:
    """Letter-spacing, which PIL has no setting for."""
    return (" " * (px // 3)).join(s)


def title_card(text: str, sub: str | None, out: str, seconds: float = 4.0,
               fade: float = 0.9) -> str:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_title = ImageFont.truetype(SERIF_B, 74)
    t = _spaced(text.upper())
    bb = d.textbbox((0, 0), t, font=f_title)
    top = H / 2 - 110
    d.text(((W - (bb[2] - bb[0])) / 2, top), t, font=f_title, fill=INK)
    # No rule. A short hairline centred under a wide title reads as underlining
    # whichever letters happen to sit above it -- here it looked like "NA" was
    # being emphasised. Space separates these two lines perfectly well, and a
    # decoration that has to be explained is not doing any work.
    if sub:
        f_sub = ImageFont.truetype(SERIF, 26)
        s = _spaced(sub, 3)
        bb2 = d.textbbox((0, 0), s, font=f_sub)
        d.text(((W - (bb2[2] - bb2[0])) / 2, top + (bb[3] - bb[1]) + 78),
               s, font=f_sub, fill=DIM)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        img.save(tf.name)
        png = tf.name
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", png,
                    "-t", f"{seconds}", "-r", "16",
                    "-vf", (f"fade=t=in:st=0:d={fade},"
                            f"fade=t=out:st={seconds-fade:.2f}:d={fade},"
                            f"format=yuv420p"),
                    "-c:v", "libx264", "-crf", "16", out], check=True)
    Path(png).unlink(missing_ok=True)
    return out


def end_card(lines: list[str], out: str, seconds: float = 6.0,
             fade: float = 1.2) -> str:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(SERIF, 26)
    y = H / 2 - (len(lines) * 44) / 2
    for ln in lines:
        s = _spaced(ln, 3)
        bb = d.textbbox((0, 0), s, font=f)
        d.text(((W - (bb[2] - bb[0])) / 2, y), s, font=f, fill=DIM)
        y += 44
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        img.save(tf.name); png = tf.name
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", png,
                    "-t", f"{seconds}", "-r", "16",
                    "-vf", (f"fade=t=in:st=0:d={fade},"
                            f"fade=t=out:st={seconds-fade:.2f}:d={fade},"
                            f"format=yuv420p"),
                    "-c:v", "libx264", "-crf", "16", out], check=True)
    Path(png).unlink(missing_ok=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("card")
    c.add_argument("--text", required=True); c.add_argument("--sub")
    c.add_argument("--seconds", type=float, default=4.0)
    c.add_argument("-o", "--out", required=True)
    e = sub.add_parser("end")
    e.add_argument("--lines", nargs="+", required=True)
    e.add_argument("--seconds", type=float, default=6.0)
    e.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    if a.cmd == "card":
        print("  " + title_card(a.text, a.sub, a.out, a.seconds))
    else:
        print("  " + end_card(a.lines, a.out, a.seconds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
