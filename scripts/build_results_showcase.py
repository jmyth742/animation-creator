#!/usr/bin/env python3
"""
Every notable result, ranked good / bad / awful, with what it measured.

The point of this pack is that it does not only show the wins. A pipeline video
that shows six good clips teaches nobody anything; the useful version puts the
failure next to the fix and says by how much.

Each entry becomes a 1080x1920 frame: the claim above, the clip at its NATIVE
16:9 in the middle (no cropping -- a cel-shaded wide is its composition), and
the measurement below. That uses the vertical space to explain rather than
fighting it, and the clip is untouched.

Ranked by what the numbers say, not by how it felt:

  GOOD   the thing works and there is a number proving it
  BAD    it renders, it is usable, but it measurably underperforms
  AWFUL  it shipped or nearly shipped and should not have
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

OUT = Path("/workspace/video_assets/17_results_showcase")
W, H = 1080, 1920
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SERIF_B = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
BG, INK, DIM = (13, 14, 17), (233, 230, 221), (132, 129, 123)
VERDICT = {"GOOD": (120, 190, 130), "BAD": (222, 176, 92), "AWFUL": (214, 96, 88)}


def _wrap(d, text, font, maxw):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textbbox((0, 0), t, font=font)[2] > maxw and cur:
            out.append(cur); cur = w
        else:
            cur = t
    if cur:
        out.append(cur)
    return out


def make(entry: dict, dst: Path) -> Path | None:
    clip = entry.get("clip")
    if not clip or not Path(clip).exists():
        return None
    vid_w = W
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", clip],
        capture_output=True, text=True).stdout.strip().split(",")
    sw, sh = int(probe[0]), int(probe[1])
    vid_h = int(vid_w * sh / sw)
    top = 620

    plate = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(plate)
    fv = ImageFont.truetype(MONO_B, 40)
    ft = ImageFont.truetype(SERIF_B, 52)
    fn = ImageFont.truetype(MONO_B, 76)
    fs = ImageFont.truetype(MONO, 28)

    col = VERDICT[entry["verdict"]]
    d.rounded_rectangle([60, 90, 60 + 250, 90 + 74], 10, fill=col)
    bb = d.textbbox((0, 0), entry["verdict"], font=fv)
    d.text((60 + (250 - (bb[2]-bb[0])) / 2, 90 + 14), entry["verdict"],
           font=fv, fill=(13, 14, 17))

    y = 210
    for ln in _wrap(d, entry["title"], ft, W - 120)[:4]:
        d.text((60, y), ln, font=ft, fill=INK); y += 66

    by = top + vid_h + 90
    bb = d.textbbox((0, 0), entry["number"], font=fn)
    d.text(((W - (bb[2]-bb[0])) / 2, by), entry["number"], font=fn, fill=col)
    by += 130
    for ln in _wrap(d, entry["note"], fs, W - 120)[:6]:
        d.text((60, by), ln, font=fs, fill=DIM); by += 42

    ptmp = dst.with_suffix(".plate.png")
    plate.save(ptmp)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(ptmp),
         "-i", clip, "-filter_complex",
         f"[1:v]scale={vid_w}:{vid_h}[v];[0:v][v]overlay=0:{top}:shortest=1,"
         f"format=yuv420p[o]", "-map", "[o]", "-t", "6", "-r", "16",
         "-c:v", "libx264", "-crf", "18", str(dst)], check=True)
    ptmp.unlink(missing_ok=True)
    return dst


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sr.set_current_series("tir-na-nog-legend")
    R = Path("/workspace/review")

    def shot(sid):
        c = sr.find_latest_clip(sid)
        return c if c else None

    ENTRIES = [
      # ── GOOD ────────────────────────────────────────────────────────
      dict(verdict="GOOD", slug="01_the_walk",
           title="A character who actually walks",
           number="12.1", clip=str(R/"walk/cross_light.mp4"),
           note="motion 12.1, travel 42.3, identity 0.842. Image-to-video, no "
                "dialogue. Full-body plate, explicit screen direction, and the "
                "words 'he does not stop'. The best locomotion this pipeline "
                "has produced."),
      dict(verdict="GOOD", slug="02_the_hold",
           title="Twelve seconds on one face, three chained samples",
           number="0.010", clip=shot("ep07_s05"),
           note="Identity spread across the whole take: 0.010. The longest and "
                "most demanding shot in the film is also its steadiest. Before "
                "chaining, no shot could exceed 5.06 seconds at all."),
      dict(verdict="GOOD", slug="03_stands_up",
           title="Whole-body verbs move a body", number="5.70",
           clip=shot("ep11_s07"),
           note="'He stands up from the stone as he speaks.' 5.70 against a "
                "3.01 baseline for shots with no action asked for. Speech and "
                "movement in the same shot -- which I had written off."),
      # ── BAD ─────────────────────────────────────────────────────────
      dict(verdict="BAD", slug="04_turns",
           title="Small verbs do nothing at all", number="2.56",
           clip=shot("ep11_s03"),
           note="'He turns from the water to face her.' 2.56 -- BELOW the 3.01 "
                "baseline for shots that were not asked to move. The "
                "instruction was simply ignored."),
      dict(verdict="BAD", slug="05_away_full",
           title="More sampling steps made it worse", number="0.738",
           clip=str(R/"walk/away_full.mp4"),
           note="Same shot as the walk above, 20 steps instead of 8. Motion "
                "fell 5.2 to 3.7 and identity fell to 0.738, the worst of any "
                "walk variant. More compute is not more quality."),
      # ── AWFUL ───────────────────────────────────────────────────────
      dict(verdict="AWFUL", slug="06_mouth_in_silence",
           title="Still talking, four seconds after the line ended",
           number="1.62", clip=str(R/"wow/s06_BEFORE.mp4"),
           note="The mouth moved MORE in the silence than during the speech. "
                "80 seconds of a 233-second film had no audio under it at all, "
                "so the model invented movement to fill the gap. Nothing "
                "errored: right length, right person, right style."),
      dict(verdict="AWFUL", slug="07_the_stranger",
           title="A man who does not exist, twice",
           number="0.316", clip=shot("ep09_s01"),
           note="Two renders came back with an invented figure. The reference "
                "plate they seeded from had three people standing in its "
                "central arch. The contamination gate scored that plate 0.316 "
                "against a 0.75 threshold and passed it."),
    ]

    made = []
    for e in ENTRIES:
        dst = OUT / f"{e['slug']}.mp4"
        if make(e, dst):
            made.append(e)
            print(f"  {e['verdict']:6} {e['slug']}")
        else:
            print(f"  {e['verdict']:6} {e['slug']}  -- no clip, skipped")

    (OUT / "index.json").write_text(json.dumps(made, indent=2))
    by = {}
    for e in made:
        by.setdefault(e["verdict"], []).append(e)
    lines = ["# Results showcase\n",
             "Every notable result as a 1080x1920 frame: claim above, the clip",
             "at its NATIVE 16:9 in the middle, the measurement below. The clip",
             "is never cropped -- a cel-shaded wide IS its composition.\n",
             "Ranked by what the numbers say, not by how it felt.\n"]
    for v in ("GOOD", "BAD", "AWFUL"):
        if v not in by:
            continue
        lines.append(f"\n## {v}\n")
        for e in by[v]:
            lines.append(f"- **{e['slug']}.mp4** — {e['title']} — `{e['number']}`")
    lines.append("\n## Why the failures are in here\n")
    lines.append("A pipeline video showing six good clips teaches nobody")
    lines.append("anything. The useful version puts the failure next to the fix")
    lines.append("and says by how much. Every AWFUL entry either shipped or")
    lines.append("nearly shipped, and each was caught by measuring output rather")
    lines.append("than by reading code.\n")
    (OUT / "README.md").write_text("\n".join(lines))
    print(f"\n  {len(made)} entries in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
