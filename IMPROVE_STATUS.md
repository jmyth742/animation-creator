# Improvement status

Updated 2026-10-10 23:53. Cycle 552.

## GPU duty cycle (last 24 h, 1-min samples)

- card working (>=20%) **5%** of the last 24 h (76 busy minutes; 744 minutes unsampled, counted idle); mean utilisation of sampled minutes 7%

## Adopted (what the masters are rendered with)

- walk: RW_STRIDE=0.6, RW_DROP=0.062, RW_ARM_OUT=10 (defaults v1)
- scene: SET_PLATE=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_geo.png, SET_RELIEF_NPY=/workspace/loopwork/improve/plate_geo_depth.npy, SET_RELIEF_GAIN=0.8, SET_PLATE_WINTER=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_winter_geo.png, SET_RELIEF_NPY_WINTER=/workspace/loopwork/improve/plate_winter_geo_depth.npy, SET_RELIEF_GAIN_WINTER=0.4 (plate v24)
- cast oisin: oisin4 (hand compactness 0.73, lower is better)
- cast niamh: niamh4 (hand compactness 0.74, lower is better)
- masters: nine_waterfalls_loop_c7a15f_web.mp4, nine_waterfalls_loop_e794bc_web.mp4, nine_waterfalls_loop_6efe7b_web.mp4
- masters built at inputs: d1|oisin4|niamh4|sl2|SET_PLATE_WINTER=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_winter_geo.png|SET_RELIEF_NPY_WINTER=/workspace/loopwork/improve/plate_winter_geo_depth.npy|SET_RELIEF_GAIN_WINTER=0.4; current inputs: d1|oisin4|niamh4|p24|sc02f8d

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
- plate_hires_valley_closer: queued @ 99eceaa7
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
- scene_fit_ep2: queued @ oisin4|niamh4|/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_winter_geo.png
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

- 2026-10-09 09:18 plate_hires valley_side: best sharpness x1.03 (need >1.15), style 0.965 -> not adopted
- 2026-10-09 09:28 plate_hires valley_reverse: hr_valley_reverse_cn0.5_d45.png sharpness x1.28 vs the upscale, style 0.958, ground -0.011 -> ADOPTED as reverse_geo_4x.png (plate v23)
- 2026-10-09 09:36 plate_hires valley_closer: best sharpness x1.14 (need >1.15), style 0.954 -> not adopted
- 2026-10-09 09:58 scene_fit ep2 @541: gains 0.4,0.6,0.8 -> best SET_RELIEF_GAIN_WINTER=0.4 (on path 80%, foot float p95 0 mm) ADOPTED
- 2026-10-09 11:51 episode 2 @ f03553 (d1|oisin4|niamh4|SET_PLATE_WINTER=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_winter_geo.png|SET_RELIEF_NPY_WINTER=/workspace/loopwork/improve/plate_winter_geo_depth.npy|SET_RELIEF_GAIN_WINTER=0.4): rendered first_snow_loop_f03553_web.mp4; 
- 2026-10-09 13:44 episode 3 @ 420767 (d1|oisin4|niamh4|SET_PLATE_CLIFF=-|SET_RELIEF_GAIN=0.8): rendered farewell_cliff_loop_420767_web.mp4; 
- 2026-10-09 13:48 plates: per-shot setups withdrawn from the masters (side/closer drifted the hall at accepted style scores); the master plate is projected from every shot camera; setups are candidates for a human pick only
- 2026-10-10 14:21 episode 1 @ e794bc (d1|oisin4|niamh4|SET_PLATE=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_geo.png|SET_RELIEF_NPY=/workspace/loopwork/improve/plate_geo_depth.npy|SET_RELIEF_GAIN=0.8): rendered nine_waterfalls_loop_e794bc_web.mp4; 
- 2026-10-10 16:29 episode 2 @ f03553 (d1|oisin4|niamh4|SET_PLATE_WINTER=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_winter_geo.png|SET_RELIEF_NPY_WINTER=/workspace/loopwork/improve/plate_winter_geo_depth.npy|SET_RELIEF_GAIN_WINTER=0.4): rendered first_snow_loop_f03553_web.mp4; SF_DONE /workspace/loopwork/improve/ep2_audit_f03553.txt ['/workspace/loopwork/improve/ep2_audit_f03553_worst_oisin_rigify_1196.png', '/workspace/loopwork/improve/ep2_audit_f03553_worst_oisin_rigify_1254.png', '/workspace/loopwork/improve/ep2_audit_f03553_worst_oisin_rigify_1118.png', '/workspace/loopwork/improve/ep2_audit_f03553_worst_niamh_rigify_1190.png'];
- 2026-10-10 19:16 episode 3 @ 420767 (d1|oisin4|niamh4|SET_PLATE_CLIFF=-|SET_RELIEF_GAIN=0.8): rendered farewell_cliff_loop_420767_web.mp4; SF_DONE /workspace/loopwork/improve/ep3_audit_420767.txt ['/workspace/loopwork/improve/ep3_audit_420767_worst_oisin_rigify_201.png', '/workspace/loopwork/improve/ep3_audit_420767_worst_oisin_rigify_1.png', '/workspace/loopwork/improve/ep3_audit_420767_worst_oisin_rigify_658.png', '/workspace/loopwork/improve/ep3_audit_420767_worst_niamh_rigify_1079.png'];
- 2026-10-10 21:36 episode 1 @ 6efe7b (d1|oisin4|niamh4|sl2|SET_PLATE=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_geo.png|SET_RELIEF_NPY=/workspace/loopwork/improve/plate_geo_depth.npy|SET_RELIEF_GAIN=0.8): rendered nine_waterfalls_loop_6efe7b_web.mp4; SF_DONE /workspace/loopwork/improve/ep1_audit_6efe7b.txt ['/workspace/loopwork/improve/ep1_audit_6efe7b_worst_oisin_rigify_1090.png', '/workspace/loopwork/improve/ep1_audit_6efe7b_worst_oisin_rigify_1282.png', '/workspace/loopwork/improve/ep1_audit_6efe7b_worst_oisin_rigify_1266.png', '/workspace/loopwork/improve/ep1_audit_6efe7b_worst_niamh_rigify_1254.png'];
- 2026-10-10 23:53 episode 2 @ 3e6ffd (d1|oisin4|niamh4|sl2|SET_PLATE_WINTER=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_winter_geo.png|SET_RELIEF_NPY_WINTER=/workspace/loopwork/improve/plate_winter_geo_depth.npy|SET_RELIEF_GAIN_WINTER=0.4): rendered first_snow_loop_3e6ffd_web.mp4; SF_DONE /workspace/loopwork/improve/ep2_audit_3e6ffd.txt ['/workspace/loopwork/improve/ep2_audit_3e6ffd_worst_oisin_rigify_1196.png', '/workspace/loopwork/improve/ep2_audit_3e6ffd_worst_oisin_rigify_1254.png', '/workspace/loopwork/improve/ep2_audit_3e6ffd_worst_oisin_rigify_1118.png', '/workspace/loopwork/improve/ep2_audit_3e6ffd_worst_niamh_rigify_1190.png'];
