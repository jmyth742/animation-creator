#!/usr/bin/env python3
"""
Rebuild an episode's SRT on the corrected timeline and re-burn it.

The old SRT was timed against the sum of clip lengths, ignoring that the
stitcher overlaps every boundary with a crossfade -- so cues drifted ~4.5s
late over an episode and the closing subtitles appeared after their audio had
finished. This regenerates the SRT with scene_start_offsets() and burns it
onto the ungraded-subtitles master, so no re-render is needed.

    python scripts/refresh_subtitles.py <series> --episode 1 [--interpolate 3]
"""
import argparse, shutil, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, default=1)
    ap.add_argument("--music", default=None,
                    help="music bed filename in ambience/ (e.g. music.mp3)")
    ap.add_argument("--no-restitch", action="store_true",
                    help="only rebuild the SRT; do not re-mux and re-join the clips")
    ap.add_argument("--interpolate", type=int, default=0,
                    help="also produce an Nx frame-interpolated cut (e.g. 3 = 16->48fps)")
    a = ap.parse_args()
    sr.set_current_series(a.series)

    ep_num = a.episode
    ep_out = sr.OUTPUT_DIR / a.series / f"ep{ep_num:02d}"
    ep = sr.load_json(sr.episode_path(a.series, ep_num))
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")

    audio_dir = ep_out / "audio"
    audio_files = []
    for scene in ep["scenes"]:
        f = audio_dir / f"{scene['id']}.mp3"
        audio_files.append(f if f.exists() else None)
    print(f"  {sum(1 for x in audio_files if x)}/{len(audio_files)} audio files found")

    # Re-stitch by default. The audio fix lives in _mux_clip_audio, so simply
    # re-burning subtitles onto the old master would leave the 15s audio
    # shortfall in place -- every clip has to be re-muxed and re-joined.
    if not a.no_restitch:
        stitched = ep_out / f"ep{ep_num:02d}_stitched.mp4"
        print("  re-stitching picture from existing clips (no re-render)...")
        # Picture only. Audio is laid on an absolute timeline afterwards:
        # muxing per clip and joining with acrossfade fades every line in over
        # the crossfade and bleeds the previous one across it.
        sr.stitch_clips_with_audio(ep["scenes"], audio_files, stitched,
                                   crossfade=True, bible=bible, use_ambience=True)
        total = sr._get_video_duration(str(stitched))
        offsets = sr.scene_start_offsets(ep["scenes"])
        wav = ep_out / f"ep{ep_num:02d}_timeline.wav"
        music = None
        if a.music:
            cand = sr.AMBIENCE_DIR / a.music
            music = cand if cand.exists() else None
            if not music:
                print(f"  WARNING: music bed {a.music} not found in {sr.AMBIENCE_DIR}")
        if sr.build_timeline_audio(ep["scenes"], audio_files, offsets, total, wav,
                                   bible=bible, use_ambience=True, music=music):
            remuxed = ep_out / f"ep{ep_num:02d}_timeline.mp4"
            if sr.run_ffmpeg(["ffmpeg", "-y", "-i", str(stitched), "-i", str(wav),
                              "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                              "-c:a", "aac", "-b:a", "192k", "-shortest", str(remuxed)],
                             "timeline mux", remuxed):
                stitched = remuxed
                print(f"  timeline audio laid{' with music' if music else ''}")
        vd = sr._get_video_duration(str(stitched))
        print(f"  stitched: {vd:.2f}s")
        graded_out = ep_out / f"ep{ep_num:02d}_graded.mp4"
        print("  applying colour grade...")
        sr.apply_colour_grade(stitched, graded_out)

    srt = ep_out / f"ep{ep_num:02d}.srt"
    sr.generate_srt(ep, bible, srt, audio_files=audio_files)
    tail = [l for l in srt.read_text().strip().splitlines() if "-->" in l]
    print(f"  SRT rebuilt: {len(tail)} cues, last ends {tail[-1].split('-->')[1].strip()}")

    graded = ep_out / f"ep{ep_num:02d}_graded.mp4"
    final = ep_out / f"ep{ep_num:02d}_final.mp4"
    if not graded.exists():
        sys.exit(f"  missing {graded}")
    print("  burning subtitles...")
    sr.burn_subtitles(graded, srt, final)
    dur = sr._get_video_duration(str(final))
    print(f"  {final}  ({dur:.2f}s)")

    if a.interpolate > 1:
        smooth = ep_out / f"ep{ep_num:02d}_final_{16 * a.interpolate}fps.mp4"
        print(f"  interpolating {a.interpolate}x...")
        if sr.interpolate_video(final, smooth, multiplier=a.interpolate):
            print(f"  {smooth}")
        else:
            print("  interpolation failed")


if __name__ == "__main__":
    main()
