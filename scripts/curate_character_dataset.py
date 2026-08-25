#!/usr/bin/env python3
"""
Build a character LoRA dataset from staged set plates, curated by identity.

WHY THIS EXISTS
The first cel LoRA for Oisin trained cleanly -- 41 frames, loss 0.044, wired
correctly, verified not stale -- and did nothing. Identity moved +0.006 on
wides and -0.027 on the close-up, and it dragged the close-up's style score
from 1.000 to 0.576. Two faults, both in the DATA:

  1. Shape. Every training frame was 480x832 portrait; every episode shot is
     832x480 landscape. It learned a portrait-framed character.
  2. Honesty. The frames came from animating one portrait with motion prompts,
     then captioning by INTENDED shot. WAN barely moved the subject, so a frame
     captioned "wide shot, full body" was the same head-and-shoulders portrait
     as one captioned "extreme close-up". The LoRA learned that framing words
     mean nothing, and bound the character to a single composition.

Staged set plates fix both: they are rendered at 832x480 into a real location,
and a full_body staging genuinely puts the figure small in the frame.

But each staged plate is itself an I2V generation, so each drifts a little from
the canonical face. Training on all of them averages those drifts back in --
the same failure by another route. So they are SCORED against the canonical
portrait and only the closest are kept.

TWO CAPTION SETS, ONE SET OF IMAGES
  lora/     neutral, shot-only captions -- what a LoRA needs
  story/    rich in-world captions -- a writing aid and a seed library

A LoRA caption must describe what VARIES and never the character: whatever is
named in the caption becomes detachable, whatever is left out is baked into the
trigger. Caption his beard and the beard becomes conditional on that word.
Caption only the framing and the face becomes part of the trigger itself.

    curate_character_dataset.py <series> <character> --trigger o1s1nx
    curate_character_dataset.py <series> <character> --keep 25 --min-identity 0.80
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import verify_render as vr                                     # noqa: E402
from PIL import Image                                          # noqa: E402

DATASETS = Path("/workspace/datasets")

# Neutral, shot-only. The trigger is prepended at write time.
SHOT_CAPTIONS = {
    "full_body":     "full body shot, the whole figure small in a wide landscape",
    "medium":        "medium shot, from the waist up",
    "close":         "close-up, head and shoulders",
    "ecu":           "extreme close-up on the face",
    "three_quarter": "three-quarter angle, upper body",
    "over_shoulder": "over the shoulder from behind",
    "low_angle":     "low angle looking up, figure against the sky",
    "walking_away":  "full body from behind, walking away into the distance",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("character")
    ap.add_argument("--trigger", default=None,
                    help="rare token to bind the identity to. A common name "
                         "competes with the base model's own prior -- 'Oisin' "
                         "already means 'generic young warrior' to it.")
    ap.add_argument("--keep", type=int, default=25)
    ap.add_argument("--min-identity", type=float, default=0.78,
                    help="reject plates further than this from the canonical "
                         "portrait; they are drift, not variety")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    char = bible.get("characters", {}).get(a.character)
    if not char:
        sys.exit(f"unknown character '{a.character}'")
    trigger = a.trigger or char.get("trigger_word") or a.character
    ref_dir = sr.series_path(a.series) / "reference_images"
    anchor = sr._find_ref(ref_dir, a.character, "char")
    if not anchor:
        sys.exit(f"no canonical portrait for {a.character}")

    sets_root = sr.series_path(a.series) / "sets"
    plates = sorted(sets_root.glob(f"*/*__{a.character}_*.png"))
    if not plates:
        sys.exit(f"no staged plates for {a.character} under {sets_root}.\n"
                 f"  run: build_sets.py stage {a.series} <location> {a.character}")

    if vr._clip() is None:
        sys.exit("CLIP unavailable — cannot curate by identity")

    print(f"  {len(plates)} staged plate(s) found")
    print(f"  scoring against {anchor.name}\n")

    av = vr._embed_images([Image.open(anchor).convert("RGB")])
    scored = []
    for f in plates:
        with Image.open(f) as im:
            img = im.convert("RGB").copy()
        fv = vr._embed_images([img])
        scored.append((float((fv @ av.T)[0][0]), f, img.size))

    scored.sort(reverse=True)
    eligible = [r for r in scored if r[0] >= a.min_identity]

    # Taking the top N by identity is what a first version does, and it is
    # wrong: the most identity-faithful images are the most similar ones, so
    # ranking by identity alone re-selects exactly the homogeneous set the
    # diversity gate exists to reject. Measured -- top-28-by-identity came back
    # 0.905 pairwise, barely worse than the 0.937 pool it was drawn from.
    #
    # Instead: everything above the identity floor is ELIGIBLE, then pick
    # greedily for maximum difference from what is already chosen. Identity is
    # a constraint; diversity is the objective.
    if len(eligible) <= a.keep:
        kept = eligible
    else:
        embs = {}
        for sc_, f, sz in eligible:
            with Image.open(f) as im:
                embs[f] = vr._embed_images([im.convert("RGB").copy()])
        kept = [eligible[0]]                      # start from the best identity
        pool = eligible[1:]
        while len(kept) < a.keep and pool:
            chosen = [embs[f] for _, f, _ in kept]
            best, best_i = None, -1
            for i, (sc_, f, sz) in enumerate(pool):
                # distance to the NEAREST already-kept image; maximise it
                worst = max(float((embs[f] @ c.T)[0][0]) for c in chosen)
                if best is None or worst < best:
                    best, best_i = worst, i
            kept.append(pool.pop(best_i))
        print(f"  selected greedily for spread (identity floor {a.min_identity})")
    rejected = [r for r in scored if r not in kept]

    print(f"  {'score':>6}  {'size':>9}  plate")
    for s, f, size in scored:
        mark = "keep" if (s, f, size) in kept else "drop"
        print(f"  {s:6.3f}  {size[0]}x{size[1]:<4}  {f.parent.name}/{f.stem}  [{mark}]")

    if not kept:
        sys.exit(f"\n  nothing scored above {a.min_identity} — the staged plates "
                 f"have drifted too far from the portrait to train on")

    vals = [s for s, _, _ in kept]
    print(f"\n  keeping {len(kept)}, dropping {len(rejected)}")
    print(f"  kept identity: min {min(vals):.3f}  mean {sum(vals)/len(vals):.3f}  "
          f"max {max(vals):.3f}")
    stagings = {f.stem.split("__")[1].split("_", 1)[1] for _, f, _ in kept}
    print(f"  framings named: {len(stagings)}  ({', '.join(sorted(stagings))})")

    # Distinct NAMES are not distinct PICTURES. The first dataset carried eight
    # different shot captions on what were all the same head-and-shoulders
    # portrait, and the LoRA learned that framing words mean nothing. Measure
    # how different the kept images actually are FROM EACH OTHER.
    embs = []
    for _, f, _ in kept:
        with Image.open(f) as im:
            embs.append(vr._embed_images([im.convert("RGB").copy()]))
    sims = []
    for i in range(len(embs)):
        for j in range(i + 1, len(embs)):
            sims.append(float((embs[i] @ embs[j].T)[0][0]))
    if sims:
        mean_sim = sum(sims) / len(sims)
        print(f"  pairwise similarity between kept images: mean {mean_sim:.3f} "
              f"(min {min(sims):.3f}, max {max(sims):.3f})")
        if mean_sim > 0.90:
            print(f"\n  WARNING: the kept images are {mean_sim:.0%} similar to each "
                  f"other.\n  They are labelled as {len(stagings)} framings but they are "
                  f"effectively one\n  picture, which is exactly what trained a LoRA "
                  f"that did nothing. Add\n  genuine variety in distance and angle "
                  f"before training on this.")
    if len(stagings) < 4:
        print("  WARNING: fewer than 4 distinct framings survived")

    if a.dry_run:
        print("\n  dry run, nothing written")
        return 0

    out = DATASETS / a.character
    story = out.parent / f"{a.character}_story"
    for d in (out, story):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    appearance = (char.get("visual") or "").split(".")[0].strip()
    manifest = []
    for i, (s, f, size) in enumerate(kept):
        staging = f.stem.split("__")[1].split("_", 1)[1]
        setup = f.stem.split("__")[0]
        loc = f.parent.name
        base = f"{a.character}_{i:03d}"
        shutil.copy2(f, out / f"{base}.png")
        # LoRA caption: trigger + framing ONLY.
        (out / f"{base}.txt").write_text(
            f"{trigger}. {SHOT_CAPTIONS.get(staging, staging)}.\n")
        # Story caption: the same picture, described in-world.
        shutil.copy2(f, story / f"{base}.png")
        (story / f"{base}.txt").write_text(
            f"{char.get('name', a.character)} at {loc.replace('_', ' ')}, "
            f"{setup} angle, {staging.replace('_', ' ')}. {appearance}.\n")
        manifest.append({"file": f"{base}.png", "identity": round(s, 3),
                         "location": loc, "setup": setup, "staging": staging,
                         "size": list(size), "source": str(f)})

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"\n  LoRA dataset : {out}   ({len(kept)} images, shot-only captions)")
    print(f"  story library: {story}  (same images, in-world captions)")
    print(f"  trigger      : {trigger}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
