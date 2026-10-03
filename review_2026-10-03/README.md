# Review drop — 3 Oct 2026

Everything the GPU improvement loop (v2) produced since 30 Sep, plus the two dense-cast masters
that finished. Read `IMPROVE_STATUS.md` first, then `IMPROVE_LEDGER.md` for the per-experiment log.

## Headline — and one honest warning

The loop now **adopts on measurement**: foot slide, knee range, foot float, time-on-path, and
plate/geometry agreement. Overnight it settled all three walk knobs, adopted a relief gain, built a
face rig for a newly adopted Oisín, and re-rendered episode 1.

**The geometry plate it adopted is a style regression.** `PLATE_FROM_GEOMETRY.png`: the new plate
agrees with the set geometry far better (r=0.84 vs 0.56 — characters stand where the picture says
they stand) but it looks like a different, cruder show: flat SDXL colouring, hall reduced to a block,
waterfall gone. The adoption metric was geometry-only; it had no notion of look. The episode in this
folder (`nine_waterfalls_loop_97c79e_web.mp4`) was rendered with that plate so you can see both the
gain (contact, path) and the loss (look). I have reverted the masters to the original plate and the
loop will not adopt a plate again unless it also passes a style-similarity gate to the original.

## Files

| file | what |
|---|---|
| `IMPROVE_STATUS.md` | adopted settings, settled knobs, duty cycle, last experiments |
| `IMPROVE_LEDGER.md` | one line per experiment the card ran (ADOPTED lines are the progress) |
| `SET_GEOMETRY_vs_PLATE.png` | the real 3D set (primitives), its depth, the original plate — the mismatch the scene fitting was fighting |
| `PLATE_FROM_GEOMETRY.png` | set depth / original plate / geometry-conditioned plate with agreement scores |
| `plate_master_old.png`, `plate_master_geo.png` | the two plates at full size |
| `SCENE_FIT_relief_probes.png` | 30 Sep: original plate + calibrated relief, feet at 0 mm float (s02 walk, s03 meet, s11 away) |
| `SCENE_FIT_97c79e.png`, `SCENE_FIT_1708dd.png` | the same three probes on the geometry plate at the adopted gains |
| `EP1_loop_97c79e_frame_{a,b,c}.png`, `nine_waterfalls_loop_97c79e_web.mp4` | episode 1 rendered by the loop with the geometry plate (see warning) |
| `first_snow_rigify_cast4d_web.mp4`, `farewell_cliff_rigify_cast4d_web.mp4.part*` | episodes 2 and 3, 30k-face cast, masters recipe (`cat name.part* > name.mp4`) |
| `RIGIFY_gate_st_chibi3_oisin_m23845_45.png`, `MOTION_st_chibi3_oisin_m23845_rigify.mp4`, `TALK_oisin_m23845_probe.png` | the newly adopted Oisín candidate (hand compactness 0.31): rig gate, walk/idle reel, talk probe |
| `AB_craft_*.png`, `AB_face_*.png` | A/B sheets awaiting your pick: line width, AO, integration, line alpha; mouth plate, mouth height |
