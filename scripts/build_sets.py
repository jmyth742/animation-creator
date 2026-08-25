#!/usr/bin/env python3
"""
Persistent sets: a background department for the pipeline.

THE PROBLEM
Every shot is an independent diffusion sample, so the geometry of a place is
re-invented each time. Two characters talking on one headland came back on two
separate sea stacks. A close-up of the same conversation came back in a modern
interior, because close-ups seed from a character portrait and the portrait
says nothing about where they are.

WHAT ACTUALLY WORKS ALREADY
Shots seeded from the SAME location plate agree with each other -- ep04 s01 and
s02 share a cliff, a wind-bent tree and a horizon line because both started
from loc_farewell_cliff.png. The plate is already a persistent set. It is just
one camera position, and close-ups never use it.

WHAT THIS ADDS
Real animation keeps a background painting per camera setup and reuses it for
every shot from that angle, across episodes. This builds the same thing:

    sets/<location>/master.png          the established view (the existing plate)
    sets/<location>/<setup>.png         other angles OF THE SAME PLACE
    sets/<location>/<setup>__<char>.png that angle with a character standing in it

Each setup is DERIVED from the master by animating a camera move and taking the
final frame, so the new angle inherits the master's geometry, palette and light
instead of inventing its own. Character plates are derived from a setup the same
way, so a close-up can be seeded with something that carries BOTH the face and
the room.

    python scripts/build_sets.py setups <series> <location>
    python scripts/build_sets.py setups <series> --all
    python scripts/build_sets.py stage  <series> <location> <character>
    python scripts/build_sets.py list   <series>

Generated once, reused by every episode. Regenerate only when the style changes.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

SETS_DIRNAME = "sets"

# Camera setups. Each is a move AWAY from the established view, phrased as
# motion because that is what I2V understands -- the last frame of the move is
# the new angle. Kept deliberately small: a location with fifteen setups is a
# location with fifteen chances to drift.
SETUPS = [
    ("reverse",     "the camera slowly orbits around to look back the other way, "
                    "revealing the view in the opposite direction, same place, "
                    "same light, same time of day"),
    ("wider",       "the camera pulls back and up, revealing more of the "
                    "surrounding landscape, same place, same light"),
    ("closer",      "the camera pushes slowly forward into the middle of the "
                    "scene, same place, same light"),
    ("side",        "the camera tracks steadily sideways to a new vantage point "
                    "on the same ground, same place, same light"),
]

# Where the character sits in frame, and at what distance.
#
# This list does two jobs: it gives an episode real coverage options, and it is
# the variety source for the character LoRA -- the job the previous dataset
# failed at. That one animated ONE portrait and captioned the harvested frames
# by INTENDED shot; WAN barely moved the subject, so a frame captioned "wide
# shot, full body" was the same head-and-shoulders portrait as one captioned
# "extreme close-up". The LoRA learned that framing words mean nothing and
# bound the character to a single composition.
#
# These are generated FROM A SET PLATE instead, so the distance is real: a
# full-body staging genuinely puts the figure small in a wide landscape frame,
# at 832x480, which is the shape episodes actually render.
STAGINGS = [
    ("full_body",     "Full body shot, the figure stands full length in the middle distance, the whole "
                      "figure visible head to foot, small in a wide landscape"),
    ("medium",        "Medium shot, the figure is seen from the waist up, turned slightly away, the "
                      "location open behind them"),
    ("close",         "Close-up, head and shoulders filling one side of "
                      "the frame, the location clearly visible behind them"),
    ("ecu",           "Extreme close-up on the face, the eyes and mouth filling "
                      "most of the frame"),
    ("three_quarter", "Three-quarter angle view, the figure seen from the front, upper "
                      "body visible, head turned across the frame"),
    ("over_shoulder", "Over-the-shoulder shot from behind and to one side, over their shoulder, "
                      "looking out across the location"),
    ("low_angle",     "Low angle shot from below against the sky, the figure large in "
                      "the frame"),
    ("walking_away",  "Full body from behind, walking away from the camera into the middle distance, "
                      "the whole figure visible from behind"),
]

FRAMES = 17            # we keep ONE frame, so a longer clip is wasted GPU.
                       # At 33 frames a plate took ~2.5 min, making a
                       # 64-plate library 2.7 hours before training starts.
STEPS = 8              # Lightning


def sets_dir(series: str) -> Path:
    return sr.series_path(series) / SETS_DIRNAME


def _render_last_frame(prompt: str, seed_png: Path, out: Path, prefix: str,
                       neg: str, take: str = "last") -> bool:
    """Animate a move from seed_png and keep one frame of it."""
    res = sr.get_resolution_config("480p", "wan")
    seed_image = sr.copy_to_input(str(seed_png))
    wf = sr.build_video_workflow(
        "wan", "i2v", prompt, seed=7777, clip_prefix=prefix,
        frames=FRAMES, res_config=res, negative_prompt=neg,
        steps=STEPS, image_name=seed_image, optimization="fast",
        loras=list(sr.LIGHTNING["i2v"]),
    )
    sr.apply_lightning(wf, steps=STEPS)
    pid = sr.queue_prompt(wf)
    if not sr.poll_until_done(pid):
        print("      generation failed")
        return False
    clip = sr.find_latest_clip(prefix)
    if not clip:
        print("      no clip produced")
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    if take == "last":
        ok = sr.extract_last_frame(clip, str(out))
    else:
        dur = sr._get_video_duration(clip) or 2.0
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{dur/2:.2f}",
                            "-i", clip, "-frames:v", "1", str(out)])
        ok = r.returncode == 0 and out.exists()
    return bool(ok)


def cmd_setups(args):
    series = args.series
    bible = sr.load_json(sr.series_path(series) / "bible.json")
    style = bible["series"].get("style", "").split(".")[0].strip()
    ref_dir = sr.series_path(series) / "reference_images"
    locations = bible.get("world", {}).get("locations", {})

    targets = list(locations) if args.all else [args.location]
    if not args.all and args.location not in locations:
        sys.exit(f"unknown location '{args.location}'. "
                 f"Known: {', '.join(locations)}")

    neg = ("people, characters, faces, figures, blurry, distorted, watermark, "
           "text, photorealistic, live action, photograph, 3d render, cgi, "
           "different place, new location")

    for loc in targets:
        master_src = sr._find_ref(ref_dir, loc, "loc")
        if not master_src:
            print(f"  {loc}: no plate on disk — run gen-refs first")
            continue
        d = sets_dir(series) / loc
        d.mkdir(parents=True, exist_ok=True)
        master = d / "master.png"
        if not master.exists() or args.force:
            shutil.copy2(master_src, master)
            print(f"  {loc}/master.png  <- {master_src.name}")

        desc = str(locations.get(loc, "")).split(".")[0].strip()
        for slug, move in SETUPS:
            out = d / f"{slug}.png"
            if out.exists() and not args.force:
                print(f"  {loc}/{slug}.png — exists, skipping")
                continue
            # The description anchors WHAT the place is; the move says where the
            # camera goes. Style last: this is a background, and leading with a
            # palette tints whatever follows it.
            prompt = f"{desc}. {move}. {style}"
            print(f"  {loc}/{slug} ...", flush=True)
            if _render_last_frame(prompt, master, out, f"set_{loc}_{slug}", neg):
                print(f"      saved {out.name}")


def cmd_stage(args):
    """Put a character INTO a location, seeded from the character.

    The first version of this seeded from the location plate and asked I2V to
    add a person. It does not work: I2V preserves its conditioning image, and
    an empty landscape stays an empty landscape. Measured on the first pass --
    'close' and 'ecu' plates came back with no character in them at all, and
    'full_body' put a barely visible figure on a cliff.

    That failure is the same one already measured in the episode itself: shots
    seeded from a location plate scored 0.645 on identity because nothing in
    the plate says what the character looks like, while shots seeded from the
    character's portrait scored 0.905. So seed from the PORTRAIT -- which is
    the strong direction -- and let the prompt carry the location and framing.
    """
    series = args.series
    bible = sr.load_json(sr.series_path(series) / "bible.json")
    style = bible["series"].get("style", "").split(".")[0].strip()
    char = bible.get("characters", {}).get(args.character)
    if not char:
        sys.exit(f"unknown character '{args.character}'")
    appearance = (char.get("visual") or "").split(".")[0].strip()
    trigger = char.get("trigger_word") or args.character.capitalize()

    locations = bible.get("world", {}).get("locations", {})
    loc_desc = str(locations.get(args.location, "")).split(".")[0].strip()

    d = sets_dir(series) / args.location
    if not d.exists():
        sys.exit(f"no sets for '{args.location}'. Run: build_sets.py setups "
                 f"{series} {args.location}")

    ref_dir = sr.series_path(series) / "reference_images"
    portrait = sr._find_ref(ref_dir, args.character, "char")
    if not portrait:
        sys.exit(f"no canonical portrait for {args.character}")

    plates = [pl for pl in sorted(d.glob("*.png")) if "__" not in pl.name]
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        plates = [pl for pl in plates if pl.stem in wanted]
        if not plates:
            sys.exit(f"no setups matching {sorted(wanted)} in {d}")

    neg = ("blurry, distorted face, deformed, extra fingers, watermark, text, "
           "multiple people, photorealistic, live action, photograph, "
           "3d render, cgi, indoor, interior, studio backdrop, plain background")

    want_staging = ({x.strip() for x in args.staging.split(",")}
                    if args.staging else None)

    for plate in plates:
        for slug, placement in STAGINGS:
            if want_staging and slug not in want_staging:
                continue
            out = d / f"{plate.stem}__{args.character}_{slug}.png"
            if out.exists() and not args.force:
                print(f"  {out.name} — exists, skipping")
                continue
            # Screen direction comes from the SETUP. Seeding from the portrait
            # means the setup plate itself no longer conditions the image, so
            # without this every setup would render an identical prompt and
            # burn GPU on duplicates. Direction is also the thing the setup is
            # FOR: master and reverse are the two sides of the 180-degree line,
            # so a conversation cut between them keeps consistent eyelines.
            facing = {
                "master":  "facing to the right of frame",
                "reverse": "facing to the left of frame",
                "closer":  "facing the camera",
                "wider":   "facing to the right of frame",
                "side":    "seen side on",
            }.get(plate.stem, "facing across the frame")
            # Framing first (it is what must change from the portrait), then
            # the character, then the place. Style last so its palette clause
            # tints the picture rather than the person.
            prompt = (f"{placement.capitalize()}, {facing}. {trigger}. "
                      f"{appearance}. {loc_desc} behind them. {style}")
            print(f"  {out.name} ...", flush=True)
            if _render_last_frame(prompt, portrait, out,
                                  f"stage_{args.location}_{plate.stem}_{args.character}_{slug}",
                                  neg, take="middle"):
                print(f"      saved {out.name}")


def cmd_check(args):
    """Find location plates with a person hallucinated into them.

    A setup plate is meant to be an empty background. It is derived by animating
    the master and keeping a frame, and the video model sometimes puts a figure
    in -- measured once at 7 of 30 plates, including a man in modern glasses on
    an Irish sea cliff. A contaminated plate seeds a shot with a stranger in it,
    and nothing downstream would flag that.

    Threshold is 0.75, not 0.5, because the classifier was checked by eye: 0.99
    and 0.98 were real people, 0.61 was a clean stormy sea. Trust it only when
    it is confident.
    """
    import shutil
    import verify_render as vr
    from PIL import Image
    root = sets_dir(args.series)
    if not root.is_dir():
        sys.exit(f"no set library at {root}")
    if vr._clip() is None:
        sys.exit("CLIP unavailable — cannot check plates")
    tv = vr._embed_texts(["an empty landscape with no people in it",
                          "a person standing in the frame, a human figure with a face"])
    q = Path("/workspace/review/contaminated_plates")
    flagged = []
    for loc in sorted(d for d in root.iterdir() if d.is_dir()):
        for f in sorted(loc.glob("*.png")):
            if "__" in f.name or f.name.startswith("tvar__"):
                continue                      # these are meant to have people
            with Image.open(f) as im:
                fv = vr._embed_images([im.convert("RGB").copy()])
            score = float(((fv @ tv.T)[0] * 100).softmax(dim=-1)[1])
            mark = ""
            if score > args.threshold:
                flagged.append((f, score))
                mark = "  <-- person in an empty-background plate"
                if args.quarantine:
                    d = q / loc.name
                    d.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(f), str(d / f.name))
                    mark += " (quarantined)"
            print(f"  {loc.name + '/' + f.stem:34} {score:6.3f}{mark}")
    print(f"\n  {len(flagged)} contaminated plate(s)"
          f"{' — moved to ' + str(q) if args.quarantine and flagged else ''}")
    return 1 if flagged and not args.quarantine else 0


def cmd_list(args):
    d = sets_dir(args.series)
    if not d.exists():
        print(f"  no sets built yet ({d})")
        return
    total = 0
    for loc in sorted(p for p in d.iterdir() if p.is_dir()):
        plates = sorted(loc.glob("*.png"))
        setups = [p for p in plates if "__" not in p.name]
        staged = [p for p in plates if "__" in p.name]
        total += len(plates)
        print(f"  {loc.name}: {len(setups)} setup(s), {len(staged)} staged")
        for p in setups:
            print(f"      {p.stem}")
        for p in staged:
            print(f"      {p.stem}   (staged)")
    print(f"\n  {total} plate(s) total in {d}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("setups", help="derive camera setups from each location plate")
    p.add_argument("series"); p.add_argument("location", nargs="?")
    p.add_argument("--all", action="store_true")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_setups)

    p = sub.add_parser("stage", help="place a character into a location's setups")
    p.add_argument("series"); p.add_argument("location"); p.add_argument("character")
    p.add_argument("--only", default=None,
                   help="comma-separated setups to stage on (default: all). "
                        "Staging every setup x every placement is 15 plates per "
                        "character per location; a two-hander needs 2.")
    p.add_argument("--staging", default=None,
                   help="comma-separated placements (default: left,right,close)")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_stage)

    p = sub.add_parser("check", help="find plates with a person hallucinated in")
    p.add_argument("series")
    p.add_argument("--threshold", type=float, default=0.75)
    p.add_argument("--quarantine", action="store_true",
                   help="move contaminated plates out of the library")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("list", help="show what the set library holds")
    p.add_argument("series")
    p.set_defaults(fn=cmd_list)

    a = ap.parse_args()
    if a.cmd == "setups" and not a.all and not a.location:
        ap.error("give a location or --all")
    sr.set_current_series(a.series)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
