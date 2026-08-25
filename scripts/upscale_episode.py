#!/usr/bin/env python3
"""
Upscale a finished episode to 1080p with an anime-domain model.

WHY THIS MODEL
Measured on cel frames from ep05, every candidate resampled to 1920x1080 so
the comparison is not just "the bigger image has more pixels":

    lanczos to 1080p              edge  4.90   flat 0.1137   (what we do today)
    RealESRGAN_x4plus_anime_6B    edge 19.79   flat 0.0108   3.25x / 0.10x
    4x-AnimeSharp                 edge 11.04   flat 0.1440   1.81x / 1.28x

Cel art needs BOTH hard edges and flat interiors. RealESRGAN's anime 6B wins
on both axes -- 3.25x the line definition AND a tenth of the texture inside
flat colour. 4x-AnimeSharp sharpens but grows texture in the flats, which is
the waxy look that made native 720p worse than upscaling 480p.

WHY SEGMENTS
A whole episode in one IMAGE tensor at 4x is about 69 GB. The video is cut
into short segments, each upscaled in its own prompt, then concatenated. The
model stays resident between prompts, so the segmentation costs little.

    upscale_episode.py <series> --episode N [--seg 1.5]
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

MODEL = "RealESRGAN_x4plus_anime_6B.pth"
OUT_W, OUT_H = 1920, 1080


def _build(video_name: str, prefix: str, fps: float) -> dict:
    return {
        "1": {"class_type": "LoadVideo", "inputs": {"file": video_name}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "3": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": MODEL}},
        "4": {"class_type": "ImageUpscaleWithModel",
              "inputs": {"upscale_model": ["3", 0], "image": ["2", 0]}},
        # 4x lands at 3328x1920. Coming back down to 1080p with lanczos keeps
        # the model's line work while hitting the delivery size exactly.
        "5": {"class_type": "ImageScale",
              "inputs": {"image": ["4", 0], "upscale_method": "lanczos",
                         "width": OUT_W, "height": OUT_H, "crop": "disabled"}},
        "6": {"class_type": "CreateVideo",
              "inputs": {"images": ["5", 0], "fps": float(fps)}},
        "7": {"class_type": "SaveVideo",
              "inputs": {"video": ["6", 0], "filename_prefix": prefix,
                         "format": "mp4", "codec": "h264"}},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("--seg", type=float, default=1.5,
                    help="seconds per segment; bounds peak VRAM")
    ap.add_argument("--source", default=None)
    a = ap.parse_args()

    sr.set_current_series(a.series)
    ep_dir = Path("output") / a.series / f"ep{a.episode:02d}"
    tag = f"ep{a.episode:02d}"
    src = Path(a.source) if a.source else None
    if src is None:
        for cand in (f"{tag}_designed.mp4", f"{tag}_graded.mp4", f"{tag}_final.mp4"):
            if (ep_dir / cand).exists():
                src = ep_dir / cand
                break
    if not src or not src.exists():
        print(f"  nothing to upscale in {ep_dir}")
        return 1

    fps = float(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=r_frame_rate", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True).stdout.strip().split("/")[0])
    dur = sr._get_video_duration(str(src))
    print(f"  source {src.name}  {dur:.2f}s @ {fps:.0f}fps -> {OUT_W}x{OUT_H}")

    work = ep_dir / "_upscale"
    work.mkdir(parents=True, exist_ok=True)
    for old in work.glob("*.mp4"):
        old.unlink()
    # Split on keyframes-agnostic fixed segments; re-encode so every segment
    # decodes independently.
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-an",
         "-c:v", "libx264", "-crf", "12", "-g", "8",
         "-f", "segment", "-segment_time", f"{a.seg}", "-reset_timestamps", "1",
         str(work / "seg_%04d.mp4")], check=True)
    segs = sorted(work.glob("seg_*.mp4"))
    print(f"  {len(segs)} segments of ~{a.seg}s")

    done = []
    for i, seg in enumerate(segs):
        staged = sr.copy_to_input(str(seg))
        prefix = f"up_{tag}_{i:04d}"
        wf = _build(staged, sr.save_prefix(prefix), fps)
        try:
            pid = sr.queue_prompt(wf)
        except Exception as e:                                 # noqa: BLE001
            print(f"    segment {i}: queue failed {e}")
            return 1
        if not sr.poll_until_done(pid, poll_interval=5, max_wait=900):
            print(f"    segment {i}: no output")
            return 1
        got = sr.find_latest_clip(prefix)
        if not got:
            print(f"    segment {i}: clip missing")
            return 1
        dst = work / f"up_{i:04d}.mp4"
        dst.write_bytes(Path(got).read_bytes())
        done.append(dst)
        if (i + 1) % 5 == 0 or i == len(segs) - 1:
            print(f"    {i + 1}/{len(segs)} segments", flush=True)

    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in done))
    silent = work / "joined.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c", "copy", str(silent)], check=True)

    out = ep_dir / f"{tag}_1080p.mp4"
    # Carry the finished soundtrack across untouched -- the upscale is picture
    # only, and re-encoding the audio here would undo the mix's loudness pass.
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent),
                    "-i", str(src), "-map", "0:v", "-map", "1:a?",
                    "-c:v", "copy", "-c:a", "copy", "-shortest", str(out)],
                   check=True)
    print(f"  {out}  ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
