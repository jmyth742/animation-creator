# Improvement status

Updated 2026-10-06 07:03. Cycle 420.

## GPU duty cycle (last 24 h, 1-min samples)

- card working (>=20%) **18%** of the last 24 h (271 busy minutes; 540 minutes unsampled, counted idle); mean utilisation of sampled minutes 29%

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

- 2026-10-06 04:04 cast: oisin best new candidate st_chibi3_oisin_m23845 hands 0.31, adopted st_chibi3_oisin_m23845 (0.31) stands
- 2026-10-06 04:04 cast: niamh best new candidate st_chibi3_niamh_m20705_tex hands 0.20, adopted st_chibi3_niamh_m20705_tex (0.20) stands
- 2026-10-06 04:43 cast: oisin best new candidate st_chibi3_oisin_m23845 hands 0.31, adopted st_chibi3_oisin_m23845 (0.31) stands
- 2026-10-06 04:43 cast: niamh best new candidate st_chibi3_niamh_m20705_tex hands 0.20, adopted st_chibi3_niamh_m20705_tex (0.20) stands
- 2026-10-06 05:22 cast: oisin best new candidate st_chibi3_oisin_m23845 hands 0.31, adopted st_chibi3_oisin_m23845 (0.31) stands
- 2026-10-06 05:22 cast: niamh best new candidate st_chibi3_niamh_m20705_tex hands 0.20, adopted st_chibi3_niamh_m20705_tex (0.20) stands
- 2026-10-06 05:40 cast: oisin best new candidate st_chibi3_oisin_m23845 hands 0.31, adopted st_chibi3_oisin_m23845 (0.31) stands
- 2026-10-06 05:40 cast: niamh best new candidate st_chibi3_niamh_m20705_tex hands 0.20, adopted st_chibi3_niamh_m20705_tex (0.20) stands
- 2026-10-06 06:22 cast: oisin best new candidate st_chibi3_oisin_m23845 hands 0.31, adopted st_chibi3_oisin_m23845 (0.31) stands
- 2026-10-06 06:22 cast: niamh best new candidate st_chibi3_niamh_m20705_tex hands 0.20, adopted st_chibi3_niamh_m20705_tex (0.20) stands
- 2026-10-06 07:03 cast: oisin best new candidate st_chibi3_oisin_m23845 hands 0.31, adopted st_chibi3_oisin_m23845 (0.31) stands
- 2026-10-06 07:03 cast: niamh best new candidate st_chibi3_niamh_m20705_tex hands 0.20, adopted st_chibi3_niamh_m20705_tex (0.20) stands
