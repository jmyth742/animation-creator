#!/usr/bin/env python3
"""
Is the series one show? Measured, per episode, on axes a binge viewer feels.

    cel score      mean CLIP cel-vs-photoreal across sampled frames
    brightness/sat mean luma and saturation -- the grade drifting between
                   episodes is the thing that reads as "different show"
    shot lengths   mean and spread -- the edit's rhythm
    loudness       integrated LUFS (should all sit at -14 now)

Output is one row per episode plus the outlier call-outs.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import verify_render as vr                                     # noqa: E402

SERIES = "tir-na-nog-legend"


def sample_frames(video, n=6):
    d = sr._get_video_duration(video)
    out = []
    with tempfile.TemporaryDirectory() as td:
        for i in range(n):
            t = d * (i + 0.5) / n
            f = f"{td}/f{i}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}",
                            "-i", str(video), "-frames:v", "1", "-vf",
                            "scale=384:-1", f], check=False)
            if Path(f).exists():
                out.append(Image.open(f).convert("RGB").copy())
    return out


def main():
    sr.set_current_series(SERIES)
    sv = vr._embed_texts(vr._STYLE_OPTIONS)
    rows = []
    for e in range(5, 18):
        f = Path("output") / SERIES / f"ep{e:02d}" / f"ep{e:02d}_final.mp4"
        if not f.exists():
            continue
        frames = sample_frames(f)
        if not frames:
            continue
        fv = vr._embed_images(frames)
        cel = float(((fv @ sv.T).mean(dim=0) * 100).softmax(dim=-1)[0])
        arrs = [np.asarray(im, dtype=np.float32) for im in frames]
        luma = float(np.mean([a.mean() for a in arrs]))
        sat = float(np.mean([(a.max(axis=2) - a.min(axis=2)).mean()
                             for a in arrs]))
        ep = sr.load_json(sr.episode_path(SERIES, e))
        holds = [float(s.get("hold_seconds") or 6) for s in ep["scenes"]]
        r = subprocess.run(["ffmpeg", "-i", str(f), "-af",
                            "loudnorm=print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True)
        t = r.stderr
        li = t.rfind("{")
        lufs = float(json.loads(t[li:]).get("input_i", 0)) if li >= 0 else None
        rows.append({"ep": e, "cel": round(cel, 3), "luma": round(luma, 1),
                     "sat": round(sat, 1),
                     "hold_mean": round(sum(holds) / len(holds), 1),
                     "lufs": round(lufs, 1) if lufs else None})
        print(f"  ep{e:02d}  cel {cel:5.3f}  luma {luma:5.1f}  sat {sat:5.1f}"
              f"  hold {sum(holds)/len(holds):4.1f}s  {lufs:6.1f} LUFS",
              flush=True)
    if len(rows) > 2:
        for k, label, tol in (("cel", "cel score", 0.05), ("luma", "brightness", 18),
                              ("sat", "saturation", 14), ("lufs", "loudness", 1.5)):
            vals = [r[k] for r in rows if r[k] is not None]
            m = sum(vals) / len(vals)
            outl = [f"ep{r['ep']:02d}" for r in rows
                    if r[k] is not None and abs(r[k] - m) > tol]
            print(f"  {label:11} mean {m:7.2f}   outliers: {outl or 'none'}")
    Path("/workspace/review/consistency.json").write_text(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
