#!/usr/bin/env python3
"""
Render the terminal-evidence stories as cards, and write a script per story.

Seven of the ten findings in VIDEO_NOTES.md have no pictures, because their
evidence is log output: a progress bar, a stack trace, a table of numbers that
are all the same. That is showable -- it just has to be SET rather than
screenshotted, so it is legible at YouTube compression and on a phone.

Dark ground, monospace, one idea per card, the damning line highlighted. The
editing guide already tells you to do this by hand with a text editor and a
screenshot; this does it consistently and at the right resolution.

Also writes script.md per story: the narration beats and the shot list, so each
folder is self-contained rather than needing VIDEO_NOTES.md open alongside.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("/workspace/video_assets")
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
BG, INK, DIM, HOT = (14, 15, 18), (226, 223, 214), (128, 126, 120), (232, 152, 92)
W = 1920


def card(lines, out: Path, title: str = "", hot: tuple = ()) -> Path:
    """lines: list of str. `hot` holds indices to highlight."""
    fs = 30
    f = ImageFont.truetype(MONO, fs)
    fb = ImageFont.truetype(MONO_B, fs)
    ft = ImageFont.truetype(MONO_B, 34)
    pad, lh = 70, int(fs * 1.55)
    h = pad * 2 + (len(lines) * lh) + (70 if title else 0)
    img = Image.new("RGB", (W, max(h, 420)), BG)
    d = ImageDraw.Draw(img)
    y = pad
    if title:
        d.text((pad, y), title, font=ft, fill=INK); y += 70
    for i, ln in enumerate(lines):
        col = HOT if i in hot else (DIM if ln.startswith("#") else INK)
        d.text((pad, y), ln, font=(fb if i in hot else f), fill=col)
        y += lh
    img.save(out)
    return out


STORIES = {
 "07_extra_chunks": dict(
   title="I added a feature, used it three times, and it never once ran",
   cards=[
     ("broken.png", "What three renders actually built", [
      "extra_chunks=0   ->  16 nodes,  0 Extend,  5.06s",
      "extra_chunks=1   ->  16 nodes,  0 Extend, 10.12s  requested",
      "extra_chunks=2   ->  16 nodes,  0 Extend, 15.19s  requested",
      "",
      "# the parameter was in the signature, documented,",
      "# and passed by the caller. the call site dropped it.",
     ], {1, 2}),
     ("fixed.png", "After one line changed", [
      "chunks=1   16 nodes,  0 Extend,  0 concat,   5.06s",
      "chunks=2   20 nodes,  1 Extend,  1 concat,  10.12s",
      "chunks=3   24 nodes,  2 Extend,  2 concat,  15.19s",
     ], {1, 2}),
   ],
   numbers="three renders, identical 16-node graphs, no error at any point",
   script="""**Beat 1 — the setup.** Shots were capped at 5.06 seconds. That cap is
why the earlier episode cut every three seconds: not a style choice, a limit.

**Beat 2 — the work.** Chaining chunks removes the cap. Signature updated,
documented, caller passes the value.

**Beat 3 — the reveal.** Show `broken.png`. Three different values, three
identical graphs. *"I rendered with this three times before I checked what it
was actually building."*

**Beat 4 — the cause.** The call site never forwarded the argument. One line.

**Beat 5 — the point.** Nothing errored. The films were just short, and short
looked like a decision.
"""),

 "08_fix_worse_than_bug": dict(
   title="I fixed it, and the fix was worse than the bug",
   cards=[
     ("trace.png", "Motion through one shot, after the 'fix'", [
      "  0.00s   12.87  ############",
      "  0.50s    1.87  #",
      "  1.12s    0.69            <- the line ends here",
      "  1.75s    1.91  #",
      "  2.38s    4.76  ####",
      "  3.00s    3.91  ###",
      "  3.62s    3.97  ###",
      "",
      "# the HELD frame moved more than the live speech",
     ], {4, 5, 6}),
   ],
   numbers="live speech 0.7-1.9   held tail 1.6-4.8",
   script="""**Beat 1.** Characters were mouthing words after their line ended. Fixed
by holding a frozen frame instead of generating picture — a single frame cannot
articulate.

**Beat 2.** Viewer feedback: the shots look *stuck*.

**Beat 3.** Show `trace.png`. The held tail measures higher than the live
speech. A slow zoom resamples every pixel each frame; real cel animation holds
flat areas perfectly still. The character stopped and the frame kept creeping.

**Beat 4 — the point.** The fix was correct and the implementation of it was
the next bug. Only measuring caught that.
"""),

 "09_broken_metric": dict(
   title="I spent a night measuring with a ruler that had no marks on it",
   cards=[
     ("broken.png", "The metric, on three very different frames", [
      "clean cel frame     0.510",
      "blurred + grain     0.513",
      "character portrait  0.513",
      "",
      "# it could not tell these apart at all",
     ], {0, 1, 2}),
     ("fixed.png", "The same three, after one change", [
      "clean cel frame     0.998",
      "blurred + grain     0.995",
      "character portrait  0.999",
      "",
      "# scale similarities by 100 BEFORE the softmax.",
      "# raw CLIP scores differ by about 0.001.",
     ], set()),
   ],
   numbers="0.510 / 0.513 / 0.513 -> 0.998 / 0.995 / 0.999",
   script="""**Beat 1.** A whole overnight experiment scored on 'is this still
cel-shaded'. Result: the style holds at every setting. Conclusion drawn.

**Beat 2.** Show `broken.png`. The metric returns the same number for a clean
frame, a destroyed frame, and a portrait.

**Beat 3.** The cause is one line: softmaxing raw CLIP similarities, which sit
around 0.2-0.3 and differ by a thousandth.

**Beat 4 — the point.** Every reading taken with it was noise. Check that your
instrument can tell apart two things you KNOW are different, before you trust it
on things you don't.
"""),

 "10_undocumented_constraint": dict(
   title="It ran for forty minutes, then died on an undocumented rule",
   cards=[
     ("error.png", "Seven shots into a 28-shot episode", [
      "  [7/28] ep10_s07  storm_cliffs  dialogue",
      "  Extended take: 2 chained chunks = 7.38s",
      "",
      "einops.EinopsError:",
      "  can't divide axis of length 15600 in chunks of 9",
      "",
      "# 9 is (37-1)/4. the final chunk was 37 frames.",
      "# tails of 33, 45, 53 and 81 all work.",
      "# the documented rule is 4n+1. 37 IS 4n+1.",
     ], {3, 4}),
   ],
   numbers="37-frame tail fails; 33/45/53/81 work; the rule is written nowhere",
   script="""**Beat 1.** A 28-shot episode. Seven shots in, it dies.

**Beat 2.** Show `error.png`. The number 9 is the giveaway: (37-1)/4.

**Beat 3.** The documented constraint is 4n+1 frames. 37 satisfies it. There is
a stricter rule that is not written down anywhere.

**Beat 4 — the fix.** Restrict to lengths that have actually produced clips, and
assert it in the test suite by sweeping every duration from 4 to 40 seconds.

**Beat 5 — the point.** You cannot reason your way to an undocumented
constraint. You can only refuse to leave the known-good set.
"""),

 "11_where_time_goes": dict(
   title="Why a four-minute film takes nine hours",
   cards=[
     ("step.png", "One line from the render log", [
      "  9/15  [08:30<05:40, 56.78s/it]",
      "",
      "# 56.8 seconds PER SAMPLING STEP.",
      "# 15 steps = 14 minutes for one chunk.",
      "# a chained two-chunk take is two of those.",
      "",
      "# the distill LoRAs cut T2V and I2V to 8 steps",
      "# -- 6x faster AND better. they are trained for a",
      "# different model family, so dialogue cannot use",
      "# them. dialogue is 80% of every film.",
     ], {0}),
   ],
   numbers="56.78s/it; 80% of shots run full steps with no distillation",
   script="""**Beat 1.** Everything takes hours. Here is exactly where the time goes.

**Beat 2.** Show `step.png`. Fifty-seven seconds for one step of one chunk.

**Beat 3.** The speed-up exists — it just doesn't apply to the model that does
dialogue, which is most of the film.

**Beat 4 — the honest bit.** Nobody had ever tested whether 15 steps was needed.
The number was inherited.
"""),

 "12_measuring_on_the_gpu": dict(
   title="My own measurements were stealing the GPU",
   cards=[
     ("contention.png", "Plate render intervals", [
      "  19:30:50   master__oisin_full_body.png",
      "  19:31:40   master__oisin_medium.png        50s",
      "  19:34:42   master__oisin_three_quarter.png  3m 02s",
      "",
      "# a scoring pass launched 'in the background'",
      "",
      "  GPU idle during staging:            65%",
      "  ComfyUI reported a prompt RUNNING:  209 of 219",
      "",
      "# the stall was INSIDE a prompt, not an empty queue.",
      "# deeper queueing would have achieved nothing.",
     ], {2, 6}),
   ],
   numbers="50s -> 3m02s per plate; 209 of 219 idle samples had a prompt running",
   script="""**Beat 1.** The GPU is the bottleneck, so I measured how idle it was.

**Beat 2.** Measuring made it worse. Show `contention.png` — plate intervals
tripled the moment a scoring pass started.

**Beat 3.** And the idle itself was misleading: ComfyUI reported a prompt
running through almost all of it. The stall was CPU-bound inside a prompt.

**Beat 4 — the point.** Two obvious fixes — queue more work, measure more —
were both wrong. Measurement is cheap on CPU and expensive on GPU.
"""),

 "13_backup_that_wasnt": dict(
   title="I backed up the wrong half",
   cards=[
     ("gitignore.png", "What was and was not tracked", [
      "  episode scripts on disk:     10",
      "  episode scripts in the repo:  0",
      "",
      "# .gitignore excluded bible.json and episodes/",
      "# as 'generated series data'. true when a model",
      "# wrote them. false for the week since.",
      "",
      "# the code that RENDERS the films was tracked.",
      "# the films were not.",
     ], {0, 1}),
     ("secret.png", "And the first push was blocked", [
      "  remote: - GITHUB PUSH PROTECTION",
      "  remote:   Push cannot contain secrets",
      "  remote:",
      "  remote:   -- Anthropic API Key ----------------",
      "  remote:     path: run_all_enhanced.sh:5",
      "",
      "# committed by me, days earlier, without looking.",
     ], {3, 4}),
   ],
   numbers="10 scripts on disk, 0 in the repo; an API key in history",
   script="""**Beat 1.** Everything lived on a rented box. Time to push it somewhere.

**Beat 2.** Show `gitignore.png`. The scripts — the actual creative work — had
never been tracked. The rule was written when a model generated them and was
never revisited once they were hand-written.

**Beat 3.** Show `secret.png`. The push was blocked anyway: an API key I had
committed days earlier.

**Beat 4 — the point.** Two failures, opposite directions, same cause: nobody
checked what was in the repo. One excluded what mattered, one included what
shouldn't be there.
"""),
}


def main():
    made = 0
    for slug, s in STORIES.items():
        d = OUT / slug
        d.mkdir(parents=True, exist_ok=True)
        for fname, title, lines, hot in s["cards"]:
            card(lines, d / fname, title=title, hot=hot)
        (d / "README.md").write_text(
            f"# {s['title']}\n\n## The numbers\n\n```\n{s['numbers']}\n```\n\n"
            f"## Cards\n\n" + "\n".join(f"- `{c[0]}` — {c[1]}" for c in s["cards"]) + "\n")
        (d / "script.md").write_text(f"# {s['title']}\n\n{s['script']}\n")
        made += 1
        print(f"  {slug:28} {len(s['cards'])} card(s) + script")
    print(f"\n  {made} story folders")
    return 0


if __name__ == "__main__":
    sys.exit(main())
