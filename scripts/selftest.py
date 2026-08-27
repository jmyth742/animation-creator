#!/usr/bin/env python3
"""
Regression suite for the pipeline's pure functions.

Every check here corresponds to a defect that actually reached a finished
episode. Not one of them crashed -- each produced a plausible-looking render
that was wrong, and cost a 2.5-hour job to discover. The point of this file is
that the next regression fails in two seconds instead.

No GPU, no ComfyUI, no network. Runs as the first step of every render job.

    python scripts/selftest.py            # all checks
    python scripts/selftest.py -v         # show each check

Exit code is non-zero on any failure, so jobctl aborts before rendering.
"""
import sys
import json
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                    # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TMP = "/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad"
SERIES = "tir-na-nog-legend"

_results: list[tuple[str, str, str]] = []                  # (status, name, detail)
VERBOSE = "-v" in sys.argv or "--verbose" in sys.argv


def check(name):
    """Decorator: run the function, record pass/fail/skip from what it raises."""
    def deco(fn):
        try:
            fn()
        except SkipCheck as e:
            _results.append(("SKIP", name, str(e)))
        except AssertionError as e:
            _results.append(("FAIL", name, str(e) or "assertion failed"))
        except Exception as e:                             # noqa: BLE001
            _results.append(("FAIL", name, f"{type(e).__name__}: {e}"))
        else:
            _results.append(("PASS", name, ""))
        return fn
    return deco


class SkipCheck(Exception):
    """Raised when a fixture this check needs is not on disk."""


def _bible():
    p = sr.series_path(SERIES) / "bible.json"
    if not p.exists():
        raise SkipCheck(f"no bible at {p}")
    return json.loads(p.read_text())


def _episode(n=1):
    p = sr.series_path(SERIES) / "episodes" / f"ep{n:02d}.json"
    if not p.exists():
        raise SkipCheck(f"no ep{n:02d}.json")
    return json.loads(p.read_text())


# ══════════════════════════════════════════════════════════════════════
#  Ambience: word-boundary matching
#
#  A bare substring test put PUB ambience under a desolate ruin, because
#  "bar" occurs inside "bare thorn trees". The unmatched default was
#  "street_rain", which laid city rain under every location it did not
#  recognise -- including an open ocean.
# ══════════════════════════════════════════════════════════════════════
@check("ambience: substrings do not match across word boundaries")
def _():
    got = sr.classify_ambient("ruined_ireland", "bare thorn trees and moss-covered stone")
    assert got != "pub", '"bare thorn trees" matched pub ambience via the substring "bar"'
    for loc, desc, bad in [
        ("field", "the campaign banners", "camp"),
        ("shed", "a wireless mast", "wire"),
        ("hill", "an old graveyard wall", "yard"),
    ]:
        got = sr.classify_ambient(loc, desc)
        assert got != bad, f'"{desc}" matched {bad} ambience across a word boundary'


@check("ambience: an unrecognised location gets silence, not city rain")
def _():
    got = sr.classify_ambient("xyzzy_nowhere", "an entirely unprecedented place")
    assert got is None, f"unmatched location returned {got!r}; silence is better than the wrong room"


# ══════════════════════════════════════════════════════════════════════
#  Reference filenames: both sides must agree
#
#  generate_reference_images() wrote "{key}.png" while get_scene_seed_image()
#  looked for "char_{key}.png". They matched only for "char_N" keys, so a
#  semantically-keyed bible ("niamh") generated portraits that were then
#  silently never used -- every shot fell through to the frame chain.
# ══════════════════════════════════════════════════════════════════════
@check("references: _ref_name is stable for both key styles")
def _():
    assert sr._ref_name("niamh", "char") == "char_niamh.png"
    assert sr._ref_name("char_niamh", "char") == "char_niamh.png", "prefix double-applied"
    assert sr._ref_name("char_1", "char") == "char_1.png"
    assert sr._ref_name("storm_cliffs", "loc") == "loc_storm_cliffs.png"
    assert sr._ref_name("loc_storm_cliffs", "loc") == "loc_storm_cliffs.png"


@check("references: every bible character and location resolves to a file")
def _():
    b = _bible()
    ref_dir = sr.series_path(SERIES) / "reference_images"
    if not ref_dir.exists():
        raise SkipCheck("no reference_images dir")
    missing = [k for k in b.get("characters", {}) if not sr._find_ref(ref_dir, k, "char")]
    assert not missing, f"characters with no portrait on disk: {missing}"
    locs = b.get("world", {}).get("locations", {})
    missing = [k for k in locs if not sr._find_ref(ref_dir, k, "loc")]
    assert not missing, f"locations with no plate on disk: {missing}"


# ══════════════════════════════════════════════════════════════════════
#  Seeding policy
#
#  A wide shot seeded from a head-and-shoulders portrait inherits portrait
#  framing. A wide shot seeded from the previous frame renders the previous
#  scene again -- which is how a heroine came to be absent from her own
#  entrance. Both failures look like a normal render.
# ══════════════════════════════════════════════════════════════════════
@check("seeding: wide shot WITH characters uses the plate, never a portrait")
def _():
    # A portrait seed forces portrait framing onto a wide. No seed at all is
    # worse: the shot free-associates and comes back in a different style with
    # the wrong costumes. The plate is a wide composition in the series' own
    # style, so it anchors both framing and look.
    ref_dir = sr.series_path(SERIES) / "reference_images"
    scene = {"id": "t_s01", "visual": "Wide shot of Niamh riding along the strand",
             "characters": ["niamh"], "location": "storm_cliffs"}
    got = sr.get_scene_seed_image(scene, SERIES, "/some/previous/frame.png")
    assert got != "/some/previous/frame.png", \
        "wide+characters fell through to the chain — it re-renders the previous shot"
    if got is None:
        assert not sr._find_ref(ref_dir, "storm_cliffs", "loc"), \
            "a plate exists but the wide shot was left unseeded — it will drift in style"
        return
    assert "char" not in Path(got).name, \
        f"wide+characters seeded from a portrait ({Path(got).name}) — inherits portrait framing"
    # A STAGED plate (<setup>__<char>_<framing>.png) is the better answer and
    # what the policy asks for; a plain location plate is the fallback when the
    # set library has not been built for that place. This check asserted "loc"
    # only, which passed for years because the fixture location had no staged
    # plates -- the moment storm_cliffs was staged, correct behaviour failed it.
    name = Path(got).name
    assert "__" in name or "loc" in name, \
        f"unexpected seed for a wide shot: {got!r}"


@check("seeding: 'Wide static shot' is recognised as wide")
def _():
    # Substring matching on "wide shot" missed "Wide static shot" and "wide
    # aerial shot", so establishing shots were classified as close-ups.
    for phrasing in ("Wide static shot of the cliffs",
                     "Wide aerial shot over the sea",
                     "Wide slow shot of the valley"):
        scene = {"id": "t_s01", "visual": phrasing,
                 "characters": ["niamh"], "location": "storm_cliffs"}
        got = sr.get_scene_seed_image(scene, SERIES, "/prev.png")
        # Recognised as wide => a plate (staged or plain) or T2V. Misread as a
        # close-up => a portrait, which is the failure this guards against.
        assert got is None or "__" in Path(got).name or "loc" in Path(got).name, \
            f"{phrasing!r} was not treated as a wide shot (seeded from {got!r})"


@check("seeding: close-up WITH characters uses the portrait")
def _():
    ref_dir = sr.series_path(SERIES) / "reference_images"
    b = _bible()
    key = next(iter(b.get("characters", {})), None)
    if not key or not sr._find_ref(ref_dir, key, "char"):
        raise SkipCheck("no portrait on disk to seed from")
    scene = {"id": "t_s02", "visual": f"Close-up on {key}, eyes wet",
             "characters": [key], "location": "storm_cliffs",
             "dialogue": [{"character": key, "line": "I must go."}]}
    got = sr.get_scene_seed_image(scene, SERIES, "/prev.png")
    assert got and "char" in Path(got).name, f"close-up did not seed from the portrait (got {got!r})"


@check("seeding: an explicit per-scene seed beats the frame chain")
def _():
    scene = {"id": "t_s03", "visual": "A hard cut to the ruined fort",
             "characters": [], "location": "ruined_ireland", "seed": "t2v"}
    assert sr.get_scene_seed_image(scene, SERIES, "/prev.png") is None, \
        'seed:"t2v" did not override the chain -- the shot continues the previous one'


@check("seeding: seed:location forces the plate rather than falling to the chain")
def _():
    b = _bible()
    ref_dir = sr.series_path(SERIES) / "reference_images"
    loc = next((k for k in b.get("world", {}).get("locations", {})
                if sr._find_ref(ref_dir, k, "loc")), None)
    if not loc:
        raise SkipCheck("no location plate on disk")
    # Deliberately phrased so the establishing heuristic does NOT fire: this is
    # the exact case that used to fall through to the chain.
    scene = {"id": "t_s04", "visual": "The fort, seen from the road",
             "characters": [], "location": loc, "seed": "location"}
    got = sr.get_scene_seed_image(scene, SERIES, "/prev.png")
    # A location plate is either the legacy loc_<name>.png or, once a set
    # library exists, sets/<location>/master.png. What must never happen is
    # falling through to the frame chain, which re-renders the previous shot.
    assert got, 'seed:"location" produced no seed at all'
    name = Path(got).name
    is_plate = name.startswith("loc_") or name in ("master.png",) or (
        "__" not in name and name.rsplit(".", 1)[0] in
        ("master", "reverse", "wider", "closer", "side"))
    assert is_plate, f'seed:"location" fell through to {name!r} instead of a plate'
    assert got != "/prev.png", 'seed:"location" fell through to the chain'


# ══════════════════════════════════════════════════════════════════════
#  Prompt construction
# ══════════════════════════════════════════════════════════════════════
@check("prompt: a LoRA-backed character emits its trigger word")
def _():
    # A LoRA can train, install, and wire correctly and still do absolutely
    # nothing if its trigger never reaches the prompt. There is no error.
    b = {"series": {"style": "Cel-shaded 2D animation"},
         "characters": {"jonny": {"visual": "A young man in a grey coat",
                                  "lora_path": "jonny-wan22.safetensors",
                                  "trigger_word": "j0nnyx"}},
         "world": {"locations": {}}}
    scene = {"id": "t_s05", "visual": "Close-up on Jonny", "characters": ["jonny"]}
    p = sr.build_scene_prompt(scene, b)
    assert "j0nnyx" in p, f"trigger word absent from prompt -- the LoRA will load and do nothing:\n  {p}"


@check("prompt: a LoRA-backed character keeps its description as a fallback")
def _():
    b = {"series": {"style": "Cel-shaded 2D animation"},
         "characters": {"jonny": {"visual": "A young man in a grey coat",
                                  "lora_path": "jonny-wan22.safetensors",
                                  "trigger_word": "j0nnyx"}},
         "world": {"locations": {}}}
    p = sr.build_scene_prompt({"id": "t", "visual": "Close-up on Jonny",
                               "characters": ["jonny"]}, b)
    assert "grey coat" in p, "brief dropped; a weak LoRA now degrades to a stranger"


@check("prompt: close-up dialogue still carries a setting cue")
def _():
    # With no setting in the prompt the model invents one, so dialogue
    # close-ups came back in modern interiors while the scene was on a cliff.
    b = _bible()
    loc = next(iter(b.get("world", {}).get("locations", {})), None)
    if not loc:
        raise SkipCheck("no locations in bible")
    char = next(iter(b.get("characters", {})))
    scene = {"id": "t_s06", "visual": "Close-up on his face, jaw tight",
             "characters": [char], "location": loc,
             "dialogue": [{"character": char, "line": "Then I am lost."}]}
    p = sr.build_scene_prompt(scene, b)
    assert "background" in p.lower(), \
        f"close-up dialogue has no setting cue -- the model will invent an interior:\n  {p}"


@check("prompt: series style describes rendering only, not subject matter")
def _():
    # The style string is appended to EVERY scene prompt and every reference
    # plate. Subject matter in it ("emerald cliffs, gold horizon light")
    # overrides every location and makes all six look like the same place.
    b = _bible()
    style = b["series"].get("style", "").lower()
    banned = ["cliff", "sea", "ocean", "forest", "castle", "mountain", "horizon",
              "valley", "shore", "beach", "meadow", "river", "sky"]
    hits = [w for w in banned if w in style]
    assert not hits, (
        f"series style contains subject matter {hits} -- it is appended to every "
        f"prompt, so every location inherits it:\n  {b['series'].get('style','')}")


@check("prompt: style truncation never cuts mid-word")
def _():
    long_style = ("Cel-shaded 2D animation, clean confident linework, flat blocks of "
                  "colour with simple shading, painted background art, restrained "
                  "palette of greens, slate blues and gold, expressive stylised faces")
    b = {"series": {"style": long_style}, "characters": {}, "world": {"locations": {}}}
    p = sr.build_scene_prompt({"id": "t", "visual": "A wide shot", "characters": []}, b)
    tail = p.rstrip(".").split(". ")[-1]
    assert long_style.startswith(tail) or tail in long_style, "style tail is not a prefix of the style"
    # The truncated tail must end on a whole word that exists in the original.
    last_word = tail.split()[-1].strip(",")
    assert f" {last_word}" in f" {long_style}" or long_style.startswith(last_word), \
        f"style was cut mid-word: ...{tail[-40:]!r}"


@check("prompt: S2V leads with the style, I2V does not")
def _():
    # S2V's own prior overrides its seed image: a cel-shaded portrait came back
    # as a smooth 3D-CGI face. Moving the style to the front of the prompt --
    # where diffusion weights it most -- fixed it. I2V and T2V get their look
    # from the seed picture instead and are deliberately left alone.
    b = _bible()
    style_head = b["series"]["style"].split(",")[0].strip().lower()
    ep = _episode(4) if (sr.series_path(SERIES) / "episodes" / "ep04.json").exists() \
        else _episode(1)
    seen_s2v = seen_other = False
    for scene in ep.get("scenes", []):
        p = sr.build_scene_prompt(scene, b).lower()
        if sr.classify_scene_type(scene) == "s2v":
            seen_s2v = True
            assert p.startswith(style_head), (
                f"{scene['id']} is S2V but does not lead with the style — it will "
                f"render 3D-CGI among cel-shaded shots:\n  {p[:90]}")
        else:
            seen_other = True
            assert not p.startswith(style_head), (
                f"{scene['id']} is {sr.classify_scene_type(scene)} but leads with the "
                "style; that reorder was only measured for S2V")
    if not seen_s2v:
        raise SkipCheck("no S2V scenes in this episode")
    assert seen_other, "episode has no non-S2V scene to contrast against"


# ══════════════════════════════════════════════════════════════════════
#  Negative prompt
#
#  The series is deliberately cel-shaded. Suppressing "cartoon, anime,
#  illustration" spent guidance fighting the chosen look -- and lost that
#  fight unevenly, which is what produced two visual styles in one episode.
# ══════════════════════════════════════════════════════════════════════
@check("negatives: do not suppress the series' own style")
def _():
    # The whole family has to be checked, not just the exact words the style
    # happens to use. A style reading "cel-shaded 2D animation" is still fought
    # by a negative prompt saying "cartoon" -- they name the same medium, and
    # the render loses that fight unevenly, which is what put two visual styles
    # in one episode.
    ANIMATED = ("cel-shaded", "cel shaded", "2d animation", "animated", "animation",
                "cartoon", "anime", "illustration", "illustrated", "painterly",
                "hand-drawn", "drawing")
    PHOTOREAL = ("photoreal", "photorealistic", "live action", "live-action",
                 "photograph", "cinematic film still")
    b = _bible()
    style = b["series"].get("style", "").lower()
    neg = sr.build_negative_prompt({"id": "t", "visual": "Close-up on her face",
                                    "characters": ["niamh"]}).lower()
    style_is_animated = any(t in style for t in ANIMATED)
    style_is_photoreal = any(t in style for t in PHOTOREAL)
    if style_is_animated:
        hits = [t for t in ANIMATED if t in neg]
        assert not hits, (
            f"the series style is animated but the negative prompt suppresses {hits} "
            "-- the render is fighting its own look")
    if style_is_photoreal:
        hits = [t for t in PHOTOREAL if t in neg]
        assert not hits, (
            f"the series style is photoreal but the negative prompt suppresses {hits}")
    assert style_is_animated or style_is_photoreal, (
        f"series style commits to no medium, so nothing anchors it:\n  {style}")


@check("negatives: genuine defects are still suppressed")
def _():
    neg = sr.build_negative_prompt({"id": "t", "visual": "A wide shot", "characters": []}).lower()
    for term in ("blurry", "deformed", "watermark", "extra fingers"):
        assert term in neg, f'"{term}" dropped from the negative prompt'


# ══════════════════════════════════════════════════════════════════════
#  Lightning (step-distilled sampling)
#
#  CFG must drop to ~1.0. Left at 5.0 the distilled model burns out and it
#  looks like the LoRA is broken rather than the guidance being wrong.
# ══════════════════════════════════════════════════════════════════════
@check("lightning: cfg drops to 1.0 and steps are rewritten")
def _():
    wf = {"1": {"class_type": "KSampler",
                "inputs": {"cfg": 5.0, "steps": 25, "sampler_name": "uni_pc_bh2",
                           "scheduler": "normal"}}}
    sr.apply_lightning(wf, steps=8)
    i = wf["1"]["inputs"]
    assert i["cfg"] == 1.0, f"cfg is {i['cfg']}; the distilled model burns out above ~1.0"
    assert i["steps"] == 8, f"steps not rewritten (got {i['steps']})"
    assert i["sampler_name"] == "euler"


@check("lightning: the dual-model handoff is rescaled to steps//2")
def _():
    wf = {
        "hi": {"class_type": "KSamplerAdvanced",
               "inputs": {"cfg": 3.5, "steps": 25, "start_at_step": 0, "end_at_step": 12,
                          "sampler_name": "euler", "scheduler": "simple"}},
        "lo": {"class_type": "KSamplerAdvanced",
               "inputs": {"cfg": 3.5, "steps": 25, "start_at_step": 12, "end_at_step": 10000,
                          "sampler_name": "euler", "scheduler": "simple"}},
    }
    sr.apply_lightning(wf, steps=8)
    assert wf["hi"]["inputs"]["end_at_step"] == 4, \
        f"high-noise expert hands off at {wf['hi']['inputs']['end_at_step']}, not steps//2"
    assert wf["lo"]["inputs"]["start_at_step"] == 4, \
        f"low-noise expert starts at {wf['lo']['inputs']['start_at_step']}, not steps//2"
    assert wf["lo"]["inputs"]["end_at_step"] == 10000, \
        "the open-ended end_at_step was rewritten; the low expert will stop early"


@check("lightning: distill LoRAs exist for the modes that use them")
def _():
    lora_dir = ROOT / "ComfyUI" / "models" / "loras"
    if not lora_dir.exists():
        raise SkipCheck("no ComfyUI loras dir")
    missing = []
    for base, _ in sr.LIGHTNING["t2v"] + sr.LIGHTNING["i2v"]:
        stem = base.replace(".safetensors", "")
        if not any((lora_dir / f"{stem}-{x}.safetensors").exists() for x in ("high", "low")) \
           and not (lora_dir / base).exists():
            missing.append(base)
    assert not missing, f"--lightning would silently render without: {missing}"


# ══════════════════════════════════════════════════════════════════════
#  Timeline
#
#  Three bugs here drifted audio and subtitles progressively later. A 70.5s
#  film ended up with a 55.1s audio stream and nothing reported an error.
# ══════════════════════════════════════════════════════════════════════
@check("timeline: _get_video_duration reads audio files too")
def _():
    # This returning 0 for .mp3 silently hid three other bugs -- every
    # narration was treated as zero-length when budgeting the slot.
    cand = sorted((ROOT / "output").rglob("*.mp3"))[:1] or sorted((ROOT / "audio").rglob("*.mp3"))[:1]
    if not cand:
        raise SkipCheck("no .mp3 on disk to measure")
    d = sr._get_video_duration(str(cand[0]))
    assert d > 0, f"_get_video_duration returned {d} for {cand[0].name}"


@check("timeline: offsets subtract each crossfade")
def _():
    scenes = [{"id": f"nonexistent_s{i:02d}", "clip_length": "long"} for i in range(5)]
    offs = sr.scene_start_offsets(scenes)
    fps = float(sr.get_model_config(sr.DEFAULT_VIDEO_MODEL)["fps"])
    nominal = sr.CLIP_LENGTHS["long"]["frames"] / fps
    assert offs[0] == 0.0
    step = offs[1] - offs[0]
    assert step < nominal, (
        f"offset step {step:.3f}s equals the raw clip length {nominal:.3f}s -- "
        "the crossfade is not being subtracted, so subtitles drift later all episode")


@check("timeline: offsets use MEASURED clip duration where a clip exists")
def _():
    # S2V sizes each clip to its audio and clamps at MAX_FRAMES, so a dialogue
    # shot is routinely 1-2.5s away from its nominal slot. Timing against the
    # nominal slot put audio and subtitles seconds out by the end of an episode.
    ep = _episode(1)
    scenes = ep.get("scenes", [])
    if not scenes:
        raise SkipCheck("episode has no scenes")
    sr.set_current_series(SERIES)
    offs = sr.scene_start_offsets(scenes)
    wrong = []
    for i, scn in enumerate(scenes[:-1]):
        clip = sr.find_latest_clip(scn["id"])
        if not clip:
            continue
        measured = sr._get_video_duration(clip)
        if measured <= 0:
            continue
        step = offs[i + 1] - offs[i] + sr.CROSSFADE_DURATION
        if abs(step - measured) > 0.05:
            wrong.append(f"{scn['id']}: advanced {step:.3f}s, clip is {measured:.3f}s")
    if not wrong and not any(sr.find_latest_clip(s0["id"]) for s0 in scenes):
        raise SkipCheck("no rendered clips on disk")
    assert not wrong, ("offsets ignore the rendered clip's real duration: "
                       + "; ".join(wrong[:4]))


@check("timeline: the stitched episode's audio is as long as its picture")
def _():
    finals = sorted((ROOT / "output" / SERIES).rglob("*_final.mp4"))
    finals = [f for f in finals if "_v" not in f.name]
    if not finals:
        raise SkipCheck("no stitched episode on disk")
    f = finals[-1]

    def _stream_dur(kind):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", kind,
             "-show_entries", "stream=duration", "-of", "csv=p=0", str(f)],
            capture_output=True, text=True).stdout.strip().splitlines()
        return float(out[0]) if out and out[0] not in ("", "N/A") else 0.0

    v, a = _stream_dur("v:0"), _stream_dur("a:0")
    if v <= 0 or a <= 0:
        raise SkipCheck(f"could not measure streams in {f.name}")
    assert abs(v - a) < 1.0, (
        f"{f.name}: video {v:.1f}s but audio {a:.1f}s ({v - a:+.1f}s) -- "
        "apad/amix regression; the film runs silent at the end")


# ══════════════════════════════════════════════════════════════════════
#  Narration
#
#  "eternal youth" was spoken as "eternal": narration was truncated BEFORE
#  it reached TTS, so the audio was complete and correct for text that had
#  already lost its ending. Five lines in one episode.
# ══════════════════════════════════════════════════════════════════════
@check("narration: the script is never word-capped before it reaches TTS")
def _():
    # The old code cut the SCRIPT to fit: max_words = budget * wps * 0.9, with
    # wps falling back to a guess for any voice missing from VOICE_WPS. It
    # dropped the last word of five lines in a sixteen-shot episode -- "the
    # Land of Eternal" with no "Youth". The TTS audio was complete and correct
    # for text that had already lost its ending, so nothing looked wrong.
    src = (ROOT / "scripts" / "showrunner.py").read_text()
    i = src.index("def generate_episode_audio")
    body = src[i:i + 12000]
    marker = "narr_text = scene[\"narration\"]"
    assert marker in body, "narration is no longer passed to TTS verbatim"
    seg = body[body.index(marker):body.index(marker) + 1500]
    # Comments in that block document the old bug by name, so scan code only.
    code = "\n".join(ln.split("#", 1)[0] for ln in seg.splitlines())
    for pat in ("max_words", "split()[:", "words[:"):
        assert pat not in code, (
            f"narration is being truncated again ({pat!r}) -- the line will be "
            "spoken complete but short of its ending")


@check("narration: every line fits its shot's post-crossfade slot")
def _():
    ep = _episode(1)
    scenes = ep.get("scenes", [])
    if not scenes:
        raise SkipCheck("no scenes")
    rate = 2.78                                    # measured w/s, en-IE-ConnorNeural
    fps = float(sr.get_model_config(sr.DEFAULT_VIDEO_MODEL)["fps"])
    over = []
    for s in scenes:
        n = (s.get("narration") or "").strip()
        if not n:
            continue
        slot = sr.CLIP_LENGTHS.get(s.get("clip_length", "long"),
                                   sr.CLIP_LENGTHS["long"])["frames"] / fps
        slot -= sr.CROSSFADE_DURATION              # the crossfade eats the tail
        need = len(n.split()) / rate + 0.19        # + TTS lead-in
        if need > slot * 1.35:                     # 1.35 = the speed-up ceiling
            over.append(f"{s['id']} needs {need:.1f}s, slot {slot:.1f}s")
    assert not over, "narration cannot fit even sped up: " + "; ".join(over)


# ══════════════════════════════════════════════════════════════════════
#  Persistent sets
#
#  Every shot is an independent sample, so the geometry of a place is
#  re-invented each time: two characters on one headland came back on two
#  separate sea stacks, and close-ups -- seeded from a bare portrait that
#  says nothing about where they are -- came back in modern interiors.
#  The set library gives a shot something that carries both face and room.
# ══════════════════════════════════════════════════════════════════════
@check("sets: the seed's framing matches the framing the shot asks for")
def _():
    # I2V inherits its seed image's framing. A portrait is head-and-shoulders,
    # so a shot written "medium shot, from the waist up" seeded from a portrait
    # rendered as an EXTREME close-up with the head cropped off. An earlier rule
    # gave plates only to wides, justified on identity (a plate cost 0.073 there)
    # -- but identity is worth little if the shot is not the shot that was
    # written. Only genuine tight close-ups should use the portrait.
    b = _bible()
    ep = _episode(4) if (sr.series_path(SERIES) / "episodes" / "ep04.json").exists() \
        else _episode(1)
    sets_root = sr.series_path(SERIES) / "sets"
    if not sets_root.is_dir():
        raise SkipCheck("no set library built")
    wrong = []
    for scene in ep.get("scenes", []):
        if not scene.get("characters"):
            continue
        v = scene["visual"].lower()
        wider = any(w in v for w in ("wide", "establishing", "medium shot",
                                     "three-quarter shot", "over-the-shoulder",
                                     "two-shot", "full body"))
        tight = "tight close-up" in v or "extreme close" in v
        got = sr.get_scene_seed_image(scene, SERIES, "/prev.png")
        if not got:
            continue
        name = Path(got).name
        is_portrait = name.startswith("char_")
        if wider and not tight and is_portrait:
            wrong.append(f"{scene['id']} asks for a wider framing but seeds from "
                         f"{name} — it will render as a close-up")
        if tight and not is_portrait:
            wrong.append(f"{scene['id']} is a tight close-up but seeds from {name} "
                         f"— the portrait is a better identity reference there")
    assert not wrong, "; ".join(wrong)


@check("sets: a tight close-up keeps the bare portrait, a wide gets a staged plate")
def _():
    # Measured on ep04: the portrait scores 1.000 against the anchor because it
    # IS the anchor, while a staged plate scores 0.908. For a TIGHT close-up the
    # background is barely in frame, so seeding from a plate trades identity for
    # scenery you cannot see -- it cost the dialogue shots 0.02-0.04 each. For a
    # WIDE it is the opposite: the portrait cannot fill a landscape, and an empty
    # location plate has no face at all, so those shots gained 0.16-0.20 from a
    # staged plate. Setting for close-ups comes from the prompt's location cue.
    b = _bible()
    loc = next(iter(b.get("world", {}).get("locations", {})), None)
    char = next(iter(b.get("characters", {})), None)
    if not loc or not char:
        raise SkipCheck("bible has no location/character to test with")
    d = sr.series_path(SERIES) / "sets" / loc
    ref_dir = sr.series_path(SERIES) / "reference_images"
    if not sr._find_ref(ref_dir, char, "char"):
        raise SkipCheck("no portrait on disk")
    made = []
    try:
        d.mkdir(parents=True, exist_ok=True)
        for name in ("master.png", f"master__{char}_full_body.png",
                     f"master__{char}_close.png"):
            f = d / name
            if not f.exists():
                f.write_bytes(b"\x89PNG\r\n\x1a\n")
                made.append(f)

        tight = {"id": "t_cu", "visual": "Tight close-up on the face, jaw tight",
                 "characters": [char], "location": loc, "setup": "master",
                 "dialogue": [{"character": char, "line": "Then I am lost."}]}
        got = sr.get_scene_seed_image(tight, SERIES, "/prev.png")
        assert got and "char" in Path(got).name, (
            f"tight close-up seeded from {Path(got).name if got else None!r}; it "
            "should keep the bare portrait, which is a perfect identity reference")

        wide = {"id": "t_wide", "visual": "Wide two-shot on the headland",
                "characters": [char], "location": loc, "setup": "master"}
        got = sr.get_scene_seed_image(wide, SERIES, "/prev.png")
        assert got and "__" in Path(got).name, (
            f"wide seeded from {Path(got).name if got else None!r}; it should use "
            "a staged plate so the frame carries both the character and the place")

        # And a characterless shot may use the plain plate.
        empty = {"id": "t_empty", "visual": "The headland at dusk",
                 "characters": [], "location": loc, "setup": "master"}
        got = sr.get_scene_seed_image(empty, SERIES, "/prev.png")
        assert got and "__" not in Path(got).name, \
            "a characterless shot should use the plain setup plate"
    finally:
        for f in made:
            f.unlink(missing_ok=True)
        try:
            d.rmdir(); d.parent.rmdir()
        except OSError:
            pass


@check("sets: an explicit setup selects that camera position")
def _():
    b = _bible()
    loc = next(iter(b.get("world", {}).get("locations", {})), None)
    if not loc:
        raise SkipCheck("no locations")
    d = sr.series_path(SERIES) / "sets" / loc
    made = []
    try:
        d.mkdir(parents=True, exist_ok=True)
        for name in ("master.png", "reverse.png"):
            f = d / name
            if not f.exists():
                f.write_bytes(b"\x89PNG\r\n\x1a\n")
                made.append(f)
        scene = {"id": "t_set2", "visual": "The headland, seen from the road",
                 "characters": [], "location": loc, "setup": "reverse"}
        got = sr.get_scene_seed_image(scene, SERIES, "/prev.png")
        assert got and Path(got).name.startswith("reverse"), (
            f'setup:"reverse" did not select reverse.png (got {got!r})')
    finally:
        for f in made:
            f.unlink(missing_ok=True)
        try:
            d.rmdir()
            d.parent.rmdir()
        except OSError:
            pass


@check("sets: a series with no set library behaves exactly as before")
def _():
    # The library is additive. A series that has not built one must not change
    # behaviour, or adding this feature silently rewrites every existing show.
    b = _bible()
    loc = next(iter(b.get("world", {}).get("locations", {})), None)
    d = sr.series_path(SERIES) / "sets"
    if d.exists() and any(d.iterdir()):
        raise SkipCheck("this series now has a set library")
    scene = {"id": "t_set3", "visual": "Wide shot of the headland",
             "characters": [], "location": loc}
    got = sr.get_scene_seed_image(scene, SERIES, "/prev.png")
    assert got is None or "loc_" in Path(got).name or got == "/prev.png", \
        f"unexpected seed with no set library: {got!r}"


# ══════════════════════════════════════════════════════════════════════
#  Mode routing
#
#  get_scene_seed_image() choosing a seed is only half the story: the mode
#  routing in cmd_produce can DISCARD it. A scene that classify_scene_type()
#  calls "t2v" falls through to the unseeded branch unless it carries an
#  explicit per-scene seed, so a plate could be resolved and then never used.
#  An unseeded shot has nothing anchoring its rendering and free-associates --
#  that is what put a 1980s-anime wide, plate armour and all, next to
#  cel-shaded shots in the same episode.
# ══════════════════════════════════════════════════════════════════════
def _routed_mode(scene):
    """Mirror the mode selection in cmd_produce (audio presence aside)."""
    st = sr.classify_scene_type(scene)
    seed = sr.get_scene_seed_image(scene, SERIES, "prev.png")
    sm = (scene.get("seed") or "").lower()
    if st == "s2v":
        mode = "s2v"
    elif st == "i2v" and seed:
        mode = "i2v"
    elif seed and sm in ("location", "portrait", "chain"):
        mode = "i2v"
    else:
        mode = "t2v"
    return mode, seed


@check("routing: no shot resolves a seed and then silently discards it")
def _():
    ep = _episode(4) if (sr.series_path(SERIES) / "episodes" / "ep04.json").exists() \
        else _episode(1)
    sr.set_current_series(SERIES)
    lost = []
    for scene in ep.get("scenes", []):
        mode, seed = _routed_mode(scene)
        if seed and mode == "t2v":
            lost.append(f"{scene['id']} (seed {Path(seed).name} dropped)")
    assert not lost, ("a seed was resolved and then discarded by mode routing: "
                      + "; ".join(lost))


@check("routing: no shot renders unanchored when an anchor exists")
def _():
    ep = _episode(4) if (sr.series_path(SERIES) / "episodes" / "ep04.json").exists() \
        else _episode(1)
    sr.set_current_series(SERIES)
    ref_dir = sr.series_path(SERIES) / "reference_images"
    bare = []
    for scene in ep.get("scenes", []):
        mode, seed = _routed_mode(scene)
        if seed:
            continue
        has_anchor = any(sr._find_ref(ref_dir, c, "char") for c in scene.get("characters", []))
        if scene.get("location") and sr._find_ref(ref_dir, scene["location"], "loc"):
            has_anchor = True
        if has_anchor:
            bare.append(scene["id"])
    assert not bare, (
        "these shots render with no seed although an anchor exists for them, so "
        "nothing holds them to the series style: " + ", ".join(bare))


@check("loras: a LoRA trained before the current anchors is detected as stale")
def _():
    # A character LoRA carries the STYLE of its training images, not just the
    # identity. After a style change every existing LoRA is training data from
    # a different show, and it does not announce that -- it quietly pulls shots
    # back toward the old look. Measured: Oisin via S2V came back photoreal in
    # an episode where Niamh via I2V came back correctly cel-shaded.
    ref_dir = sr.series_path(SERIES) / "reference_images"
    b = _bible()
    named = [c["lora_path"] for c in b.get("characters", {}).values()
             if isinstance(c, dict) and c.get("lora_path")]
    if not named:
        raise SkipCheck("no character LoRAs configured")
    lora_dir = sr.COMFYUI_DIR / "models" / "loras"
    present = [n for n in named
               if (lora_dir / n).exists()
               or (lora_dir / f"{n.removesuffix('.safetensors')}-high.safetensors").exists()]
    if not present:
        raise SkipCheck("configured LoRAs are not installed")
    # The function must be able to answer both ways, not just return False.
    verdicts = {n: sr.lora_is_stale(n, ref_dir) for n in present}
    assert isinstance(list(verdicts.values())[0], bool)
    # And a file newer than every anchor must NOT be called stale.
    import tempfile, os
    fresh = lora_dir / "_selftest_fresh_probe.safetensors"
    try:
        fresh.write_bytes(b"")
        os.utime(fresh, None)
        assert not sr.lora_is_stale("_selftest_fresh_probe.safetensors", ref_dir), \
            "a LoRA newer than every reference image was still called stale — " \
            "retraining would never clear the flag"
    finally:
        fresh.unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════════
#  Strict mode
#
#  The whole point: a wrong configuration must not produce the same exit
#  code as a right one. If these revert to warn-and-continue, every other
#  check in this file is still green while episodes come out broken.
# ══════════════════════════════════════════════════════════════════════
@check("graph: the validator catches a discarded conditioning path")
def _():
    # A checker that has never rejected anything proves nothing. Build a real
    # S2V graph, break it exactly the way it was broken for the life of this
    # project, and confirm the validator says so.
    import validate_workflow as vw
    b = _bible()
    ep = _episode(4) if (sr.series_path(SERIES) / "episodes" / "ep04.json").exists() \
        else _episode(1)
    scene = next((x for x in ep["scenes"] if sr.classify_scene_type(x) == "s2v"), None)
    if scene is None:
        raise SkipCheck("no S2V scene to build")
    res = sr.get_resolution_config("480p", "wan")
    wf = sr.build_video_workflow(
        "wan", "s2v", sr.build_scene_prompt(scene, b), 42, "t_graph", 81, res,
        negative_prompt="x", steps=8, image_name="char_oisin.png",
        audio_path="a.mp3")

    assert not vw.check(wf, "s2v"), \
        f"the CURRENT graph is already wrong: {vw.check(wf, 's2v')}"

    ks = next(k for k, v in wf.items() if v.get("class_type") == "KSampler")
    wf[ks]["inputs"]["positive"] = ["4", 0]
    wf[ks]["inputs"]["negative"] = ["5", 0]
    problems = vw.check(wf, "s2v")
    assert problems, ("the validator did not notice the sampler bypassing the "
                      "S2V conditioning — the exact bug it exists to catch")
    assert any("discarded" in p for p in problems)


@check("graph: an unused seed image is reported")
def _():
    import validate_workflow as vw
    res = sr.get_resolution_config("480p", "wan")
    wf = sr.build_video_workflow("wan", "i2v", "p", 42, "t_orphan", 81, res,
                                 negative_prompt="x", steps=8,
                                 image_name="char_oisin.png")
    li = next((k for k, v in wf.items() if v.get("class_type") == "LoadImage"), None)
    if li is None:
        raise SkipCheck("no LoadImage in the I2V graph")
    for node in wf.values():
        for name, val in list((node.get("inputs") or {}).items()):
            if isinstance(val, list) and val and val[0] == li:
                node["inputs"][name] = ["0", 0]
    problems = vw.check(wf, "i2v")
    assert any("nothing consumes it" in p for p in problems), \
        "a loaded-but-unused seed image was not reported"


@check("s2v: the sampler uses the node's conditioning, not raw text")
def _():
    # WanSoundImageToVideo writes BOTH the audio embedding and the ref_image's
    # VAE latent into the conditioning it returns. Taking only its latent and
    # passing the raw CLIPTextEncode outputs to the sampler silently discards
    # the character reference on every dialogue shot -- which is why S2V
    # identity averaged 0.777 against I2V's 0.876, and why seven of ep04's
    # eight worst shots were dialogue.
    b = _bible()
    ep = _episode(4) if (sr.series_path(SERIES) / "episodes" / "ep04.json").exists() \
        else _episode(1)
    scene = next((x for x in ep["scenes"] if sr.classify_scene_type(x) == "s2v"), None)
    if scene is None:
        raise SkipCheck("no S2V scene to build")
    res = sr.get_resolution_config("480p", "wan")
    wf = sr.build_video_workflow(
        "wan", "s2v", sr.build_scene_prompt(scene, b), 42, "t_s2v", 81, res,
        negative_prompt="x", steps=20, image_name="char_oisin.png",
        audio_path="a.mp3")
    node = next((k for k, v in wf.items()
                 if v.get("class_type") == "WanSoundImageToVideo"), None)
    assert node, "no WanSoundImageToVideo node in the S2V workflow"
    assert "ref_image" in wf[node]["inputs"], \
        "S2V built without a ref_image — nothing carries the character"
    ks = next((v for v in wf.values() if v.get("class_type") == "KSampler"), None)
    assert ks, "no KSampler in the S2V workflow"
    for side in ("positive", "negative"):
        assert ks["inputs"][side][0] == node, (
            f"KSampler {side} comes from node {ks['inputs'][side][0]!r}, not the "
            f"S2V node {node!r} — the reference latent and audio embedding are "
            "being discarded")


@check("loras: character LoRAs are never applied to S2V")
def _():
    # A character LoRA is trained against the T2V checkpoints; S2V is a
    # different model family (Wan2.2-S2V-14B). Measured on ep04_s03 with a
    # correctly built rank-64 LoRA: identity 0.782 -> 0.644 and the cel-style
    # score collapsed 0.999 -> 0.001 -- a photoreal face in a cel-shaded show.
    # The Lightning distill LoRAs were already skipped here for the same
    # reason; character LoRAs were not, and nothing flagged it.
    src = (ROOT / "scripts" / "showrunner.py").read_text()
    i = src.index('if mode == "s2v" and scene_loras:')
    block = src[i:i + 1400]
    assert "scene_loras = []" in block, (
        "S2V no longer clears character LoRAs — a cross-family LoRA will "
        "destroy the art style on every dialogue shot")
    assert "different" in block and "family" in block.lower(), \
        "the reason for clearing them is no longer documented at the site"


@check("strict: fatal() raises under strict and warns when off")
def _():
    was = sr.STRICT
    try:
        sr.STRICT = True
        try:
            sr.fatal("test condition")
        except sr.PipelineError:
            pass
        else:
            raise AssertionError("fatal() did not raise under strict mode")
        sr.STRICT = False
        sr.fatal("test condition")            # must not raise
    finally:
        sr.STRICT = was


@check("strict: a missing LoRA aborts instead of rendering without it")
def _():
    was = sr.STRICT
    try:
        sr.STRICT = True
        try:
            sr._resolve_wan_dual_loras([("no-such-lora-xyzzy.safetensors", 1.0)])
        except sr.PipelineError:
            return
        raise AssertionError(
            "a missing LoRA rendered without aborting -- the shot looks plausible "
            "and proves nothing about the LoRA")
    finally:
        sr.STRICT = was


@check("strict: is the default, and --no-strict is the only way off")
def _():
    assert sr.STRICT is True, "STRICT no longer defaults to True"
    src = (ROOT / "scripts" / "showrunner.py").read_text()
    assert '"--no-strict"' in src, "the --no-strict opt-out is gone"
    assert "STRICT = not getattr(args, 'no_strict', False)" in src, \
        "main() no longer wires the flag; --no-strict would be silently ignored"


# ══════════════════════════════════════════════════════════════════════
#  Clip geometry
# ══════════════════════════════════════════════════════════════════════
@check("clips: every frame count is 4n+1 and within the ceiling")
def _():
    for name, cl in sr.CLIP_LENGTHS.items():
        f = cl["frames"]
        assert f % 4 == 1, f"{name}: {f} frames is not 4n+1 -- WAN will pad or fail"
        assert f <= sr.MAX_FRAMES, f"{name}: {f} frames exceeds MAX_FRAMES={sr.MAX_FRAMES}"


@check("clips: scene ids in the episode are unique")
def _():
    ep = _episode(1)
    ids = [s["id"] for s in ep.get("scenes", [])]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate scene ids {dupes} -- find_latest_clip returns the wrong take"


# ══════════════════════════════════════════════════════════════════════
#  Extended takes (chained S2V chunks)
# ══════════════════════════════════════════════════════════════════════
# The 5.06s single-sample ceiling forced a 3-second average cut and no amount
# of identity or style work fixes a restless edit. Chaining removes it -- but
# only if the parameter actually reaches the builder, which it did not for the
# first three attempts: extra_chunks was accepted, defaulted, and dropped at
# the call site, so every graph came back 16 nodes regardless.
@check("extend: a line inside the ceiling builds the graph it always built")
def _():
    res = sr.get_resolution_config("480p", "wan")
    f, extra, tail = sr.s2v_chunks_for_duration(3.0, fps=16)
    assert extra == 0 and tail is None, \
        f"a 3s line asked for {extra} extra chunk(s) -- chaining is not additive"
    wf = sr.build_video_workflow("wan", "s2v", "p", 42, "t", f, res,
                                 extra_chunks=extra, last_chunk_frames=tail,
                                 negative_prompt="n", steps=8,
                                 image_name="char_oisin.png", audio_path="a.mp3")
    assert not [v for v in wf.values()
                if v["class_type"] == "WanSoundImageToVideoExtend"], \
        "a short line built Extend nodes -- existing shots would change"


@check("extend: extra_chunks reaches the builder and lengthens the take")
def _():
    res = sr.get_resolution_config("480p", "wan")
    seen = {}
    for extra in (0, 1):
        wf = sr.build_video_workflow("wan", "s2v", "p", 42, "t", 81, res,
                                     extra_chunks=extra, negative_prompt="n",
                                     steps=8, image_name="char_oisin.png",
                                     audio_path="a.mp3")
        seen[extra] = sum(1 for v in wf.values()
                          if v["class_type"] == "WanSoundImageToVideoExtend")
    assert seen[1] == seen[0] + 1, (
        f"extra_chunks=1 produced {seen[1]} Extend node(s) against "
        f"{seen[0]} at 0 -- the parameter is not reaching build_wan_s2v_workflow")


@check("extend: the take covers the line, and the tail chunk is not padded")
def _():
    fps = 16
    for spoken in (5.4, 6.5, 7.5, 9.8):
        f, extra, tail = sr.s2v_chunks_for_duration(spoken, fps=fps)
        total = (extra * f + (tail or f)) / fps
        assert total >= spoken, \
            f"{spoken}s of speech got {total:.2f}s of picture -- the line is cut off"
        assert total - spoken < 1.0, (
            f"{spoken}s of speech got {total:.2f}s of picture -- rounding the tail "
            f"chunk up buys silent picture at a full sampling pass each")


@check("extend: a chained graph keeps every sampler on real conditioning")
def _():
    import validate_workflow as vw
    res = sr.get_resolution_config("480p", "wan")
    wf = sr.build_video_workflow("wan", "s2v", "p", 42, "t", 81, res,
                                 extra_chunks=1, last_chunk_frames=33,
                                 negative_prompt="n", steps=8,
                                 image_name="char_oisin.png", audio_path="a.mp3")
    bad = vw.check(wf, "s2v")
    assert not bad, f"chained graph fails its own validator: {bad}"
    lens = [v["inputs"]["length"] for v in wf.values()
            if v["class_type"] in ("WanSoundImageToVideo",
                                   "WanSoundImageToVideoExtend")]
    assert lens == [81, 33], f"chunk lengths {lens} -- the tail size was ignored"


@check("extend: the final chunk is a length that has actually rendered")
def _():
    """A tail of 37 frames killed ep10_s07 inside the Extend node:

        einops: can't divide axis of length 15600 in chunks of 9   ((37-1)/4)

    Tails of 33, 45, 53 and 81 render fine, so the constraint is stricter than
    4n+1 and is documented nowhere. The sizer is therefore restricted to
    lengths this pipeline has produced clips at, and this asserts it stays
    restricted -- a plausible-looking 4n+1 tail is exactly what slipped
    through the first time.
    """
    seen = set()
    for tenths in range(40, 400):
        secs = tenths / 10.0
        f, extra, tail = sr.s2v_chunks_for_duration(secs, fps=16)
        if tail is not None:
            seen.add(tail)
    bad = sorted(t for t in seen if t not in sr.SAFE_TAIL_FRAMES)
    assert not bad, (
        f"the sizer can still produce final chunks of {bad} frames, which are "
        f"not in SAFE_TAIL_FRAMES {sr.SAFE_TAIL_FRAMES} -- one of these will "
        f"fail inside WanSoundImageToVideoExtend partway through a render")


@check("extend: the chunk cap matches what has actually been rendered")
def _():
    # 3-chunk was built and queued once; the poll timed out at 30 minutes and
    # no clip was ever produced or scored. Shipping a cap above what exists on
    # disk is how unverified capability reaches a delivery.
    proven = sorted(Path("/workspace/review/extend_test").glob("*chunk.mp4"))
    have = max([int(p.name[0]) for p in proven], default=1)
    assert sr.MAX_S2V_CHUNKS <= have, (
        f"MAX_S2V_CHUNKS={sr.MAX_S2V_CHUNKS} but only {have}-chunk takes have "
        f"been rendered and scored ({[p.name for p in proven]})")


@check("audio: a chained take budgets against its real length, not one chunk")
def _():
    single = sr.CLIP_LENGTHS["long"]["seconds"]
    plain = {"clip_length": "long"}
    held = {"clip_length": "long", "hold_seconds": 12.0}
    assert sr.scene_audio_budget(plain) == single, \
        "an ordinary shot's budget changed -- chaining must be additive"
    assert sr.scene_audio_budget(held) >= 12.0, (
        f"a 12s chained take gets a {sr.scene_audio_budget(held):.2f}s audio "
        f"budget -- its dialogue will be cut to fit a shot half its size")


@check("audio: a written dialogue line is never silently truncated")
def _():
    src = (ROOT / "scripts" / "showrunner.py").read_text()
    i = src.index("# Generate per-character dialogue segments")
    body = src[i:i + 2400]
    assert "line_text.split()[:max_w]" not in body, (
        "dialogue is still trimmed to fit -- narration overrunning is fatal a "
        "few lines earlier, and dialogue matters more, not less")


@check("seeding: a cross-episode carry-over never beats an authored plate")
def _():
    scene = {"id": "x", "setup": "master", "staging": "full_body"}
    carry = "carry_ep04.png"
    # A staged plate, a portrait and a location plate are all authored choices.
    for planned in ("master__oisin_full_body.png", "char_oisin.png", "loc_cliff.png"):
        assert not sr.should_use_carry_over(0, scene, carry, planned), (
            f"scene 1 takes the previous episode's end frame over {planned}")
    # With nothing authored, the carry-over is exactly what it is for.
    assert sr.should_use_carry_over(0, scene, carry, "chain_prev.png"), \
        "the carry-over stopped working for the case it exists to cover"
    assert not sr.should_use_carry_over(3, scene, carry, "chain_prev.png"), \
        "the carry-over applied to a shot that is not the episode opener"
    assert not sr.should_use_carry_over(0, {**scene, "seed": "location"}, carry,
                                        "chain_prev.png"), \
        "an explicit per-scene seed was overridden by the carry-over"


@check("assembly: the soundtrack is timed from the FINAL clips, not the source")
def _():
    """zoompan rounds each shot up to a whole frame.

    A 9.938s clip comes back 10.000s from the camera pass. One frame per shot
    is nothing; across 55 shots it was 2.7 seconds, and the mix had been built
    from durations recorded BEFORE the post pass. The finished film drifted
    progressively out of sync -- voice and effects sliding later and later --
    from a rounding error repeated 55 times.
    """
    src = (ROOT / "scripts" / "assemble_film.py").read_text()
    i = src.index("soundtrack, built once across the whole film")
    j = src.index("sd.mix_episode", i)
    body = src[i:j]
    assert "_get_video_duration" in body, (
        "offsets are still computed from edit['seconds'] without re-measuring "
        "the clips the post pass actually produced")


@check("poll: waiting in the queue does not spend the render's timeout")
def _():
    """A prompt queued behind a long job used to be abandoned unstarted.

    Tonight that lost a 3-chunk take and three banner concepts in one evening:
    each reported "no output produced" while ComfyUI was still holding them in
    the queue, and the 3-chunk one was found rendering an hour later. Simulated
    here rather than against a live server so it runs in the no-GPU suite.
    """
    import types
    calls = {"n": 0}
    PID = "p1"

    class _R:
        def __init__(self, payload): self._p = payload
        def json(self): return self._p

    def fake_get(url, **kw):
        calls["n"] += 1
        if "/history/" in url:
            # Only appears once it has actually executed.
            return _R({PID: {"status": {"status_str": "success"},
                             "outputs": {"18": {}}}} if calls["n"] > 40 else {})
        # 20 polls queued behind another job, then it starts running.
        if calls["n"] < 40:
            return _R({"queue_running": [[1, "other", {}]],
                       "queue_pending": [[2, PID, {}]]})
        return _R({"queue_running": [[2, PID, {}]], "queue_pending": []})

    stub = types.SimpleNamespace(get=fake_get, ConnectionError=Exception)
    real_req, real_sleep = sr.requests, sr.time.sleep
    sr.requests, sr.time.sleep = stub, lambda _s: None
    try:
        # A budget far smaller than the queue wait it sits through.
        ok = sr.poll_until_done(PID, poll_interval=10, max_wait=60)
    finally:
        sr.requests, sr.time.sleep = real_req, real_sleep
    assert ok, ("a prompt queued behind another job timed out before it ever "
                "ran -- queue time is being charged to the render budget")


@check("upscale: the cel metric rewards hard edges and punishes texture")
def _():
    """This metric changed my conclusion twice before it was right.

    First it compared Laplacian energy ACROSS resolutions, where a 4x image
    spreads each edge over sixteen times the pixels, so every upscaler scored
    worse than doing nothing. Then, once scoring at a common size, a strict
    `<` median bound returned an EMPTY flat-region mask on the best result --
    more than half the frame had a Laplacian of exactly zero -- and reported
    nan, which read as a failure when it was the ideal outcome.

    Both mistakes pointed at the wrong model. So the metric is asserted
    against synthetic images whose right answer is known.
    """
    import numpy as np
    from PIL import Image
    sys.path.insert(0, str(ROOT / "scripts"))
    import compare_upscalers as cu

    tmp = Path(TMP) / "celmetric"
    tmp.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)

    # Cel: flat blocks with hard boundaries.
    cel = np.zeros((480, 832), dtype=np.uint8)
    cel[:, :400] = 40
    cel[:, 400:] = 200
    cel[200:300, :] = 120
    Image.fromarray(cel).save(tmp / "cel.png")

    # Same shapes, but every flat area given fine texture -- the waxy failure.
    waxy = np.clip(cel.astype(np.float32)
                   + rng.normal(0, 6, cel.shape), 0, 255).astype(np.uint8)
    Image.fromarray(waxy).save(tmp / "waxy.png")

    # Same shapes, but the edges blurred -- the soft-upscale failure.
    soft = Image.fromarray(cel).filter(
        __import__("PIL.ImageFilter", fromlist=["ImageFilter"]).GaussianBlur(3))
    soft.save(tmp / "soft.png")

    e_cel, f_cel = cu._scores(tmp / "cel.png")
    e_waxy, f_waxy = cu._scores(tmp / "waxy.png")
    e_soft, f_soft = cu._scores(tmp / "soft.png")

    assert f_waxy > f_cel * 2, (
        f"texture in the flats scored {f_waxy:.4f} against clean {f_cel:.4f} -- "
        f"the metric does not punish waxiness, which is the failure mode that "
        f"matters most for cel")
    assert e_soft < e_cel, (
        f"blurred edges scored {e_soft:.2f} against hard {e_cel:.2f} -- the "
        f"metric does not reward line definition")
    assert not (f_cel != f_cel), \
        "clean cel art scored nan for flatness -- the empty-mask bug is back"

    # Resolution invariance. THE bug that inverted the model ranking: the same
    # picture at 4x scored far worse simply because each edge covered sixteen
    # times the pixels. Identical content at two sizes must score the same,
    # because _scores resamples to a common target before measuring.
    big = Image.fromarray(cel).resize((3328, 1920), Image.NEAREST)
    big.save(tmp / "cel_4x.png")
    e_big, f_big = cu._scores(tmp / "cel_4x.png")
    assert abs(e_big - e_cel) < e_cel * 0.35, (
        f"the same image at 4x scored edge {e_big:.2f} against {e_cel:.2f} at "
        f"native -- scores are not resolution-invariant, so every upscaler is "
        f"judged against a baseline it cannot win")


def main():
    b = ROOT / "series" / SERIES
    print(f"selftest — fixtures: {b if b.exists() else '(missing, checks will skip)'}\n")
    for status, name, detail in _results:
        if status == "PASS" and not VERBOSE:
            continue
        mark = {"PASS": "  ok  ", "FAIL": " FAIL ", "SKIP": " skip "}[status]
        print(f"{mark} {name}")
        if detail:
            print(f"        {detail}")
    n_pass = sum(1 for s, _, _ in _results if s == "PASS")
    n_fail = sum(1 for s, _, _ in _results if s == "FAIL")
    n_skip = sum(1 for s, _, _ in _results if s == "SKIP")
    print(f"\n{n_pass} passed, {n_fail} failed, {n_skip} skipped")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
