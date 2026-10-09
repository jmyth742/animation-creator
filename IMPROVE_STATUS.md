# Improvement status

Updated 2026-10-09 01:43. Cycle 527.

## GPU duty cycle (last 24 h, 1-min samples)

- card working (>=20%) **28%** of the last 24 h (410 busy minutes; 3 minutes unsampled, counted idle); mean utilisation of sampled minutes 27%

## Adopted (what the masters are rendered with)

- walk: RW_STRIDE=0.6, RW_DROP=0.062, RW_ARM_OUT=10 (defaults v1)
- scene: SET_PLATE=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_geo.png, SET_RELIEF_NPY=/workspace/loopwork/improve/plate_geo_depth.npy, SET_RELIEF_GAIN=0.8, SET_PLATE_WINTER=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_winter_geo.png, SET_RELIEF_NPY_WINTER=/workspace/loopwork/improve/plate_winter_geo_depth.npy (plate v18)
- cast oisin: oisin4 (hand compactness 0.73, lower is better)
- cast niamh: niamh4 (hand compactness 0.74, lower is better)
- masters: nine_waterfalls_loop_97c79e_web.mp4, nine_waterfalls_loop_419a38_web.mp4, nine_waterfalls_loop_c7a15f_web.mp4
- masters built at inputs: d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705|SET_PLATE_WINTER=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_winter_geo.png|SET_RELIEF_NPY_WINTER=/workspace/loopwork/improve/plate_winter_geo_depth.npy|SET_RELIEF_GAIN=0.8; current inputs: d1|oisin4|niamh4|p17|s84a4b1

## Settled (not re-run until an input changes)

- cast_face_st_chibi3_niamh_m20705: queued @ st_chibi3_niamh_m20705
- cast_face_st_chibi3_oisin_m22223: queued @ st_chibi3_oisin_m22223
- cast_face_st_chibi3_oisin_m23845: queued @ st_chibi3_oisin_m23845
- craft_CHAR_AO: queued @ d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174
- craft_FILM_FILL: queued as 85_fill_ab @ d1|oisin4|niamh4|p16|s84a4b1
- craft_FILM_INTEGRATE: queued @ d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174
- craft_FILM_LINES: queued @ d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174
- craft_FILM_LINE_ALPHA: queued @ d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174
- face_FCG_MOUTH: queued @ d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174
- face_FP_MOUTH_PLATE: queued @ d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174
- plate_flux_cliff_r0: queued @ g2
- plate_flux_cliff_r1: queued @ g2
- plate_flux_cliff_r2: queued @ g2
- plate_flux_r0: queued @ g1
- plate_flux_r1: queued @ g1
- plate_flux_r2: queued @ g1
- plate_flux_winter_r0: queued @ g2
- plate_flux_winter_r1: queued @ g2
- plate_flux_winter_r2: queued @ g2
- plate_hires_valley_closer: queued @ a924056a
- plate_hires_valley_master: queued @ bb967a36
- plate_hires_valley_reverse: queued @ b8271cbe
- plate_hires_valley_side: queued @ f9fa0499
- plate_hires_winter_master: queued @ dd3a9630
- plate_shots_m16_r0: queued @ g2
- plate_shots_m17_r1: queued @ g2
- scene_fit: queued @ st_chibi3_oisin_m23845|st_chibi3_niamh_m20705|p16
- walk_RW_ARM_OUT: queued @ d1|st_chibi3_oisin_m22223|st_chibi3_niamh_m20705_tex|p2|s39c2a7
- walk_RW_DROP: queued @ d1|st_chibi3_oisin_m22223|st_chibi3_niamh_m20705_tex|p2|s39c2a7
- walk_RW_STRIDE: queued @ d1|st_chibi3_oisin_m22223|st_chibi3_niamh_m20705_tex|p2|s39c2a7
- walk knob RW_STRIDE: settled (lo 0.4, hi 0.76, step 0.005)
- walk knob RW_DROP: settled (lo 0.03, hi 0.1, step 0.00125)
- walk knob RW_ARM_OUT: settled (lo 2, hi 22, step 4)

## Awaiting a human pick

- AB_craft_CHAR_AO.png
- AB_craft_FILM_FILL.png
- AB_craft_FILM_INTEGRATE.png
- AB_craft_FILM_LINES.png
- AB_craft_FILM_LINE_ALPHA.png
- AB_face_FCG_MOUTH.png
- AB_face_FP_MOUTH_PLATE.png

## Last 12 experiments

- 2026-10-08 22:02 plate_hires valley_side: 3 candidates, none kept the picture (style>=0.95, ground within 0.03)
- 2026-10-08 22:11 plate_hires valley_reverse: best sharpness x1.13 (need >1.15), style 0.971 -> not adopted
- 2026-10-08 22:20 plate_hires valley_closer: hr_valley_closer_cn0.5_d25.png sharpness x1.21 vs the upscale, style 0.976, ground -0.004 -> ADOPTED as closer_geo_4x.png (plate v16)
- 2026-10-08 22:28 plate_hires winter_master: best sharpness x1.14 (need >1.15), style 0.961 -> not adopted
- 2026-10-08 22:48 scene_fit @521: gains 0.4,0.6,0.8 -> best gain 0.8 (on path 84%, foot float p95 0 mm) (unchanged)
- 2026-10-09 00:48 episode 1 @ c7a15f (d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705|SET_PLATE=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_geo.png|SET_RELIEF_NPY=/workspace/loopwork/improve/plate_geo_depth.npy|SET_RELIEF_GAIN=0.8): rendered nine_waterfalls_loop_c7a15f_web.mp4; 
- 2026-10-09 01:06 plate_shots round 0: side r=0.40 style=0.92 ADOPTED (4/4 passed); reverse r=0.35 style=0.93 ADOPTED (4/4 passed); closer r=0.48 style=0.88 ADOPTED (4/4 passed) -> plate v17
- 2026-10-09 01:10 craft: FILM_FILL A/B over 0,0.6,1.2 -> AB_craft_FILM_FILL.png (human pick)
- 2026-10-09 01:13 craft: FILM_FILL=0.6 ADOPTED into the loop's master recipe (AB_craft_FILM_FILL: lifts the near head's hair detail in the over-the-shoulder, neutral on close and wide; 1.2 flattens the face)
- 2026-10-09 01:24 plate_shots round 1: side: none of 4 beat the standing plate (0 failed style); reverse: none of 4 beat the standing plate (0 failed style); closer: none of 4 beat the standing plate (0 failed style)
- 2026-10-09 01:34 plate_hires valley_side: best sharpness x1.07 (need >1.15), style 0.969 -> not adopted
- 2026-10-09 01:43 plate_hires valley_reverse: hr_valley_reverse_cn0.5_d45.png sharpness x1.25 vs the upscale, style 0.977, ground -0.004 -> ADOPTED as reverse_geo_4x.png (plate v18)
