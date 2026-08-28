# Video notes — what actually happened, with the numbers

Raw material for the YouTube series. Every item here is something that was
MEASURED, not remembered. The numbers are the credibility; keep them.

The through-line, if you want one: **almost nothing in this project failed
loudly.** Twenty-odd real defects and not one of them crashed. That is the
story. A wrong configuration and a right one produce the same exit code, the
same "JOB COMPLETE", and a video that plays. The only way to tell them apart is
to measure the output — and every time I trusted the code instead of the
output, it cost hours.

---

## TIER 1 — the ones that carry a whole video

### 1. The feature that was accepted, defaulted, and thrown away
`extra_chunks` was the parameter that let a shot exceed 5.06 seconds. It was
added to the function signature, documented, and passed by the caller. Three
separate renders produced **16-node graphs every time, regardless of its
value** — because the call site never forwarded it. Nothing errored. The films
just stayed short.

    extra_chunks=0  ->  16 nodes, 0 Extend nodes,  5.06s
    extra_chunks=1  ->  16 nodes, 0 Extend nodes, 10.12s "requested"
    extra_chunks=2  ->  16 nodes, 0 Extend nodes, 15.19s "requested"

**Hook:** "I added a feature, used it three times, and it never once ran."

### 2. Three hundred seconds of a character mouthing words nobody spoke
S2V drives a mouth from audio. A shot held longer than its line was given audio
only as long as the SPEECH — so 22-36% of every shot had no audio covering it
and the model invented mouth movement to fill the gap. Across the finished
film that was **80 seconds of 233**.

Measured as face-region motion during speech vs after it:

    ep05_s01  ratio 0.30   mouth stops       (wide, face is tiny)
    ep05_s02  ratio 0.92   STILL MOVING
    ep05_s06  ratio 1.62   moves MORE in silence than in speech

**Hook:** "The characters were talking after they'd stopped talking."

### 3. The fix that became the next bug
Padding the audio with silence helped. Holding a frozen frame instead of
generating picture fixed it outright — a single frame cannot articulate. But
then the viewer said shots looked "stuck", and the trace showed why:

    live speech   0.7 - 1.9   motion falling as the line ends
    "held" tail   1.6 - 4.8   motion RISING

The hold was moving MORE than the footage before it, because a slow zoom
resamples every pixel each frame while real cel animation holds flat areas
perfectly still.

**Hook:** "I fixed it, and the fix was worse than the bug."

### 4. The camera that wasn't moving
27 of 27 shots were locked off, so I wrote a camera-move pass. It measured
**bit-identical to static**: 2.920 against 2.918.

ffmpeg's `crop` filter evaluates its width and height expressions **once at
initialisation** — only x and y are re-evaluated per frame. A push written as a
shrinking crop window freezes at frame 0's size. Drift worked only because it
happens to move x. **Seventeen of twenty-seven shots had no camera on them** and
the graded cut shipped anyway.

**Hook:** "Half the film had a camera move that did nothing, and it looked fine."

### 5. The measuring instrument that measured nothing
A metric scoring "is this frame cel-shaded or photoreal" returned **~0.51 for
everything**: a clean cel frame, that frame destroyed with blur and grain, and
a character portrait alike.

It softmaxed raw CLIP similarities, which sit around 0.2-0.3 and differ by
~0.001. The working version scales by 100 first, and then gives 0.998 and 0.999.
Every "the style is holding" reading taken with the broken one was noise.

**Hook:** "I spent a night measuring with a ruler that had no marks on it."

---

## TIER 2 — strong segments

### 6. The plate with three strangers in it
A shot kept coming back with people who should not exist — first an invented
standing warrior, then, after removing the character from the scene entirely
and putting "people" in the negative prompt, a figure beside the horse anyway.

The model was innocent. **The location plate itself had three figures standing
in its central arch**, and every shot seeded from it inherited them. The
contamination gate had passed that plate at 0.316 against a 0.75 threshold.

**Hook:** "I blamed the model for two hours. The bug was in the reference image."

### 7. An undocumented constraint that only fails at minute 40
A 28-shot episode died 7 shots in:

    einops: can't divide axis of length 15600 in chunks of 9

9 is (37-1)/4 — the final chunk had been sized at 37 frames. Tails of 33, 45,
53 and 81 all work. The rule is stricter than the documented 4n+1 and is written
down nowhere. Now restricted to lengths that have actually produced clips.

### 8. Where the time really goes
    9/15  [08:30<05:40, 56.78s/it]

**56.8 seconds per sampling step.** The distill LoRAs cut T2V and I2V from ~18
steps to 8 — six times faster AND better — but they are trained for a different
model family, so every dialogue shot (about 80% of the film) runs full steps
with no distillation.

### 9. Measuring on the GPU while it renders
A scoring pass launched "in the background" during staging took plate intervals
from **50 seconds to 3 minutes**. Interleaving an upscaler comparison between
render prompts forced an 8.5GB model swap each way and produced the single
longest idle stretch of the night, 120 seconds.

GPU idle during staging measured 65% — but ComfyUI reported a prompt RUNNING in
**209 of 219** of those samples. The stall was inside a prompt, not an empty
queue, so deeper queueing would have achieved nothing.

### 10. The backup that wasn't
Pushing to GitHub for the first time revealed two things at once. The push was
blocked by an **Anthropic API key committed in history**. And the `.gitignore`
had been excluding `bible.json` and `episodes/` as "generated data" — true when
a model wrote them, false for the week since. **Every episode script, the actual
creative work, had never been backed up at all.** The code that renders the
films was tracked; the films were not.

**Hook:** "I backed up the wrong half."

---

## TIER 3 — good detail, use as texture

- **Best-of-three takes is worth 27% of the total identity spread**, and the
  effect is bimodal: three shots varied 0.003-0.006 between takes, three varied
  0.035-0.040. So re-rolling only the shots that score low captures most of the
  benefit at a third of the cost. Found from partial data after cancelling the
  experiment early.
- **Shot-to-shot colour drift within ONE location**: luminance spread 19-27,
  red/blue balance spread up to 63. On a real set those are a few units.
- **The vignette that crushed the frame**: edges 78.9 -> 24.4, whole-image mean
  down 30%, at the setting labelled "subtle".
- **musubi-tuner has no S2V support at all** — zero mentions in source. The
  character LoRA everyone assumes you can train simply cannot be trained.
- **The cross-family LoRA rule rests on one measurement at one strength.**
  Character LoRAs are dropped from ~80% of shots because of a single reading at
  strength 0.9. Nobody had tried 0.2 or 0.35.
- **42 of 55 shots are a person standing still, talking.** Only 13 describe any
  physical action. The ceiling may have been the writing, not the model.
- **Grain costs 36 MB -> 243 MB.** It genuinely unifies separately-generated
  shots and it destroys compression.

---

## THE ARC, if you want one video instead of several

1. It works. Here is a four-minute animated film made on one graphics card.
2. Now here is everything that was silently broken while it "worked".
3. Every single one was found by measuring the OUTPUT, never by reading code.
4. Several of my fixes were worse than the bugs, and measurement caught those too.
5. The instruments themselves were wrong twice.
6. What's actually left is not model quality. It's that I wrote 42 talking heads.

---

# PART TWO — the audit, and what it found in my own work

Added after a documentation audit of the prompts and sampler settings against
Wan2.2's own source. This part is stronger material than Part One, because the
bugs in Part One were mistakes and these were BELIEFS.

## T1 — "I spent weeks wondering why the characters wouldn't move"

The single best item in the whole project.

WAN 2.2 ships a default negative prompt. Three of its 28 terms are 静态
(static), 静止 (motionless) and 静止不动的画面 (a completely still picture).
**The reference implementation fights stillness for you.**

A custom negative REPLACES that string. It does not extend it. Verified in the
source: `if n_prompt == '': n_prompt = self.sample_neg_prompt` — there is no
concatenation path anywhere.

My hand-built list deleted all three anti-static terms and substituted six that
suppress MOTION:

    fast movement, erratic motion, motion blur,
    camera shake, shaky camera, extreme camera movement

At S2V's cfg 5.0 the negative is extrapolated against at full strength. So on
roughly 80% of every film I was instructing the model to hold still, then
concluding the model could not move.

**The honest coda:** fixing it gave 1.14x motion on the shot I tested. Real,
but small. The big movement win turned out to be structural, not prompt-level
— see T2. Do not overclaim this one; the story is the mistake, not the fix.

## T1 — "The plate made for walking is the worst one"

    full_body plate + "from the left of the frame to the right" +
      "he does not stop"                          motion 12.1  travel 42.3
    walking_away plate + "walks away from camera" motion  5.2
    same at 20 steps instead of 8                 motion  3.7
    best that speech-to-video managed, any verb   motion  5.7

Two counter-intuitive results in one table. The plate specifically staged for
walking produces less than half the motion of a generic full-body plate with an
explicit screen direction. And more sampling steps made it WORSE.

The real finding underneath: speech-to-video is anchored to a talking head and
will not walk. Movement has to be written as its own silent shots. Which is how
animation is cut anyway — you rarely hear someone speak while they cross a room
in a wide.

## T2 — "Whole-body verbs work, small ones are ignored"

    stands up 5.70   rises 5.59   walks 5.44   crouches 3.62
    turns 2.97/2.56  lowers 2.25        (no action asked: 3.01)

"Turns to look" does nothing. "Stands up" nearly doubles the motion. A writing
rule, discovered by writing an episode with action in seven of eleven shots
after a two-shot test had concluded movement was unavailable.

## T2 — "Two capabilities I declared impossible, wrongly, by testing badly"

Both conclusions were about a MEASUREMENT, not a capability.

The two-shot test seeded from an EMPTY location plate — it gave the model no
face for either character and then scored it on whether it produced the right
faces. It also applied a 0.75 threshold built for close-ups to a wide shot
where each face is a fraction of the frame.

The action test used mostly the weak verbs, on two shots.

A badly built test does not return "unknown". It returns a confident wrong
answer, and that closes a question for good unless somebody pushes back. Both
were reopened because the person I was working for asked "are we really
saying that?"

## T2 — "A third of every prompt was describing what the picture already showed"

Wan's I2V system prompt, verbatim: *"Focus on dynamic content in the video
description and avoid adding static scene descriptions. If the user's input
already describes elements visible in the image, remove those static
descriptions."*

Both shipped ComfyUI templates match it — their positive prompts are subject +
action only. No background, no style, no palette.

Nearly every shot here is seeded from a staged plate that already shows the
location, the light and the palette. Ours described all three again. 75 words
to 50 once removed.

## T3 — settings that were in no documented configuration

    reference repo    shift 3   40 steps  cfg 4.5
    ComfyUI template  shift 8   20 steps  cfg 6.0
    this pipeline     shift 12  15 steps  cfg 5.0    <- neither

Not "close to the defaults with a tweak" — a configuration nobody documents,
with cfg BELOW the ComfyUI value rather than above the repo one.

## T3 — the negative that could not possibly matter

On the distilled branch at cfg 1.0, ComfyUI **discards negative conditioning
entirely before any forward pass** — `if math.isclose(cond_scale, 1.0): uncond_
= None`. Not a zero weight, a skipped computation.

So every hour spent tuning that 40-term list was, on those shots, tuning a
string the model never sees.

---

## What the arc is now

Part One was "everything silently broken". Part Two is better and harder:
**most of my beliefs about what the model could not do were beliefs about my
own tests.** Movement, two-shots, character LoRAs, step counts — each was
closed by a measurement I had built wrong, and each reopened only when someone
asked whether I was sure.
