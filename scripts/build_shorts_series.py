#!/usr/bin/env python3
"""
Every finding as a numbered short: what worked, what didn't, and why.

One catalogue, sequentially ordered, so a series can be recorded in order and
tracked. Each short is 30-60 seconds and carries ONE idea.

Two frame kinds, chosen by what the evidence actually is:

  CLIP   a 1080x1920 frame with the claim above, the clip at its NATIVE 16:9
         in the middle, and the number below. Never cropped -- a cel-shaded
         wide IS its composition.
  CARD   for findings whose evidence is a log line, a stack trace, or a table
         where every number is the same. Those cannot be filmed, but they can
         be SET, and set large enough to read on a phone.

Every entry carries a verdict (WORKED / FAILED / BROKEN / SURPRISE), the number
that proves it, and a script with timed beats. `manifest.json` is the running
trace: order, status, and what each one needs.
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

OUT = Path("/workspace/video_assets/SHORTS_SERIES")
W, H = 1080, 1920
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SERIF_B = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
BG, INK, DIM = (13, 14, 17), (233, 230, 221), (132, 129, 123)
COLOURS = {"WORKED": (120, 190, 130), "FAILED": (222, 176, 92),
           "BROKEN": (214, 96, 88), "SURPRISE": (140, 165, 220)}
R = Path("/workspace/review")


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


def _header(d, verdict, title, top_y=90):
    col = COLOURS[verdict]
    fv = ImageFont.truetype(MONO_B, 38)
    bw = d.textbbox((0, 0), verdict, font=fv)[2] + 60
    d.rounded_rectangle([60, top_y, 60 + bw, top_y + 70], 10, fill=col)
    d.text((90, top_y + 14), verdict, font=fv, fill=BG)
    y = top_y + 120
    ft = ImageFont.truetype(SERIF_B, 52)
    for ln in _wrap(d, title, ft, W - 120)[:4]:
        d.text((60, y), ln, font=ft, fill=INK); y += 66
    return y, col


def clip_frame(e, dst):
    clip = e.get("clip")
    if not clip or not Path(str(clip)).exists():
        return None
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=width,height", "-of",
                         "csv=p=0", str(clip)],
                        capture_output=True, text=True).stdout.strip().split(",")
    sw, sh = int(pr[0]), int(pr[1])
    vh = int(W * sh / sw)
    top = 620
    plate = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(plate)
    _, col = _header(d, e["verdict"], e["title"])
    fn = ImageFont.truetype(MONO_B, 76)
    fs = ImageFont.truetype(MONO, 27)
    by = top + vh + 80
    bb = d.textbbox((0, 0), e["number"], font=fn)
    d.text(((W - (bb[2]-bb[0])) / 2, by), e["number"], font=fn, fill=col)
    by += 128
    for ln in _wrap(d, e["note"], fs, W - 120)[:7]:
        d.text((60, by), ln, font=fs, fill=DIM); by += 40
    p = dst.with_suffix(".plate.png"); plate.save(p)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(p),
                    "-i", str(clip), "-filter_complex",
                    f"[1:v]scale={W}:{vh}[v];[0:v][v]overlay=0:{top}:shortest=1,"
                    f"format=yuv420p[o]", "-map", "[o]", "-t", "6", "-r", "16",
                    "-c:v", "libx264", "-crf", "18", str(dst)], check=True)
    p.unlink(missing_ok=True)
    return dst


def card_frame(e, dst):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    y, col = _header(d, e["verdict"], e["title"])
    y += 60
    fm = ImageFont.truetype(MONO, 30)
    fmb = ImageFont.truetype(MONO_B, 30)
    for i, ln in enumerate(e.get("lines", [])):
        c = col if i in e.get("hot", set()) else (DIM if ln.strip().startswith("#") else INK)
        d.text((60, y), ln[:44], font=(fmb if i in e.get("hot", set()) else fm), fill=c)
        y += 46
    y += 60
    fn = ImageFont.truetype(MONO_B, 76)
    bb = d.textbbox((0, 0), e["number"], font=fn)
    d.text(((W - (bb[2]-bb[0])) / 2, y), e["number"], font=fn, fill=col)
    y += 130
    fs = ImageFont.truetype(MONO, 27)
    for ln in _wrap(d, e["note"], fs, W - 120)[:8]:
        d.text((60, y), ln, font=fs, fill=DIM); y += 40
    img.save(dst)
    return dst


def shot(sid):
    c = sr.find_latest_clip(sid)
    return c if c else None


def build():
    sr.set_current_series("tir-na-nog-legend")
    E = []
    def add(**k): E.append(k)

    # ── the wins ────────────────────────────────────────────────────
    add(verdict="WORKED", title="Making a character actually walk",
        number="12.1", clip=str(R/"walk/cross_light.mp4"),
        note="Image-to-video, no dialogue. Full-body plate, an explicit screen "
             "direction, and the words 'he does not stop'. Motion 12.1, travel "
             "42.3, identity 0.842.",
        script="HOOK: play it, say nothing.\nBEAT: everything before this "
               "barely moved.\nTURN: this is image-to-video with NO dialogue. "
               "Speech-to-video is anchored to a talking head.\nPUNCH: movement "
               "has to be its own shot. Which is how animation is cut anyway.")
    add(verdict="SURPRISE", title="The plate made for walking is the worst one",
        number="5.2 vs 12.1", clip=str(R/"walk/away_light.mp4"),
        note="A plate staged specifically for walking scored 5.2. A generic "
             "full-body plate with an explicit left-to-right instruction "
             "scored 12.1. The specialised asset lost to the generic one.",
        script="HOOK: 'I built a plate specifically for walking.'\nBEAT: it "
               "scored 5.2.\nTURN: a generic full-body plate scored 12.1.\n"
               "PUNCH: the instruction mattered more than the asset.")
    add(verdict="SURPRISE", title="More sampling steps made it worse",
        number="0.738", clip=str(R/"walk/away_full.mp4"),
        note="Same shot, 20 steps instead of 8. Motion fell from 5.2 to 3.7 and "
             "identity to 0.738 -- the worst of any walk variant. More compute "
             "is not more quality.",
        script="HOOK: 'I doubled the sampling steps to improve it.'\nBEAT: "
               "motion 5.2 to 3.7. Identity 0.829 to 0.738.\nTURN: worse on "
               "both axes.\nPUNCH: the distilled 8-step path beat the full one.")
    add(verdict="WORKED", title="Twelve seconds on one face, three chained samples",
        number="0.010", clip=shot("ep07_s05"),
        note="Identity spread across the whole take: 0.010, the steadiest shot "
             "in the film. Before chaining, nothing could exceed 5.06 seconds.",
        script="HOOK: 'Every shot was capped at five seconds.'\nBEAT: that cap "
               "is why the first cut changed shot every three seconds.\nTURN: "
               "chaining samples removes it. Drift across 15 seconds: +0.015.\n"
               "PUNCH: the hardest shot in the film is also the steadiest.")
    add(verdict="WORKED", title="Whole-body verbs move a body. Small ones don't.",
        number="5.70 vs 2.56", clip=shot("ep11_s07"),
        note="stands up 5.70, rises 5.59, walks 5.44, crouches 3.62. "
             "turns 2.56, lowers 2.25 -- both BELOW the 3.01 baseline for "
             "shots not asked to move at all.",
        script="HOOK: 'Half my action shots did nothing.'\nBEAT: show the "
               "ladder.\nTURN: 'turns to look' is below the do-nothing "
               "baseline. 'Stands up' nearly doubles it.\nPUNCH: it's a "
               "writing rule, not a model limit.")

    # ── the failures that shipped ───────────────────────────────────
    add(verdict="BROKEN", title="Still talking, four seconds after the line ended",
        number="1.62", clip=str(R/"wow/s06_BEFORE.mp4"),
        note="The mouth moved MORE in the silence than during the speech. 80 "
             "seconds of a 233-second film had no audio under it, so the model "
             "invented movement. Nothing errored.",
        script="HOOK: play it. The line ended four seconds ago.\nBEAT: "
               "speech-to-video drives the mouth from audio.\nTURN: a third of "
               "every shot had no audio covering it at all.\nPUNCH: right "
               "length, right person, right style, no error.")
    add(verdict="BROKEN", title="A man who does not exist, twice",
        number="0.316", clip=shot("ep09_s01"),
        note="Two renders came back with an invented figure. The reference "
             "plate had three people standing in its central arch. The "
             "contamination gate scored it 0.316 against a 0.75 threshold and "
             "passed it.",
        script="HOOK: 'Who is that man?'\nBEAT: I removed the character and put "
               "'people' in the negative. Still there.\nTURN: show the plate. "
               "Three people, in the reference.\nPUNCH: I blamed the model for "
               "two hours.")
    add(verdict="BROKEN", title="'Turns to look' does nothing at all",
        number="2.56", clip=shot("ep11_s03"),
        note="Below the 3.01 baseline for shots that were not asked to move. "
             "The instruction was simply ignored, and I had written seven "
             "shots using verbs like it.",
        script="HOOK: 'This shot was written with an action in it.'\nBEAT: 2.56."
               "\nTURN: shots asked to do NOTHING scored 3.01.\nPUNCH: asking "
               "made it move less than not asking.")

    # ── the audit ───────────────────────────────────────────────────
    add(verdict="BROKEN", title="I was telling it not to move",
        number="6 words", kind="card",
        lines=["WAN ships a default negative prompt.",
               "Three of its terms mean:", "",
               "  静态           static",
               "  静止           motionless",
               "  静止不动的画面  a completely still picture", "",
               "# it fights stillness FOR you.", "",
               "mine replaced it with:",
               "  fast movement, erratic motion, motion blur,",
               "  camera shake, extreme camera movement"],
        hot={3,4,5,10,11},
        note="A custom negative REPLACES the default -- there is no "
             "concatenation path. Mine deleted three anti-static terms and "
             "added six that suppress motion, on 80% of every film.",
        script="HOOK: 'I spent weeks wondering why nothing moved.'\nBEAT: WAN "
               "ships a negative prompt that fights stillness for you.\nTURN: a "
               "custom one REPLACES it. Mine deleted all three.\nPUNCH: I was "
               "instructing it to hold still, then blaming the model. Honest "
               "coda: fixing it gave 1.14x. The real answer was structural.")
    add(verdict="BROKEN", title="A negative prompt the model never reads",
        number="cfg 1.0", kind="card",
        lines=["  if math.isclose(cond_scale, 1.0):",
               "      uncond_ = None", "",
               "# on the distilled branch, ComfyUI DISCARDS",
               "# negative conditioning before any forward pass.",
               "# not a zero weight -- a skipped computation."],
        hot={0,1},
        note="Every hour spent tuning a 40-term negative list was, on those "
             "shots, tuning a string that never reaches the model.",
        script="HOOK: 'I spent hours tuning my negative prompt.'\nBEAT: show "
               "the two lines.\nTURN: at cfg 1.0 it is discarded before any "
               "forward pass.\nPUNCH: on half the shots I was editing a string "
               "the model never sees.")
    add(verdict="BROKEN", title="Settings from nowhere",
        number="shift 12", kind="card",
        lines=["  reference repo    shift 3   40 steps  cfg 4.5",
               "  ComfyUI template  shift 8   20 steps  cfg 6.0",
               "  this pipeline     shift 12  15 steps  cfg 5.0", "",
               "# not 'the defaults with a tweak'.",
               "# a configuration nobody documents,",
               "# on every frame, for the whole project."],
        hot={2},
        note="Two authorities, two sets of numbers, and this pipeline matched "
             "neither -- with cfg BELOW the ComfyUI value rather than above "
             "the repo one.",
        script="HOOK: 'Where did these numbers come from?'\nBEAT: show the "
               "table.\nTURN: I matched neither authority.\nPUNCH: nobody had "
               "ever checked. They were inherited from a workflow I copied.")
    add(verdict="BROKEN", title="A third of every prompt described the picture",
        number="75 -> 50", kind="card",
        lines=["Wan's own I2V system prompt says:", "",
               "  'If the user's input already describes",
               "   elements visible in the image, remove",
               "   those static descriptions.'", "",
               "# every shot is seeded from a plate that",
               "# already shows the location, the light",
               "# and the palette. Mine described all three."],
        hot={2,3,4},
        note="Both shipped ComfyUI templates match the instruction -- their "
             "positive prompts are subject plus action only. No background, no "
             "style, no palette.",
        script="HOOK: 'My prompts were 75 words.'\nBEAT: about 30 of them "
               "described the background.\nTURN: which the seed image already "
               "shows. Wan's own docs say delete it.\nPUNCH: 50 words now, all "
               "of it about what MOVES.")

    # ── engineering failures ────────────────────────────────────────
    add(verdict="BROKEN", title="A feature I used three times that never ran",
        number="16 nodes", kind="card",
        lines=["  extra_chunks=0  ->  16 nodes,  5.06s",
               "  extra_chunks=1  ->  16 nodes, 10.12s requested",
               "  extra_chunks=2  ->  16 nodes, 15.19s requested", "",
               "# it was in the signature, documented,",
               "# and passed by the caller.",
               "# the call site dropped it."],
        hot={1,2},
        note="Three different values, three identical graphs, no error at any "
             "point. The films were just short, and short looked like a "
             "decision.",
        script="HOOK: 'I added a feature and used it three times.'\nBEAT: show "
               "the table -- same graph every time.\nTURN: the call site never "
               "forwarded the argument.\nPUNCH: nothing errored. It just "
               "silently did nothing, and I shipped three films that way.")
    add(verdict="BROKEN", title="Half my film had a camera move that did nothing",
        number="2.920 / 2.918", kind="card",
        lines=["  static push   mean frame delta 2.918",
               "  'moving' push mean frame delta 2.920", "",
               "# ffmpeg's crop filter evaluates w and h",
               "# ONCE at initialisation. only x and y",
               "# are re-evaluated per frame.", "",
               "# 17 of 27 shots. in a finished cut."],
        hot={0,1},
        note="A push written as a shrinking crop window freezes at frame "
             "zero's size. Drift worked only because it happens to move x.",
        script="HOOK: two clips side by side. 'One has a camera move.'\nBEAT: "
               "they are identical.\nTURN: crop evaluates width and height "
               "once.\nPUNCH: seventeen of twenty-seven shots, in a cut I had "
               "already called finished.")
    add(verdict="BROKEN", title="A seven-minute film that played in 86 seconds",
        number="80fps", kind="card",
        lines=["  all 144 segments present",
               "  6910 frames -- correct count",
               "  container says 80fps. film runs at 16.", "",
               "# r_frame_rate is the smallest rate that",
               "# can express every timestamp. a few",
               "# irregular ones pushed it to 80.",
               "# I read the wrong field."],
        hot={2},
        note="The source film was never wrong. Only my upscale of it -- and it "
             "shipped as a deliverable.",
        script="HOOK: play the film at 5x. 'This is the finished cut.'\nBEAT: "
               "every frame present, count correct.\nTURN: the container said "
               "80fps.\nPUNCH: I read r_frame_rate instead of avg_frame_rate.")
    add(verdict="BROKEN", title="The whole film drifted out of sync",
        number="2.7s", kind="card",
        lines=["  picture      424.313s",
               "  soundtrack   421.607s", "",
               "# the beds crossfade. the picture is a",
               "# HARD CUT -- nothing is lost at an edit.",
               "# subtracting the crossfade made the track",
               "# short by 0.05s x 54 shots.", "",
               "# container durations MATCHED. the audio",
               "# was padded; the content inside was not."],
        hot={0,1},
        note="Voice and effects slid later and later through the film. My "
             "first check compared container durations, which matched, and "
             "told me nothing.",
        script="HOOK: 'The viewer said the audio was off.'\nBEAT: I checked "
               "durations. They matched.\nTURN: the container is padded; the "
               "content inside was compressed by 2.7 seconds.\nPUNCH: a "
               "rounding error repeated 54 times.")
    add(verdict="BROKEN", title="I measured with a ruler that had no marks",
        number="0.51", kind="card",
        lines=["  clean cel frame     0.510",
               "  blurred + grain     0.513",
               "  character portrait  0.513", "",
               "# it could not tell these apart at all.", "",
               "# cause: softmaxing RAW clip similarities,",
               "# which differ by about 0.001.",
               "# scale by 100 first: 0.998 / 0.995 / 0.999"],
        hot={0,1,2},
        note="An entire overnight experiment was scored with it. Every "
             "conclusion drawn from those numbers was noise.",
        script="HOOK: 'I ran an experiment all night and got a clean result.'\n"
               "BEAT: show the three numbers.\nTURN: a clean frame, a destroyed "
               "frame and a portrait scored the same.\nPUNCH: check your "
               "instrument can tell apart two things you KNOW are different.")
    add(verdict="BROKEN", title="I backed up the wrong half",
        number="10 / 0", kind="card",
        lines=["  episode scripts on disk:     10",
               "  episode scripts in the repo:  0", "",
               "# .gitignore excluded them as",
               "# 'generated series data'. true when a",
               "# model wrote them. false for a week.", "",
               "# and the first push was blocked:",
               "# an API key I had committed myself."],
        hot={0,1},
        note="The code that renders the films was tracked. The films were not. "
             "Two failures in opposite directions, same cause: nobody checked "
             "what was in the repo.",
        script="HOOK: 'Everything lived on a rented box.'\nBEAT: time to back "
               "it up.\nTURN: the scripts had never been tracked. And the push "
               "was blocked by a key I had committed.\nPUNCH: I excluded what "
               "mattered and included what shouldn't be there.")
    add(verdict="SURPRISE", title="My own measurements were stealing the GPU",
        number="50s -> 3min", kind="card",
        lines=["  plate render intervals:",
               "    19:30:50   50 seconds",
               "    19:34:42   3 min 02",
               "  # a scoring pass started in between", "",
               "  GPU idle during staging:  65%",
               "  ComfyUI said RUNNING in:  209 of 219", "",
               "# the stall was INSIDE a prompt."],
        hot={2,6},
        note="Two obvious responses -- queue more work, measure more -- were "
             "both wrong. Measurement is cheap on CPU and expensive on GPU.",
        script="HOOK: 'The GPU is the bottleneck, so I measured how idle it "
               "was.'\nBEAT: measuring made it worse. Plate times tripled.\n"
               "TURN: and the idle was misleading -- a prompt was running "
               "through almost all of it.\nPUNCH: the stall was CPU-bound "
               "inside a prompt. Deeper queueing would have done nothing.")
    add(verdict="SURPRISE", title="Ten steps is enough",
        number="33%", kind="card",
        lines=["   steps  identity      render",
               "      15     0.924     13.3 min",
               "      12     0.921     10.8 min",
               "      10     0.918      9.0 min",
               "       8     0.911      7.3 min",
               "       6     0.857      5.7 min", "",
               "# 15 was inherited. nobody measured it."],
        hot={3},
        note="A third off every dialogue render, permanently, for six "
             "thousandths of identity. Dialogue is 80% of every film.",
        script="HOOK: 'Every render took 13 minutes a chunk.'\nBEAT: the step "
               "count was inherited from a workflow I copied.\nTURN: 10 steps "
               "costs 0.006 of identity.\nPUNCH: a third off everything, "
               "forever, from a number nobody had questioned.")
    add(verdict="SURPRISE", title="Best-of-three is mostly waste",
        number="27%", kind="card",
        lines=["  spread between takes of the same shot:",
               "    ep07_s06   0.003",
               "    ep08_s06   0.005",
               "    ep07_s05   0.006",
               "    ep06_s05   0.035",
               "    ep09_s03   0.039",
               "    ep05_s03   0.040", "",
               "# bimodal. half barely move."],
        hot={4,5,6},
        note="Rendering every shot three times and picking the best is worth "
             "27% of the total identity spread -- but half the shots gain "
             "nothing. Re-roll only the ones that score low.",
        script="HOOK: 'A real production shoots several takes.'\nBEAT: I "
               "rendered ten shots three times each.\nTURN: half varied by "
               "0.003. Half by 0.040.\nPUNCH: blanket coverage is waste. "
               "Re-roll the weak ones only -- and I found that by CANCELLING "
               "the experiment early.")
    add(verdict="FAILED", title="Two characters in one frame",
        number="0.62 / 0.68", kind="card",
        lines=["  side by side    oisin 0.621  niamh 0.675",
               "  over shoulder   oisin 0.642  niamh 0.747", "",
               "# neither recognisable.", "",
               "# but the test seeded from an EMPTY plate.",
               "# it gave the model no face for either",
               "# character, then scored it on whether it",
               "# produced the right faces."],
        hot={0,1,4},
        note="55 shots across six films and not one contains two characters. "
             "The first test said impossible; the test was built wrong and is "
             "being re-run properly.",
        script="HOOK: '55 shots. Not one has two characters in it.'\nBEAT: I "
               "tested it. 0.62 and 0.68. Impossible.\nTURN: the test seeded "
               "from an empty plate -- no face for either character.\nPUNCH: I "
               "scored the model on inventing faces I never showed it.")

    return E


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    entries = build()
    manifest = []
    for i, e in enumerate(entries, 1):
        num = f"S{i:02d}"
        slug = f"{num}_" + "".join(
            c if c.isalnum() else "_" for c in e["title"].lower())[:44].strip("_")
        d = OUT / slug
        d.mkdir(exist_ok=True)
        kind = e.get("kind", "clip")
        made = None
        if kind == "clip":
            made = clip_frame(e, d / "short.mp4")
            if not made:                       # clip missing -> fall back
                kind = "card"
                e.setdefault("lines", [])
        if kind == "card":
            made = card_frame(e, d / "frame.png")
        (d / "script.md").write_text(
            f"# {num} — {e['title']}\n\n"
            f"**Verdict:** {e['verdict']}  \n**Number on screen:** {e['number']}\n\n"
            f"## Beats\n\n{e['script']}\n\n## The note under the number\n\n"
            f"{e['note']}\n\n---\n\nTarget 30-60s. One idea. The number is the "
            f"reason anyone keeps watching.\n")
        manifest.append({"n": i, "id": num, "slug": slug,
                         "verdict": e["verdict"], "title": e["title"],
                         "number": e["number"], "kind": kind,
                         "asset": made.name if made else None,
                         "recorded": False})
        print(f"  {num}  {e['verdict']:8} {kind:4}  {e['title'][:52]}")

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    by = {}
    for m in manifest:
        by.setdefault(m["verdict"], []).append(m)
    lines = ["# The shorts series\n",
             f"{len(manifest)} shorts, numbered in recording order. One idea",
             "each, 30-60 seconds. `manifest.json` is the running trace --",
             "flip `recorded` to true as you go.\n",
             "Each folder holds the frame (a 1080x1920 video for clip-backed",
             "findings, a PNG for the ones whose evidence is a log line) and",
             "`script.md` with timed beats.\n",
             "## Order\n",
             "| # | verdict | title | number |",
             "|---|---|---|---|"]
    for m in manifest:
        lines.append(f"| {m['id']} | {m['verdict']} | {m['title']} | `{m['number']}` |")
    lines += ["\n## Verdicts\n",
              "- **WORKED** — it does the thing, and there's a number proving it",
              "- **FAILED** — it doesn't work, or didn't when tested",
              "- **BROKEN** — it shipped or nearly shipped and should not have",
              "- **SURPRISE** — the result contradicts what you'd expect\n",
              "## Why the failures outnumber the wins\n",
              "Because that is what happened. A pipeline series showing only",
              "successes teaches nobody anything, and every BROKEN entry here",
              "either reached the viewer or came within one check of it.\n"]
    (OUT / "README.md").write_text("\n".join(lines))
    counts = {v: len(x) for v, x in by.items()}
    print(f"\n  {len(manifest)} shorts in {OUT}")
    print(f"  {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
