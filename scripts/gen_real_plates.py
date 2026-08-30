#!/usr/bin/env python3
"""
Generate plates that actually have composition in them.

The staged library is one head-and-shoulders portrait per character per
location, filed under fifteen framing names -- full_body, three_quarter,
over_shoulder, walking_away are all the same image. Staging seeds from the
character portrait and asks the prompt to supply framing and place, but I2V
preserves its conditioning image, so the portrait comes back with minor
variation whatever the prompt says.

The only images in this project with genuine composition are the location
plates, and they were made with FLUX text-to-image. So make character plates
the same way: describe the place AND the framing to FLUX directly instead of
trying to transform a portrait into something it cannot become.

The trade is identity. A generated figure has no character reference, so
likeness will be weaker than a portrait seed. That is acceptable exactly where
composition matters and the face is small -- wides and two-shots -- and not
acceptable for close-ups, which already work from portraits and are left
alone.

Writes as gen__*.png alongside the existing plates. Nothing is overwritten.

    gen_real_plates.py <series>
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

# The first version gave FLUX the rendering technique and not the series'
# PALETTE, and the plates came back brighter, warmer and more saturated than
# the episodes -- prettier, and a different show. The look is not "cel-shaded";
# it is cel-shaded in a specific cold, desaturated, overcast register, and that
# has to be said or the model reaches for a sunnier default.
STYLE = ("Cel-shaded 2D animation, clean confident linework, flat blocks of "
         "colour with simple shading, painted background art, animated film "
         "still. Restrained desaturated palette of deep greens, slate blue-grey "
         "and cold stone. Overcast diffuse light, low contrast, muted, no warm "
         "sunlight, sombre and cool. No text, no lettering, no watermark")

OISIN = ("a young Celtic warrior with dark shoulder-length hair, a short "
         "trimmed beard, a brown leather jerkin and a dark green cloak")
NIAMH = ("a Celtic princess with long flowing golden hair and an emerald "
         "green gown")


STORM = ("high black sea cliffs under a storm sky, heavy grey cloud, spray "
         "breaking white against the rock far below, wind-flattened grass on "
         "the clifftop, cold and unwelcoming")
SEA = ("a heaving grey-green sea under low storm cloud, white water on the "
       "swell, no land in sight, cold flat light")

RUIN = ("a bleak grey Irish landscape under heavy overcast, a collapsed "
        "overgrown ring-fort of moss-covered stone, bare black thorn trees, "
        "cold flat diffuse daylight, grey-green and slate, no sunshine")
CLIFF = ("a high green headland above an endless calm sea at golden hour, "
         "one ancient wind-bent tree on the clifftop, long low shadows")
VALLEY = ("a lush Celtic valley of eternal summer, tall silver waterfalls "
          "spilling from green mountains, a still lake, wildflowers, warm light")

PLATES = [
    # (name, prompt) -- WIDES: the figure small, the place doing the work
    ("gen__ruin_wide_oisin", f"Extreme wide shot. {RUIN}. Far away in the "
     f"middle distance, small in the frame, {OISIN} stands alone among the "
     f"fallen stones, his whole body visible, no larger than a tenth of the "
     f"frame height. The landscape fills the picture."),
    ("gen__cliff_wide_niamh", f"Extreme wide shot. {CLIFF}. Far away near the "
     f"cliff edge, small in the frame, {NIAMH} stands beside the bent tree, "
     f"her whole body visible and no larger than a tenth of the frame height. "
     f"The landscape fills the picture."),
    ("gen__valley_wide_oisin", f"Extreme wide shot. {VALLEY}. Far off on the "
     f"path beside the lake, tiny in the frame, {OISIN} walks away from "
     f"camera, his whole body visible. The valley fills the picture."),

    # TWO-SHOTS: both figures, one frame, sharing ground and scale
    ("gen__ruin_twoshot", f"Wide two shot. {RUIN}. {OISIN} stands on the left "
     f"facing right, and {NIAMH} stands on the right facing left, several "
     f"paces apart on the same ground, both full-length and at the same scale, "
     f"the fallen stones between them. They are looking at each other."),
    ("gen__cliff_twoshot", f"Wide two shot. {CLIFF}. {OISIN} on the left and "
     f"{NIAMH} on the right, standing a few paces apart on the same clifftop, "
     f"both full-length and at the same scale, facing each other in profile, "
     f"the sea behind them."),
    ("gen__ruin_ots_oisin", f"Over-the-shoulder shot. {RUIN}. The camera is "
     f"behind and just past the shoulder of {NIAMH}, who is large and "
     f"out of focus at the left edge of frame seen from behind; beyond her, "
     f"facing camera and in focus, {OISIN} stands among the stones at "
     f"medium distance."),
    ("gen__cliff_wide_oisin", f"Extreme wide shot. {CLIFF}. Far away near the "
     f"cliff edge, small in the frame, {OISIN} stands alone looking out to sea, "
     f"his whole body visible and no larger than a tenth of the frame height."),
    ("gen__valley_wide_niamh", f"Extreme wide shot. {VALLEY}. Far off beside "
     f"the lake, small in the frame, {NIAMH} walks along the path, her whole "
     f"body visible. The valley fills the picture."),
    ("gen__ruin_wide_niamh", f"Extreme wide shot. {RUIN}. Far away among the "
     f"fallen stones, small in the frame, {NIAMH} stands alone, her whole body "
     f"visible and no larger than a tenth of the frame height."),
    ("gen__valley_twoshot", f"Wide two shot. {VALLEY}. {OISIN} on the left and "
     f"{NIAMH} on the right, standing a few paces apart on the same grass, both "
     f"full-length and at the same scale, facing each other, the waterfall "
     f"behind them."),
    ("gen__ruin_walking", f"Wide shot. {RUIN}. {OISIN} walks from left to right "
     f"across the open ground in front of the fallen stones, mid-stride, his "
     f"whole body visible, small in a wide landscape."),

    ("gen__storm_wide_oisin", f"Extreme wide shot. {STORM}. Far away near the "
     f"cliff edge, small in the frame and braced against the wind, {OISIN} "
     f"stands looking out, his whole body visible."),
    ("gen__storm_wide_niamh", f"Extreme wide shot. {STORM}. Far away on the "
     f"clifftop, small in the frame, {NIAMH} stands with her gown and hair "
     f"pulled sideways by the wind, her whole body visible."),
    ("gen__storm_twoshot", f"Wide two shot. {STORM}. {OISIN} on the left and "
     f"{NIAMH} on the right, a few paces apart on the same clifftop, both "
     f"full-length and at the same scale, facing each other in the wind."),
    ("gen__sea_wide", f"Extreme wide shot of {SEA}. Nothing in the frame but "
     f"water and sky. No figures, no boat, no land."),

]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    sr.set_current_series(a.series)
    out_dir = sr.series_path(a.series) / "sets" / "_generated"
    out_dir.mkdir(parents=True, exist_ok=True)

    made = []
    for i, (name, subject) in enumerate(PLATES):
        if a.only and a.only not in name:
            continue
        dst = out_dir / f"{name}.png"
        if dst.exists():
            print(f"  {name}: exists, skipping"); continue
        prompt = f"{subject}. {STYLE}"
        print(f"  {name} ...", flush=True)
        wf = sr.build_t2i_workflow(prompt, seed=6100 + i * 137, prefix=name,
                                   width=832, height=480)
        try:
            pid = sr.queue_prompt(wf)
            sr.poll_until_done(pid, max_wait=600)
        except Exception as e:                                 # noqa: BLE001
            print(f"    FAILED {type(e).__name__}: {e}"); continue
        hits = sorted((sr.COMFYUI_DIR / "output").rglob(f"{name}*.png"))
        if not hits:
            print("    no output"); continue
        dst.write_bytes(hits[-1].read_bytes())
        made.append(dst)
        print(f"    -> {dst}")

    print(f"\n  {len(made)} generated plate(s) in {out_dir}")
    print("  Look at them before anything is rendered from them: the question "
          "is\n  whether FLUX composes a figure in a landscape, not whether "
          "it draws a face.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
