#!/usr/bin/env python3
"""
Cut the separate pieces into one film.

Four pieces played end to end are not a film: each was written self-contained,
so the assembly opens four times, restates itself, and stops just before its
climax. The EDIT below fixes that structurally, without re-rendering a frame:

  1. ARRIVAL   (ep06)  he cannot stop counting
  2. FAREWELL  (ep05)  she warns him
  3. CROSS-CUT (ep08 x ep07)  her waiting played AGAINST his ruin, alternating
                       shot for shot, so every pair is an ironic rhyme --
                       "you have been gone one day, I have counted it" against
                       "being right is worth nothing at all", and finally
                       "come back and I will learn to count" against
                       "there is nobody left to lift me down"
  4. ENDING    (ep09)  he gets down; the last face in the film is hers

Played sequentially those twelve middle shots are two monologues. Interleaved
they are one scene, and the interleave costs nothing -- it is an edit of
footage that already exists.

The soundtrack is rebuilt across the whole film rather than four times: one
score, and the ambience bed follows the LOCATION of each shot, so the cross-cut
audibly moves between the valley and the ruin.

    assemble_film.py <series> -o film.mp4
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import sound_design as sd                                      # noqa: E402


def _interleave(a: list, b: list) -> list:
    out = []
    for i in range(max(len(a), len(b))):
        if i < len(a):
            out.append(a[i])
        if i < len(b):
            out.append(b[i])
    return out


# A held frame at the end of a line is a beat; too much of one reads as the
# video stalling. Shots whose line is short against their authored beat end up
# mostly frozen -- ep07_s04 was 4.0s live and 4.0s held -- so the edit trims
# them back. This is an editorial cap, applied at assembly, so changing it
# costs nothing and re-rendering is never required.
MAX_HELD_SHARE = 0.40
# A hold is perceived in SECONDS, not as a proportion of its shot: two seconds
# reads as a beat whether the shot is eight seconds or twelve, and five seconds
# reads as the video having stopped. Capping only by share left 4-5s freezes on
# the longest shots, which is exactly where they were noticed.
MAX_HELD_SECONDS = 2.0


def _trim_to(clip: str, seconds: float, out: str) -> str:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip,
                    "-t", f"{seconds:.3f}", "-c:v", "libx264", "-crf", "16",
                    "-an", out], check=True)
    return out


def build_edit(series: str) -> list[dict]:
    def scenes(ep):
        return json.loads(
            (sr.series_path(series) / "episodes" / f"{ep}.json").read_text())["scenes"]

    arrival = [("ep06", s) for s in scenes("ep06")]
    farewell = [("ep05", s) for s in scenes("ep05")]
    her = [("ep08", s) for s in scenes("ep08")]
    him = [("ep07", s) for s in scenes("ep07")]
    ending = [("ep09", s) for s in scenes("ep09")]
    order = arrival + farewell + _interleave(her, him) + ending

    edit = []
    for ep, sc in order:
        clip = sr.find_latest_clip(sc["id"])
        if not clip:
            print(f"  MISSING {sc['id']} -- render it before assembling")
            continue
        loc = sc.get("location")
        preset = sd.PRESET_BY_LOCATION.get(loc)
        if not preset:
            raise SystemExit(f"no ambience bed mapped for '{loc}'")
        vo = Path("output") / series / ep / "audio" / f"{sc['id']}.mp3"
        dur = sr._get_video_duration(clip)
        spoken = sr._get_video_duration(str(vo)) if vo.exists() else 0.0
        live = min(dur, spoken + sr.S2V_LIVE_TAIL) if spoken > 0 else dur
        held = max(0.0, dur - live)
        if dur > 0 and (held / dur > MAX_HELD_SHARE or held > MAX_HELD_SECONDS):
            keep = min(live / (1.0 - MAX_HELD_SHARE), live + MAX_HELD_SECONDS)
            trimmed = str(Path("/workspace/review/wow/_film") /
                          f"trim_{sc['id']}.mp4")
            Path(trimmed).parent.mkdir(parents=True, exist_ok=True)
            _trim_to(clip, keep, trimmed)
            print(f"  trimmed {sc['id']} {dur:.2f}s -> {keep:.2f}s "
                  f"({held/dur*100:.0f}% was a held frame)")
            clip, dur = trimmed, sr._get_video_duration(trimmed)
        edit.append({
            "id": sc["id"], "ep": ep, "clip": clip, "location": loc,
            "preset": preset, "staging": sc.get("staging", "medium"),
            "seconds": round(dur, 3),
            "vo": str(vo) if vo.exists() else None,
        })
    return edit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("-o", "--out", default="/workspace/review/wow/film.mp4")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    sr.set_current_series(a.series)
    edit = build_edit(a.series)
    total = sum(e["seconds"] for e in edit)
    print(f"  {len(edit)} shots, {total:.1f}s ({total/60:.1f} min)\n")
    prev_loc = None
    for i, e in enumerate(edit):
        mark = " <- cut to" if e["location"] != prev_loc else ""
        print(f"  {i+1:2}. {e['id']:10} {e['seconds']:5.2f}s  {e['location']:15}{mark}")
        prev_loc = e["location"]
    if a.dry_run:
        return 0

    work = Path(a.out).parent / "_film"
    work.mkdir(parents=True, exist_ok=True)

    # ── picture ──────────────────────────────────────────────────────────
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{Path(e['clip']).resolve()}'\n" for e in edit))
    silent = work / "picture.mp4"
    # Re-encode rather than stream-copy: the clips come from different renders
    # and a concat demuxer copy across mismatched GOP structures produces a
    # file that plays locally and stutters everywhere else.
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c:v", "libx264", "-crf", "16",
                    "-pix_fmt", "yuv420p", "-an", str(silent)], check=True)

    # ── soundtrack, built once across the whole film ─────────────────────
    offsets, t = [], 0.0
    for e in edit:
        offsets.append(t)
        t += e["seconds"]
    plan = [{"id": e["id"], "seconds": e["seconds"], "staging": e["staging"],
             "preset": e["preset"], "vo": e["vo"]} for e in edit]
    mix = work / "film.wav"
    sd.mix_episode(plan, work, mix, preset=edit[0]["preset"],
                   offsets=offsets, vo_lead=0.0)

    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent),
                    "-i", str(mix), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", str(a.out)], check=True)
    print(f"\n  {a.out}  ({Path(a.out).stat().st_size/1e6:.1f} MB, {total:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
