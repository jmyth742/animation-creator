#!/usr/bin/env python3
"""
Keep every character training brief in step with the series bible.

build_character_dataset.py builds its training clips with
    prompt = brief["style"] + brief["appearance"] + motion
so the brief's style string decides what the LoRA learns to look like. When the
series style changes and the briefs do not, the next LoRA is trained in the OLD
style -- and it does not fail, it just quietly drags every shot back. That is
exactly the defect that made Oisin render photoreal in a cel-shaded episode.

    python scripts/sync_character_briefs.py <series>            # apply
    python scripts/sync_character_briefs.py <series> --check    # exit 1 on drift

--check is the job gate: it refuses to start a two-hour training run on a brief
that would teach the wrong style.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

BUILD_ROOT = Path("/workspace/text-to-video/training/character_builds")

# Suppress genuine defects, and push toward the style rather than away from it.
# Never list the series' own medium here -- a brief that fights its own style
# produces training frames in neither.
BASE_NEGATIVE = (
    "blurry, distorted face, deformed, asymmetric eyes, extra fingers, "
    "watermark, text, multiple people, changing face, morphing, "
    "photorealistic, live action, photograph, 3d render, cgi"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit non-zero instead of fixing it")
    a = ap.parse_args()

    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    style = bible["series"].get("style", "").strip()
    if not style:
        sys.exit("series bible has no style")

    chars = bible.get("characters", {})
    drift, synced, missing = [], [], []

    for key, char in chars.items():
        brief_path = BUILD_ROOT / key / "brief.json"
        if not brief_path.exists():
            missing.append(key)
            continue
        brief = json.loads(brief_path.read_text())
        want_appearance = (char.get("visual") or brief.get("appearance", "")).strip()

        changes = []
        if brief.get("style", "").strip() != style:
            changes.append("style")
        if want_appearance and brief.get("appearance", "").strip() != want_appearance:
            changes.append("appearance")
        if brief.get("negative", "").strip() != BASE_NEGATIVE:
            changes.append("negative")

        if not changes:
            print(f"  {key}: in step")
            continue

        drift.append(f"{key} ({', '.join(changes)})")
        if a.check:
            print(f"  {key}: DRIFT in {', '.join(changes)}")
            print(f"      brief style : {brief.get('style','')[:80]}")
            print(f"      bible style : {style[:80]}")
            continue

        brief["style"] = style
        if want_appearance:
            brief["appearance"] = want_appearance
        brief["negative"] = BASE_NEGATIVE
        brief_path.write_text(json.dumps(brief, indent=2) + "\n")
        synced.append(key)
        print(f"  {key}: synced ({', '.join(changes)})")

    if missing:
        print(f"\n  no brief on disk for: {', '.join(missing)} "
              f"(expected under {BUILD_ROOT})")

    if a.check and drift:
        print(f"\n  {len(drift)} brief(s) would train the WRONG style: "
              f"{'; '.join(drift)}")
        print("  fix with: python scripts/sync_character_briefs.py "
              f"{a.series}")
        return 1
    if synced:
        print(f"\n  synced {len(synced)} brief(s) to the current series style")
    return 0


if __name__ == "__main__":
    sys.exit(main())
