"""
Bridge LAM Audio2Expression ARKit-52 curves (30 fps JSON) onto the film's
per-line texture-viseme arrays (16 fps): writes l<i>_vis_lam.npy (column
0..5 of the 6-way mouth switch), l<i>_env_lam.npy (jaw drive from jawOpen)
and l<i>_blink_lam.npy, plus a curves sheet PNG per line (PIL only).
Usage: arkit_bridge.py <audio_dir> <bsData_dir> [fps=16]
  bsData_dir holds l<i>.json as written by LAM's export_blendshape_animation.
Column semantics follow rhubarb_visemes.MAP: 0 closed, 1 small, 2 mid,
3 open, 4 wide, 5 round (pucker/funnel).
"""
import json, sys, pathlib
import numpy as np
from PIL import Image, ImageDraw

audio_dir, bs_dir = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
FPS = int(sys.argv[3]) if len(sys.argv) > 3 else 16
lines = json.load(open(audio_dir / "lines.json"))

def load_curves(p):
    d = json.load(open(p))
    names = d.get("names") or d.get("metadata", {}).get("blendshape_names")
    fps = float(d.get("metadata", {}).get("fps", 30.0))
    W = np.array([f["weights"] for f in d["frames"]], dtype=np.float32)   # [T, 52]
    return names, fps, W

def col(name, names, W):
    return W[:, names.index(name)] if name in names else np.zeros(len(W), np.float32)

for L in lines:
    i, n_frames = L["i"], L["frames"]
    p = bs_dir / f"l{i}.json"
    if not p.exists():
        print(f"l{i}: no curves ({p})"); continue
    names, sfps, W = load_curves(p)
    # resample 30 fps -> film fps by nearest source frame
    t = np.arange(n_frames) / FPS
    idx = np.clip(np.round(t * sfps).astype(int), 0, len(W) - 1)
    # LAM voices mouth opening mostly through mouthLowerDown (peaks ~0.8) and
    # only weakly through jawOpen (peaks ~0.35): normalise each per line by
    # its 95th percentile so thresholds mean "fraction of this line's range".
    jaw_raw = col("jawOpen", names, W); low_raw = np.maximum(col("mouthLowerDownLeft", names, W), col("mouthLowerDownRight", names, W))
    jawn = jaw_raw / max(np.percentile(jaw_raw, 95), 0.12)
    lown = low_raw / max(np.percentile(low_raw, 95), 0.25)
    jaw = jawn[idx]
    rnd = np.maximum(col("mouthFunnel", names, W), col("mouthPucker", names, W))[idx]
    blink = np.maximum(col("eyeBlinkLeft", names, W), col("eyeBlinkRight", names, W))[idx]
    smile = np.maximum(col("mouthSmileLeft", names, W), col("mouthSmileRight", names, W))[idx]
    opening = np.clip(0.55 * jawn[idx] + 0.45 * lown[idx], 0, 1.2)
    vis = np.zeros(n_frames, np.int64)
    vis[opening >= 0.18] = 1
    vis[opening >= 0.36] = 2
    vis[opening >= 0.58] = 3
    vis[opening >= 0.85] = 4
    vis[(rnd > 0.25) & (opening >= 0.18)] = 5
    env = np.clip(opening, 0, 1).astype(np.float32)
    np.save(audio_dir / f"l{i}_vis_lam.npy", vis)
    np.save(audio_dir / f"l{i}_env_lam.npy", env)
    np.save(audio_dir / f"l{i}_blink_lam.npy", (blink > 0.5).astype(np.int64))
    old = audio_dir / f"l{i}_vis.npy"
    agree = ""
    if old.exists():
        ov = np.load(old)[:n_frames]
        agree = f" rhubarb-open-agreement {np.mean((ov > 0) == (vis > 0)):.2f}"
    print(f"l{i} {L['who']}: {n_frames}f src {len(W)}@{sfps:.0f}fps  open {np.mean(vis > 0):.2f}"
          f" round {np.mean(vis == 5):.2f} blinks {int(np.sum(np.diff((blink > 0.5).astype(int)) == 1))}{agree}")
    # curves sheet: jawOpen, round, smile, blink over time + the chosen column
    Wd, Hd = 1500, 260   # fixed width so per-line sheets stack
    im = Image.new("RGB", (Wd, Hd), (250, 248, 244)); dr = ImageDraw.Draw(im)
    def plot(y, color, row):
        pts = [(int(k * (Wd - 20) / max(1, n_frames - 1)) + 10, int(row - y[k] * 60)) for k in range(n_frames)]
        dr.line(pts, fill=color, width=2)
    for k in range(n_frames):
        x = int(k * (Wd - 20) / max(1, n_frames - 1)) + 10
        dr.line([(x, 250), (x, 250 - vis[k] * 10)], fill=(90, 90, 90), width=3)
    plot(np.clip(opening, 0, 1), (200, 60, 40), 70); plot(rnd, (40, 120, 200), 140); plot(smile, (40, 160, 80), 140); plot(blink, (120, 40, 160), 200)
    dr.text((10, 2), f"l{i} {L['who']}  red=opening(jaw+lowerDown, normalised)  blue=round  green=smile  purple=blink  bars=viseme column", fill=(30, 30, 30))
    im.save(bs_dir / f"l{i}_curves.png")
print("BRIDGE DONE")
