# Production quality — what is left, ranked

State at the time of writing: two films finished (3:57 and 3:25), cel-shaded,
character identity 0.88-0.91, long takes 4-14.5s, layered per-location
ambience, 1080p via RealESRGAN anime 6B. What follows is what still separates
this from a small studio's work, in the order I would do it.

---

## POST-PRODUCTION — no GPU, mostly free

### 1. Give every shot a camera  *(built: scripts/camera_move.py)*
27 of 27 shots in the film are locked off. That is the loudest remaining
amateur signal -- louder than lip sync, louder than resolution. 27 static
frames read as a slideshow of moving portraits however well each is composed.

Free because the 1080p pass already upscales to 3328x1920 before resampling to
1920x1080: 1.73x linear headroom sitting unused. Cropping a MOVING 1920x1080
window out of the 4x frames is a real camera move at delivery resolution.

    close-up / medium  -> push in     decisions, confessions
    wide / full body   -> pull out    isolation, endings
    over-shoulder      -> drift       lateral
    a few              -> hold        so stillness reads as a choice

4-7% across a shot. A move you notice is too big.

### 2. Cut inside the takes -- reaction shots
One shot is currently one complete line, always. That is why it still plays as
alternating statements rather than as a conversation. Take 1.5s of the
listener's take, drop it into the middle of the speaker's line, run the
speaker's audio unbroken underneath. Existing footage, no GPU. Would change the
cross-cut most of all.

### 3. Per-movement colour grade
One grade across everything. The valley wants warmth and lift; the ruin wants
coolness and crushed blacks. Free, and it reads as "someone finished this".

### 4. Score with structure, and spot foley
The drone never develops -- no motif, no arrival. A theme tied to the counting
line, returning at the end, would bind the film. And there is not one spot
effect anywhere: no hoofbeat, no spear planted, no cloth movement. Beds alone
are ambience, not sound design.

### 5. Title and end cards
There are none. Typography is disproportionately cheap and effective.

---

## GENERATION — this is what the GPU is for

### 6. Coverage: alternate takes on the shots that matter
The single biggest gap in method. A real production shoots a scene several
times and picks. This pipeline renders each shot ONCE and accepts whatever
comes back -- every shot in both films is a first take. Rendering 3 variants of
the 10 most important shots and choosing on measured identity plus eye is what
a studio actually does, and it is pure GPU time.

### 7. Does WAN 2.2 do camera moves natively?
Deep research returned ZERO surviving claims on this. Unanswered, and worth
answering empirically: render the same shot as static, "slow dolly in", "slow
pan left", "handheld", score identity and artefacts on each. If the model can
execute a move without warping, that beats a post crop, because the parallax is
real. If it cannot, item 1 stands and the question is closed.

### 8. A character LoRA trained against the S2V checkpoint
Character LoRAs are currently DROPPED on every dialogue shot -- measured
cross-family degradation, identity -0.138 and cel style collapsing 0.999 ->
0.001. Dialogue is ~80% of both films, so those shots run with no character
training at all. A LoRA trained on the S2V family would apply where it matters
most. Highest potential identity gain available; also the highest risk, since
musubi's S2V support is unverified.

### 9. More setups per location, and the locations not yet built
3-5 camera positions per place. More angles means more varied cutting and less
reuse of the same framing. stormy_sea has never been staged at all.

### 10. Better anchors
Every plate and every shot descends from nine portraits. Regenerating them at
higher quality, with more angles, lifts everything downstream.

---

## WHAT SEPARATES THIS FROM A STUDIO NOW

Post-production is largely done -- camera, grade, shot matching, film look,
reaction cuts, titles. What remains is not finishing, it is generation.

### 11. Characters do not DO anything   *(testing: scripts/action_test.py)*
**42 of 55 shots are a person standing still, talking.** Only 13 describe any
physical action and most of those are "turns to look". Studio animation has
bodies doing things -- walking, reaching, sitting, handing something over --
and the absence of that is the deepest remaining tell, deeper than lip sync or
resolution.

Two questions in one, and they need separating. WRITING: nearly every visual in
every episode ends "Static camera. He speaks." If the prompt never asks for
action, none appears. CAPABILITY: whether S2V will move a body while driving a
mouth from audio is untested -- it may ignore the clause, or take it and lose
the face or the sync.

### 12. Two characters in one frame   *(testing: scripts/two_shot_test.py)*
55 shots, zero two-shots. Every conversation is two people never seen together.

### 13. Voice performance
With the picture this consistent, Edge-TTS is the loudest artifact left: clear
but flat, no breath, no hesitation, the same energy from first word to last.
Only edge-tts is installed. Two routes -- splitting lines into phrases with real
pauses and varied rate (cheap, CPU), or an expressive local TTS with cloning
(bigger, better ceiling).

### 14. Backgrounds that live
Plates are static and I2V adds only slight motion. Real animation has water
moving, cloth lifting, birds, light shifting. Currently the only thing moving in
most shots is a face.

### 15. Continuity of action across a cut
Nobody picks something up in one shot and holds it in the next. Every shot is
self-contained, which is why the pieces read as a series of statements.

---

## NOT NEXT, and why

**Phoneme-accurate lip sync.** Research is unambiguous: every locally runnable
model is measurably WORSE on stylised faces (MuseTalk 67.8%, LatentSync 35.6%
success on stylised vs 92.2%/74.9% on all video) because they depend on
photoreal face detection. The one method that holds up has no public weights.
The local route is Rhubarb, which emits timing data, not pixels -- so it only
pays off after building a mouth-art compositing stage. Large job, gain most
viewers cannot name.

**Frame interpolation to 24fps.** Research produced no surviving claim, and cel
animation held on twos can look worse interpolated, not better. Test before
believing.

**Native 720p rendering.** Already measured: 2.75x the cost, waxier not
sharper. Upscaling wins.

**Prop/costume consistency via MAGREF.** The only verified route, but it is
Wan 2.1 not 2.2, a full 14B checkpoint rather than a LoRA, and evaluated only
on photoreal content.
