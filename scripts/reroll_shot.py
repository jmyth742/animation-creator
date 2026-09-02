#!/usr/bin/env python3
"""
Re-render one shot with a fresh seed and install the take beside the live one.

The single most-wanted button in any cutting room: "this one again, different
dice." Dialogue goes back through S2V with its own line; silent shots through
I2V from whatever seed the scene prescribes. The new take lands with the next
sequence number, so it becomes live immediately -- the takes browser can put
the old one back with one tap, and a re-stitch folds it into the final.

    reroll_shot.py <series> <shot_id> [--seed-shift N]
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

SEQ = re.compile(r"^(?P<stem>.+?)_(?P<n>\d+)_?\.mp4$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("shot")
    ap.add_argument("--seed-shift", type=int, default=0)
    a = ap.parse_args()
    sr.set_current_series(a.series)
    ep_num = int(a.shot.split("_")[0][2:])
    ep = sr.load_json(sr.episode_path(a.series, ep_num))
    scene = next((s for s in ep["scenes"] if s["id"] == a.shot), None)
    if not scene:
        sys.exit(f"[reroll] no shot {a.shot}")
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    res = sr.get_resolution_config("480p", "wan")
    cur = sr.find_latest_clip(a.shot)
    takes = len(list((Path("ComfyUI/output/video") / a.series)
                     .glob(f"{a.shot}_*.mp4")))
    seed = 31000 + takes * 977 + a.seed_shift
    prompt = sr.build_scene_prompt(scene, bible)
    neg = sr.build_negative_prompt(scene)
    seed_img = sr.get_scene_seed_image(scene, a.series, None)
    prefix = f"rr1_{a.shot}_{takes}"
    if scene.get("dialogue"):
        vo = (Path("output") / a.series / f"ep{ep_num:02d}" / "audio"
              / f"{a.shot}.mp3")
        if not vo.exists():
            sys.exit(f"[reroll] no voice track {vo}")
        spoken = sr._get_video_duration(str(vo))
        padded = str(vo.with_name(f"{a.shot}_rr1.mp3"))
        sr.pad_audio_to(str(vo), spoken + sr.S2V_LIVE_TAIL, padded)
        frames, extra, tail = sr.s2v_chunks_for_duration(
            spoken + sr.S2V_LIVE_TAIL, fps=16, floor_seconds=spoken)
        wf = sr.build_video_workflow(
            "wan", "s2v", prompt, seed, prefix, frames, res,
            negative_prompt=neg, steps=10, image_name=seed_img,
            audio_path=sr.copy_to_input(padded), extra_chunks=extra,
            last_chunk_frames=tail)
        budget = 2400 * (1 + extra)
    else:
        loras = sr.get_scene_loras(scene, bible)
        wf = sr.build_video_workflow(
            "wan", "i2v", prompt, seed, prefix, sr.MAX_FRAMES, res,
            negative_prompt=neg, steps=8, image_name=seed_img,
            loras=loras or None)
        budget = 1800
    print(f"[reroll] {a.shot} take {takes + 1}, seed {seed}", flush=True)
    pid = sr.queue_prompt(wf)
    if not sr.poll_until_done(pid, max_wait=budget):
        sys.exit("[reroll] FAILED: no output")
    clip = sr.find_latest_clip(prefix)
    if not clip:
        sys.exit("[reroll] FAILED: clip missing")
    hold = float(scene.get("hold_seconds") or 0)
    have = sr._get_video_duration(clip)
    src = clip
    if hold > have + 0.1:
        held = f"/tmp/rr1_{a.shot}.mp4"
        sr.hold_tail(clip, hold, held)
        src = held
    m = SEQ.match(Path(cur).name) if cur else None
    stem = m.group("stem") if m else a.shot
    n = 1
    d = Path("ComfyUI/output/video") / a.series
    while (d / f"{stem}_{n:05d}_.mp4").exists():
        n += 1
    dst = d / f"{stem}_{n:05d}_.mp4"
    shutil.copy(src, dst)
    print(f"[reroll] DONE -> {dst.name} (now live; re-stitch to fold in)",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
