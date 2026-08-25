#!/usr/bin/env python3
"""
Generate genuine framing variety for a character LoRA, using FLUX T2I.

WHY T2I AND NOT I2V
Both I2V directions failed to produce framing variety, for the same reason:
I2V preserves whatever its conditioning image contains, framing included.

  seeded from the location plate -> good framing, NO CHARACTER. Close-up and
      ECU plates came back as empty cliffs.
  seeded from the character portrait -> excellent identity, NO FRAMING VARIETY.
      24 plates labelled as eight framings measured 0.940 mean pairwise
      similarity: effectively one head-and-shoulders picture, which is the
      regime that trained a LoRA that did nothing.

T2I generates from text, so distance and angle are actually controllable -- it
is how the series anchors were made. The cost is that identity is weaker with
no image to condition on. That is what curation is for: generate generously,
then keep only what scores close to the canonical portrait.

    build_framing_variety.py <series> <character> --per-framing 6
    build_framing_variety.py <series> <character> --dry-run     # print prompts

Output goes to sets/<location>/tvar__<character>_<framing>_<n>.png so
curate_character_dataset.py picks it up alongside the staged plates.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

# Distance and angle, phrased as a camera would frame it. These are the axis
# the staged plates could not vary, so they carry the weight here.
FRAMINGS = [
    ("full_body",     "full body shot, the entire figure from head to feet "
                      "visible, standing small in a wide landscape, lots of "
                      "empty space above and around"),
    ("wide_figure",   "wide shot, the figure small in the frame and seen at a "
                      "distance across open ground"),
    ("three_quarter_body", "three-quarter length shot from the knees up, the "
                           "figure turned slightly away from camera"),
    ("medium",        "medium shot from the waist up, arms visible"),
    ("close",         "close-up, head and shoulders"),
    ("ecu",           "extreme close-up on the eyes and mouth, face filling "
                      "the frame"),
    ("profile",       "strict side profile, the head seen exactly from the "
                      "side against the sky"),
    ("back",          "seen from directly behind, the back of the head and "
                      "shoulders, looking away from camera"),
    ("low_angle",     "low angle shot looking steeply up at the figure from "
                      "below, sky behind"),
    ("high_angle",    "high angle shot looking down at the figure from above"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("character")
    ap.add_argument("--location", default=None,
                    help="write into sets/<location>/ (default: first location "
                         "that already has a set directory)")
    ap.add_argument("--per-framing", type=int, default=6)
    ap.add_argument("--width", type=int, default=832)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    char = bible.get("characters", {}).get(a.character)
    if not char:
        sys.exit(f"unknown character '{a.character}'")
    # The FULL appearance, not the first clause: with no seed image this text is
    # the only thing carrying identity, so every distinguishing detail matters.
    appearance = (char.get("visual") or "").strip().rstrip(".")
    style = bible["series"].get("style", "").split(".")[0].strip()
    locations = bible.get("world", {}).get("locations", {})

    sets_root = sr.series_path(a.series) / "sets"
    if a.location:
        loc = a.location
    else:
        existing = [d.name for d in sorted(sets_root.glob("*")) if d.is_dir()]
        if not existing:
            sys.exit("no set directories yet — run build_sets.py setups first")
        loc = existing[0]
    out_dir = sets_root / loc
    out_dir.mkdir(parents=True, exist_ok=True)
    loc_desc = str(locations.get(loc, "")).split(".")[0].strip()

    print(f"  character : {a.character}")
    print(f"  location  : {loc}")
    print(f"  size      : {a.width}x{a.height}  (matches episode renders)")
    print(f"  framings  : {len(FRAMINGS)} x {a.per_framing} = "
          f"{len(FRAMINGS) * a.per_framing} candidates\n")

    made = 0
    for slug, framing in FRAMINGS:
        for n in range(1, a.per_framing + 1):
            out = out_dir / f"tvar__{a.character}_{slug}_{n:02d}.png"
            if out.exists() and not a.force:
                continue
            # Framing FIRST: it is the axis that must actually change, and the
            # earliest tokens carry the most weight. Style last so its palette
            # clause tints the picture rather than the person -- a palette
            # clause immediately before a character name once rendered him as
            # a green ogre.
            prompt = (f"{framing}. {appearance}. Standing at {loc_desc}. {style}")
            if a.dry_run:
                if n == 1:
                    print(f"  [{slug}]\n    {prompt[:150]}...")
                continue
            prefix = f"tvar_{a.character}_{slug}_{n:02d}"
            wf = sr.build_t2i_workflow(prompt, seed=9000 + made * 137,
                                       prefix=prefix, width=a.width,
                                       height=a.height)
            try:
                pid = sr.queue_prompt(wf)
                sr.poll_until_done(pid)
            except Exception as e:                             # noqa: BLE001
                print(f"  {out.name}: FAILED {type(e).__name__}: {e}")
                continue
            src = sr.COMFYUI_DIR / "output" / "refs"
            hits = sorted(src.glob(f"{prefix}*.png"))
            if not hits:
                hits = sorted((sr.COMFYUI_DIR / "output").rglob(f"{prefix}*.png"))
            if hits:
                out.write_bytes(hits[-1].read_bytes())
                made += 1
                print(f"  {out.name}", flush=True)
            else:
                print(f"  {out.name}: no output found")

    if a.dry_run:
        print("\n  dry run — nothing generated")
        return 0
    print(f"\n  {made} candidate(s) written to {out_dir}")
    print(f"  next: curate_character_dataset.py {a.series} {a.character} "
          f"--trigger <rare-token>")
    print(f"  curation scores each against the canonical portrait and reports "
          f"how different\n  the survivors are from EACH OTHER — that second "
          f"number is the one that failed before.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
