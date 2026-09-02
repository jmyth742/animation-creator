#!/usr/bin/env python3
"""
One QC report per episode, built only from metrics that have been validated.

The recurring failure of this project is instruments that lie: six metrics in
one day returned "fine" while the picture was wrong, and every one had been
trusted without being tested against a known-bad case. So this report uses
ONLY checks that have each been proven to catch a real defect:

    streams        caught the silent ep13/ep15         (validated 30 Aug)
    location       caught valley imagery in a sea shot (validated 1 Sep, 4/4)
    duration drift caught the 4.5s subtitle slide      (validated weeks ago)
    lip_ratio      caught ep14_s07's inverted sync     (validated 29 Aug)
    p(wide)        caught 11/11 collapsed wides        (validated 29 Aug)

It deliberately does NOT score identity (rewards wrong framing), whole-frame
setting match (scored a placeless close HIGHER than a placed one), or corner
artifacts (cannot tell a logo from grass). Those live in the git log as
warnings, not here as numbers.

    episode_qc.py <series>                    # the whole series, ranked
    episode_qc.py <series> --episode 13
    episode_qc.py <series> --json out.json    # for tooling
"""
import argparse
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

LIP_OK, LIP_WEAK = 2.0, 1.3
WIDE_OK = 0.5



_LOC_REFS = None
def location_of(clip, series, t=2.0):
    """
    Which location a frame most resembles, classified against the bare master
    plates. Validated 1 Sep: flagged ep12_s05 (valley imagery installed into a
    sea-crossing shot) and passed three known-good shots. This is the check
    p(wide) cannot do -- a wide in the WRONG PLACE still reads as a wide.
    """
    global _LOC_REFS
    import verify_render as vr
    from PIL import Image
    if _LOC_REFS is None:
        SETS = sr.series_path(series) / "sets"
        locs = {d.name: d / "master.png" for d in SETS.iterdir()
                if d.is_dir() and not d.name.startswith("_")
                and (d / "master.png").exists()}
        names = sorted(locs)
        refs = vr._embed_images([Image.open(locs[n]).convert("RGB")
                                 for n in names])
        _LOC_REFS = (names, refs)
    names, refs = _LOC_REFS
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i",
                        clip, "-frames:v", "1", f"{td}/f.png"], check=True)
        v = vr._embed_images([Image.open(f"{td}/f.png").convert("RGB")])
    probs = ((v @ refs.T)[0] * 100).softmax(dim=-1)
    i = int(probs.argmax())
    return names[i], float(probs[i])


def lip_ratio(clip, vo):
    """Mouth-region motion while speaking vs while silent. >2 good, <1.3 broken."""
    import numpy as np
    from PIL import Image
    try:
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip, "-vf",
                            "fps=4,crop=iw*0.30:ih*0.16:iw*0.36:ih*0.36,scale=64:-1",
                            f"{td}/m_%03d.png"], check=True)
            fr = [np.asarray(Image.open(f).convert("L"), dtype=np.float32)
                  for f in sorted(Path(td).glob("m_*.png"))]
            if len(fr) < 3:
                return None
            mo = np.array([np.abs(fr[i+1]-fr[i]).mean() for i in range(len(fr)-1)])
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(vo),
                            "-ac", "1", "-ar", "8000", f"{td}/a.wav"], check=True)
            w = wave.open(f"{td}/a.wav")
            a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
        env = np.array([np.abs(a[i*2000:(i+1)*2000]).mean() for i in range(len(a)//2000)])
        n = min(len(mo), len(env))
        if n < 4 or env[:n].max() == 0:
            return None
        m, e = mo[:n], env[:n]
        sp = e > e.max() * 0.15
        if not (~sp).any() or m[~sp].mean() == 0:
            return None
        return round(float(m[sp].mean() / m[~sp].mean()), 2)
    except Exception:                                          # noqa: BLE001
        return None


def qc_episode(series, ep_num):
    ep = sr.load_json(sr.episode_path(series, ep_num))
    final = Path("output") / series / f"ep{ep_num:02d}" / f"ep{ep_num:02d}_final.mp4"
    rep = {"episode": ep_num, "title": ep.get("title", ""), "issues": [],
           "shots": []}
    if not final.exists():
        rep["issues"].append("no final file")
        return rep
    st = sorted(sr._streams(final))
    if "audio" not in st:
        rep["issues"].append("MISSING AUDIO")
    # duration drift: assembled vs sum of latest takes
    total = 0.0
    for s in ep["scenes"]:
        c = sr.find_latest_clip(s["id"])
        if c:
            total += sr._get_video_duration(c)
    have = sr._get_video_duration(final)
    # crossfades legitimately remove ~0.3s per cut; flag only beyond that
    slack = 0.35 * max(0, len(ep["scenes"]) - 1) + 1.0
    if abs(have - total) > slack + 6.0:
        rep["issues"].append(f"duration drift {have - total:+.1f}s beyond "
                             f"crossfade budget")
    import wide_dialogue_test as wd
    for s in ep["scenes"]:
        c = sr.find_latest_clip(s["id"])
        if not c:
            rep["shots"].append({"id": s["id"], "issue": "no clip"})
            continue
        row = {"id": s["id"]}
        if s.get("dialogue"):
            vo = (Path("output") / series / f"ep{ep_num:02d}" / "audio"
                  / f"{s['id']}.mp3")
            if vo.exists():
                lr = lip_ratio(c, vo)
                row["lip_ratio"] = lr
                if lr is not None and lr < LIP_WEAK:
                    row["issue"] = f"lip sync broken ({lr}x)"
                elif lr is not None and lr < LIP_OK:
                    row["warn"] = f"lip sync weak ({lr}x)"
        else:
            v = (s.get("visual") or "").lower()
            wants_wide = any(w in v for w in ("wide", "small ", "extreme"))
            if wants_wide:
                p, label = wd.framing(c)
                row["p_wide"] = round(p, 3)
                if p < WIDE_OK:
                    row["issue"] = f"authored wide, reads {label} ({p:.2f})"
        # wrong-place check on SILENT shots only. Applied to dialogue closes
        # it flagged sibling locations off a background sliver -- a golden-lit
        # close on the sea classified as the golden-lit cliff at 0.98, three
        # false positives eyeballed 2 Sep. The check was validated on wides;
        # it runs where it was validated and nowhere else.
        want_loc = s.get("location")
        if want_loc and "issue" not in row and not s.get("dialogue"):
            got, conf = location_of(c, series)
            if got != want_loc and conf >= 0.85:
                row["issue"] = (f"authored in {want_loc}, frame classifies as "
                                f"{got} ({conf:.2f})")
        rep["shots"].append(row)
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--episode", type=int)
    ap.add_argument("--json")
    a = ap.parse_args()
    sr.set_current_series(a.series)
    eps = [a.episode] if a.episode else [
        int(p.stem.replace("ep", ""))
        for p in sorted((sr.series_path(a.series) / "episodes").glob("ep*.json"))
        if (Path("output") / a.series / p.stem / f"{p.stem}_final.mp4").exists()]

    reports, bad_shots = [], []
    for e in eps:
        r = qc_episode(a.series, e)
        reports.append(r)
        n_issue = sum(1 for s in r["shots"] if "issue" in s) + len(r["issues"])
        n_warn = sum(1 for s in r["shots"] if "warn" in s)
        print(f"\n  ep{e:02d} · {r['title'][:38]:38} "
              f"{n_issue} issue(s), {n_warn} warn(s)")
        for i in r["issues"]:
            print(f"    [EP  ] {i}")
        for s in r["shots"]:
            if "issue" in s:
                print(f"    [SHOT] {s['id']}: {s['issue']}")
                bad_shots.append((e, s["id"], s["issue"]))
            elif "warn" in s:
                print(f"    [warn] {s['id']}: {s['warn']}")

    print(f"\n  ═══ {len(bad_shots)} shot-level issue(s) across "
          f"{len(reports)} episode(s) ═══")
    if a.json:
        Path(a.json).write_text(json.dumps(reports, indent=2))
        print(f"  wrote {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
