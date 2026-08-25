#!/usr/bin/env python3
"""
Score lip articulation objectively so a variant can be chosen unattended.

All variants speak the same line from the same seed, so the mouth region should
differ between them only in how much it actually moves. Motion energy in that
region is a usable proxy: sample frames, crop to the lower face, scale every
crop to the same size (so a tighter shot is not rewarded merely for having more
pixels), and measure mean absolute difference between consecutive crops.

It is a proxy, not a verdict -- the mouth strips are written alongside for a
human to confirm. Prints a ranking and writes winner.json.
"""
import json, subprocess, sys, tempfile
from pathlib import Path

IN = Path("/workspace/review/lipsync")


def energy(clip: Path, samples: int = 24) -> float:
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(clip)],
        capture_output=True, text=True).stdout.strip() or 0)
    if dur <= 0:
        return 0.0
    tmp = Path(tempfile.mkdtemp())
    # same relative crop, same output size for every variant
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip),
                    "-vf", f"fps={samples/dur:.3f},crop=iw*0.45:ih*0.28:iw*0.275:ih*0.46,"
                           f"scale=96:64,format=gray",
                    str(tmp / "f_%03d.png")], timeout=120)
    frames = sorted(tmp.glob("*.png"))
    if len(frames) < 3:
        return 0.0
    try:
        from PIL import Image
        import statistics
        arrs = []
        for f in frames:
            with Image.open(f) as im:
                arrs.append(list(im.getdata()))
        diffs = []
        for a, b in zip(arrs, arrs[1:]):
            diffs.append(sum(abs(x - y) for x, y in zip(a, b)) / len(a))
        return statistics.mean(diffs)
    finally:
        for f in frames:
            f.unlink(missing_ok=True)
        tmp.rmdir()


def main():
    clips = sorted(IN.glob("*_[A-D]_*.mp4"))
    if not clips:
        print("  no lipsync clips found"); return 1
    scored = []
    for c in clips:
        e = energy(c)
        label = c.stem.split("_", 1)[1]
        scored.append((label, e, c.name))
        print(f"  {label:14} mouth motion {e:6.2f}   {c.name}")
    scored.sort(key=lambda x: -x[1])
    best = scored[0]
    print(f"\n  highest articulation: {best[0]}  ({best[1]:.2f})")
    steps = 40 if "40" in best[0] else 25
    tight = "tight" in best[0]
    (IN / "winner.json").write_text(json.dumps(
        {"variant": best[0], "score": round(best[1], 3), "steps": steps, "tight": tight,
         "ranking": [{"variant": l, "score": round(e, 3)} for l, e, _ in scored]}, indent=2))
    print(f"  -> steps={steps} tight_framing={tight}")
    print("  (proxy metric — confirm against the *_MOUTH.png strips)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
