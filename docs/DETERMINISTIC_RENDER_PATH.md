# Showrunner — Deterministic Render Path (3D / Blender)

Design doc for an alternative to the diffusion-based shot generation currently in the
pipeline. Drop this in the repo root or `docs/` and reference it from `CLAUDE.md`.

Status: **proposal / not yet implemented**. Nothing here replaces the existing
HunyuanVideo + FLUX path yet; see "Migration" for how they coexist.

---

## 1. Premise

The current pipeline generates **pixels**. This proposal generates a **scene graph** and
renders it deterministically with headless Blender.

The problem this solves is episodic consistency. Character identity across 400 shots and
12 episodes is a losing fight with LoRAs — you get to roughly 80% and the remaining 20%
is where an audience notices. In a 3D pipeline, consistency is not something you optimise
for; it is a property of the asset. The character *is* a mesh. Shot 1 and shot 4,000 are
identical by construction.

Secondary wins:

- Exact camera control (position, lens, DOF, movement) instead of prompt-steering
- Correct occlusion, contact, and scale
- Re-render any shot at any resolution without re-rolling
- Fix one shot without disturbing its neighbours
- Deterministic output: same input JSON → byte-identical frames

---

## 2. Architecture

```
script (Claude Sonnet)
        │
        ▼
shot list JSON  ◄── the LLM's real job: structured data, not pixel steering
        │
        ▼
scene compiler (Python)  ──►  bpy calls
        │
        ▼
headless Blender  ──►  frames + AOVs
        │
        ▼
FFmpeg assembly
```

The key move: the LLM is very good at emitting structured scene descriptions and very bad
at controlling a diffusion sampler. Give it the job it's good at.

### 2.1 Shot list schema (starting point)

```jsonc
{
  "episode": "s01e03",
  "scene": 4,
  "location": "kitchen_interior",
  "time_of_day": "night",
  "shots": [
    {
      "id": "s01e03_sc04_sh01",
      "type": "establishing",          // establishing | wide | medium | ots | cu | ecu | insert
      "duration": 3.2,
      "camera": {
        "focal_mm": 35,
        "height_m": 1.6,
        "target": "room_center",
        "move": { "kind": "static" }   // static | push | pan | handheld | dolly
      },
      "blocking": [
        { "character": "mika", "mark": "counter_left", "facing": "camera" },
        { "character": "ren",  "mark": "door",        "facing": "mika"   }
      ],
      "performance": [
        { "character": "mika", "motion": "wiping a countertop, distracted",
          "emotion": "resigned", "intensity": 0.4 }
      ],
      "dialogue": [
        { "character": "ren", "line": "You didn't call.", "emotion": "flat" }
      ]
    }
  ]
}
```

Validate with pydantic. The compiler should hard-fail on an unknown character, location,
or mark rather than improvising — silent improvisation is how continuity dies.

### 2.2 Scene compiler responsibilities

- Resolve `location` → load the set .blend, link (don't append) so sets stay single-source
- Resolve `character` → link rigged character collection
- Place characters on named empties (`mark`) defined in the set file
- Solve camera from shot `type` + character bounding boxes (see §4)
- Bind motion clips and lip sync to the rigs
- Set render settings, write frames + AOVs, emit a manifest

---

## 3. Generation still happens — at the motion layer

Motion curves are cheap, controllable, and temporally coherent by construction. This is
where generative models belong in this pipeline, not at the pixel layer.

| Need | Tool | Notes |
|---|---|---|
| Text → 3D body motion | **HY-Motion 1.0** (Tencent, MIT) | Billion-param DiT + flow matching, skeleton output, built to drop into 3D pipelines. Same family as the HunyuanVideo we already use. |
| Locomotion / idles / long tail | **Mixamo**, **AMASS** | Retarget once into the canonical skeleton, cache as a clip library |
| Lip sync | **Rhubarb Lip Sync** | Runs on the existing Edge-TTS wav output → viseme timeline → shape keys. Deterministic, and far better than what video diffusion does to a mouth. |
| Facial performance | ARKit-style blendshapes | Driven from `emotion` + `intensity` in the shot JSON |

Caching matters: a generated motion clip should be content-addressed by its prompt hash
and reused. Don't re-infer "walks to the door, tired" forty times.

---

## 4. Cinematography as code

The compiler needs opinions, or every shot looks like a security camera.

- **Shot type → framing rule.** CU = head bbox fills ~60% of frame height; medium =
  waist-up; OTS = foreground shoulder occupies a third, subject on the opposing third.
- **180° rule.** Track the scene's action line from the first two-shot; assert every
  subsequent camera stays on one side. Fail loudly on violation.
- **Thirds placement.** Place the subject's eyeline on a third, with lead room in the
  direction they face.
- **Cut rhythm.** Vary shot duration by beat type (dialogue vs. reaction vs. action).
  Uniform durations read as machine-made instantly.
- **Lens language.** Longer lens for intimacy/compression, wider for isolation. Keep a
  per-character or per-scene lens palette so episodes feel authored.

This layer is where the project actually succeeds or fails. Budget for it.

---

## 5. Assets

The front-loaded cost lives here.

**Characters — VRoid Studio.** Free, anime-stylised, exports VRM, ships rigged on a
standard humanoid skeleton. That satisfies the existing "force all character meshes into
a canonical humanoid skeleton" constraint at the source, which removes most of the need
for the UniRig / Mesh2Motion / Rigify auto-rigging work for main cast. Keep auto-rigging
in scope only for bespoke or non-humanoid meshes.

**Sets.** Build once per recurring location, with named empties for blocking marks. This
is the highest-leverage asset investment — a kitchen built once pays back across every
episode.

**Look.** EEVEE Next for speed. Toon shader ramps + the Line Art modifier for a cel look.
Cycles only if a specific shot needs it.

---

## 6. Migration — how this coexists with the current pipeline

Do not rewrite. Render Blender AOVs and feed them into the existing FLUX pass:

```
Blender  ──►  depth / normal / line art / segmentation
                        │
                        ▼
              ControlNet conditioning  ──►  FLUX.1-schnell  ──►  styled frames
```

Geometry supplies consistency and control; diffusion supplies style and detail. Because
the control signal is temporally coherent, the frame-to-frame flicker largely goes away.
Most of the existing ComfyUI stack survives; only the parts that are actually failing get
swapped.

Suggested sequencing:

1. Scene compiler + one set + one character, static camera, no dialogue. Prove the loop.
2. Add lip sync and the clip library. Prove a talking two-shot.
3. Add the cinematography rules. Prove a full scene.
4. Add the ControlNet style pass. Compare against the current pure-diffusion output.
5. Add HY-Motion for bespoke performance beats.

---

## 7. Honest tradeoffs

- **Front-loaded cost.** Diffusion gives you a shot in an hour and a series in never. 3D
  gives you nothing for weeks, then episodes for pennies. If the goal is a demo reel,
  this is the wrong path. If the goal is a series, it's the right one.
- **The hard problem moves, it doesn't vanish.** It stops being "does she look like
  herself?" and becomes "why does this performance feel dead?" That's a cinematography
  and acting problem, and it lands on the shot compiler.
- **Asset ceiling.** Anything not in the asset library cannot appear on screen. Diffusion
  will happily hallucinate a new prop; Blender will not. That's a feature for continuity
  and a constraint on story.
- **Style ceiling.** Pure EEVEE toon output has a recognisable "3D anime" look. The
  ControlNet hybrid is the escape hatch.

---

## 8. Open questions

- Where does the set/prop library come from — hand-built, asset packs, or 3D generation
  (Hunyuan3D / TRELLIS-class) with manual cleanup?
- Retargeting strategy: one canonical skeleton for everything, or per-character rigs with
  a retarget step? (Canonical is simpler; costs you body-type variety.)
- Does the shot compiler emit .blend files, or drive a persistent Blender process?
  Persistent is faster; .blend files are inspectable and debuggable.
- Render farm: local, or RunPod alongside the existing musubi-tuner work?

---

## 9. Project fit & answers (added by the code session, 2026-09-03)

Read alongside `docs/TALK_FIRST_FORMAT.md` and `docs/PRODUCTION_GRAMMAR.md`.
One correction to §2: this repo's diffusion stack is **WAN 2.2 (S2V +
i2v GGUF) + FLUX.1-schnell**, not HunyuanVideo — which changes one
conclusion below.

### 9.1 Where this lands in THIS pipeline

The doc's strengths map one-to-one onto our measured weaknesses, and its
weakness onto our strength:

| Shot type | Diffusion today (measured) | 3D path |
|---|---|---|
| Locomotion / walk-aways | worst instrument, blob characters | **wins by construction** |
| Wides / geography | plate-dependent, drift-prone | **wins by construction** |
| Two-shot blocking | fragile, plate-gated | **wins** (marks + occlusion) |
| Dialogue closes | **our best instrument** (S2V audio-driven lips) | *loses* — Rhubarb visemes are below S2V lip quality |

So the split is by shot type, not a migration: **3D owns everything the
grammar currently bans or rations** (movement, staging, geography);
**S2V keeps the dialogue closes** that the talk-piece format is built on.
The hybrid style pass (§6) is what keeps a 3D wide cuttable against an
S2V close.

### 9.2 Answers to §8

**Set/prop library — hand-built low-poly + projected plates, no 3D gen.**
The look of every location already exists as validated FLUX plates. Sets
should be *blocking geometry* — terrain, water plane, hall facade, path —
whose job is occlusion, parallax and marks, not beauty. Two routes for
appearance, tried in order: (a) camera-project the existing location
plates onto the geometry (the plate literally becomes the set), (b) the
ControlNet→FLUX style pass. Six recurring sets (valley, cliff, ruin,
storm, sea, winter valley) at roughly a day each. Hunyuan3D/TRELLIS is
deferred: cleanup cost plus the workspace quota trap make it a bad first
dollar.

**Retargeting — one canonical skeleton (VRM standard humanoid).** The
cast is two humans; body-type variety is not worth a retarget layer.
Mixamo/AMASS clips retargeted once into the canonical rig, cached
content-addressed as §3 says. Auto-rigging stays out of scope until a
non-humanoid appears in a script.

**Compiler output — .blend files, not a persistent process.** At our
scale (a talk piece is <30 shots; a chapter ~17) compile time is noise
next to render time, and this repo's hardest-won lesson is that silent
in-memory state hides failures — see `silent-failure-patterns`. A .blend
per shot can be opened and eyeballed the way `probe_shot.py` frames are
today, and diffing two .blends answers "what changed" the way seed
discipline does now. Revisit persistence only if compile ever exceeds
~10% of wall-clock.

**Render farm — the same 3090, same serial queue.** EEVEE shots are
minutes, not hours; they enqueue on the existing workbench render queue
(`workbench_data/render_queue.txt`) exactly like diffusion jobs, so the
idle-hibernate and cost story is unchanged. Two pod-specific facts:
apt ships Blender 3.0.1 — EEVEE Next needs the **4.2 LTS tarball**
(~350MB; test the workspace quota with a small write first, per the
environment-traps note), and headless EEVEE on the 3090 needs an EGL
context — verify with a 1-frame render before building anything on it.

### 9.3 Amendments to the doc's sequencing

Phase 1's proof should be **our known-bad shot, not a neutral one**: the
ep16 s11 walk-away wide (the murky blob-character shot) rebuilt as
geometry + walk cycle + style pass, cut against the current take. This
repo's QC doctrine is "validate instruments against a failure already
seen" — same rule for a new renderer.

Phase 2 (lip sync) is **descoped**, not deferred: S2V keeps mouths.
Rhubarb enters only if a 3D mid-shot ever needs incidental mouth
movement.

New precondition for the style pass: a FLUX-compatible ControlNet
(Union ~3.5GB, or a depth LoRA) is not on the pod — that download needs
the quota check and a hash-pinned source before phase 4 exists.

VRoid is a GUI app and cannot run here: main-cast VRMs get made on a
workstation and uploaded through the console's existing upload endpoint
(extend it to accept `.vrm` alongside images) — the same
bring-your-own-asset path new shows already use.

### 9.4 What is deliberately not answered yet

Whether projected-plate sets or the ControlNet pass better match the
established cel look is an empirical question — it is phase 1/4's job to
answer it with an A/B, not this document's to guess.

---

## 10. Phase-1 trial results (2026-09-03)

Rebuilt ep16 s11 (the walk-away wide) with `scripts/blender3d/trial_walkaway.py`.
Blender 4.2.9 LTS headless at `/workspace/blender42` (+ libSM/libEGL apt deps).

**Proven:**
- The loop: shot params → bpy → EEVEE Next → frames → ffmpeg. **81 frames in
  44 seconds** on CPU-contended hardware, vs ~10–15 GPU-minutes for the same
  shot through WAN. Deterministic: same script → same frames.
- **AI plate as the 3D set** (the driving idea): the FLUX valley master
  window-projected as emission makes the rendered background pixel-identical
  to the validated plate. Zero drift, zero palette risk, and the figure
  moves through it with correct perspective shrink.
- Iteration speed: three figure revisions at ~45s each. A diffusion shot
  gives one roll per 12 minutes.

**Learned the hard way:**
- EEVEE Next defaults motion blur ON — smeared the walk into a translucent
  ghost. Cel has none; `use_motion_blur = False`.
- Inverted-hull outlines consume small parts at wide-shot scale; skip
  outlines below ~30px on-screen height.
- Emission colours are linear; pick them ~1 stop darker than the sRGB target.

**The asset ceiling, confirmed:** a procedural cone-and-spheres figure reads
as a cone. Geometry, travel and gait are right; the *drawing* is absent.
The front-loaded cost the doc promises is real and it is exactly here:
a proper character mesh (VRoid VRM made on a workstation, uploaded through
the console) is the gate to phase 2.

**Style pass (phase-4 preview, single frame):** FLUX img2img over the 3D
frame at denoise 0.45 keeps the environment beautifully and **erases the
small figure**; 0.62 re-invents a different figure elsewhere. Plain img2img
cannot pin a small character — ControlNet conditioning (depth/line AOVs,
Union ~3.5GB download) or a WAN-side video restyle (VACE, not installed)
is a hard precondition, not an optimisation. Trial script:
`scripts/blender3d/style_pass_trial.py`.

**Review artefacts:** `b3d_ab_walkaway.mp4` (A/B vs the live diffusion take),
`b3d_style_pass.png` (raw | d45 | d62), sent to the user 2026-09-03.

---

## 11. Pivot: the pure-Blender path (user direction, 2026-09-03)

The hybrid in §9 kept WAN for dialogue. The user's actual target is stronger:
**Blender is the whole studio.** AI images are seed material only —
everything on screen is 3D, animated and rendered deterministically.
No WAN in the animation path.

```
plates (FLUX)      ──depth──►  terrain + projected environments
portraits (FLUX)   ──img→3D──► character meshes ──auto-rig──► rigged cast
                                   │
motion library (walk/idle/turn) ───┤
                                   ▼
             episode JSON ──► scene compiler ──► EEVEE ──► film
```

### Trial A — scene from an image: PROVEN
`depth_from_plate.py` (Depth-Anything-V2-Small, CPU) +
`scene_from_image.py`: every plate pixel becomes a vertex at its estimated
depth, textured by the plate. The camera dollies **through** the painting
with true parallax — 81 frames in 46s. Limitation measured: disocclusion
smear where the source image has no information; keep moves ≤ ~2m push or
fill with a second projected plate. Artefact: `b3d_scene_flythrough.mp4`.

### Trial B — character from an image: mesh PROVEN, rig pending
`character_from_image.py` (Hunyuan3D-2 shape, 30 steps, ~4 min/mesh):
- The head-and-shoulders portrait produced a faithful **bust** — image→3D
  gives you exactly the framing you feed it. Full characters need
  full-body seeds.
- `fullbody_sheet.py` generates an A-pose character sheet with FLUX
  (plain ground, no props), and that meshed into a clean **210k-vert
  full-body figure**: separated limbs, modelled cloak, boots — riggable
  geometry. `series/tir-na-nog-legend/meshes/oisin_fullbody.glb`.
- Identity note: the FLUX sheet drifted younger/less beard than the
  canonical portrait — sheet prompts need the same eye/beard pinning as
  the plates, and the head can be judged before rigging.
Next: **UniRig** auto-rig → CMU BVH walk retarget → the depth-terrain
walk-away with a real character. Texture: Hunyuan3D paint stage, or
projected portrait — decide after the rig proves out.

### S2V decision (user, 2026-09-03)
Dialogue closes stay S2V for now — the mouth question is parked, not
solved. The pure-Blender path owns scenes, movement, blocking, wides.

### Faces and dialogue in pure 3D — the honest plan
Audio-driven S2V lips are out by definition here. The replacement is the
**limited-animation mouth**: 6–8 viseme texture/shape swaps driven by
Rhubarb from the existing TTS/recorded audio. That is Samurai Jack /
South Park grammar — stylised, deterministic, and consistent with the
show's lineage — but it is a *style change* from the current S2V closes,
and the user should judge a test close before any episode commits to it.

### Sequencing
1. ✔ scene-from-image parallax
2. Hunyuan3D on Oisín's portrait → mesh (first GPU window)
3. UniRig + one retargeted walk clip on that mesh
4. The walk-away rebuilt with the real character in the depth terrain
5. Rhubarb mouth test on a close-up
6. Then: compiler grows blocking marks, shot types, and the cinematography
   rules from §4 — the full automated series maker, no diffusion at runtime.

### Trial C — the first pure-3D shot: DONE (2026-09-03)
`shot_walkaway_v2.py`: the Hunyuan3D character, auto-weighted onto a
scripted biped armature with a keyframed walk cycle, sheet-projected
costume, walking away through the depth-terrain valley. 81 frames,
~55s per render, six art iterations in under an hour.
Bugs that will bite again: stage to the TERRAIN surface, not z=0 (the
camera-height float); the mesh faces -Y (turn it for walk-aways);
single-view projection has no back — head samples the sheet's hair band
(probed at v≈0.908), a real texture needs the paint stage.
Artefact: `review/pure3d_walkaway.mp4`.

### Trial D — the REAL 3D set (user: "this seems superimposed") — DONE
Correct call: trial C was 2.5D — a painting draped over depth geometry
with an unlit sticker of a character. `valley_set.py` +
`shot_walkaway_3d.py` replace it with true scene rendering: modelled
valley (terrain relief, lake, waterfall, hall with tower, trees, cross,
flowers, clouds), two-tone toon materials via ShaderToRGB ramps, a sun
with cast shadows (clouds dapple the grass; `sc.eevee.use_shadows` must
be set), and the character's projected costume now goes through a lit
two-tone mix instead of raw emission — he is lit by the scene and
occluded by it. 81 frames / ~62s. The look is flat-cel primitive-shape
(closer to Samurai Jack backgrounds than the FLUX painted look) — the
style gap vs the plates is the next argument for either Hunyuan3D props
from images or the ControlNet style pass.
Artefact: `review/real3d_walkaway.mp4`.

### Trial E — the VIRTUAL STUDIO (user direction): DONE
`build_studio.py` saves the whole stage as one .blend (set + rigged,
dressed character + the walk performance + master camera, textures
packed — 35MB, `review/studio_valley.blend`). Open it in Blender to
orbit, scrub the take, pose cameras. `film.py` renders any angle from
the command line:

    blender -b studio_valley.blend --python film.py -- \
        <outdir> <cam x,y,z> <target x,y,z> [lens] [f_start] [f_end]

Proof: the SAME 81-frame performance filmed from three cameras (master
wide 35mm / low-follow 30mm / side profile 40mm) and cut as coverage —
`review/studio_coverage_cut.mp4`. One take, many angles: the property
diffusion cannot offer. The side angle shows a true cast shadow; it also
shows the single-view projection smearing at close range, and the
walk-away head-hair hack means no face from the front — both are the
same argument: Hunyuan3D's texture-paint stage is the next unlock.

**Both set types stay in the toolkit** (user: "the 2.5D is also looking
good"): the depth-terrain painted backlot for the FLUX painted look with
parallax on modest moves, and the full-3D set for free camera, shadows
and blocking. film.py doesn't care which kind of stage the .blend holds.

### Trial F — cameras that move IN the scene: DONE
film.py now keyframes real camera moves: `pan` (fixed position, tracks
the character each frame via the rig's world position), `dolly:x,y,z`,
`orbit:degrees`, `crane:dz` — all smoothstepped, all deterministic.
Showcase (`review/studio_camera_moves.mp4`): orbiting establisher →
tracking pan as he passes close → low dolly push, one performance.
Head upgraded to front/back split projection: a real face from the
front (eyes smear into a band — the projection stretches the sheet's
eye row; texture paint is still the fix), hair from behind.
