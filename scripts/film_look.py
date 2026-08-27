#!/usr/bin/env python3
"""
The finishing layer: halation, grain, vignette.

What still says "rendered" rather than "photographed", after camera moves,
grading and matching are done:

  HALATION. Cel animation shot on film blooms around bright areas -- the
  emulsion scatters light, so a sunlit sky bleeds slightly into the ridge in
  front of it. Digital frames have perfectly hard highlight edges. This is the
  single strongest "shot on film" cue for animation, and the sunlit path and
  the valley are exactly the material for it.

  GRAIN. A tiny amount of moving grain unifies shots that were generated
  separately -- it sits on top of everything equally, so it partially masks the
  residual differences between takes and the softness that upscaling leaves.
  Clean digital black is the giveaway; film never had it.

  VIGNETTE. A slight fall-off at the edges. Barely visible on its own, but it
  puts the centre of the frame forward.

All three are deliberately underdone. The failure mode here is a film that
looks processed, which is worse than one that looks plain -- so the grain is
below the level most viewers consciously register, and the halation only lifts
highlights that are already bright.
"""
import argparse
import subprocess
import sys

# strength presets: subtle is the default for a reason
# Measured on a valley wide, single frame at t=2s:
#
#   original           mean 87.8   highlight area 14.84%   left edge 54.6
#   halation only      mean 90.6   highlight area 16.45%   edge 56.2   <- correct
#   grain only         mean 87.9   highlight area 14.89%   edge 54.6   <- correct
#   vignette PI/4.28   mean 61.7   highlight area  5.75%   edge 13.0   <- ruinous
#   vignette PI/9      mean 81.0   highlight area 10.17%   edge 42.5   <- still 8%
#
# Halation lifts highlights and spreads light, which is the point. Grain leaves
# exposure untouched, which is also the point. ffmpeg's vignette is brutal even
# at its weakest useful angle -- it took 8% off the whole image and 22% off the
# edges, and at the setting I first shipped it crushed the edges to near black.
# It is off by default; "film" uses a token amount and nothing more.
LOOKS = {
    "off":    dict(halation=0.0, grain=0.0, vignette=0.0),
    "subtle": dict(halation=0.16, grain=4.0, vignette=0.0),
    "film":   dict(halation=0.24, grain=6.0, vignette=0.03),
}


def look_filter(halation: float = 0.16, grain: float = 4.0,
                vignette: float = 0.12) -> str:
    """One filter_complex chain: halation, then grain, then vignette."""
    chain = []
    if halation > 0:
        # Isolate the top of the range, blur it wide, screen it back on.
        # lutrgb keeps only bright values; gblur spreads them; blend=screen
        # adds light without darkening anything.
        chain.append(
            f"split=2[base][hl];"
            f"[hl]lutrgb=r='if(gt(val,175),val,0)':g='if(gt(val,175),val,0)':"
            f"b='if(gt(val,175),val,0)',gblur=sigma=18[glow];"
            f"[base][glow]blend=all_mode=screen:all_opacity={halation:.3f}[lit]"
        )
        last = "[lit]"
    else:
        last = None
    post = []
    if grain > 0:
        # Temporal noise: it must MOVE, or it reads as dirt on the lens.
        post.append(f"noise=alls={int(grain)}:allf=t")
    if vignette > 0:
        # Denominator UP means weaker. PI/12 costs about 4% of mean luminance;
        # anything below PI/9 is a look, not a finish.
        post.append(f"vignette=PI/{12.0 + (0.1 - min(vignette, 0.1)) * 60:.2f}")
    post.append("format=yuv420p")
    tail = ",".join(post)
    if last:
        return f"{chain[0]};{last}{tail}[out]"
    return tail


def apply_look(src: str, out: str, preset: str = "subtle") -> str:
    p = LOOKS.get(preset, LOOKS["subtle"])
    f = look_filter(**p)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src]
    if "[out]" in f:
        cmd += ["-filter_complex", f, "-map", "[out]"]
    else:
        cmd += ["-vf", f]
    # Carry audio across untouched.
    cmd += ["-map", "0:a?", "-c:a", "copy", "-c:v", "libx264", "-crf", "16", out]
    subprocess.run(cmd, check=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--preset", default="subtle", choices=list(LOOKS))
    a = ap.parse_args()
    print(f"  {apply_look(a.src, a.out, a.preset)}  [{a.preset}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
