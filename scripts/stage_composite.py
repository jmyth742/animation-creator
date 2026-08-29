#!/usr/bin/env python3
"""
Build a staging seed that carries the character AND the place.

Two directions have been tried and both fail in opposite ways:

  seed from the location plate   the place is right and the character never
                                 appears -- I2V preserves its conditioning
                                 image, so an empty ruin stays an empty ruin
  seed from the character        the character is right and the place is
                                 whatever the portrait's background was; the
                                 prompt's location cue does not override it

So every close-up in every episode is set somewhere that does not match the
wides around it. Measured on ep13: the wides are a grey ruin under low cloud,
the closes are a bright teal sea. Cut together they are two different scenes,
and no identity or framing score can see it because neither compares one shot
to another.

The fix is the one that already worked for the split panel: give the model a
seed that already contains both, and let it harmonise. Paste the character
region of the staged plate over the location plate with a feathered mask. The
result is a rough collage -- it is not meant to be looked at, it is meant to
be diffused from.

    stage_composite.py <series> <location> <character> [--setups master,reverse]
                       [--stagings close,medium]
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageFilter, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402


def composite_into(location: Path, character: Path, out: Path,
                   scale: float = 0.82, feather: int = 48) -> Path:
    """
    Character over location, soft-edged.

    The character plate is already framed the way the shot wants (close,
    medium); it is the BACKGROUND that is wrong. So keep the character's
    framing and replace what is behind it, feathering the join so the model
    is not handed a hard rectangle to preserve.
    """
    loc = Image.open(location).convert("RGB")
    ch = Image.open(character).convert("RGB").resize(loc.size, Image.LANCZOS)

    w, h = loc.size
    # An ellipse over the middle of the frame: that is where the figure is in
    # every staged plate, and a soft ellipse leaves the corners -- sky, stone,
    # horizon -- coming from the location.
    mask = Image.new("L", (w, h), 0)
    dr = ImageDraw.Draw(mask)
    cw, chh = int(w * scale), int(h * 1.02)
    dr.ellipse([(w - cw) // 2, int(h * 0.5 - chh / 2),
                (w + cw) // 2, int(h * 0.5 + chh / 2)], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(feather))

    out.parent.mkdir(parents=True, exist_ok=True)
    Image.composite(ch, loc, mask).save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("location")
    ap.add_argument("character")
    ap.add_argument("--setups", default="master,reverse")
    ap.add_argument("--stagings", default="close,medium,three_quarter")
    a = ap.parse_args()

    d = sr.series_path(a.series) / "sets" / a.location
    if not d.is_dir():
        sys.exit(f"no sets at {d}")
    made = []
    for setup in [s.strip() for s in a.setups.split(",") if s.strip()]:
        loc_plate = d / f"{setup}.png"
        if not loc_plate.exists():
            print(f"  {setup}: no bare plate, skipping"); continue
        for st in [s.strip() for s in a.stagings.split(",") if s.strip()]:
            src = d / f"{setup}__{a.character}_{st}.png"
            if not src.exists():
                print(f"  {src.name}: not staged, skipping"); continue
            out = d / f"{setup}__{a.character}_{st}__inplace.png"
            composite_into(loc_plate, src, out)
            made.append(out.name)
            print(f"  {out.name}")
    print(f"\n  {len(made)} in-place seed(s). These are collages, not plates —"
          f"\n  judge them by what renders from them, not by how they look.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
