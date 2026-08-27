#!/usr/bin/env python3
"""
Is there a strength at which a T2V-trained character LoRA HELPS an S2V shot?

Character LoRAs are dropped on every dialogue shot -- roughly 80% of both
films -- on the strength of a single measurement: ep04_s03 went identity
0.782 -> 0.644 and its cel-style score collapsed 0.999 -> 0.001, so the shot
came back photoreal in a cel-shaded series. That was decisive and correct.

But it was taken at ONE strength: 0.9. Nobody tried 0.2, or 0.35. A LoRA
applied across model families does not have to be all-or-nothing -- there may
be a window where it contributes likeness before it starts overriding the
checkpoint's own style prior.

That window is worth an hour of GPU because of what it unlocks: character
training on the shots that carry the dialogue, which is where plates cannot
reach and where identity is currently weakest.

Two numbers per strength, and BOTH must hold:
    identity   CLIP against the character anchor
    cel        CLIP against "cel-shaded 2D animation, flat blocks of colour"

Training musibi against the S2V checkpoint is not an alternative: musibi has no
S2V task (only t2v-14B / i2v-14B and FC variants) and the S2V weights on disk
are GGUF Q5_K_M, which cannot be trained from.

    lora_strength_sweep.py <series> --scene ep05_s03
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import verify_render as vr                                     # noqa: E402

# Extended past 0.7 deliberately. At <=0.7 the cel style holds (0.996-0.997)
# and identity does not move, contradicting the documented collapse at 0.9. So
# either the break is between 0.7 and 0.9, or the original measurement had
# another cause -- and that is worth knowing, because the rule that drops
# character LoRAs from ~80% of shots rests on it.
STRENGTHS = [0.0, 0.35, 0.70, 0.90, 1.00]
CEL = "cel-shaded 2D animation, flat blocks of colour, clean linework"
PHOTO = "a photograph of a real person, photorealistic"


def _style(img: Image.Image) -> float:
    """How cel is this frame, against a photoreal alternative.

    Delegates to verify_render rather than re-deriving it. The first version
    here softmaxed the RAW CLIP similarities, which sit around 0.2-0.3 and
    differ between captions by about 0.001 -- so it returned ~0.51 for
    everything: a clean cel frame, that frame destroyed with blur and grain,
    and a character portrait alike. It could not discriminate at all, and
    "style holds" measured with it meant nothing.

    verify_render scales similarities by 100 before the softmax, which is what
    separates them.
    """
    v = vr._embed_images([img])
    sv = vr._embed_texts(vr._STYLE_OPTIONS)
    sims = (v @ sv.T).mean(dim=0)
    return float((sims * 100).softmax(dim=-1)[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--scene", required=True)
    ap.add_argument("--steps", type=int, default=15)
    a = ap.parse_args()

    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    ep_num = int(a.scene.split("_")[0].replace("ep", ""))
    ep = sr.load_json(sr.episode_path(a.series, ep_num))
    scene = next(s for s in ep["scenes"] if s["id"] == a.scene)
    who = scene["dialogue"][0]["character"]
    ch = bible["characters"][who]
    lora = ch.get("lora_path")
    if not lora:
        print(f"  {who} has no LoRA"); return 1

    res = sr.get_resolution_config("480p", "wan")
    seed_img = sr.get_scene_seed_image(scene, a.series, None)
    prompt = sr.build_scene_prompt(scene, bible)
    neg = sr.build_negative_prompt(scene)
    vo = Path("output") / a.series / f"ep{ep_num:02d}" / "audio" / f"{a.scene}.mp3"
    spoken = sr._get_video_duration(str(vo))
    padded = str(vo.with_name(f"{a.scene}_sweep.mp3"))
    sr.pad_audio_to(str(vo), spoken + sr.S2V_LIVE_TAIL, padded)
    audio = sr.copy_to_input(padded)
    frames, extra, tail = sr.s2v_chunks_for_duration(
        spoken + sr.S2V_LIVE_TAIL, fps=16, floor_seconds=spoken)

    ref_dir = sr.series_path(a.series) / "reference_images"
    anchor = vr._embed_images([Image.open(
        sr._find_ref(ref_dir, who, "char")).convert("RGB")])

    rows = []
    for st in STRENGTHS:
        prefix = f"sweep_{a.scene}_{int(st*100):03d}"
        clip = sr.find_latest_clip(prefix)
        if not clip:
            loras = [(lora, st)] if st > 0 else None
            wf = sr.build_video_workflow(
                "wan", "s2v", prompt, 5150, prefix, frames, res,
                negative_prompt=neg, steps=a.steps, image_name=seed_img,
                audio_path=audio, loras=loras,
                extra_chunks=extra, last_chunk_frames=tail)
            print(f"  strength {st:.2f} ...", flush=True)
            try:
                pid = sr.queue_prompt(wf)
                if not sr.poll_until_done(pid, max_wait=1800 * (1 + extra)):
                    print("    no output"); continue
            except Exception as e:                             # noqa: BLE001
                print(f"    {type(e).__name__}: {e}"); continue
            clip = sr.find_latest_clip(prefix)
        if not clip:
            continue
        dur = sr._get_video_duration(clip)
        ids, cels = [], []
        with tempfile.TemporaryDirectory() as td:
            for frac in (0.15, 0.5, 0.85):
                p = f"{td}/f{int(frac*100)}.png"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss",
                                f"{dur*frac:.2f}", "-i", clip, "-frames:v", "1", p],
                               check=True)
                with Image.open(p) as im:
                    rgb = im.convert("RGB").copy()
                ids.append(float((vr._embed_images([rgb]) @ anchor.T)[0][0]))
                cels.append(_style(rgb))
        rows.append((st, sum(ids)/len(ids), sum(cels)/len(cels), clip))

    print(f"\n  {a.scene} — {who}, LoRA {lora}")
    print(f"  {'strength':>9} {'identity':>9} {'cel':>7}   verdict")
    base_id = rows[0][1] if rows else 0
    for st, idn, cel, _ in rows:
        d = idn - base_id
        v = ("baseline" if st == 0 else
             "STYLE LOST" if cel < 0.5 else
             f"identity {d:+.3f}, style holds" if d > 0.005 else
             f"identity {d:+.3f}, no gain")
        print(f"  {st:9.2f} {idn:9.3f} {cel:7.3f}   {v}")
    good = [r for r in rows[1:] if r[2] >= 0.5 and r[1] > base_id + 0.005]
    print(f"\n  {'a usable window exists at strength ' + str(good[0][0]) if good else 'no strength both helps identity and keeps the style'}")
    out = Path("/workspace/review/lora_sweep"); out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.scene}.json").write_text(json.dumps(
        [{"strength": r[0], "identity": r[1], "cel": r[2]} for r in rows], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
