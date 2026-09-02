#!/usr/bin/env python3
"""
Turn an Episode Builder export into a gated, render-ready episode.

The builder (a claude.ai artifact) composes in the show's grammar and
exports a compact JSON: shot type + location + characters + words, with the
seed named symbolically. This resolves it to the full episode schema --
real plate paths, setups, holds -- assigns the next episode number, and
runs the linter and preflight so a bad import is refused before it costs a
render.

    import_episode.py <series> --file paste.json
    cat paste.json | import_episode.py <series>
    import_episode.py <series> --file paste.json --dry-run
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

STEM = {"ruined_ireland": "ruin", "tir_na_nog": "valley",
        "farewell_cliff": "cliff", "sunlight_path": "sun",
        "storm_cliffs": "storm", "stormy_sea": "sea"}


def stem(loc):
    """Forged locations use their own id as the plate stem."""
    return STEM.get(loc, loc)


def resolve_scene(series, i, sc, ep_id):
    S = sr.series_path(series) / "sets"
    G = S / "_generated"
    t, loc = sc["type"], sc["location"]
    out = {"id": f"{ep_id}_s{i:02d}", "location": loc,
           "characters": sc.get("characters", []),
           "clip_length": "long",
           "hold_seconds": float(sc.get("hold_seconds") or 7.0),
           "visual": sc.get("visual", ""), "narration": None,
           "dialogue": sc.get("dialogue", [])}
    plate = sc.get("plate")
    if t == "wide":
        out["seed"] = "location"
        out["setup"], out["staging"] = "master", None
    elif t in ("figure", "twoshot"):
        p = (G / f"{plate}.png") if plate and plate.startswith("gen__") else None
        if not (p and p.exists()):
            raise SystemExit(f"  {out['id']}: plate {plate!r} not found — "
                             f"regenerate it or change the shot")
        out["reference_image"] = str(p.resolve())
    elif t == "close":
        who = (sc.get("characters") or [None])[0]
        cands = sorted((S / loc).glob(f"*__{who}_close__inplace.png"))
        if not cands:
            raise SystemExit(f"  {out['id']}: no in-place close seed for "
                             f"{who} at {loc} — run stage_composite.py first")
        out["reference_image"] = str(cands[0].resolve())
        out["setup"] = cands[0].name.split("__")[0]
        out["staging"] = "close"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--file", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sr.set_current_series(a.series)
    raw = Path(a.file).read_text() if a.file else sys.stdin.read()
    doc = json.loads(raw)

    eps = sorted((sr.series_path(a.series) / "episodes").glob("ep*.json"))
    n = max(int(p.stem[2:]) for p in eps) + 1 if eps else 1
    ep_id = f"ep{n:02d}"
    scenes = [resolve_scene(a.series, i + 1, sc, ep_id)
              for i, sc in enumerate(doc.get("scenes", []))]
    out = {"id": ep_id, "title": doc.get("title", "Untitled"),
           "summary": doc.get("summary", ""), "scenes": scenes}
    dst = sr.series_path(a.series) / "episodes" / f"{ep_id}.json"
    d = sum(1 for s in scenes if s["dialogue"])
    total = sum(s["hold_seconds"] for s in scenes)
    print(f"  {ep_id} '{out['title']}': {len(scenes)} shots · "
          f"{total:.0f}s = {total/60:.2f} min · {d} dialogue")
    if a.dry_run:
        print("  dry run — nothing written")
        return 0
    dst.write_text(json.dumps(out, indent=2))
    print(f"  wrote {dst}")

    import subprocess
    for gate in ("lint_episode.py", "preflight.py"):
        r = subprocess.run([sys.executable, str(Path(__file__).parent / gate),
                            a.series, "--episode", str(n)],
                           capture_output=True, text=True)
        tail = [l for l in r.stdout.splitlines() if l.strip()][-3:]
        for l in tail:
            print(f"    {l.strip()[:110]}")
        if r.returncode != 0:
            print(f"  {gate} FAILED — episode written but NOT render-ready")
            return 1
    print(f"\n  gates passed. Render with:\n"
          f"    showrunner.py produce {a.series} --episode {n} "
          f"--quality final --upscale")
    return 0


if __name__ == "__main__":
    sys.exit(main())
