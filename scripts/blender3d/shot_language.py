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
  5. NEAR-FIGURE GUARD — the foreground guard measures the aim point, but an over-the-shoulder
     puts the OTHER figure 1.5 m from the lens: a dark head across a third of the frame in
     every master to date. SL_MARKS="x,y;x,y" names where the cast stands; a camera closer than
     SL_NEAR_DIST to any mark that is not its aim point slides sideways, away from that figure,
     until it clears it, keeping its aim. Marks come from the builders (OP/NP per episode).
Env: SL_MAX_LENS (42), SL_PULLBACK (0.15), SL_MIN_DIST (2.2), SL_HOLD (0), SL_MARKS, SL_NEAR_DIST (2.0)
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
    near_dist = float(os.environ.get("SL_NEAR_DIST", "2.0"))
    marks = [[float(v) for v in m.split(",")] for m in os.environ.get("SL_MARKS", "").split(";") if m.strip()]
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
        # rule 5: slide sideways past any figure that is not the aim point
        slide = [0.0, 0.0, 0.0]
        for mk in marks:
            if math.hypot(mk[0] - tgt[0], mk[1] - tgt[1]) < 0.6: continue      # the aim point's own figure
            dxy = math.hypot(mk[0] - cam[0], mk[1] - cam[1])
            if dxy >= near_dist: continue
            vx, vy = tgt[0] - cam[0], tgt[1] - cam[1]; vl = math.hypot(vx, vy) or 1e-6
            px, py = -vy / vl, vx / vl                                            # screen-right in the ground plane
            side = 1.0 if (mk[0] - cam[0]) * px + (mk[1] - cam[1]) * py < 0 else -1.0   # away from the figure
            shift = (near_dist - dxy) * 1.6
            cam = [cam[0] + px * shift * side, cam[1] + py * shift * side, cam[2]]
            slide = [px * shift * side, py * shift * side, 0.0]
            note.append("near figure %.2f m -> slid %.2f m aside" % (dxy, shift))

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
        if move.startswith("dolly:") and any(abs(v) > 1e-6 for v in slide):
            p1 = vec(move[6:]); p1 = [p1[i] + slide[i] for i in range(3)]      # the END slides with the start
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
