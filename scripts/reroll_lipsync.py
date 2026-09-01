#!/usr/bin/env python3
"""
Re-roll dialogue shots whose lips do not track their line.

Lip sync is per-shot lottery: measured across ep13/ep14, the ratio of mouth
motion while speaking to mouth motion while silent runs from 15x (excellent)
to 0.73x (inverted -- the mouth moves MORE in the pauses). The cause was
chased twice (chunk count, assembly drift) and both theories died; what
survived is that the METRIC reliably identifies bad shots, which is enough
to fix them without explaining them.

For each shot below the threshold: re-render with shifted seeds, keep the
take with the best ratio, and install it beside the original (held to the
authored length) only if it actually beats the current one.

    reroll_lipsync.py <series> --episode 14 --threshold 1.5 --takes 2
    reroll_lipsync.py <series> --from-qc /workspace/review/qc_series.json
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import episode_qc as qc                                        # noqa: E402

SEQ = re.compile(r"^(?P<stem>.+?)_(?P<n>\d+)_?\.mp4$", re.IGNORECASE)


def next_name(original: Path) -> Path:
    m = SEQ.match(original.name)
    n, d = (int(m.group("n")) if m else 60000), original.parent
    stem = m.group("stem") if m else original.stem
    while True:
        n += 1
        c = d / f"{stem}_{n:05d}_.mp4"
        if not c.exists():
            return c


def fix_shot(series, ep_num, scene, bible, threshold, takes, steps):
    sid = scene["id"]
    cur = sr.find_latest_clip(sid)
    vo = Path("output") / series / f"ep{ep_num:02d}" / "audio" / f"{sid}.mp3"
    if not (cur and vo.exists()):
        return None
    base = qc.lip_ratio(cur, vo)
    if base is None or base >= threshold:
        return None
    print(f"  {sid}: lip {base}x — re-rolling", flush=True)
    res = sr.get_resolution_config("480p", "wan")
    spoken = sr._get_video_duration(str(vo))
    padded = str(vo.with_name(f"{sid}_lr.mp3"))
    sr.pad_audio_to(str(vo), spoken + sr.S2V_LIVE_TAIL, padded)
    frames, extra, tail = sr.s2v_chunks_for_duration(
        spoken + sr.S2V_LIVE_TAIL, fps=16, floor_seconds=spoken)
    seed_img = sr.get_scene_seed_image(scene, series, None)
    audio = sr.copy_to_input(padded)
    best = (base, None)
    for k in range(takes):
        prefix = f"lr_{sid}_t{k}"
        clip = sr.find_latest_clip(prefix)
        if not clip:
            wf = sr.build_video_workflow(
                "wan", "s2v", sr.build_scene_prompt(scene, bible),
                7900 + k * 1511, prefix, frames, res,
                negative_prompt=sr.build_negative_prompt(scene),
                steps=steps, image_name=seed_img, audio_path=audio,
                extra_chunks=extra, last_chunk_frames=tail)
            try:
                pid = sr.queue_prompt(wf)
                if not sr.poll_until_done(pid, max_wait=2400 * (1 + extra)):
                    continue
            except Exception as e:                             # noqa: BLE001
                print(f"    take {k}: {type(e).__name__}"); continue
            clip = sr.find_latest_clip(prefix)
        if not clip:
            continue
        r = qc.lip_ratio(clip, vo)
        print(f"    take {k}: lip {r}x", flush=True)
        if r is not None and r > best[0]:
            best = (r, clip)
    if best[1] is None:
        print(f"    no take beat {base}x — keeping the original")
        return {"shot": sid, "was": base, "best": base, "installed": False}
    # hold to the authored length so it drops in without desynchronising
    hold = float(scene.get("hold_seconds") or 0)
    have = sr._get_video_duration(best[1])
    src = best[1]
    if hold > have + 0.1:
        held = f"/tmp/lr_{sid}_held.mp4"
        sr.hold_tail(best[1], hold, held)
        src = held
    dst = next_name(Path(cur))
    shutil.copy(src, dst)
    print(f"    installed {best[0]}x -> {dst.name}", flush=True)
    return {"shot": sid, "was": base, "best": best[0], "installed": True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--episode", type=int)
    ap.add_argument("--from-qc")
    ap.add_argument("--threshold", type=float, default=1.5)
    ap.add_argument("--takes", type=int, default=2)
    ap.add_argument("--steps", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0,
                    help="cap the number of shots, worst ratio first — 38 "
                         "flagged shots at ~2 takes each is more night than "
                         "the night has")
    ap.add_argument("--min-episode", type=int, default=0,
                    help="skip legacy episodes below this number")
    a = ap.parse_args()
    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")

    targets = {}                       # ep -> [shot ids] or None for all-dialogue
    if a.from_qc and Path(a.from_qc).exists():
        for r in json.loads(Path(a.from_qc).read_text()):
            bad = [s["id"] for s in r.get("shots", [])
                   if "lip" in str(s.get("issue", "")) + str(s.get("warn", ""))]
            if bad:
                targets[r["episode"]] = bad
    elif a.episode:
        targets[a.episode] = None
    else:
        sys.exit("need --episode or --from-qc")

    # Flatten to (ratio, ep, scene) and take the worst first, so a capped
    # run spends its takes where the sync is most broken.
    work = []
    for ep_num, shots in sorted(targets.items()):
        if ep_num < a.min_episode:
            continue
        ep = sr.load_json(sr.episode_path(a.series, ep_num))
        for scene in ep["scenes"]:
            if not scene.get("dialogue"):
                continue
            if shots is not None and scene["id"] not in shots:
                continue
            cur = sr.find_latest_clip(scene["id"])
            vo = (Path("output") / a.series / f"ep{ep_num:02d}" / "audio"
                  / f"{scene['id']}.mp3")
            r0 = qc.lip_ratio(cur, vo) if (cur and vo.exists()) else None
            if r0 is not None and r0 < a.threshold:
                work.append((r0, ep_num, scene))
    work.sort(key=lambda w: w[0])
    if a.limit:
        dropped = len(work) - a.limit
        work = work[:a.limit]
        if dropped > 0:
            print(f"  capped at {a.limit} worst shots ({dropped} deferred)")
    results, touched = [], set()
    for _, ep_num, scene in work:
        r = fix_shot(a.series, ep_num, scene, bible, a.threshold,
                     a.takes, a.steps)
        if r:
            results.append(r)
            if r["installed"]:
                touched.add(ep_num)
    fixed = sum(1 for r in results if r["installed"])
    print(f"\n  {fixed}/{len(results)} weak shots improved and installed")
    if touched:
        print(f"  re-stitch episodes: {sorted(touched)}")
    Path("/workspace/review/lipsync_reroll.json").write_text(
        json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
