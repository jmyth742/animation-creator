"""
SHOT LANGUAGE pass — design the cut around what the pipeline actually does well.

The renderer is strongest on painted environments and weakest on faces at close range,
and the current cut leans on dialogue close-ups and extreme foreground over-shoulder
heads, which is exactly backwards. This rewrites the emitted shot list rather than the
scene, so it is data-only, reversible, and costs nothing: film.py reads camera position,
aim, lens and move from this JSON at render time.

Rules applied:
  1. LENS CAP — any shot tighter than SL_MAX_LENS is widened. A wider lens from the same
     position keeps the subject centred on its aim point but smaller in frame, turning a
     close-up into a medium and a medium into a wide.
  2. PULL BACK — the camera retreats along its own view vector by a fraction of its
     distance to the aim point, giving the figure air and putting more painted
     environment on screen.
  3. FOREGROUND GUARD — a camera closer to its subject than SL_MIN_DIST is pushed out.
     This is what kills the giant blurry over-shoulder head, where a low-resolution
     painted face is magnified across half the frame.
  4. HOLD — wide shots may be lengthened and close shots shortened (SL_HOLD), so screen
     time moves toward the strong material. Off by default: it changes edit timing and
     must stay in sync with the audio.

Run:
  python shot_language.py <shots.json> <out.json>
Env: SL_MAX_LENS (42), SL_PULLBACK (0.15), SL_MIN_DIST (2.2), SL_HOLD (0)
"""
import json
import math
import os
import sys


def vec(s):
    return [float(v) for v in s.split(",")]


def fmt(v):
    return ",".join("%.3f" % x for x in v)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    max_lens = float(os.environ.get("SL_MAX_LENS", "42"))
    pullback = float(os.environ.get("SL_PULLBACK", "0.15"))
    min_dist = float(os.environ.get("SL_MIN_DIST", "2.2"))
    hold = os.environ.get("SL_HOLD", "0") not in ("", "0")

    d = json.load(open(src))
    changed = []
    for s in d["shots"]:
        cam, tgt = vec(s["cam"]), vec(s["tgt"])
        lens = float(s["lens"])
        note = []

        if lens > max_lens:
            note.append("lens %g->%g" % (lens, max_lens))
            lens = max_lens

        view = [cam[i] - tgt[i] for i in range(3)]
        dist = math.sqrt(sum(v * v for v in view)) or 1e-6
        unit = [v / dist for v in view]

        new_dist = dist
        if dist < min_dist:
            new_dist = min_dist
            note.append("dist %.2f->%.2f (foreground guard)" % (dist, new_dist))
        if pullback > 0:
            new_dist *= (1.0 + pullback)
            note.append("pull back %.0f%%" % (pullback * 100))

        if abs(new_dist - dist) > 1e-6:
            cam = [tgt[i] + unit[i] * new_dist for i in range(3)]

        # a dolly move names an END position; move it by the same delta so the move keeps
        # its shape instead of drifting back toward the subject mid-shot
        move = s.get("move", "static")
        if move.startswith("dolly:") and abs(new_dist - dist) > 1e-6:
            p1 = vec(move[6:])
            v1 = [p1[i] - tgt[i] for i in range(3)]
            d1 = math.sqrt(sum(v * v for v in v1)) or 1e-6
            u1 = [v / d1 for v in v1]
            scale = new_dist / dist
            p1 = [tgt[i] + u1[i] * d1 * scale for i in range(3)]
            move = "dolly:" + fmt(p1)

        s["cam"], s["lens"], s["move"] = fmt(cam), lens, move
        if note:
            changed.append("%-12s %s" % (s["name"], "; ".join(note)))

    if hold:
        # widest third gains what the tightest third loses, keeping total length equal
        order = sorted(d["shots"], key=lambda x: float(x["lens"]))
        n = max(1, len(order) // 3)
        for s in order[:n]:
            s["f1"] = int(s["f1"]) + 8
        for s in order[-n:]:
            s["f1"] = max(int(s["f0"]) + 8, int(s["f1"]) - 8)
        changed.append("HOLD: %d widest +8f, %d tightest -8f" % (n, n))

    json.dump(d, open(dst, "w"), indent=1)
    print("SHOTLANG %d of %d shots adjusted -> %s" % (len(changed), len(d["shots"]), dst))
    for c in changed:
        print("  " + c)


if __name__ == "__main__":
    main()
