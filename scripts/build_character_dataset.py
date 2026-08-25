#!/usr/bin/env python3
"""
Build a LoRA training dataset for a persistent character.

The problem this solves: independent text-to-image generations produce a
DIFFERENT PERSON every time, so a LoRA trained on them learns a generic look
rather than one specific character. Identity-lock tools (IP-Adapter FaceID,
InstantID, PuLID) would fix that, but their weights are not installed here.

What this does instead, using only what is already on the box: FLUX generates
a set of candidate portraits, you promote ONE to canonical, and WAN I2V then
animates that single portrait into short clips. Every clip is conditioned on
the same face, so the harvested frames are one person at varied angles,
expressions and lighting -- which is exactly what a character LoRA needs.

Stages (run in order; review between them):

    portraits   generate N FLUX candidates into candidates/
    pick        promote one candidate to canonical.png
    clips       animate the canonical portrait into motion clips
    frames      harvest frames from the clips and write captions
    config      emit the musubi-tuner dataset TOML

    python scripts/build_character_dataset.py portraits jonny --count 8
    python scripts/build_character_dataset.py pick       jonny --candidate 3
    python scripts/build_character_dataset.py clips      jonny
    python scripts/build_character_dataset.py frames     jonny
    python scripts/build_character_dataset.py config     jonny
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr  # noqa: E402

WORKSPACE = Path("/workspace")
DATASETS = WORKSPACE / "datasets"
BUILD_ROOT = WORKSPACE / "text-to-video" / "training" / "character_builds"

# 49 frames (~3.1s). The first pass used 33 to guard against identity drift,
# but the harvested frames turned out near-identical to the seed -- WAN barely
# moved the subject, giving a dataset with no pose or framing variety, which
# trains a LoRA that bakes in the background and clothing. Identity holds far
# better than expected, so give the motion room to develop instead.
CLIP_FRAMES = 49
CLIP_W, CLIP_H = 480, 832          # portrait, matches a person better than 832x480
PORTRAIT_W, PORTRAIT_H = 480, 640  # same as the existing reemi/bibi datasets


def build_dir(name: str) -> Path:
    return BUILD_ROOT / name


def load_brief(name: str) -> dict:
    f = build_dir(name) / "brief.json"
    if not f.exists():
        sys.exit(f"No brief for '{name}'. Expected {f}")
    return json.loads(f.read_text())


def res_config() -> dict:
    """Portrait-orientation copy of the 480p config."""
    rc = dict(sr.get_resolution_config("480p", "wan"))
    rc["width"], rc["height"] = CLIP_W, CLIP_H
    return rc


# ── stage: portraits ─────────────────────────────────────────────────
def cmd_portraits(args):
    name = args.name
    d = build_dir(name)
    cand = d / "candidates"
    cand.mkdir(parents=True, exist_ok=True)
    brief = load_brief(name)

    refs_out = sr.COMFYUI_DIR / "output" / "refs"
    print(f"Generating {args.count} candidate portraits for '{name}'")
    print(f"  appearance: {brief['appearance'][:90]}...")

    for i in range(1, args.count + 1):
        out = cand / f"cand_{i:02d}.png"
        if out.exists() and not args.force:
            print(f"  cand_{i:02d} — exists, skipping")
            continue
        prompt = ", ".join([
            brief["style"],
            "cinematic portrait photograph",
            brief["appearance"],
            brief.get("portrait_framing",
                      "head and shoulders, facing camera, neutral expression"),
            "sharp focus on the face, natural skin texture, even soft lighting,"
            " plain uncluttered background",
        ])
        prefix = f"cand_{name}_{i:02d}"
        wf = sr.build_t2i_workflow(prompt, seed=1000 + i * 137, prefix=prefix,
                                   width=PORTRAIT_W, height=PORTRAIT_H)
        print(f"  cand_{i:02d} ...", flush=True)
        try:
            pid = sr.queue_prompt(wf)
        except Exception as e:
            sys.exit(f"  ComfyUI not reachable at {sr.SERVER}: {e}")
        if not sr.poll_until_done(pid):
            print("    WARNING: generation failed")
            continue
        got = sorted(refs_out.glob(f"{prefix}*.png"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
        if got:
            shutil.copy2(got[0], out)
            print(f"    saved {out.name}")
        else:
            print(f"    WARNING: no output found in {refs_out}")

    print(f"\nCandidates in {cand}")
    print(f"Review them, then: build_character_dataset.py pick {name} --candidate N")


# ── stage: pick ──────────────────────────────────────────────────────
def cmd_pick(args):
    d = build_dir(args.name)
    src = d / "candidates" / f"cand_{args.candidate:02d}.png"
    if not src.exists():
        sys.exit(f"No such candidate: {src}")
    dst = d / "canonical.png"
    shutil.copy2(src, dst)
    print(f"Canonical portrait for '{args.name}' -> {dst}")
    print("Every training image will be derived from this one face.")


# ── stage: clips ─────────────────────────────────────────────────────
# Each entry: (slug, motion prompt, caption fragment describing the SHOT).
# Captions describe framing/setting only -- never the character's appearance,
# which is what the LoRA is supposed to learn.
MOTIONS = [
    ("profile_turn", "he turns his head fully to the right into a sharp side profile, then holds it. Static camera, natural light",
     "Side profile view"),
    ("three_quarter", "he turns his body and head to a three-quarter angle away from camera, looking off to the side",
     "Three-quarter angle, looking off camera"),
    ("look_down_up", "he looks down at the ground, then raises his eyes slowly to the camera, serious",
     "Looking down then up to camera, serious"),
    ("smile_laugh", "he breaks into a broad smile and laughs, head tipping back slightly",
     "Smiling and laughing"),
    ("walk_wide", "wide shot, he walks away from the camera down a wet cobbled street, full body visible, overcast day",
     "Wide shot, full body, walking away, wet street, overcast"),
    ("cliff_wind", "wide shot of him standing on a windswept green sea cliff, coat and hair blown by strong wind, grey stormy sky",
     "Wide shot, windswept sea cliff, stormy grey daylight"),
    ("pub_warm", "he sits at a candlelit wooden table in a dim warm interior, firelight on one side of his face, no coat, shirt sleeves",
     "Seated, dim warm interior, candlelight from one side, no coat"),
    ("sunlit_close", "extreme close-up on his face in bright golden late afternoon sunlight, squinting slightly, warm rim light",
     "Extreme close-up, bright golden sunlight, warm rim light"),
]


def motions_for(brief: dict) -> list[tuple[str, str, str]]:
    """
    Motion/setting list for this character.

    The defaults are contemporary (wet streets, interiors). A brief can carry
    its own "motions": [[slug, prompt, caption], ...] so a mythic character is
    not filmed walking past shopfronts.
    """
    custom = brief.get("motions")
    if custom:
        return [tuple(m) for m in custom]
    return MOTIONS


def cmd_clips(args):
    name = args.name
    d = build_dir(name)
    canonical = d / "canonical.png"
    if not canonical.exists():
        sys.exit(f"No canonical portrait. Run 'pick' first ({canonical})")
    clips_dir = d / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    brief = load_brief(name)

    seed_image = sr.copy_to_input(str(canonical))
    rc = res_config()
    neg = brief.get("negative",
                    "blurry, distorted face, deformed, extra fingers, watermark, text, "
                    "multiple people, changing face, morphing")

    motions = motions_for(brief)[:args.count]
    print(f"Animating the canonical portrait into {len(motions)} clips "
          f"({CLIP_FRAMES} frames, {CLIP_W}x{CLIP_H}, {args.steps} steps)")

    failed = []
    for i, (slug, motion, _cap) in enumerate(motions, 1):
        target = clips_dir / f"{slug}.mp4"
        if target.exists() and not args.force:
            print(f"  [{i}/{len(motions)}] {slug} — exists, skipping")
            continue
        prompt = ", ".join([brief["style"], brief["appearance"], motion])
        prefix = f"ds_{name}_{slug}"
        # Step-distilled sampling. Measured on this box at 6x faster AND
        # cleaner than 18 undistilled steps, so there is no quality argument
        # for the slow path -- and a dataset is 16 clips, where 7.5 min each
        # costs two hours before training even starts.
        ds_steps = sr.LIGHTNING["steps"] if not args.no_lightning else args.steps
        ds_loras = list(sr.LIGHTNING["i2v"]) if not args.no_lightning else None
        wf = sr.build_video_workflow(
            "wan", "i2v", prompt, seed=4242 + i, clip_prefix=prefix,
            frames=CLIP_FRAMES, res_config=rc, negative_prompt=neg,
            steps=ds_steps, image_name=seed_image, optimization="fast",
            loras=ds_loras,
        )
        if not args.no_lightning:
            sr.apply_lightning(wf, steps=ds_steps)
        print(f"  [{i}/{len(motions)}] {slug} ...", flush=True)
        pid = sr.queue_prompt(wf)
        if not sr.poll_until_done(pid):
            print("    WARNING: clip failed")
            failed.append(slug)
            continue
        produced = sr.find_latest_clip(prefix)
        if produced:
            shutil.copy2(produced, target)
            print(f"    saved {target.name}")
        else:
            print("    WARNING: clip not found on disk")
            failed.append(slug)

    have = len(list(clips_dir.glob("*.mp4")))
    print(f"\n{have}/{len(motions)} clips in {clips_dir}")
    if failed:
        # Exit non-zero so the job runner retries instead of marching on to
        # frame extraction with nothing to extract. Clips that did succeed are
        # skipped on the retry, so a retry only fills the gaps.
        print(f"FAILED clips: {', '.join(failed)}")
        sys.exit(1)


# ── stage: frames ────────────────────────────────────────────────────
def cmd_frames(args):
    name = args.name
    d = build_dir(name)
    clips_dir = d / "clips"
    clips = sorted(clips_dir.glob("*.mp4"))
    if not clips:
        sys.exit(f"No clips in {clips_dir}. Run 'clips' first.")

    out = DATASETS / name
    out.mkdir(parents=True, exist_ok=True)
    brief = load_brief(name)
    trigger = brief["trigger"]
    cap_by_slug = {slug: cap for slug, _m, cap in motions_for(brief)}

    # Harvest from the first ~70% of each clip: WAN I2V holds the seeded
    # identity best early, and drifts toward the end.
    n = 0
    for clip in clips:
        dur = sr._get_video_duration(str(clip)) or (CLIP_FRAMES / 16)
        # Use the full clip: identity proved stable end-to-end, and the later
        # frames are where the pose actually differs from the seed portrait.
        usable = dur * 0.95
        stamps = [usable * (k + 1) / (args.per_clip + 1) for k in range(args.per_clip)]
        for t in stamps:
            n += 1
            img = out / f"{name}_{n:03d}.png"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(clip),
                 "-frames:v", "1", str(img)],
                check=False, timeout=60,
            )
            if not img.exists():
                n -= 1
                continue
            shot = cap_by_slug.get(clip.stem, "Medium shot")
            (out / f"{name}_{n:03d}.txt").write_text(f"{trigger}. {shot}.\n")

    # The canonical portrait itself is the cleanest reference in the set.
    canonical = d / "canonical.png"
    if canonical.exists():
        n += 1
        shutil.copy2(canonical, out / f"{name}_{n:03d}.png")
        (out / f"{name}_{n:03d}.txt").write_text(
            f"{trigger}. Head and shoulders portrait, facing camera, "
            f"neutral expression, plain background.\n")

    print(f"Wrote {n} image/caption pairs to {out}")
    print("Captions name the trigger and the SHOT only -- never his appearance,")
    print("so the LoRA learns the face rather than a description of it.")


# ── stage: config ────────────────────────────────────────────────────
TOML = """[general]
resolution = [480, 480]
caption_extension = ".txt"
batch_size = 1
enable_bucket = true
bucket_no_upscale = false

[[datasets]]
image_directory = "/workspace/datasets/{name}"
cache_directory = "/workspace/training_models/wan22/cache_v3/{name}{suffix}"
num_repeats = {repeats}
"""


def cmd_config(args):
    name = args.name
    imgs = sorted((DATASETS / name).glob("*.png"))
    if not imgs:
        sys.exit(f"No images in {DATASETS / name}. Run 'frames' first.")
    # Small sets benefit from repeats so each epoch sees enough samples.
    repeats = 1 if len(imgs) >= 40 else 2
    # One config for both ranks: the cached latents and text-encoder outputs
    # depend on resolution/VAE/T5, not on LoRA rank, so the rank-32 and
    # rank-64 runs share a cache instead of building it twice.
    p = Path(f"/workspace/training_models/wan22/dataset_{name}_v3.toml")
    p.write_text(TOML.format(name=name, suffix="", repeats=repeats))
    print(f"  wrote {p}")
    print(f"\n{len(imgs)} images, num_repeats={repeats}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("portraits"); p.add_argument("name")
    p.add_argument("--count", type=int, default=8); p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_portraits)

    p = sub.add_parser("pick"); p.add_argument("name")
    p.add_argument("--candidate", type=int, required=True); p.set_defaults(fn=cmd_pick)

    p = sub.add_parser("clips"); p.add_argument("name")
    p.add_argument("--count", type=int, default=8)
    p.add_argument("--steps", type=int, default=18); p.add_argument("--force", action="store_true")
    p.add_argument("--no-lightning", action="store_true",
                   help="undistilled sampling: ~6x slower and not better")
    p.set_defaults(fn=cmd_clips)

    p = sub.add_parser("frames"); p.add_argument("name")
    p.add_argument("--per-clip", type=int, default=4); p.set_defaults(fn=cmd_frames)

    p = sub.add_parser("config"); p.add_argument("name"); p.set_defaults(fn=cmd_config)

    args = ap.parse_args()
    sr.set_current_series(None)
    args.fn(args)


if __name__ == "__main__":
    main()
