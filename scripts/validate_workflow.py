#!/usr/bin/env python3
"""
Check the workflow GRAPH before it costs GPU time.

WHY THIS LAYER EXISTS
Three layers of checking already run: preflight (configuration), the dataset
gates (data), and verify_render (output). Ten silent defects still reached
finished renders, because every one of them lived in the gap between: the graph
that actually gets sent to ComfyUI.

The worst example ran for the entire project. WanSoundImageToVideo bakes the
character reference into its CONDITIONING output:

    positive = conditioning_set_values(positive, {"reference_latents": [...]})

The sampler was wired to the raw CLIPTextEncode outputs instead, and consumed
only the node's latent. So on every dialogue shot the reference image was
loaded, scaled, VAE-encoded -- and thrown away. Nothing errored. Lip sync still
worked. Identity averaged 0.777 against I2V's 0.876 and it read as "the model
drifts" rather than "the wiring is wrong". Fixing it moved two shots +0.227 and
+0.195.

A configuration check cannot see that. An output check cannot tell a discarded
reference from a model limitation. Only the graph shows it.

    validate_workflow.py <series> --episode N     # build every shot, check each
    python -c "import validate_workflow as v; v.check(wf, mode)"

Exits non-zero on any error, so it gates a render.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

# Nodes whose whole purpose is to inject conditioning. If one of these is in the
# graph, the sampler must consume its conditioning, not bypass it.
CONDITIONING_INJECTORS = {
    "WanSoundImageToVideo": ("audio + character reference", (0, 1)),
    "WanImageToVideo": ("image conditioning", (0, 1)),
}
SAMPLERS = ("KSampler", "KSamplerAdvanced")


def _links(wf: dict):
    """Every (from_node, to_node, input_name) edge in the graph."""
    for nid, node in wf.items():
        for name, val in (node.get("inputs") or {}).items():
            if isinstance(val, list) and len(val) == 2 and isinstance(val[0], str):
                yield val[0], nid, name


def check(wf: dict, mode: str = "?") -> list[str]:
    """Return a list of problems. Empty means the graph is sane."""
    problems = []
    by_class = {}
    for nid, node in wf.items():
        by_class.setdefault(node.get("class_type"), []).append(nid)

    consumed = {src for src, _, _ in _links(wf)}
    samplers = [n for c in SAMPLERS for n in by_class.get(c, [])]

    # ── 1. A conditioning injector must actually reach the sampler ───────
    for cls, (what, out_idx) in CONDITIONING_INJECTORS.items():
        for nid in by_class.get(cls, []):
            for s in samplers:
                ins = wf[s].get("inputs", {})
                for side in ("positive", "negative"):
                    ref = ins.get(side)
                    if not (isinstance(ref, list) and ref[0] == nid):
                        problems.append(
                            f"{cls} (node {nid}) carries {what}, but sampler "
                            f"{s} takes '{side}' from node "
                            f"{ref[0] if isinstance(ref, list) else ref!r} — "
                            f"that conditioning is discarded")

    # ── 2. Every image loaded must be reachable from a sampler ───────────
    for nid in by_class.get("LoadImage", []):
        if nid not in consumed:
            name = wf[nid].get("inputs", {}).get("image")
            problems.append(f"LoadImage {nid} ({name}) is loaded but nothing "
                            f"consumes it — the seed image does nothing")

    # ── 3. No orphan nodes doing work nobody reads ───────────────────────
    terminals = {"SaveVideo", "SaveImage", "PreviewImage", "SaveAudio"}
    for nid, node in wf.items():
        cls = node.get("class_type")
        if cls in terminals or nid in consumed:
            continue
        problems.append(f"node {nid} ({cls}) produces output nothing uses")

    # ── 4. A sampler must exist and be wired ─────────────────────────────
    if not samplers:
        problems.append("no sampler in the graph")
    for s in samplers:
        ins = wf[s].get("inputs", {})
        for req in ("model", "positive", "negative", "latent_image"):
            if req not in ins:
                problems.append(f"sampler {s} is missing '{req}'")

    # ── 5. Cross-family LoRAs ────────────────────────────────────────────
    # A LoRA trained on the T2V checkpoints applied to the S2V model degrades
    # the result: measured identity -0.138 and the cel-style score collapsing
    # 0.999 -> 0.001 on a dialogue shot.
    if mode == "s2v":
        unets = [wf[n].get("inputs", {}).get("unet_name", "")
                 for n in by_class.get("UnetLoaderGGUF", [])]
        is_s2v_model = any("S2V" in str(u).upper() for u in unets)
        loras = [wf[n].get("inputs", {}).get("lora_name", "")
                 for c in ("LoraLoader", "LoraLoaderModelOnly")
                 for n in by_class.get(c, [])]
        chars = [l for l in loras if "lightning" not in str(l).lower()]
        if is_s2v_model and chars:
            problems.append(
                f"S2V checkpoint with character LoRA(s) {chars} — these are "
                f"trained on the T2V checkpoints and degrade across families")

    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--episode", type=int, default=1)
    a = ap.parse_args()

    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    ep = sr.load_json(sr.episode_path(a.series, a.episode))
    res = sr.get_resolution_config("480p", "wan")

    total = 0
    print(f"  building and checking {len(ep['scenes'])} shot graphs\n")
    for scene in ep["scenes"]:
        mode = sr.classify_scene_type(scene)
        seed_img = sr.get_scene_seed_image(scene, a.series, None)
        loras = sr.get_scene_loras(scene, bible)
        # mirror cmd_produce: character LoRAs are dropped for S2V
        if mode == "s2v":
            loras = []
        frames = sr.CLIP_LENGTHS.get(scene.get("clip_length", "long"),
                                     sr.CLIP_LENGTHS["long"])["frames"]
        audio = "dummy.mp3" if mode == "s2v" else None
        try:
            wf = sr.build_video_workflow(
                "wan", mode, sr.build_scene_prompt(scene, bible), 42,
                f"chk_{scene['id']}", frames, res,
                negative_prompt=sr.build_negative_prompt(scene),
                steps=8, image_name=seed_img, audio_path=audio,
                loras=loras or None)
        except Exception as e:                                 # noqa: BLE001
            print(f"  {scene['id']}  {mode:5} BUILD FAILED: "
                  f"{type(e).__name__}: {e}")
            total += 1
            continue
        bad = check(wf, mode)
        mark = "ok" if not bad else "PROBLEM"
        print(f"  {scene['id']}  {mode:5} {len(wf):3} nodes  {mark}")
        for b in bad:
            print(f"      {b}")
        total += len(bad)

    print(f"\n  {total} problem(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
