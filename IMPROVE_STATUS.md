# Improvement status

Updated 2026-10-09 00:48. Cycle 522.

## GPU duty cycle (last 24 h, 1-min samples)

- card working (>=20%) **28%** of the last 24 h (405 busy minutes; 2 minutes unsampled, counted idle); mean utilisation of sampled minutes 27%

## Adopted (what the masters are rendered with)

- walk: RW_STRIDE=0.6, RW_DROP=0.062, RW_ARM_OUT=10 (defaults v1)
- scene: SET_PLATE=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_geo.png, SET_RELIEF_NPY=/workspace/loopwork/improve/plate_geo_depth.npy, SET_RELIEF_GAIN=0.8, SET_PLATE_WINTER=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_winter_geo.png, SET_RELIEF_NPY_WINTER=/workspace/loopwork/improve/plate_winter_geo_depth.npy (plate v16)
- cast oisin: st_chibi3_oisin_m23845 (hand compactness 0.31, lower is better)
- cast niamh: st_chibi3_niamh_m20705_tex (hand compactness 0.20, lower is better)
- masters: nine_waterfalls_loop_97c79e_web.mp4, nine_waterfalls_loop_419a38_web.mp4, nine_waterfalls_loop_c7a15f_web.mp4
- masters built at inputs: d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705|SET_PLATE=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_geo.png|SET_RELIEF_NPY=/workspace/loopwork/improve/plate_geo_depth.npy|SET_RELIEF_GAIN=0.8; current inputs: d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705|p16|s84a4b1

## Settled (not re-run until an input changes)

- cast_face_st_chibi3_niamh_m20705: queued @ st_chibi3_niamh_m20705
- cast_face_st_chibi3_oisin_m22223: queued @ st_chibi3_oisin_m22223
- cast_face_st_chibi3_oisin_m23845: queued @ st_chibi3_oisin_m23845
- craft_CHAR_AO: queued @ d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174
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
- plate_hires_valley_reverse: queued @ c9fb8ccd
- plate_hires_valley_side: queued @ b3683ea8
- plate_hires_winter_master: queued @ dd3a9630
- plate_shots_m13_r1: queued @ g2
- plate_shots_m9_r0: queued @ g2
- scene_fit: queued @ st_chibi3_oisin_m23845|st_chibi3_niamh_m20705|p16
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

- 2026-10-08 20:53 plate_shots round 0: side r=0.56 style=0.87 ADOPTED (4/4 passed); reverse r=0.41 style=0.91 ADOPTED (4/4 passed); closer r=0.59 style=0.93 ADOPTED (4/4 passed) -> plate v11
- 2026-10-08 21:05 plate_geo winter round 10: 9 plates, best r10_winter_cn0.7_flux_d60.png agreement r=0.397 style 0.932 vs old plate r=0.298 -> ADOPTED as master_winter_geo.png (plate v12)
- 2026-10-08 21:18 plate_geo winter round 11: 9 plates, best r11_winter_cn0.9_flux_d60.png agreement r=0.459 style 0.936 vs old plate r=0.298 -> ADOPTED as master_winter_geo.png (plate v13)
- 2026-10-08 21:30 plate_geo winter round 12: 9 plates (5 failed the style gate >=0.85), best agreement r=0.511 vs old plate r=0.298, adopted r=0.511 stands
- 2026-10-08 21:45 plate_shots round 1: side r=0.55 style=0.90 ADOPTED (4/4 passed); reverse r=0.46 style=0.91 ADOPTED (4/4 passed); closer r=0.61 style=0.89 ADOPTED (4/4 passed) -> plate v14
- 2026-10-08 21:54 plate_hires valley_master: hr_valley_master_cn0.5_d25.png sharpness x1.19 vs the upscale, style 0.983, ground +0.002 -> ADOPTED as master_geo_4x.png (plate v15)
- 2026-10-08 22:02 plate_hires valley_side: 3 candidates, none kept the picture (style>=0.95, ground within 0.03)
- 2026-10-08 22:11 plate_hires valley_reverse: best sharpness x1.13 (need >1.15), style 0.971 -> not adopted
- 2026-10-08 22:20 plate_hires valley_closer: hr_valley_closer_cn0.5_d25.png sharpness x1.21 vs the upscale, style 0.976, ground -0.004 -> ADOPTED as closer_geo_4x.png (plate v16)
- 2026-10-08 22:28 plate_hires winter_master: best sharpness x1.14 (need >1.15), style 0.961 -> not adopted
- 2026-10-08 22:48 scene_fit @521: gains 0.4,0.6,0.8 -> best gain 0.8 (on path 84%, foot float p95 0 mm) (unchanged)
- 2026-10-09 00:48 episode 1 @ c7a15f (d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705|SET_PLATE=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_geo.png|SET_RELIEF_NPY=/workspace/loopwork/improve/plate_geo_depth.npy|SET_RELIEF_GAIN=0.8): rendered nine_waterfalls_loop_c7a15f_web.mp4;
