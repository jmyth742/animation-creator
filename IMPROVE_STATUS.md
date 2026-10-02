# Improvement status

Updated 2026-10-02 20:36. Cycle 362.

## GPU duty cycle (last 24 h, 1-min samples)

- mean utilisation **10%**, samples with the card working (>=20%): **10%** of 73

## Adopted (what the masters are rendered with)

- walk: RW_STRIDE=0.6, RW_DROP=0.062, RW_ARM_OUT=10 (defaults v1)
- scene: SET_PLATE=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_geo.png, SET_RELIEF_NPY=/workspace/loopwork/improve/plate_geo_depth.npy, SET_RELIEF_GAIN=0.6 (plate v2)
- cast oisin: st_chibi3_oisin_m22223 (hand compactness 0.35, lower is better)
- cast niamh: st_chibi3_niamh_m20705_tex (hand compactness 0.20, lower is better)
- masters: nine_waterfalls_rigify_oisin4_web.mp4, nine_waterfalls_rigify_cast4d_web.mp4, nine_waterfalls_rigify_cast4_web.mp4
- masters built at inputs: 1; current inputs: d1|st_chibi3_oisin_m22223|st_chibi3_niamh_m20705_tex|p2|s39c2a7

## Settled (not re-run until an input changes)

- cast_face_st_chibi3_oisin_m22223: queued @ st_chibi3_oisin_m22223
- plate_geo_r0: queued @ g1
- plate_geo_r1: queued @ g1
- plate_geo_r2: queued @ g1
- scene_fit: queued @ d1|st_chibi3_oisin_m22223|st_chibi3_niamh_m20705_tex|p2|s39c2a7
- walk_RW_ARM_OUT: queued @ d1|st_chibi3_oisin_m22223|st_chibi3_niamh_m20705_tex|p2|s39c2a7
- walk_RW_DROP: queued @ d1|st_chibi3_oisin_m22223|st_chibi3_niamh_m20705_tex|p2|s39c2a7
- walk_RW_STRIDE: queued @ d1|st_chibi3_oisin_m22223|st_chibi3_niamh_m20705_tex|p2|s39c2a7
- walk knob RW_STRIDE: settled (lo 0.4, hi 0.76, step 0.005)
- walk knob RW_DROP: settled (lo 0.03, hi 0.1, step 0.00125)
- walk knob RW_ARM_OUT: settled (lo 2, hi 22, step 4)

## Awaiting a human pick

- AB_craft_CHAR_AO.png
- AB_craft_FILM_INTEGRATE.png
- AB_craft_FILM_LINES.png
- AB_craft_FILM_LINE_ALPHA.png
- AB_face_FCG_MOUTH.png
- AB_face_FP_MOUTH_PLATE.png

## Last 12 experiments

- 2026-10-02 19:45 cast_face: st_chibi3_oisin_m22223 face rig built, talk probe 40 frames
- 2026-10-02 19:51 plate_geo round 0: 9 plates, best r0_cn1.0_s90.png agreement r=0.809 vs old plate r=0.561 -> ADOPTED as master_geo.png (plate v1)
- 2026-10-02 19:55 plate_geo round 1: 9 plates, best r1_cn1.0_s90.png agreement r=0.837 vs old plate r=0.561 -> ADOPTED as master_geo.png (plate v2)
- 2026-10-02 19:59 plate_geo round 2: 9 plates, best agreement r=0.837 vs old plate r=0.561, adopted r=0.837 stands
- 2026-10-02 20:24 scene_fit @355: gains 0.4,0.6,0.8 -> best gain 0.6 (on path 79%, foot float p95 18 mm) (unchanged)
- 2026-10-02 20:26 walk: RW_STRIDE sweep 0.52,0.56,0.6,0.64,0.68 -> best 0.6 (score 1.3), current 0.6 (1.3) (step -> 0.02)
- 2026-10-02 20:28 walk: RW_STRIDE sweep 0.56,0.58,0.6,0.62,0.64 -> best 0.62 (score 0.4), current 0.6 (1.3) (step -> 0.01)
- 2026-10-02 20:29 walk: RW_STRIDE sweep 0.58,0.59,0.6,0.61,0.62 -> best 0.61 (score 0.4), current 0.6 (1.3) (step below minimum: settled at 0.6)
- 2026-10-02 20:31 walk: RW_DROP sweep 0.042,0.052,0.062,0.072,0.082 -> best 0.062 (score 1.3), current 0.062 (1.3) (step -> 0.005)
- 2026-10-02 20:33 walk: RW_DROP sweep 0.052,0.057,0.062,0.067,0.072 -> best 0.057 (score 0.8), current 0.062 (1.3) (step -> 0.0025)
- 2026-10-02 20:34 walk: RW_DROP sweep 0.057,0.0595,0.062,0.0645,0.067 -> best 0.057 (score 0.8), current 0.062 (1.3) (step below minimum: settled at 0.062)
- 2026-10-02 20:36 walk: RW_ARM_OUT sweep 2,6,10,14,18 -> best 10 (score 1.3), current 10 (1.3) (no signal across the sweep: settled)
