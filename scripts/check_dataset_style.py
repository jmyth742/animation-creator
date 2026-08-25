#!/usr/bin/env python3
"""
Are these training images actually in the series' current style?

A LoRA learns the style of its training frames, not the style you intended. Two
separate mistakes have now produced photoreal training data for a cel-shaded
series: a brief carrying the old style string, and -- after that was fixed --
a clips stage that skipped regeneration because Aug-23 clips were still on
disk. The brief gate checked the PROMPT. This checks the PIXELS, so it catches
the failure whatever caused it.

Scores a sample of the dataset against two captions via CLIP and requires the
series' own medium to win.

    python scripts/check_dataset_style.py <series> oisin niamh
    python scripts/check_dataset_style.py <series> oisin --sample 12

Exits non-zero if the dataset would train the wrong look, so it can gate a job
before a multi-hour GPU run.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import verify_render as vr                                     # noqa: E402
from PIL import Image                                          # noqa: E402

DATASETS = Path("/workspace/datasets")

ANIMATED = ("cel-shaded", "cel shaded", "2d animation", "animated", "animation",
            "cartoon", "anime", "illustration", "illustrated", "hand-drawn")

CAPTIONS = {
    "animated": "a cel-shaded 2D animation frame, flat colour and clean linework",
    "photoreal": "a photorealistic photograph of a real person, natural skin texture",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("names", nargs="+")
    ap.add_argument("--sample", type=int, default=10,
                    help="how many frames to score per character")
    ap.add_argument("--min-share", type=float, default=0.8,
                    help="fraction of sampled frames that must match the style")
    a = ap.parse_args()

    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    style = bible["series"].get("style", "").lower()
    want = "animated" if any(t in style for t in ANIMATED) else "photoreal"
    print(f"  series style is {want.upper()}")

    if vr._clip() is None:
        print("  CLIP unavailable — cannot check dataset style", file=sys.stderr)
        return 1

    texts = [CAPTIONS["animated"], CAPTIONS["photoreal"]]
    tv = vr._embed_texts(texts)
    failed = []

    for name in a.names:
        d = DATASETS / name
        imgs = sorted(d.glob("*.png"))
        if not imgs:
            print(f"  {name}: NO IMAGES in {d}")
            failed.append(f"{name} (empty)")
            continue
        step = max(1, len(imgs) // a.sample)
        sample = imgs[::step][:a.sample]

        matches = 0
        for f in sample:
            with Image.open(f) as im:
                fv = vr._embed_images([im.convert("RGB").copy()])
            sims = (fv @ tv.T)[0]
            verdict = "animated" if sims[0] > sims[1] else "photoreal"
            if verdict == want:
                matches += 1

        share = matches / len(sample)
        ok = share >= a.min_share
        print(f"  {name}: {matches}/{len(sample)} frames read as {want} "
              f"({share:.0%})  {'ok' if ok else 'FAIL'}")
        if not ok:
            failed.append(f"{name} ({share:.0%} {want})")

    if failed:
        print(f"\n  dataset would train the WRONG style: {'; '.join(failed)}")
        print("  the training clips are probably stale — regenerate them with --force:")
        print(f"    python scripts/build_character_dataset.py clips <name> --force")
        return 1
    print(f"\n  all datasets are in the series style")
    return 0


if __name__ == "__main__":
    sys.exit(main())
