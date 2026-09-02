#!/usr/bin/env python3
"""Rebuild the builder's data blob (locations, characters, plates) from disk."""
import base64
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402


def thumb(p, w=280):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-vf",
                        f"scale={w}:-1", "-q:v", "7", "-f", "mjpeg", "-"],
                       capture_output=True)
    return ("data:image/jpeg;base64,"
            + base64.b64encode(r.stdout).decode()) if r.stdout else None


def build(series, out=None):
    out = out or f"/tmp/builder_data_{series}.json"
    sr.set_current_series(series)
    S = sr.series_path(series) / "sets"
    b = sr.load_json(sr.series_path(series) / "bible.json")
    if not isinstance(b.get("characters"), dict):
        b["characters"] = {}
    if not isinstance(b.get("world"), dict):
        b["world"] = {"locations": {}}
    data = {"locations": {}, "characters": {}, "gen": {}, "inplace": []}
    for k, v in (b.get("world", {}).get("locations", {}) or {}).items():
        m = S / k / "master.png"
        if not m.exists():
            m = sr._find_ref(sr.series_path(series) / "reference_images", k, "loc") or m
        data["locations"][k] = {"desc": str(v)[:160],
                                "thumb": thumb(m) if Path(m).exists() else None}
    for k, v in b.get("characters", {}).items():
        ref = sr._find_ref(sr.series_path(series) / "reference_images", k, "char")
        data["characters"][k] = {"visual": (v.get("visual") or "")[:110],
                                 "voice": v.get("voice"),
                                 "thumb": thumb(ref, 160) if ref else None}
    if (S / "_generated").exists():
        for p in sorted((S / "_generated").glob("gen__*.png")):
            data["gen"][p.stem] = thumb(p)
    data["inplace"] = sorted(str(p.relative_to(S))
                             for p in S.glob("*/*__inplace.png")) \
        if S.exists() else []
    Path(out).write_text(json.dumps(data))
    return data


if __name__ == "__main__":
    d = build(sys.argv[1] if len(sys.argv) > 1 else "tir-na-nog-legend")
    print(f"{len(d['locations'])} locations, {len(d['characters'])} characters, "
          f"{len(d['gen'])} plates")
