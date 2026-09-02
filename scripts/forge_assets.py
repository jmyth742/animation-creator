#!/usr/bin/env python3
"""
Forge a new character or location into renderable existence.

A name in the bible is nothing until the pipeline can seed shots from it.
Forging runs the whole chain that the existing cast went through piecemeal:

  character:  bible entry -> cel portrait (FLUX) -> staged into every
              location that has a master -> in-place composite close seeds
  location:   bible entry -> reference plate + sets/master (FLUX) ->
              camera setups -> generated wides for each lead + a two-shot

Everything lands under the same names the rest of the pipeline expects, so
the builder, the importer and the renderer see the new thing immediately.

    forge_assets.py character <id> --visual "..." --voice en-IE-... [--seed N]
    forge_assets.py location  <id> --desc "..." [--seed N]
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

SERIES = "tir-na-nog-legend"
STYLE = ("Cel-shaded 2D animation, clean confident linework, flat blocks of "
         "colour with simple shading, painted background art. Restrained "
         "desaturated palette of deep greens, slate blue-grey and cold stone, "
         "overcast diffuse light, muted. No text, no watermark")


def t2i(prompt, prefix, seed, w=832, h=480):
    wf = sr.build_t2i_workflow(prompt, seed=seed, prefix=prefix,
                               width=w, height=h)
    pid = sr.queue_prompt(wf)
    if not sr.poll_until_done(pid, max_wait=900):
        return None
    hits = sorted((sr.COMFYUI_DIR / "output").rglob(f"{prefix}*.png"))
    return hits[-1] if hits else None


def save_bible(b):
    p = sr.series_path(SERIES) / "bible.json"
    shutil.copy(p, p.with_suffix(f".json.bak.{int(time.time())}"))
    p.write_text(json.dumps(b, indent=2))


def forge_character(a):
    sr.set_current_series(SERIES)
    b = sr.load_json(sr.series_path(SERIES) / "bible.json")
    cid = a.id.lower()
    b.setdefault("characters", {})[cid] = {
        "visual": a.visual, "voice": a.voice,
        "personality": a.personality or "",
        "trigger_word": a.trigger or cid.capitalize()}
    save_bible(b)
    print(f"[forge] bible: character '{cid}' written", flush=True)

    ref_dir = sr.series_path(SERIES) / "reference_images"
    prompt = (f"Character portrait, head and shoulders, facing camera, "
              f"neutral expression. {a.visual}. {STYLE}")
    out = t2i(prompt, f"forge_char_{cid}", a.seed, 832, 480)
    if not out:
        print("[forge] FAILED: no portrait rendered"); return 1
    dst = ref_dir / f"char_{cid}.png"
    dst.write_bytes(out.read_bytes())
    print(f"[forge] portrait -> {dst.name}", flush=True)

    import subprocess
    S = sr.series_path(SERIES) / "sets"
    for loc in sorted(d.name for d in S.iterdir()
                      if d.is_dir() and not d.name.startswith("_")
                      and (d / "master.png").exists()):
        print(f"[forge] staging into {loc} ...", flush=True)
        subprocess.run([sys.executable, str(Path(__file__).parent / "build_sets.py"),
                        "stage", SERIES, loc, cid, "--only", "master,reverse",
                        "--staging", "close,medium"], capture_output=True)
        subprocess.run([sys.executable, str(Path(__file__).parent / "stage_composite.py"),
                        SERIES, loc, cid, "--setups", "master,reverse",
                        "--stagings", "close,medium"], capture_output=True)
        # a generated wide so the figure-in-landscape shot exists day one
        gp = S / "_generated" / f"gen__{loc}_wide_{cid}.png"
        if not gp.exists():
            desc = str(b.get("world", {}).get("locations", {}).get(loc, ""))[:180]
            g = t2i(f"Extreme wide shot. {desc}. Far away, small in the frame, "
                    f"{a.visual}, whole body visible, no larger than a tenth "
                    f"of the frame height. {STYLE}",
                    f"forge_wide_{loc}_{cid}", a.seed + 71)
            if g:
                gp.write_bytes(g.read_bytes())
                print(f"[forge] wide plate -> {gp.name}", flush=True)
    print("[forge] DONE character", flush=True)
    return 0


def forge_location(a):
    sr.set_current_series(SERIES)
    b = sr.load_json(sr.series_path(SERIES) / "bible.json")
    lid = a.id.lower()
    b.setdefault("world", {}).setdefault("locations", {})[lid] = a.desc
    save_bible(b)
    print(f"[forge] bible: location '{lid}' written", flush=True)

    ref_dir = sr.series_path(SERIES) / "reference_images"
    out = t2i(f"Very wide establishing shot of {a.desc}. No people, no "
              f"figures, empty. {STYLE}", f"forge_loc_{lid}", a.seed)
    if not out:
        print("[forge] FAILED: no plate rendered"); return 1
    (ref_dir / f"loc_{lid}.png").write_bytes(out.read_bytes())
    S = sr.series_path(SERIES) / "sets" / lid
    S.mkdir(parents=True, exist_ok=True)
    (S / "master.png").write_bytes(out.read_bytes())
    print(f"[forge] master plate -> sets/{lid}/master.png", flush=True)

    import subprocess
    subprocess.run([sys.executable, str(Path(__file__).parent / "build_sets.py"),
                    "setups", SERIES, lid], capture_output=True)
    G = sr.series_path(SERIES) / "sets" / "_generated"
    chars = {k: v for k, v in b.get("characters", {}).items() if v.get("voice")}
    for cid, cv in chars.items():
        g = t2i(f"Extreme wide shot. {a.desc}. Far away, small in the frame, "
                f"{cv.get('visual','')[:150]}, whole body visible. {STYLE}",
                f"forge_wide_{lid}_{cid}", a.seed + 37)
        if g:
            (G / f"gen__{lid}_wide_{cid}.png").write_bytes(g.read_bytes())
            print(f"[forge] wide -> gen__{lid}_wide_{cid}.png", flush=True)
    ids = list(chars)
    if len(ids) >= 2:
        v0, v1 = (chars[i].get("visual", "")[:110] for i in ids[:2])
        g = t2i(f"Wide two shot. {a.desc}. On the left {v0}; on the right "
                f"{v1}. A few paces apart on the same ground, both "
                f"full-length at the same scale, facing each other. {STYLE}",
                f"forge_two_{lid}", a.seed + 93)
        if g:
            (G / f"gen__{lid}_twoshot.png").write_bytes(g.read_bytes())
            print(f"[forge] two-shot -> gen__{lid}_twoshot.png", flush=True)
    print("[forge] DONE location", flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="kind", required=True)
    c = sub.add_parser("character")
    c.add_argument("id"); c.add_argument("--visual", required=True)
    c.add_argument("--voice", required=True)
    c.add_argument("--personality", default="")
    c.add_argument("--trigger", default=None)
    c.add_argument("--seed", type=int, default=4400)
    l = sub.add_parser("location")
    l.add_argument("id"); l.add_argument("--desc", required=True)
    l.add_argument("--seed", type=int, default=5500)
    a = ap.parse_args()
    rc = forge_character(a) if a.kind == "character" else forge_location(a)
    import build_builder_data
    build_builder_data.build(SERIES)
    print("[forge] builder data refreshed", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
