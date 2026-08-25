# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

An end-to-end automated animated series production pipeline. Given a concept, it uses Claude to write episode scripts, ComfyUI (WAN 2.2) to generate video clips, Edge-TTS for voiceover, and FFmpeg to stitch everything into finished MP4 episodes. A full-stack web UI (FastAPI + React) manages projects, characters, locations, and episodes — and is intentionally kept polished for screen recording/demo purposes.

**Current owner: personal use only.** The UI is a demo asset — preserve its look and feel when making changes.

---

## Running the System

Three services must all be running:

```bash
# Terminal 1: ComfyUI video generation server
# conda activate video-comfy  (if using conda)
bash scripts/launch.sh                  # → http://localhost:8188

# Terminal 2: FastAPI backend
cd app/backend
# Requires app/backend/.env with SECRET_KEY set (see .env.example)
export ANTHROPIC_API_KEY="sk-ant-..."
uvicorn main:app --reload               # → http://localhost:8000

# Terminal 3: React frontend dev server
cd app/frontend
npm run dev                             # → http://localhost:5173

# Build frontend for production
cd app/frontend && npm run build        # output → dist/
```

### First-time setup
```bash
cp app/backend/.env.example app/backend/.env
# Edit .env and set SECRET_KEY=$(openssl rand -hex 32)
```

### Long production runs (survive SSH drops)

Never run a multi-hour production in the foreground — a dropped SSH connection
kills it. Use the checkpointed job runner instead:

```bash
scripts/jobctl start jobs/palestine-v2-quality.job.sh   # detached + checkpointed
scripts/jobctl status <job>                             # progress
scripts/jobctl log <job> -f                             # follow
scripts/jobctl start <job>                              # resume after any interruption
```

ComfyUI runs as its own detached daemon (`scripts/ensure_comfyui.sh`), so a clip
in flight when the connection drops still finishes and is picked up on resume.
See `jobs/README.md`.

### CLI Production Pipeline (standalone, no web UI)

```bash
python scripts/showrunner.py create my_series
python scripts/showrunner.py write my_series          # Claude generates bible + episodes
python scripts/showrunner.py write my_series --episode 5
python scripts/showrunner.py produce my_series --episode 1 --image ref.png
python scripts/showrunner.py produce my_series --episode 1 --resume
python scripts/showrunner.py produce-all my_series
python scripts/showrunner.py status my_series

# Quick single-clip test
python scripts/comfyui_api_gen.py workflows/wan22_t2v_480p.json \
  -p "A cat on a windowsill, cinematic" -s 42
```

---

## Architecture

```
React UI (Vite/Tailwind)
    ↓  Axios + WebSocket (?token= for WS auth)
FastAPI Backend (app/backend/)
    ├── routers/           CRUD + scene regeneration + portrait selection
    ├── pipeline.py        DB↔showrunner bridge; scene + episode job runners
    ├── routers/generate.py  → Claude API for script generation
    └── SQLite (SQLAlchemy ORM)
         ↓
showrunner.py (scripts/)
    ├── ComfyUI API (localhost:8188)   T2V + I2V video generation
    ├── Edge-TTS                       Per-scene voiceover
    └── FFmpeg                         Clip stitching → final MP4
```

### Episode Production Data Flow

1. `POST /episodes/{id}/produce` → `pipeline.produce_episode_job()` in a `threading.Thread`
2. `export_project_to_files()` writes `series/{slug}/bible.json` + `episodes/ep*.json` from DB
3. `showrunner.cmd_produce()` runs: T2V first scene → I2V chaining for subsequent scenes
4. Edge-TTS + FFmpeg stitch audio and clips
5. `_backfill_scene_clips()` updates every `scene.output_clip_path` + `scene.status` in the DB after completion so previews appear in the UI
6. Progress streamed to UI via `GET /ws/{job_id}?token=<jwt>`
7. **Cancel**: `POST /jobs/{id}/cancel` sets `cancelled_at`, progress thread detects it, sends `/interrupt` to ComfyUI, job ends with status `"cancelled"`

### Auto-Export (DB → JSON sync)

Every create/update/delete on characters, locations, scenes, and episodes triggers `export_project_in_background()` — a fire-and-forget thread that writes `bible.json` + episode JSONs. This keeps the on-disk files in sync with the DB at all times, eliminating the previous dual source-of-truth issue where files could go stale between production runs.

### Single-Scene Regeneration Data Flow

1. `POST /scenes/{id}/regenerate?quality=draft` → `pipeline.generate_single_scene_job()` in a thread
2. Scene marked `status="generating"` immediately
3. Project exported, `build_scene_prompt()` + `get_scene_seed_image()` called from showrunner
4. T2V or I2V workflow submitted to ComfyUI; `scene.output_clip_path` + `scene.status` updated on completion
5. UI polls `GET /episodes/{id}` every 3s while any scene in the episode has `status="generating"`

### Character Consistency System

Characters have a **canonical portrait** that feeds directly into video generation:

1. **Generate**: `POST /characters/{id}/generate-portrait` → ComfyUI T2I → 3 candidates saved to `series/{slug}/reference_images/char_{id}_v{1,2,3}.png`
2. **Select**: `POST /characters/{id}/select-portrait` with `portrait_path` → copies chosen file to `series/{slug}/reference_images/char_{id}.png` (the path `showrunner.get_scene_seed_image()` looks for) + updates `character.reference_image_path` in DB
3. **Used**: `get_scene_seed_image()` in showrunner uses the canonical `char_{id}.png` as the I2V seed image for dialogue scenes and close-ups featuring that character — ensuring visual consistency across episodes

Character `visual_description` is injected into every scene prompt via `build_scene_prompt()` (brief form for dialogue, full form for wide/establishing shots).

---

## Key Source Files

| File | Role |
|------|------|
| `scripts/showrunner.py` | ~95KB orchestrator: Claude calls, ComfyUI workflows, FFmpeg, prompt building |
| `app/backend/pipeline.py` | `produce_episode_job`, `generate_single_scene_job`, `_backfill_scene_clips`, `export_project_to_files`, `generate_character_portrait` |
| `app/backend/models.py` | SQLAlchemy ORM: User, Project, Character, Location, Episode, Scene, GenerationJob |
| `app/backend/schemas.py` | Pydantic v2 schemas with field validation, password complexity, `SelectPortraitRequest` |
| `app/backend/routers/scenes.py` | Scene CRUD + `POST /scenes/{id}/regenerate` |
| `app/backend/routers/characters.py` | Character CRUD + portrait generation + `POST /characters/{id}/select-portrait` |
| `app/backend/routers/episodes.py` | Episode CRUD + `POST /episodes/{id}/produce` |
| `app/backend/routers/jobs.py` | Job status REST + WebSocket (`/ws/{job_id}?token=`) |
| `app/frontend/src/components/EpisodesTab.jsx` | Episode/scene list, per-scene regenerate button, inline preview player, 3s polling |
| `app/frontend/src/components/CharacterModal.jsx` | Character form + portrait generation + canonical portrait selection |
| `app/frontend/src/components/TheaterTab.jsx` | Episode viewer — lists finished episodes with inline video player |
| `app/frontend/src/components/CharacterCard.jsx` | Character card with canonical portrait star badge |
| `app/backend/templates.py` | Pre-seeded project templates (noir-detective, space-frontier, folklore-horror) |
| `workflows/wan22_t2v_480p.json` | Default ComfyUI T2V workflow |
| `workflows/wan22_i2v_480p.json` | I2V workflow (used for chaining + character ref seeding) |

### Key showrunner.py Functions (for pipeline.py integration)

| Function | Line | Purpose |
|----------|------|---------|
| `build_scene_prompt(scene, bible)` | ~596 | Builds video prompt with character descriptions injected |
| `get_scene_seed_image(scene, series, chain)` | ~1223 | Picks I2V seed: char ref → location ref → previous frame chain |
| `build_wan_t2v_workflow(...)` | ~822 | T2V workflow: single high-noise model + KSampler |
| `build_wan_i2v_workflow(...)` | ~855 | I2V workflow: dual-model KSamplerAdvanced (high+low noise) |
| `classify_scene_type(scene)` | ~1081 | Returns "i2v" (characters), "s2v" (dialogue), or "t2v" (establishing) |
| `build_negative_prompt(scene)` | ~645 | Universal negatives for all scenes; extra for dialogue |
| `DENOISE_PRESETS` / `DEFAULT_DENOISE` | ~76 | Faithful (0.70), Balanced (0.82), Creative (1.0) |
| `queue_prompt(workflow)` | ~766 | POST to ComfyUI, returns prompt_id |
| `poll_until_done(prompt_id)` | ~773 | Polls until complete (30min timeout) |
| `find_latest_clip(prefix, series=None)` | ~814 | Most recent MP4 for a scene id **within one series** (defaults to the thread's current series) |
| `set_current_series(slug)` / `current_series()` | ~64 | Thread-local series scope for clip output + lookup |
| `save_prefix(clip_prefix)` | ~78 | ComfyUI `filename_prefix`, scoped to the series |
| `update_flags(ep_out, bad, checked)` | ~2705 | Records the latest verdict for examined clips; un-flags ones that now pass |
| `read_json_state` / `write_json_state` | ~1701 | Corruption-tolerant read + atomic write for on-disk state |
| `CLIP_LENGTHS` | ~80 | `{"short": {"frames": 49}, "medium": {"frames": 65}, "long": {"frames": 81}}` |
| `QUALITY_STEPS` | ~70 | `{"draft": 15, "good": 25, "final": 40}` — largely superseded by `--lightning` |

---

## Clip Storage Layout

Rendered clips live in **per-series subdirectories**:

```
ComfyUI/output/video/
├── tir-na-nog/            ep01_s01_00011_.mp4 …
├── palestine-stories-v2/  ep01_s01_00010_.mp4 …
└── archive/               superseded takes (scene-version snapshots)
```

Scene ids (`ep01_s01`) are only unique *within* a series — every series has an
`ep01_s01`. They were previously written to one flat directory, so
`find_latest_clip()` returned whichever series rendered last: a `--resume` run
of series B could skip a scene because series A had a same-named clip, and
stitch the wrong series' footage into the episode.

Rules when touching clip code:

- Never build a `filename_prefix` by hand — call `save_prefix(clip_prefix)`.
- Never call `find_latest_clip(prefix)` from a context that has not set the
  series. CLI runs get it from `main()`; `cmd_produce`/`cmd_produce_all` set it
  from `args.series`; the FastAPI backend calls `showrunner.set_current_series()`
  per job thread and passes `series=` explicitly where it looks clips up.
- The scope is **thread-local** — the backend produces episodes in threads, and
  a plain global would let two concurrent jobs file clips under the wrong series.

Legacy clips written before this split are attributed with
`python scripts/migrate_clips_to_series.py` (dry run by default, `--apply` to
hardlink them into the right series directory). It replays the old selection
rule against each episode's stitched-mp4 timestamp.

---

## Series File Format

```
series/{slug}/
├── concept.json           # User-authored: title, premise, tone, visual_style, setting
├── bible.json             # Claude-generated: characters, locations, world rules
├── reference_images/
│   ├── char_1.png         # Canonical portrait (copied here by select-portrait)
│   ├── char_1_v1.png      # Generated candidates
│   ├── char_1_v2.png
│   └── char_1_v3.png
└── episodes/
    ├── ep01.json          # Claude-generated scenes
    └── ep02.json
```

Scene JSON fields: `id`, `location`, `characters[]` (keys like `char_1`), `clip_length`, `visual`, `narration`, `dialogue[]`.

---

## API Reference (additions to standard CRUD)

| Endpoint | Purpose |
|----------|---------|
| `POST /scenes/{id}/regenerate?quality=draft\|quality` | Regenerate single clip; polls via scene.status |
| `POST /characters/{id}/generate-portrait` | Generate 3 portrait candidates via ComfyUI |
| `POST /characters/{id}/select-portrait` | Set canonical portrait; copies to `char_{id}.png` |
| `POST /episodes/{id}/produce?quality=draft\|quality&denoise=0.82` | Full episode production; denoise controls reference fidelity |
| `POST /jobs/{id}/cancel` | Cancel a running production job; interrupts ComfyUI |
| `GET /ws/{job_id}?token=<jwt>` | WebSocket: streams job progress |
| `POST /projects/{id}/generate-scripts` | Claude writes all episode scripts |
| `GET /projects/templates` | List available project templates |
| `POST /projects/from-template?template_id=X` | Create project pre-seeded from template |
| `GET /projects/{id}/theater` | List episodes with final video paths for viewing |

---

## Security Notes

- `SECRET_KEY` is **required** in `.env` — app refuses to start without it. Generate: `openssl rand -hex 32`
- WebSocket auth via `?token=<jwt>` query param — ownership verified before `accept()`
- All `location_id` and `character_ids` in scene create/update are validated to belong to the same project
- Rate limiting: `/auth/login` 20/hour, `/auth/register` 10/hour (via `slowapi`)
- CORS restricted to `localhost:5173` and `localhost:4173` — update `ALLOWED_ORIGINS` in `.env` for production

---

## Two mistakes that keep costing hours

**1. Never `pkill -f` / `pgrep -f` a pattern.** The shell running the command has
that pattern in its own command line, so it matches and kills itself. This killed
a working session five times in one day, twice mid-edit, and once left a wait
loop spinning forever against its own process. There is no safe pattern; record
the PID instead:

```bash
scripts/bglaunch <name> <command...>    # runs detached, writes .jobs/pids/<name>.pid
scripts/bglaunch stop <name>
scripts/bglaunch status
```

**2. Test the configuration you are shipping, not one beside it.** Twice in one
day a change was validated in a setup that differed from the render it went into:

- an S2V prompt fix was tested with **no LoRAs**, then shipped into a render
  **with** a stale LoRA that reversed the result — an hour lost, render stopped
- the whole staged-plate system was built seeding **from the location plate**,
  two hours after measuring that plate seeds score 0.645 on identity precisely
  because they contain no face — 40 minutes of GPU, every close-up plate came
  back empty

Before a test that informs a decision, write down the shipped config and the test
config side by side. If they differ, the test does not answer the question.

---

## Before rendering an episode

Three gates, in this order. Skipping the third is how most of this file's
hard-won rules were learned the expensive way.

```bash
python scripts/selftest.py                                 # INVARIANTS  (seconds, no GPU)
python scripts/preflight.py <series> --episode N           # CONFIGURATION
python scripts/probe_shot.py <series> --episode N --auto   # INTENT
```

`selftest` asserts the pure functions behind every defect this pipeline has
shipped: seeding policy, trigger words, crossfade-aware offsets, narration that
is never word-capped, Lightning's cfg and dual-model handoff, ambience word
boundaries, and that the negative prompt does not fight the series' own style.
It runs in seconds with no GPU and exits non-zero, so it gates a job. `preflight`
runs it too — the two answer different questions and a green preflight over a
regressed stitcher still produces a broken episode.

Add a check here whenever a defect is found. A suite that has never failed
proves nothing: after adding one, deliberately regress the fix and confirm it
goes red.

`preflight` verifies wiring: trigger words reaching prompts, LoRA files
resolving, seeding, models present, ambience mapping, narration budgets. It
exits non-zero on failures so it can gate a job.

`probe_shot` renders **three shots** — a dialogue close-up, a character wide,
an establishing plate — and prints the exact prompt for each. These are the
three shapes that have failed differently, and every serious defect in this
project was found by looking at a picture rather than by a check that passed:

- a heroine absent from her own entrance (seeding fell through to the chain)
- six locations that were all the same cliff (style string held subject matter)
- dialogue close-ups in modern interiors (location omitted for close-ups)
- a shot double-exposed over the previous one (seed override ignored)

Each cost a 2.5-hour render to discover and would have been obvious in ten
minutes. **Look at the probe before committing to the episode.**

### Strict mode (on by default)

Every path in `showrunner.py` used to warn and continue, so a wrong
configuration and a right one produced the same exit code and the same
"JOB COMPLETE". These conditions now abort at the offending shot:

| Condition | Why it is fatal |
|---|---|
| LoRA file not found | Renders without it, looks plausible, proves nothing |
| `seed:location` with no plate | Falls through to the chain — re-renders the previous shot |
| Chain broken, no portrait fallback | Next shot seeds from a stale or missing frame |
| Narration too long even sped up | Audio overruns the shot and drifts the rest of the film |
| Clip validation failure | Stitches a finished-looking episode with broken shots in it |

`jobctl` checkpoints completed shots, so aborting at shot 7 of 16 and resuming
after the fix costs only shot 7. Finishing wrong costs the whole render.
`--no-strict` opts out per run; use it for experiments, never for a delivery.

Advisory warnings — recoverable state, absent optional binaries — are
deliberately **not** promoted. Only conditions where the output will be wrong.

---

## Sampling: use `--lightning`

LightX2V's step-distilled LoRAs are installed (`lightning-{t2v,i2v}-{high,low}.safetensors`).
Measured on this box at 49 frames / 480x832:

| Setting | Time | Result |
|---|---|---|
| 18 steps, cfg 5.0 | 490s | smeared, painterly |
| 4 steps, cfg 1.0 + LoRA | 80s | clean |
| 8 steps, cfg 1.0 + LoRA | 120s | clean, slightly better |

So it is ~6x faster **and** better — final quality now costs less than the old draft.
`--lightning [--lightning-steps N]` injects the LoRAs, forces cfg 1.0 / euler / simple, and
rescales the dual-model handoff (I2V splits at `steps//2`).

**CFG must drop to ~1.0.** Left at 5.0 the distilled model burns out and it looks like the
LoRA is broken rather than the guidance being wrong.

---

## Audio and subtitle timeline invariants

Three bugs here caused audio and subtitles to drift progressively later in an episode.
If you touch stitching, preserve all three:

1. **`_mux_clip_audio` must pad, not just trim.** `atrim` only truncates, so a 4.0s narration
   in a 5.06s clip left the muxed clip with less audio than picture. `acrossfade` then joins on
   audio time while `xfade` joins on video time, and the gap compounds — a 70.5s film ended up
   with a 55.1s audio stream. Pad with `apad=whole_dur=<clip>`.
2. **Never `amix=duration=shortest`.** It collapsed the whole mix to the narration even with a
   full-length ambience bed. Use `duration=longest` then trim to the clip.
3. **Subtitle times must use `scene_start_offsets()`**, which subtracts each boundary's
   crossfade. Timing cues against the raw sum of clip lengths drifts ~4.5s over 16 shots.
   Use `frames/fps`, not `CLIP_LENGTHS["seconds"]` — the latter is rounded (5.1 vs 5.0625).

`scripts/refresh_subtitles.py` re-stitches, re-grades, rebuilds the SRT and re-burns from
existing clips, so these can be fixed without re-rendering.

---

## Seeding policy (character consistency)

`get_scene_seed_image()`:

| Shot | Seed |
|---|---|
| **tight** close-up / ECU with characters | **character portrait** |
| medium / two-shot with characters | staged plate at matching framing |
| wide **with** characters | staged plate (`full_body`), else location plate |
| any shot **without** characters | plain setup plate, else chain |

**What is actually established, and what is not.**

ROBUST — a staged plate transforms a **wide** shot. A portrait cannot fill a
landscape, and an empty location plate has no face in it at all, so the model
invents one. The two wides in ep04 scored 0.632 and 0.669; with a staged plate
they scored **0.827 and 0.834** (+0.195, +0.165), and s02 reproduced to three
decimals on a re-render. Large, consistent, worth acting on.

NOT ESTABLISHED — everything else. A first reading of the ep04 v2 table (which
used plates on all 17 shots) showed "seven shots regressed", and a rule was
written here saying tight close-ups should keep the portrait. Reading it
properly: **seven shots improved and seven regressed**, splitting by neither
shot type nor render mode, all within ±0.05. One of the shots cited as evidence
for the rule (s04) had actually IMPROVED with a plate, and got worse when v3
gave it the portrait back.

A first correction called those thirteen "noise". That was also wrong. **Renders
are deterministic**: the seed number is fixed per shot, so the same prompt, seed
image and mode produce a bit-identical clip. Verified by accident -- v3's s04
scored exactly v1's 0.865 (both used the portrait) while its s03 scored exactly
v2's 0.782. There is no sampling variance to hide behind.

So every difference IS a real causal effect of the seed image. It simply varies
in SIGN from shot to shot -- s04 +0.043 and s06 +0.017 against s03 -0.038 and
s07 -0.020 -- and nothing about shot type or render mode predicts which. The
wides are the only case where the direction is reliable, and there the effect is
four times larger than anything else measured.

Practical consequence: for a shot that matters, render it both ways and score it.
That costs a few minutes and is the only thing that actually answers it.

The portrait scores 1.000 against the anchor because it IS the anchor; a plate
scores 0.908. That gap is real but it is smaller than per-render variance, so
it does not by itself decide anything outside the wide case.

**Conditioning and training are complementary, not rivals.** An early rank-32
LoRA moved these same shots +0.006, which looked like proof that training was
pointless. It was not. That LoRA was trained on a dataset broken in eight silent
ways. Rebuilt properly and trained at rank 64, the identical three shots moved:

| shot | baseline | rank-32 (broken data) | rank-64 (fixed data) |
|---|---|---|---|
| s09 wide      | 0.632 | +0.006 | **+0.108** |
| s02 wide      | 0.669 | +0.008 | **+0.154** |
| s07 S2V dialogue | 0.739 | — | **+0.087** |
| mean          | 0.680 | +0.006 | **+0.116** |

**Caveat on those numbers — the probe was confounded.** It rendered each shot
with the new LoRA AND the current seeding policy, then compared against a
baseline recorded before either existed. For the two wide shots that means the
staged plate's contribution was credited to the LoRA. The clean comparison is
v4 against v3, which differ only by the LoRA:

| shot | v3 (seeding only) | v4 (seeding + LoRA) | LoRA's own effect |
|---|---|---|---|
| s02 wide | 0.834 | 0.833 | **+0.000** — a plate already does the job |
| s07 S2V dialogue | 0.719 | *see below* | this is the honest test |

Where a staged plate works, the LoRA adds nothing. Its value is where plates
cannot reach. Always isolate ONE variable: comparing a two-change render against
a two-change-old baseline tells you the sum, not which half did the work.

The eight faults that made the first LoRA useless, none of which produced an
error:

1. training images 480x832 portrait, renders 832x480 landscape
2. captions claiming eight framings on what was one head-and-shoulders picture
3. a latent cache holding 41 photoreal entries while the directory held 28 cel ones
4. curation taking top-N by identity, which re-selects near-duplicates
5. `Oisin` as trigger, competing with the base model's own prior
6. rank 32
7. an install glob matching two eras of weights
8. character briefs still carrying the previous style string

Use both. A plate fixes a WIDE, where a portrait cannot fill the frame. A LoRA
fixes S2V DIALOGUE, where the model leans least on its seed image and no amount
of conditioning reaches — s07 is the proof, and plates could not move it.

A wide seeded from a head-and-shoulders portrait inherits portrait framing, so
that is never done. Leaving it unseeded (pure T2V) was the previous rule and it
cost the series its look: with nothing anchoring the rendering, a wide shot
free-associates from the prompt — "cel-shaded 2D animation" came back as generic
1980s anime, with plate armour and a red gown instead of the leather jerkin and
emerald dress in the bible, sitting next to seeded shots that looked like a
different show. The plate is already a wide composition *in the series' style*,
so it anchors framing, place, and look at once; characters are composed in from
the prompt.

A wide shot seeded from a head-and-shoulders portrait inherits portrait framing; a wide shot
seeded from the previous frame renders the previous scene again. Per-scene `"seed":
"t2v"|"portrait"|"location"|"chain"` overrides this.

Reference filenames come from `_ref_name()` on **both** sides — generation and lookup
previously disagreed (`niamh.png` vs `char_niamh.png`), so portraits were silently unused
for any semantically-keyed bible.

### The series is cel-shaded animation — deliberately

WAN's S2V checkpoint renders stylised faces; I2V could be pushed toward
photoreal. Running both in one episode gave dialogue close-ups in one medium
and everything else in another, and it read as a defect rather than a style.
It was not a quality problem — it was two renderers disagreeing.

The series now commits to cel-shaded 2D animation, which is what S2V produces
naturally, so both paths agree. Two consequences:

- The **negative prompt must not contain** `cartoon`, `anime`, `illustration`,
  `painterly`. Suppressing them spent guidance fighting the chosen look and
  lost that fight unevenly. It now suppresses genuine defects plus
  `photorealistic, live action, photograph` to push *toward* the style.
- **Reference images must be regenerated whenever the style changes.** The nine
  anchors seed every shot; photoreal portraits feeding a cel-shaded prompt
  recreate the same split, just inverted. `showrunner.py gen-refs <series>`.

`selftest.py` asserts the style and the negative prompt cannot contradict each
other again.

### Persistent sets — `scripts/build_sets.py`

Every shot is an independent diffusion sample, so a place is re-invented each
time: two characters on one headland came back on two separate sea stacks, and
close-ups came back in modern interiors because they seed from a bare portrait
that says nothing about where they are.

Shots seeded from the SAME plate already agree — ep04 s01 and s02 share a cliff,
a wind-bent tree and a horizon line. The set library extends that from one camera
position to several, and gives close-ups a seed carrying both face and room:

```
series/<slug>/sets/<location>/
    master.png                       the established view (copied from the plate)
    reverse.png  wider.png  ...      other angles OF THE SAME PLACE
    master__oisin_close.png          that angle with a character standing in it
```

Every setup is **derived from the master** by animating a camera move and keeping
the final frame, so the new angle inherits the master's geometry, palette and
light rather than inventing its own. Character plates are derived from a setup
the same way.

```bash
python scripts/build_sets.py setups <series> --all       # angles per location
python scripts/build_sets.py stage  <series> <loc> <char>  # character on set
python scripts/build_sets.py list   <series>
```

Scenes select a setup with `"setup": "reverse"` and a placement with
`"staging": "left"|"right"|"close"`. `get_scene_seed_image()` prefers a staged
plate for any close-up/dialogue shot with characters, then a plain setup plate.

**The library is additive.** A series that has not built one behaves exactly as
before — `selftest.py` asserts that, so adding sets cannot silently rewrite an
existing show.

Regenerate the library when the series style changes; the plates are seeds, and a
stale-style plate propagates into every shot that uses it.

**Series `style` must describe rendering only** (camera, lighting, film stock). It is appended
to every scene prompt and every reference plate, so subject matter in it ("emerald cliffs, gold
horizon light") overrides every location and makes them all look the same.

---

## Hardware Constraints (RTX 3090, 24GB VRAM)

Do not change these without testing:

| Parameter | T2V Value | I2V Value | Reason |
|-----------|-----------|-----------|--------|
| Resolution | 832×480 or 480×832 | same | WAN 2.2 480p default |
| `cfg` | **5.0** | **3.5** | I2V uses lower guidance (official WAN 2.2) |
| `shift` | **12.0** | **8.0** | I2V uses different noise schedule (official WAN 2.2) |
| `sampler` | uni_pc_bh2 | **euler** | I2V uses euler (official WAN 2.2) |
| Sampler node | KSampler | **KSamplerAdvanced** x2 | I2V needs dual-model step handoff |
| Frame count | 33 / 49 / 81 | same | short/medium/long; must be `4n+1` |
| Clip duration | 2.1s / 3.1s / 5.1s | same | At 16fps |

**T2V Model**: `wan2.2_t2v_high_noise_14B_Q8_0.gguf` (single model)
**I2V Models**: `wan2.2_i2v_high_noise_14B_Q4_K_S.gguf` + `wan2.2_i2v_low_noise_14B_Q4_K_S.gguf` (dual model)

---

## Environment

- **Python env**: `# conda activate video-comfy  (if using conda)` (Python 3.10.9, PyTorch 2.5.1+cu121)
- **`ANTHROPIC_API_KEY`**: required for script generation
- **`SECRET_KEY`**: required for JWT auth — set in `app/backend/.env`
- **ComfyUI**: must be running on `localhost:8188` for any video/portrait generation
- **Database**: SQLite at `app/backend/storybuilder.db` (auto-created on first `uvicorn` run)
- **Claude model**: `claude-opus-5` — `CLAUDE_MODEL` in `showrunner.py`, override with `SHOWRUNNER_CLAUDE_MODEL`. Adaptive thinking + structured outputs; effort via `SHOWRUNNER_CLAUDE_EFFORT`.
- **Static file mounts**: `/static/clips/` → `ComfyUI/output/video/`, `/static/series/` → `series/`, `/static/output/` → `output/`
  (clip paths under this mount are now `<series-slug>/<file>.mp4` — see Clip Storage Layout)
