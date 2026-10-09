# Improvement status

Updated 2026-10-09 09:28. Cycle 539.

## GPU duty cycle (last 24 h, 1-min samples)

- card working (>=20%) **24%** of the last 24 h (346 busy minutes; 2 minutes unsampled, counted idle); mean utilisation of sampled minutes 22%

## Adopted (what the masters are rendered with)

- walk: RW_STRIDE=0.6, RW_DROP=0.062, RW_ARM_OUT=10 (defaults v1)
- scene: SET_PLATE=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_geo.png, SET_RELIEF_NPY=/workspace/loopwork/improve/plate_geo_depth.npy, SET_RELIEF_GAIN=0.8, SET_PLATE_WINTER=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_winter_geo.png, SET_RELIEF_NPY_WINTER=/workspace/loopwork/improve/plate_winter_geo_depth.npy (plate v23)
- cast oisin: oisin4 (hand compactness 0.73, lower is better)
- cast niamh: niamh4 (hand compactness 0.74, lower is better)
- masters: nine_waterfalls_loop_419a38_web.mp4, nine_waterfalls_loop_c7a15f_web.mp4, nine_waterfalls_loop_e794bc_web.mp4
- masters built at inputs: d1|oisin4|niamh4|SET_PLATE_CLIFF=-|SET_RELIEF_GAIN=0.8; current inputs: d1|oisin4|niamh4|p22|s84a4b1

## Settled (not re-run until an input changes)

- cast_face_st_chibi3_niamh_m20705: queued @ st_chibi3_niamh_m20705
- cast_face_st_chibi3_oisin_m22223: queued @ st_chibi3_oisin_m22223
- cast_face_st_chibi3_oisin_m23845: queued @ st_chibi3_oisin_m23845
- craft_CHAR_AO: queued @ d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174
- craft_FILM_FILL: queued @ d1|oisin4|niamh4|p18|s84a4b1
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
- plate_hires_valley_closer: queued @ 7fae92d2
- plate_hires_valley_master: queued @ bb967a36
- plate_hires_valley_reverse: queued @ 48b180cc
- plate_hires_valley_side: queued @ 85f7c6df
- plate_hires_winter_master: queued @ dd3a9630
- plate_shots_m16_r0: queued @ g2
- plate_shots_m17_r1: queued @ g2
- plate_shots_valley_bb967a36_r0: queued @ g2
- plate_shots_valley_bb967a36_r1: queued @ g2
- plate_shots_winter_dd3a9630_r0: queued @ g2
- plate_shots_winter_dd3a9630_r1: queued @ g2
- scene_fit_ep1: settled (gain 0.8) @ oisin4|niamh4|/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_geo.png
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

- 2026-10-09 01:51 plate_hires valley_closer: best sharpness x1.05 (need >1.15), style 0.979 -> not adopted
- 2026-10-09 02:12 scene_fit @529: gains 0.4,0.6,0.8 -> best gain 0.8 (on path 84%, foot float p95 0 mm) (unchanged)
- 2026-10-09 04:10 episode 1 @ e794bc (d1|oisin4|niamh4|SET_PLATE=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_geo.png|SET_RELIEF_NPY=/workspace/loopwork/improve/plate_geo_depth.npy|SET_RELIEF_GAIN=0.8): rendered nine_waterfalls_loop_e794bc_web.mp4; 
- 2026-10-09 06:05 episode 2 @ 4c130d (d1|oisin4|niamh4|SET_PLATE_WINTER=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_winter_geo.png|SET_RELIEF_NPY_WINTER=/workspace/loopwork/improve/plate_winter_geo_depth.npy|SET_RELIEF_GAIN=0.8): rendered first_snow_loop_4c130d_web.mp4; 
- 2026-10-09 08:01 episode 3 @ 420767 (d1|oisin4|niamh4|SET_PLATE_CLIFF=-|SET_RELIEF_GAIN=0.8): rendered farewell_cliff_loop_420767_web.mp4; 
- 2026-10-09 08:07 craft: FILM_FILL A/B over 0,0.6,1.2 -> AB_craft_FILM_FILL.png (human pick)
- 2026-10-09 08:21 plate_shots_geo round 0: side r=0.40 style=0.89 ADOPTED (4/4 passed); reverse: none of 4 beat the standing plate (0 failed style); closer r=0.46 style=0.88 ADOPTED (4/4 passed) -> plate v19
- 2026-10-09 08:37 plate_shots_geo round 1: side r=0.42 style=0.92 ADOPTED (4/4 passed); reverse r=0.38 style=0.92 ADOPTED (4/4 passed); closer r=0.52 style=0.87 ADOPTED (4/4 passed) -> plate v20
- 2026-10-09 08:52 plate_shots_winter_geo round 0: side r=0.53 style=0.88 ADOPTED (4/4 passed); reverse r=0.36 style=0.89 ADOPTED (4/4 passed); closer r=0.50 style=0.87 ADOPTED (4/4 passed) -> plate v21
- 2026-10-09 09:08 plate_shots_winter_geo round 1: side: none of 4 beat the standing plate (1 failed style); reverse r=0.41 style=0.88 ADOPTED (4/4 passed); closer r=0.51 style=0.89 ADOPTED (3/4 passed) -> plate v22
- 2026-10-09 09:18 plate_hires valley_side: best sharpness x1.03 (need >1.15), style 0.965 -> not adopted
- 2026-10-09 09:28 plate_hires valley_reverse: hr_valley_reverse_cn0.5_d45.png sharpness x1.28 vs the upscale, style 0.958, ground -0.011 -> ADOPTED as reverse_geo_4x.png (plate v23)
