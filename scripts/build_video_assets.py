#!/usr/bin/env python3
"""
Package the evidence for each story in VIDEO_NOTES.md.

A finding is only usable on video if you can SHOW it. Every item here already
has evidence on disk from when it was diagnosed -- the before clip, the
contaminated plate, the frame where two figures appear. This gathers each
story's material into its own folder with the numbers and a shot list, so the
video can be cut without going back through logs.

Where a comparison matters, it builds a side-by-side: the same moment, before
and after, one frame, labelled. Those are the shots that make a technical point
land without narration.

    build_video_assets.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("/workspace/video_assets")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SMALL = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _label(img: Image.Image, text: str, sub: str = "") -> Image.Image:
    """Caption a frame so it reads without a voice-over."""
    pad = 78 if sub else 54
    out = Image.new("RGB", (img.width, img.height + pad), (12, 13, 15))
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    d.text((16, img.height + 10), text,
           font=ImageFont.truetype(FONT, 26), fill=(235, 231, 222))
    if sub:
        d.text((16, img.height + 44), sub,
               font=ImageFont.truetype(SMALL, 19), fill=(150, 146, 138))
    return out


def side_by_side(a: Path, b: Path, la: str, lb: str, out: Path,
                 sa: str = "", sb: str = "") -> Path | None:
    if not (a.exists() and b.exists()):
        return None
    with Image.open(a) as ia, Image.open(b) as ib:
        ia, ib = ia.convert("RGB"), ib.convert("RGB")
        h = min(ia.height, ib.height)
        ia = ia.resize((int(ia.width * h / ia.height), h))
        ib = ib.resize((int(ib.width * h / ib.height), h))
        ca, cb = _label(ia, la, sa), _label(ib, lb, sb)
    gap = 10
    canvas = Image.new("RGB", (ca.width + cb.width + gap,
                               max(ca.height, cb.height)), (12, 13, 15))
    canvas.paste(ca, (0, 0)); canvas.paste(cb, (ca.width + gap, 0))
    canvas.save(out)
    return out


def frame(src: str, t: float, dst: Path) -> Path | None:
    if not Path(src).exists():
        return None
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}",
                    "-i", src, "-frames:v", "1", str(dst)], check=False)
    return dst if dst.exists() else None


def story(n: int, slug: str, title: str, numbers: str, shots: str) -> Path:
    d = OUT / f"{n:02d}_{slug}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "README.md").write_text(
        f"# {title}\n\n## The numbers\n\n```\n{numbers.strip()}\n```\n\n"
        f"## What to show\n\n{shots.strip()}\n")
    return d


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    R = Path("/workspace/review")
    made = []

    # ── 1. lips moving in silence ────────────────────────────────────────
    d = story(1, "lips_in_silence", "The characters kept talking after they stopped",
              """80 of 233 seconds of the film had no audio under the picture
ep05_s06  motion during speech 3.878   during silence 6.287   ratio 1.62
after the fix   speech 3.744   silence 2.191   ratio 0.59
speech motion essentially unchanged; silence motion down 65%""",
              "- s06_BEFORE.mp4 and s06_AFTER.mp4, cut to the same moment\n"
              "- the ratio table on screen\n"
              "- point out this is the SAME shot, one variable changed")
    before = R / "wow/s06_BEFORE.mp4"
    after = None
    for c in sorted(Path("ComfyUI/output/video/tir-na-nog-legend").glob("ep05_s06_*.mp4")):
        after = c
    if before.exists():
        shutil.copy(before, d / "s06_BEFORE.mp4")
    if after:
        shutil.copy(after, d / "s06_AFTER.mp4")
        fa = frame(str(before), 8.5, d / "_a.png")
        fb = frame(str(after), 8.5, d / "_b.png")
        if fa and fb:
            side_by_side(fa, fb, "BEFORE", "AFTER", d / "compare.png",
                         "mouth still moving, 1.62x", "mouth stops, 0.59")
            fa.unlink(); fb.unlink()
    made.append(d)

    # ── 2. the contaminated plate ────────────────────────────────────────
    d = story(2, "contaminated_plate", "I blamed the model. The bug was in the reference image.",
              """the plate scored 0.316 against a 0.75 contamination threshold -- it PASSED
two renders came back with people who should not exist
the plate itself has three figures standing in its central arch""",
              "- plate_3figures.png: zoom into the central arch, they are small\n"
              "- render1_two_figures.png: the invented standing warrior\n"
              "- render2_still_a_figure.png: after removing the character AND\n"
              "  putting 'people' in the negative prompt, still there\n"
              "- render3_fixed.png: seeded from the clean plate instead\n"
              "- beat: the model was doing exactly what it was shown")
    for src, dst in ((R/"wow/plate_check.png", "plate_3figures.png"),
                     (R/"wow/fall_check.png", "render1_two_figures.png"),
                     (R/"wow/fall_v2.png", "render2_still_a_figure.png"),
                     (R/"wow/fall_v3.png", "render3_fixed.png")):
        if src.exists():
            shutil.copy(src, d / dst)
    side_by_side(d/"render1_two_figures.png", d/"render3_fixed.png",
                 "SEEDED FROM THE BAD PLATE", "SEEDED FROM THE CLEAN ONE",
                 d/"compare.png", "an invented man with a spear", "nobody")
    made.append(d)

    # ── 3. the camera that was not moving ────────────────────────────────
    d = story(3, "camera_not_moving", "Half the film had a camera move that did nothing",
              """ffmpeg's crop filter evaluates w and h ONCE at initialisation
only x and y are re-evaluated per frame
push  mean frame delta 2.920   static 2.918   -- bit-identical
drift worked only because it moves x
17 of 27 shots in the graded cut had no camera on them
after the zoompan rewrite: push 1.51x, pull 1.51x, drift 1.53x, hold 1.00x""",
              "- broken_push.mp4 next to static: they look the same because they ARE\n"
              "- working_push.mp4: the same shot with a real move\n"
              "- the two numbers on screen, 2.920 and 2.918\n"
              "- beat: this shipped in a finished cut and looked fine")
    for src, dst in ((R/"post/mv_push.mp4", "broken_push.mp4"),
                     (R/"post/mv2_push.mp4", "working_push.mp4")):
        if src.exists():
            shutil.copy(src, d / dst)
    made.append(d)

    # ── 4. the film look, and the vignette that ate the frame ────────────
    d = story(4, "film_look", "The finishing pass, and the setting labelled 'subtle'",
              """original            mean 87.8   highlight area 14.84%   left edge 54.6
halation only       mean 90.6   highlight area 16.45%   edge 56.2
grain only          mean 87.9   highlight area 14.89%   edge 54.6
vignette PI/4.28    mean 61.7   highlight area  5.75%   edge 13.0
grain costs 36 MB -> 243 MB""",
              "- look_before.png vs look_after.png\n"
              "- the vignette row is the joke: that was the 'subtle' preset\n"
              "- beat: isolating each component is what found it")
    src_clip = sorted(Path("ComfyUI/output/video/tir-na-nog-legend").glob("ep06_s01_*.mp4"))
    if src_clip:
        fa = frame(str(src_clip[-1]), 2.0, d / "look_before.png")
        fb = frame(str(R/"post/look_subtle.mp4"), 2.0, d / "look_after.png")
        if fa and fb:
            side_by_side(fa, fb, "NO FINISH", "HALATION + GRAIN", d / "compare.png",
                         "highlight area 14.8%", "16.4%, nothing crushed")
    made.append(d)

    # ── 5. the films themselves ──────────────────────────────────────────
    d = story(5, "the_films", "The output, for cutaways",
              """film_v3      3:47  full post: matching, camera, grade, film look, reactions
film_react   3:56  same cut without grain
prelude      3:26  the prelude, 28 shots
27 shots, 9.5s average, against ep04's 17 shots at 3.0s""",
              "- use these for any b-roll where you need the work itself on screen\n"
              "- the 12-second hold in the film is the shot to show for long takes")
    for src in (R/"post/film_v3.mp4", R/"wow/deliver/film_react.mp4",
                R/"wow/deliver/prelude_react.mp4", R/"wow/deliver/extend_15s_proof.mp4"):
        if src.exists():
            shutil.copy(src, d / src.name)
    made.append(d)

    # ── 6. the raw measurements ──────────────────────────────────────────
    d = OUT / "06_measurements"
    d.mkdir(parents=True, exist_ok=True)
    for sub in ("variants", "lora_sweep", "two_shot", "action", "steps"):
        s = R / sub
        if s.exists() and any(s.iterdir()):
            shutil.copytree(s, d / sub, dirs_exist_ok=True)
    (d / "README.md").write_text(
        "# Raw measurement data\n\nEvery JSON here was produced by a script in\n"
        "`scripts/`, not typed by hand. Use them for on-screen tables.\n")
    made.append(d)

    # ── index ────────────────────────────────────────────────────────────
    lines = ["# Video assets\n",
             "One folder per story. Each has the evidence, the numbers, and a\n"
             "shot list. `compare.png` where a before/after exists -- those are\n"
             "the frames that make a technical point land without narration.\n"]
    for d in made:
        n = len(list(d.rglob("*"))) - 1
        lines.append(f"- **{d.name}** — {n} file(s)")
    lines.append("\nSee VIDEO_NOTES.md in the repo for the full write-up and hooks.\n")
    (OUT / "README.md").write_text("\n".join(lines))

    print(f"  {len(made)} story folders in {OUT}")
    for d in made:
        print(f"    {d.name:26} {len(list(d.rglob('*')))-1} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
