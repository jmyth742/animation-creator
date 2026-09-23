"""
Score generated character meshes by how mitten-like the hands are, so the overnight
cast build can pick a seed without a person looking.

Hand = the far 18 per cent of the arm cloud (geometry lateral to the torso). A mitten is a
compact blob: its spread perpendicular to the arm axis is about the arm's own thickness.
Splayed fingers fan out to two or three times that. Score = spread / arm thickness,
lower is better. Prints one line per mesh and BEST <who> <basename>.

  python pick_hands.py <props_dir> '<glob>'
"""
import sys, glob, os
import numpy as np
import trimesh

P, pat = sys.argv[1], sys.argv[2]
best = {}
for f in sorted(glob.glob(os.path.join(P, pat))):
    try:
        m = trimesh.load(f, force='mesh')
    except Exception as e:                                          # noqa: BLE001
        print("skip", os.path.basename(f), e); continue
    V = np.asarray(m.vertices, dtype=float)
    V = V - V.min(axis=0); H = V[:, 2].max() if V[:, 2].max() > 0 else 1.0
    V = V / H
    # torso half width at mid-height, then the arm cloud on the +x side
    mid = (np.abs(V[:, 2] - 0.55) < 0.03)
    w = np.percentile(np.abs(V[mid, 0] - np.median(V[:, 0])), 60) if mid.sum() > 20 else 0.12
    cx = np.median(V[:, 0])
    arm = V[(V[:, 0] - cx > 1.25 * w) & (V[:, 2] > 0.25) & (V[:, 2] < 0.75)]
    if len(arm) < 80:
        print("%-40s no arm cloud" % os.path.basename(f)); continue
    c = arm.mean(axis=0); u = np.linalg.svd(arm - c, full_matrices=False)[2][0]
    if u @ (arm.mean(axis=0) - np.array([cx, c[1], c[2]])) < 0: u = -u
    t = (arm - c) @ u
    hand = arm[t > np.percentile(t, 82)]
    shaft = arm[(t > np.percentile(t, 30)) & (t < np.percentile(t, 60))]
    def spread(A):
        d = A - A.mean(axis=0); d = d - np.outer(d @ u, u)
        return float(np.percentile(np.linalg.norm(d, axis=1), 90))
    score = spread(hand) / max(1e-6, spread(shaft))
    who = "niamh" if "niamh" in f else "oisin"
    print("%-40s hand/arm spread %.2f" % (os.path.basename(f), score))
    if who not in best or score < best[who][0]:
        best[who] = (score, os.path.basename(f)[:-4])
for who, (s, b) in best.items():
    print("BEST", who, b, "%.2f" % s)
