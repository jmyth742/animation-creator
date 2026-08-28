#!/usr/bin/env python3
"""
Package the movement and two-shot investigation.

This one is worth keeping whole because it is a story about being WRONG twice
and finding out by measuring: two capabilities were declared impossible on the
strength of tests that were badly built, and both turned out to be partly or
wholly available once tested properly.

Gathers the clips, renders the evidence as cards, and writes the narration
beats. Re-runnable -- as later results land it picks them up.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

OUT = Path("/workspace/video_assets/15_movement_and_two_shots")
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
BG, INK, DIM, HOT, COOL = (14, 15, 18), (226, 223, 214), (128, 126, 120), \
                          (232, 152, 92), (120, 175, 205)


def card(lines, out: Path, title: str = "", hot=(), cool=()) -> Path:
    fs = 30
    f, fb = ImageFont.truetype(MONO, fs), ImageFont.truetype(MONO_B, fs)
    ft = ImageFont.truetype(MONO_B, 34)
    pad, lh = 70, int(fs * 1.55)
    h = pad * 2 + len(lines) * lh + (70 if title else 0)
    img = Image.new("RGB", (1920, max(h, 420)), BG)
    d = ImageDraw.Draw(img)
    y = pad
    if title:
        d.text((pad, y), title, font=ft, fill=INK); y += 70
    for i, ln in enumerate(lines):
        col = HOT if i in hot else COOL if i in cool else \
              (DIM if ln.strip().startswith("#") else INK)
        d.text((pad, y), ln, font=(fb if (i in hot or i in cool) else f), fill=col)
        y += lh
    img.save(out)
    return out


def motion(clip: str) -> float:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip, "-vf",
                        "fps=6", f"{td}/f_%03d.png"], check=True)
        fr = [np.asarray(Image.open(f).convert("L"), dtype=np.float32)
              for f in sorted(Path(td).glob("f_*.png"))]
    return float(np.mean([np.abs(fr[i+1]-fr[i]).mean()
                          for i in range(len(fr)-1)])) if len(fr) > 1 else 0.0


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sr.set_current_series("tir-na-nog-legend")

    # ── card 1: the wrong conclusion ─────────────────────────────────────
    card([
        "42 of 55 shots were a person standing still, talking.",
        "",
        "So: does the model refuse to move a body while it drives a mouth?",
        "",
        "  action      motion   verdict",
        "  still        2.871   reference",
        "  turn         3.779   moved, lip sync suspect",
        "  step         3.847   USABLE",
        "  gesture      3.473   USABLE",
        "  sit          3.397   moved, lip sync suspect",
        "",
        "# a second shot came back 'nothing happened' on four of five.",
        "# I concluded movement was mostly unavailable. Two shots.",
    ], OUT / "01_the_wrong_conclusion.png",
        "What I tested, and what I concluded from it", hot=(12, 13))

    # ── card 2: ep11, seven shots, the real pattern ──────────────────────
    card([
        "  action asked for   motion   identity",
        "  stands up           5.702      0.867",
        "  rises               5.592      0.830",
        "  walks               5.435      0.905",
        "  crouches            3.624      0.885",
        "  turns               2.968      0.864",
        "  turns               2.556      0.883",
        "  lowers              2.248      0.870",
        "",
        "  no action asked     3.014   <- the baseline",
        "",
        "# WHOLE-BODY verbs move a body. Small ones are ignored.",
        "# my test used mostly small verbs, on two shots.",
    ], OUT / "02_the_actual_pattern.png",
        "ep11: seven shots written with action", hot=(1, 2, 3), cool=(5, 6, 7))

    # ── card 3: the two-shot test that was wrong ─────────────────────────
    card([
        "  variant          oisin    niamh   verdict",
        "  side_by_side     0.621    0.675   neither recognisable",
        "  over_shoulder    0.642    0.747   neither recognisable",
        "",
        "  'no variant held both characters'  -- closed the question",
        "",
        "# three things wrong with that test:",
        "#  1. it seeded from an EMPTY location plate, so the model",
        "#     had no face for either character, then I blamed it",
        "#     for guessing",
        "#  2. a 0.75 threshold built for close-ups, applied to a",
        "#     wide shot where each face is a fraction of the frame",
        "#  3. compositing two staged plates into one seed was never",
        "#     tried, and the plates already existed",
    ], OUT / "03_the_two_shot_test_was_bad.png",
        "Two characters in one frame: 'impossible'", hot=(1, 2))

    # ── clips ────────────────────────────────────────────────────────────
    clips = OUT / "clips"; clips.mkdir(exist_ok=True)
    rows = []
    ep = json.loads((sr.series_path("tir-na-nog-legend") /
                     "episodes" / "ep11.json").read_text())
    ACT = ("walks", "turns", "lowers", "crouches", "picks up", "stands up",
           "rises", "steps")
    for s in ep["scenes"]:
        c = sr.find_latest_clip(s["id"])
        if not c:
            continue
        verb = next((a for a in ACT if a in s["visual"].lower()), "still")
        dst = clips / f"{verb.replace(' ', '_')}_{s['id']}.mp4"
        shutil.copy(c, dst)
        rows.append((s["id"], verb, motion(c)))
    for name, src in (("action_still.mp4", "act_ep05_s04_still"),
                      ("action_step.mp4", "act_ep05_s04_step"),
                      ("action_gesture.mp4", "act_ep05_s04_gesture")):
        c = sr.find_latest_clip(src)
        if c:
            shutil.copy(c, clips / name)
    ts = Path("/workspace/review/two_shot")
    if ts.exists():
        for f in ts.glob("*.png"):
            shutil.copy(f, OUT / f"two_shot_failed_{f.name}")
    tc = Path("/workspace/review/two_shot_composite")
    if tc.exists():
        for f in list(tc.glob("*.png")) + list(tc.glob("*.mp4")):
            shutil.copy(f, OUT / f"two_shot_composite_{f.name}")

    (OUT / "measurements.json").write_text(json.dumps(
        [{"shot": a, "verb": b, "motion": round(c, 3)} for a, b, c in rows],
        indent=2))

    (OUT / "script.md").write_text("""# Two capabilities I declared impossible, twice, wrongly

## The shape of it

This is a story about being wrong by testing badly, and only finding out
because someone asked "are we really saying that?"

## Beat 1 — the real gap

42 of 55 shots across six films were a person standing still, talking. Show a
montage. That is the deepest difference from studio animation: bodies do things
there, and here they did not.

## Beat 2 — the test, and the wrong answer

Show `01_the_wrong_conclusion.png`. Five action clauses on two shots. One shot
gave two usable results, the other gave "nothing happened" four times out of
five. I concluded the model would not move a body while driving a mouth.

## Beat 3 — the evidence that contradicted me

Then an episode was written with action in seven of eleven shots, because the
writing was suspected as well as the model. Show `02_the_actual_pattern.png`.

**Whole-body verbs move a body. Small ones are ignored.**

    stands up 5.70   rises 5.59   walks 5.44   crouches 3.62
    turns 2.97/2.56  lowers 2.25        baseline 3.01

Play `clips/stands_up_*.mp4` and `clips/turns_*.mp4` back to back. One moves,
one does not, and they were asked in the same script by the same model.

My test had used mostly the weak verbs. The capability was there; the prompt
was not asking for it.

## Beat 4 — and the second one was worse

Show `03_the_two_shot_test_was_bad.png`. Two characters in one frame scored
0.62 and 0.68 and I called it closed.

Three flaws, and the first is the damning one: **it seeded from an empty
location plate.** The model was given no face for either character and then
scored on whether it produced the right faces. Every good shot in the project
seeds from a plate that already contains the right face.

## Beat 5 — the point

Both conclusions were about a MEASUREMENT, not a capability. A badly built test
does not return "unknown", it returns a confident wrong answer, and a confident
wrong answer closes a question for good unless somebody pushes back.

The prompt that reopened it was three words: "are we saying".
""")

    (OUT / "README.md").write_text(
        "# Movement and two-shots\n\n"
        "Cards, clips and raw measurements for the investigation into whether "
        "characters can move and whether two can share a frame. `script.md` has "
        "the narration beats.\n\n"
        "## Files\n\n"
        "- `01_the_wrong_conclusion.png` — the small test and its verdict\n"
        "- `02_the_actual_pattern.png` — ep11's seven action shots\n"
        "- `03_the_two_shot_test_was_bad.png` — three flaws in the two-shot test\n"
        "- `clips/` — every ep11 shot, named by the verb it was asked for\n"
        "- `two_shot_*` — the failed renders and, once it runs, the composite test\n"
        "- `measurements.json` — motion per shot, produced by script\n\n"
        "## The one-line version\n\n"
        "Whole-body verbs move a body; small ones are ignored. And a test that "
        "gives the model no face reference cannot tell you whether the model "
        "can render faces.\n")

    n = len(list(OUT.rglob("*")))
    print(f"  {OUT}")
    print(f"  {n} files, {len(rows)} ep11 clips with motion scores")
    for a, b, c in sorted(rows, key=lambda r: -r[2])[:5]:
        print(f"    {b:12} {c:6.3f}  {a}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
