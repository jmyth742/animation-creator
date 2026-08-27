#!/usr/bin/env python3
"""
Draw the graph that actually renders a shot.

Two things worth showing on video, and they are different:

  THE REAL GRAPH -- what gets sent to ComfyUI for one shot. Not a tidied
  diagram: the actual nodes, in the actual order, including the chained Extend
  blocks that let a take run past five seconds. This is where the extra_chunks
  bug was visible and nowhere else -- three renders produced 16-node graphs when
  they should have produced 20 and 24. A picture of that graph IS the story.

  THE PIPELINE -- script to finished film, so an audience knows where the graph
  sits in the larger thing.

Renders with PIL because graphviz is not installed and a hand-laid graph is
clearer than an auto-routed one anyway: nodes are placed in dependency layers,
left to right, and the S2V conditioning path is highlighted because that is the
edge that was wrong for the whole project.

Also writes the workflows out in ComfyUI's own format so they can be dropped
into the UI and screen-recorded there -- which looks better than any diagram.

    draw_workflow.py --shot ep05_s03 --chunks 3
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
BG, BOX, INK, DIM = (14, 15, 18), (32, 35, 42), (228, 225, 216), (135, 132, 126)
EDGE, HOT, HOTBOX = (78, 82, 92), (232, 152, 92), (58, 44, 34)

# Nodes worth colouring: the ones that carry the story.
FAMILY = {
    "WanSoundImageToVideo": "audio + reference conditioning",
    "WanSoundImageToVideoExtend": "chains past the 5.06s ceiling",
    "KSampler": "sampling",
    "UnetLoaderGGUF": "the 14B checkpoint",
}


def layers(wf: dict) -> list[list[str]]:
    """Longest-path layering: a node sits one level right of its deepest input."""
    depth, order = {}, []
    def d(n, seen=()):
        if n in depth:
            return depth[n]
        if n in seen:
            return 0
        best = 0
        for v in (wf[n].get("inputs") or {}).values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and v[0] in wf:
                best = max(best, d(v[0], seen + (n,)) + 1)
        depth[n] = best
        return best
    for n in wf:
        d(n)
    by = defaultdict(list)
    for n, lv in depth.items():
        by[lv].append(n)
    return [sorted(by[k], key=lambda x: (len(x), x)) for k in sorted(by)]


def draw(wf: dict, out: Path, title: str) -> Path:
    L = layers(wf)
    BW, BH, GX, GY, PAD = 300, 74, 120, 34, 90
    W = PAD * 2 + len(L) * BW + (len(L) - 1) * GX
    H = PAD * 2 + 90 + max(len(c) for c in L) * (BH + GY)
    img = Image.new("RGB", (W, H), BG)
    dr = ImageDraw.Draw(img)
    f = ImageFont.truetype(MONO, 17)
    fb = ImageFont.truetype(MONO_B, 19)
    ft = ImageFont.truetype(MONO_B, 34)
    dr.text((PAD, 44), title, font=ft, fill=INK)

    pos = {}
    for ci, col in enumerate(L):
        x = PAD + ci * (BW + GX)
        for ri, n in enumerate(col):
            y = PAD + 90 + ri * (BH + GY)
            pos[n] = (x, y)

    # edges first, so boxes sit on top
    for n, node in wf.items():
        for name, v in (node.get("inputs") or {}).items():
            if not (isinstance(v, list) and len(v) == 2 and v[0] in pos):
                continue
            x0, y0 = pos[v[0]]; x1, y1 = pos[n]
            hot = (wf[v[0]]["class_type"].startswith("WanSoundImageToVideo")
                   and name in ("positive", "negative", "latent_image"))
            dr.line([(x0 + BW, y0 + BH // 2), (x0 + BW + GX // 2, y0 + BH // 2),
                     (x0 + BW + GX // 2, y1 + BH // 2), (x1, y1 + BH // 2)],
                    fill=HOT if hot else EDGE, width=3 if hot else 2)

    for n, (x, y) in pos.items():
        cls = wf[n]["class_type"]
        hot = cls in ("WanSoundImageToVideo", "WanSoundImageToVideoExtend")
        dr.rounded_rectangle([x, y, x + BW, y + BH], 9,
                             fill=HOTBOX if hot else BOX,
                             outline=HOT if hot else (58, 62, 70), width=2)
        label = cls if len(cls) <= 26 else cls[:24] + ".."
        dr.text((x + 14, y + 12), label, font=fb, fill=HOT if hot else INK)
        note = FAMILY.get(cls, "")
        if note:
            dr.text((x + 14, y + 40), note[:32], font=f, fill=DIM)
    img.save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", default="tir-na-nog-legend")
    ap.add_argument("--shot", default="ep05_s03")
    ap.add_argument("--chunks", type=int, default=3)
    ap.add_argument("--outdir", default="/workspace/video_assets/14_the_graph")
    a = ap.parse_args()

    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    ep_num = int(a.shot.split("_")[0].replace("ep", ""))
    ep = sr.load_json(sr.episode_path(a.series, ep_num))
    scene = next(s for s in ep["scenes"] if s["id"] == a.shot)
    res = sr.get_resolution_config("480p", "wan")
    prompt = sr.build_scene_prompt(scene, bible)
    neg = sr.build_negative_prompt(scene)
    seed_img = sr.get_scene_seed_image(scene, a.series, None)

    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    made = []
    for ch in range(1, a.chunks + 1):
        wf = sr.build_video_workflow(
            "wan", "s2v", prompt, 42, a.shot, 81, res, negative_prompt=neg,
            steps=15, image_name=seed_img, audio_path="line.mp3",
            extra_chunks=ch - 1)
        n_ext = sum(1 for v in wf.values()
                    if v["class_type"] == "WanSoundImageToVideoExtend")
        secs = (ch * 81) / 16
        png = out / f"graph_{ch}chunk.png"
        draw(wf, png, f"One dialogue shot — {ch} chunk(s), {secs:.2f}s "
                      f"({len(wf)} nodes, {n_ext} Extend)")
        (out / f"workflow_{ch}chunk.json").write_text(json.dumps(wf, indent=2))
        made.append((ch, len(wf), n_ext, secs))
        print(f"  {ch} chunk(s): {len(wf)} nodes, {n_ext} Extend -> {png.name}")

    rows = "\n".join(f"{c} chunk(s)   {n:2} nodes   {e} Extend   {s:5.2f}s"
                     for c, n, e, s in made)
    (out / "README.md").write_text(
        "# The graph that renders one shot\n\n"
        "Not a tidied diagram — the actual node graph sent to ComfyUI, laid out\n"
        "in dependency order. The highlighted path is the conditioning that\n"
        "carries the audio embedding AND the character reference; wiring the\n"
        "sampler around it was the defect that ran for the whole project.\n\n"
        f"```\n{rows}\n```\n\n"
        "## For a better-looking version\n\n"
        "`workflow_*.json` are in ComfyUI's API format. Drop one into ComfyUI\n"
        "and screen-record the real UI — it looks better than any diagram, and\n"
        "you can drag nodes around while narrating.\n\n"
        "## Why three of them\n\n"
        "This is the picture that made the `extra_chunks` bug visible: three\n"
        "renders should have produced 16, 20 and 24 nodes. All three produced\n"
        "16, because the call site dropped the argument.\n")
    print(f"\n  {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
