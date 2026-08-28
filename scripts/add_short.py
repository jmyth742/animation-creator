#!/usr/bin/env python3
"""
Append a short to the series without writing another one-off script.

build_shorts_series.py generated the first 23 and build_archive_shorts.py the
next 12, each with its own copy of the card renderer. A third copy for every
new finding is how the three drift apart, so this is the last one: it reads
the manifest, takes the next number, renders the card with the same layout,
and writes the script file.

    add_short.py --verdict BROKEN --title "..." --number "867 MB" \
                 --note "..." --beats "HOOK: ...\nBEAT: ..." [--image path]

The manifest is the running trace, so numbering is derived from it rather than
passed in -- two shorts added in either order still come out sequential.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("/workspace/video_assets/SHORTS_SERIES")
W, H = 1080, 1920
SERIF_B = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
MONO, MONO_B = ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf")
BG, INK, DIM = (13, 14, 17), (233, 230, 221), (132, 129, 123)
COL = {"WORKED": (120, 190, 130), "FAILED": (222, 176, 92),
       "BROKEN": (214, 96, 88), "SURPRISE": (140, 165, 220)}


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


def card(verdict, title, number, note, img, dst):
    plate = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(plate)
    c = COL[verdict]
    fv = ImageFont.truetype(MONO_B, 38)
    bw = d.textbbox((0, 0), verdict, font=fv)[2] + 60
    d.rounded_rectangle([60, 90, 60 + bw, 160], 10, fill=c)
    d.text((90, 104), verdict, font=fv, fill=BG)
    ft = ImageFont.truetype(SERIF_B, 52)
    y = 210
    for ln in wrap(d, title, ft, W - 120)[:3]:
        d.text((60, y), ln, font=ft, fill=INK); y += 66
    top = 560
    if img and Path(img).exists():
        with Image.open(img) as im:
            im = im.convert("RGB")
            ih = int(W * im.height / im.width)
            plate.paste(im.resize((W, ih)), (0, top))
        by = top + ih + 80
    else:
        by = top + 100
    fn = ImageFont.truetype(MONO_B, 76)
    bb = d.textbbox((0, 0), number, font=fn)
    d.text(((W - (bb[2] - bb[0])) / 2, by), number, font=fn, fill=c)
    by += 130
    fnote = ImageFont.truetype(MONO, 27)
    for ln in wrap(d, note, fnote, W - 120)[:8]:
        d.text((60, by), ln, font=fnote, fill=DIM); by += 40
    plate.save(dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdict", required=True, choices=sorted(COL))
    ap.add_argument("--title", required=True)
    ap.add_argument("--number", required=True)
    ap.add_argument("--note", required=True)
    ap.add_argument("--beats", required=True)
    ap.add_argument("--image")
    a = ap.parse_args()

    mp = OUT / "manifest.json"
    man = json.loads(mp.read_text())
    n = max(m["n"] for m in man) + 1
    num = f"S{n:02d}"
    slug = f"{num}_" + "".join(ch if ch.isalnum() else "_"
                               for ch in a.title.lower())[:44].strip("_")
    d = OUT / slug
    d.mkdir(exist_ok=True)
    if a.image and Path(a.image).exists():
        shutil.copy(a.image, d / Path(a.image).name)
    card(a.verdict, a.title, a.number, a.note, a.image, d / "frame.png")
    (d / "script.md").write_text(
        f"# {num} — {a.title}\n\n**Verdict:** {a.verdict}  \n"
        f"**Number on screen:** {a.number}\n\n## Beats\n\n"
        f"{a.beats.encode().decode('unicode_escape')}\n\n"
        f"## The note under the number\n\n{a.note}\n")
    man.append({"n": n, "id": num, "slug": slug, "verdict": a.verdict,
                "title": a.title, "number": a.number, "kind": "card",
                "asset": "frame.png", "recorded": False})
    mp.write_text(json.dumps(man, indent=2))
    print(f"  {num}  {a.verdict:8} {a.title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
