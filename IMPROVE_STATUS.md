# Improvement status

Updated 2026-10-05 20:52. Cycle 404.

## GPU duty cycle (last 24 h, 1-min samples)

- card working (>=20%) **4%** of the last 24 h (63 busy minutes; 1149 minutes unsampled, counted idle); mean utilisation of sampled minutes 19%

## Adopted (what the masters are rendered with)

- walk: RW_STRIDE=0.6, RW_DROP=0.062, RW_ARM_OUT=10 (defaults v1)
- scene: SET_PLATE=/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog/master_geo.png, SET_RELIEF_NPY=/workspace/loopwork/improve/plate_geo_depth.npy, SET_RELIEF_GAIN=0.8 (plate v7)
- cast oisin: st_chibi3_oisin_m23845 (hand compactness 0.31, lower is better)
- cast niamh: st_chibi3_niamh_m20705_tex (hand compactness 0.20, lower is better)
- masters: nine_waterfalls_rigify_cast4_web.mp4, nine_waterfalls_loop_97c79e_web.mp4, nine_waterfalls_loop_419a38_web.mp4
- masters built at inputs: d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174; current inputs: d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174

## Settled (not re-run until an input changes)

- cast_face_st_chibi3_oisin_m22223: queued @ st_chibi3_oisin_m22223
- cast_face_st_chibi3_oisin_m23845: queued @ st_chibi3_oisin_m23845
- craft_CHAR_AO: queued @ d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174
- craft_FILM_INTEGRATE: queued @ d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174
- craft_FILM_LINES: queued @ d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174
- craft_FILM_LINE_ALPHA: queued @ d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174
- face_FCG_MOUTH: queued @ d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174
- face_FP_MOUTH_PLATE: queued @ d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174
- plate_flux_r0: queued @ g1
- plate_flux_r1: queued @ g1
- plate_flux_r2: queued @ g1
- scene_fit: queued @ st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7
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

- 2026-10-05 16:59 plate_geo round 13: no results
- 2026-10-05 17:18 scene_fit @396: gains 0.4,0.6,0.8 -> best gain 0.4 (on path 84%, foot float p95 0 mm) ADOPTED
- 2026-10-05 17:43 scene_fit @396: gains 0.4,0.6,0.8 -> best gain 0.8 (on path 83%, foot float p95 0 mm) ADOPTED
- 2026-10-05 19:43 episode @ 419a38 (d1|st_chibi3_oisin_m23845|st_chibi3_niamh_m20705_tex|p7|scb8174): rendered nine_waterfalls_loop_419a38_web.mp4; 
- 2026-10-05 19:47 craft: FILM_LINES A/B over 3.2,4.8,6.4 -> AB_craft_FILM_LINES.png (human pick)
- 2026-10-05 19:50 craft: CHAR_AO A/B over 0,0.35,0.6 -> AB_craft_CHAR_AO.png (human pick)
- 2026-10-05 19:52 craft: FILM_INTEGRATE A/B over 0,0.22,0.4 -> AB_craft_FILM_INTEGRATE.png (human pick)
- 2026-10-05 19:55 craft: FILM_LINE_ALPHA A/B over 0.6,0.82,1.0 -> AB_craft_FILM_LINE_ALPHA.png (human pick)
- 2026-10-05 20:03 face: FP_MOUTH_PLATE A/B over 1.2,1.5,1.9 -> AB_face_FP_MOUTH_PLATE.png (human pick)
- 2026-10-05 20:11 face: FCG_MOUTH A/B over 0.17,0.195,0.22 -> AB_face_FCG_MOUTH.png (human pick)
- 2026-10-05 20:52 cast: oisin best new candidate st_chibi3_oisin_m23845 hands 0.31, adopted st_chibi3_oisin_m23845 (0.31) stands
- 2026-10-05 20:52 cast: niamh best new candidate st_chibi3_niamh_m20705_tex hands 0.20, adopted st_chibi3_niamh_m20705_tex (0.20) stands
