"""The three painted sets the improvement loop paints geometry-first plates for, shared by
improve_loop.py (which writes the jobs) and improve_score.py (which adopts the results)."""
W = "/workspace/loopwork"; REPO = "/workspace/text-to-video"; S = REPO + "/series/tir-na-nog-legend/sets/"
SETS = {
    # guide: depth guide stem under loopwork/geo; init/comfy_guide: files staged in ComfyUI/input;
    # style_ref: the look to keep; out: adopted plate; key/npy_key: configs/scene_defaults.env entries
    "valley": dict(guide=W + "/geo/valley2_depth.png", comfy_guide="geo_depth2.png", init="geo_plate_old.png",
                   style_ref=S + "tir_na_nog/master_4x.png", out=S + "tir_na_nog/master_geo.png",
                   key="SET_PLATE", npy_key="SET_RELIEF_NPY", depth_out=W + "/improve/plate_geo"),
    "winter": dict(guide=W + "/geo/valley2_depth.png", comfy_guide="geo_depth2.png", init="geo_init_winter.png",
                   style_ref=S + "tir_na_nog/master_winter_grade_4x.png", out=S + "tir_na_nog/master_winter_geo.png",
                   key="SET_PLATE_WINTER", npy_key="SET_RELIEF_NPY_WINTER", depth_out=W + "/improve/plate_winter_geo"),
    "cliff":  dict(guide=W + "/geo/cliff2_depth.png", comfy_guide="geo_depth2_cliff.png", init="geo_init_cliff.png",
                   style_ref=S + "farewell_cliff/master_4x.png", out=S + "farewell_cliff/master_geo.png",
                   key="SET_PLATE_CLIFF", npy_key=None, depth_out=None),
}
# episodes: builder, audio, title, sun, output stem, and which scene_defaults keys feed SET_PLATE / SET_RELIEF_NPY
# per-set prompts: the winter plate painted with the summer prompt came back as a summer meadow
# (8 Oct, "winter geo v9": yellow flowers, warm light) and the style gate let it through
PROMPTS = {
    "valley": ("anime background art, painted cel background, lush green valley of Tir na nOg, a golden stone hall "
               "with round celtic emblems and battlements standing on a grassy rise, a tall standing celtic stone cross "
               "beside a still lake, a high waterfall pouring from green cliffs, a winding earthen footpath through a "
               "wildflower meadow, distant mountains, soft summer daylight, clean flat colours, masterpiece, best quality"),
    "winter": ("anime background art, painted cel background, the valley of Tir na nOg under fresh snow, a golden stone hall "
               "with round celtic emblems and battlements on a snow-covered rise, a tall standing celtic stone cross beside a "
               "frozen lake, a waterfall between icy cliffs, a footpath trodden through deep snow, bare frosted trees, "
               "pale overcast winter light, cool blue and white palette, clean flat colours, masterpiece, best quality"),
    "cliff":  ("anime background art, painted cel background, a grassy headland on high sea cliffs, a lone wind-bent tree, "
               "the open sea below under a warm evening sky, distant horizon, soft golden light, clean flat colours, "
               "masterpiece, best quality"),
}
EPISODES = {
    1: dict(script="build_film.py",  audio="film_audio",  title="The Nine Waterfalls", sun="52,118", out="nine_waterfalls", plate="SET_PLATE",        npy="SET_RELIEF_NPY"),
    2: dict(script="build_film2.py", audio="film2_audio", title="The First Snow",      sun="45,120", out="first_snow",      plate="SET_PLATE_WINTER", npy="SET_RELIEF_NPY_WINTER", gain="SET_RELIEF_GAIN_WINTER"),
    3: dict(script="build_film3.py", audio="film3_audio", title="The Farewell Cliff",  sun="26,96",  out="farewell_cliff",  plate="SET_PLATE_CLIFF",  npy=None),
}
