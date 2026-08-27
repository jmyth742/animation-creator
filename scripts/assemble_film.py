#!/usr/bin/env python3
"""
Cut the separate pieces into one film.

Four pieces played end to end are not a film: each was written self-contained,
so the assembly opens four times, restates itself, and stops just before its
climax. The EDIT below fixes that structurally, without re-rendering a frame:

  0. PRELUDE   (ep10)  how they met on the Irish cliffs and rode west
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
import camera_move as cam                                      # noqa: E402
import grade as gr                                             # noqa: E402
import titles as ti                                            # noqa: E402


ONLY_EPISODES: set[str] = set()


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

    prelude = [("ep10", s) for s in scenes("ep10")]
    arrival = [("ep06", s) for s in scenes("ep06")]
    farewell = [("ep05", s) for s in scenes("ep05")]
    her = [("ep08", s) for s in scenes("ep08")]
    him = [("ep07", s) for s in scenes("ep07")]
    ending = [("ep09", s) for s in scenes("ep09")]
    # The prelude opens: how they met and rode west. Then the myth in order.
    order = prelude + arrival + farewell + _interleave(her, him) + ending
    if ONLY_EPISODES:
        # Cut a single piece rather than the whole film. Without this the
        # --title flag was the ONLY thing that changed, so asking for "the
        # prelude, with a post pass" silently produced the main film wearing
        # the prelude's title card.
        order = [(ep, sc) for ep, sc in order if ep in ONLY_EPISODES]
        if not order:
            raise SystemExit(f"no shots for episodes {sorted(ONLY_EPISODES)}")

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
    ap.add_argument("--post", action="store_true",
                    help="camera moves, per-location grade, title and end cards")
    ap.add_argument("--episodes", help="comma-separated, e.g. ep10 — cut one "
                                       "piece instead of the whole film")
    ap.add_argument("--title", default="Tir na nOg")
    ap.add_argument("--subtitle", default="a film in four movements")
    a = ap.parse_args()

    sr.set_current_series(a.series)
    if a.episodes:
        globals()["ONLY_EPISODES"] = {e.strip() for e in a.episodes.split(",")}
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

    # ── post: a camera and a grade on every shot ─────────────────────────
    # Both are edit-time and deterministic, so they can be re-judged and
    # changed without touching the GPU. The camera move is free at 1080p
    # because the upscale already produces 3328x1920; at 832x480 it costs a
    # little resolution, which is why the move is small.
    if a.post:
        post_dir = work / "post"; post_dir.mkdir(exist_ok=True)
        for e in edit:
            kind = cam.MOVE_BY_STAGING.get(e["staging"], "push")
            # A silent shot with no character is a landscape: let it drift.
            if not e.get("vo"):
                kind = "drift"
            moved = str(post_dir / f"mv_{e['id']}.mp4")
            cam.apply_move(e["clip"], kind, moved)
            graded = str(post_dir / f"gr_{e['id']}.mp4")
            gr.apply_grade(moved, e["location"], graded)
            e["clip"] = graded
            e["move"] = kind
        moves = {}
        for e in edit:
            moves[e["move"]] = moves.get(e["move"], 0) + 1
        print(f"\n  camera: {moves}")
        print(f"  graded per location: "
              f"{sorted({e['location'] for e in edit})}")

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

    body = work / "body.mp4" if a.post else Path(a.out)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent),
                    "-i", str(mix), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", str(body)], check=True)

    # ── title and end cards ──────────────────────────────────────────────
    if a.post:
        w, h = 1920, 1080
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0",
             str(body)], capture_output=True, text=True).stdout.strip().split(",")
        w, h = int(probe[0]), int(probe[1])
        ti.W, ti.H = w, h
        card = str(work / "title.mp4")
        endc = str(work / "end.mp4")
        ti.title_card(a.title, a.subtitle, card, seconds=4.0)
        ti.end_card([a.title, "a folk tale",
                     "rendered on one graphics card"], endc, seconds=6.0)
        # Cards are silent; give them a matching silent track so concat does
        # not drop the audio stream of the film between them.
        lst2 = work / "final.txt"
        parts = []
        for i, seg in enumerate((card, str(body), endc)):
            fixed = str(work / f"part{i}.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", seg,
                            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                            "-map", "0:v", "-map", "1:a?" if i != 1 else "0:a",
                            "-shortest", "-c:v", "libx264", "-crf", "16",
                            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                            fixed], check=True)
            parts.append(fixed)
        lst2.write_text("".join(f"file '{Path(p).resolve()}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat",
                        "-safe", "0", "-i", str(lst2), "-c", "copy",
                        str(a.out)], check=True)
    print(f"\n  {a.out}  ({Path(a.out).stat().st_size/1e6:.1f} MB, {total:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
