# Production grammar

How to write an episode this pipeline will render well.

The models do not make an arbitrary shot. They make a narrow set of shots very
well and everything else badly, quietly. Writing to that set is the whole
difference between an episode that looks authored and one that looks like it
fought its tools.

`scripts/lint_episode.py` enforces all of this. Run it before rendering:

    python scripts/lint_episode.py tir-na-nog-legend --episode 13 --strict

---

## The one rule that matters most

**A shot either talks, or it moves, or it is wide. Never two of those.**

Everything below is that sentence, in detail.

---

## The three shot types

The pipeline has exactly three, and they are good at different things.

| | drives | motion | framing you get | use it for |
|---|---|---|---|---|
| **Speech** (S2V) | a voice | 2.9 – 3.9 | close / medium, always | someone saying something |
| **Silent action** (I2V) | a plate | up to **12.1** | whatever the plate is | movement, travel, gesture |
| **Establishing** (T2V) | text only | n/a | wide | landscape with nobody in it |

Two numbers to keep in your head: a talking shot moves at about **3**, a silent
shot of the same character moves at about **12**. That is the entire argument
for separating speech from movement.

---

## R1 · Dialogue is never wide

Write "wide shot, the warrior small among the stones" and give him a line, and
you get a head and shoulders. Six times out of eight, measured. Every one was
seeded from a correct full-body plate; the speech model pulls to the face
because that is what it was trained to do.

**Write instead:** dialogue in medium or closer. If you want the line delivered
over a landscape, make the shot *silent* and lay the voice over it — nobody
needs lip sync on a mouth six pixels across, and this is what an animator would
do anyway.

## R2 · Dialogue never moves

Verbs measured *inside* a talking shot:

    step 3.85 · turn 3.78 · gesture 3.47 · sit 3.40 · still 2.87

The best a talking shot manages is 3.85. The same character walking, silently,
measures **12.13**. A talking shot that is asked to walk does not walk; it
stands still and you have spent a shot.

**Write instead:** two shots. He crosses the ground (silent). He stops and
speaks (close). That is also just better cutting.

## R3 · One speaker per shot

The speech model drives **one** face from **one** audio track. A second speaking
character in the same shot has no mechanism to be driven, and distorts.

**Write instead:** shot / reverse-shot. She speaks. Cut. He answers. This is the
standard grammar of every filmed conversation and it happens to be the only one
available.

Two characters *present* with one speaking is a warning rather than an error —
the silent one may drift. Prefer one character per dialogue shot.

## R4 · Movement wants a full-body plate

The same walk, two different seeds:

    full_body plate      motion 12.13   travel 42.3
    walking_away plate   motion  5.17   travel 30.1

The plate chooses the movement more than the prompt does. Seed movement shots
from `*_full_body` or `*_three_quarter`, never from a location plate with no
figure in it.

Use whole-body verbs — *walks, crosses, climbs, rides*. Small verbs (*turns,
lowers, glances*) produce about half the motion.

## R5 · A line fits in 15 seconds

Speech chains to three chunks — 15.19s, roughly **39 words**. Longer is
truncated, and the truncation used to be silent. Split long speeches across
shots; it reads better anyway.

## R6 · Two characters in one frame is a split panel

From a composite seed both faces render recognisably (0.888 / 0.790). But what
arrives is a hard vertical seam with the two at different scales — a diptych,
not a staged two-shot. Without a composite seed both identities collapse
(0.62 / 0.68).

**So:** do not write naturalistic two-shots. Either cut between single shots, or
use the split panel *deliberately*, as anime does — two faces, one frame, one
beat. Used on purpose it is a style. Used by accident it is a mistake.

---

## Writing to this, positively

The constraints point at a real and recognisable style — closer to a graphic
novel or to older limited animation than to full character animation:

- **Scenes alternate between held speech and silent movement.** A character
  crosses a landscape; he stops; he speaks; we cut wide as he walks on. The
  rhythm comes from the alternation.
- **Conversations are shot/reverse-shot,** in close and medium, held long. Shots
  can now run 8–15 seconds, so let them.
- **Landscape carries the weight.** Wides are silent, and they are where the
  scale and the beauty live. Put voiceover over them freely.
- **Nobody talks while walking.** Which is fine — in myth, people stop to speak.
- **Two people in one frame is a deliberate device,** used once or twice an
  episode for a beat, not the default coverage.

None of that is a compromise. It is a house style with a reason behind every
element, which is more than most series can say.

---

## Checklist before rendering

    python scripts/selftest.py                        # 56 regression checks
    python scripts/lint_episode.py <series> --episode N --strict
    python scripts/preflight.py <series> --episode N  # plates, audio, config
    python scripts/validate_workflow.py <series> --episode N

Then render. Then `verify_render.py`, remembering that it scores faces and
cannot see framing, staging, or performance — the three things this document
exists to protect.
