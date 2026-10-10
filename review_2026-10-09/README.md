# Review drop — 9 Oct 2026 (part 1: episode 1)

**`nine_waterfalls_loop_e794bc_web.mp4`** — episode 1 on the geometry-first plates with the calibrated cast
(oisin4 / niamh4), fill light 0.6, relief gain 0.8. `EP1_e794bc_frames.png` has four frames.

What changed since the 3 Oct drop, all adopted on measurement (see `IMPROVE_LEDGER.md`, `IMPROVE_STATUS.md`):
- **Plates are painted onto the set's geometry** with FLUX + depth control, gated on style (`PLATE_FROM_GEOMETRY.png`,
  `plate_valley_master_geo.png`): ground agreement 0.60 vs 0.30 for the original; characters stand on the painted path
  84% of walking time, 0 mm foot float (`SCENE_FIT_plate_v7.png`).
- **Per-shot setups** (`plate_valley_{side,reverse,closer}_geo.png`) painted from their own geometry guides so every
  angle is the same place; the renderer swaps them in by heading. `SETUPS_candidates.png` shows every candidate the loop
  made with its scores — two of the chosen ones carry a FLUX artefact (a blue glowing orb); pick a different one there
  if you prefer and I'll set it.
- **Winter plate** (`plate_winter_master_geo.png`) for episode 2, painted as winter; episode 2 and 3 masters follow in
  part 2 of this folder.
- **Cast policy**: the loop had auto-adopted a new Oisín/Niamh on a hand score; their auto-built faces were worse in
  close-ups, so candidates are now built for review only and the masters use the calibrated cast.
- **Fill light** (`AB_craft_FILM_FILL.png`): 0.6 adopted — the near head in over-the-shoulder shots keeps its detail.
  `OTS_PROBE.png` shows the black-head mass seen in earlier masters is specific to two mesh variants, not the camera.

## Part 2 (09:00)

**`first_snow_loop_4c130d_web.mp4`** — episode 2 on the winter geometry plate (`EP2_4c130d_frames.png`): snowed cliffs,
frozen shore, the golden hall, the calibrated cast. Known fault: the wide shots show a streaked band at the bottom edge —
the relief gain tuned for the summer plate applied to the winter depth; the loop now tunes a separate winter gain and will
re-render.

Episode 3 rendered in this pass is **not included**: a bug in the job environment projected the valley plate onto the
cliff set (the whole episode played in the valley). Fixed; the re-render is queued behind the winter scene-fit.

## Part 3 (14:00)

**`farewell_cliff_loop_420767_web.mp4.part*`** (`cat … > name.mp4`) — episode 3 re-rendered correctly on the cliff
(`EP3_420767_frames.png`): the headland, the sea stack, the cast on the shelf, calibrated faces, fill light.

Decision taken on review of the per-shot setup plates: at style scores the gate accepted, the side/closer paintings kept
drifting the hall (a green block, a gothic gold version, a white disc on the winter side). The master plate projected from
every shot camera is consistent, so the setups are **withdrawn** from the masters; the loop still paints candidates for a
human pick (`setups_review/`). Episodes 1 and 2 re-render on master-only plates next.

## Part 4 (10 Oct, 17:00) — the follow-projection masters

The streaked bands and smeared hall in the moving shots turned out to be a projection flaw: the plate was projected once
from mid-shot, and every orbit/dolly/pan drifted away from it. The projector now **follows the camera frame by frame** on
moving shots (the painting pans like a 2D anime background under the 3D cast). Episodes 1 and 2 re-rendered with it, on
the master plates only (per-shot setups withdrawn):

- **`nine_waterfalls_loop_e794bc_web.mp4`** (replaces the part-1 file of the same name) — `EP1_e794bc_follow_frames.png`
- **`first_snow_loop_f03553_web.mp4`** (replaces `4c130d`) — `EP2_f03553_follow_frames.png`: no bottom band any more.

Episode 3 with the same fix follows. Known remaining blemish: the hall billboard smears its texels when seen at a grazing
angle (behind Niamh in the over-the-shoulder of episode 1) — needs a real hall mass rather than a billboard; next on the list.
