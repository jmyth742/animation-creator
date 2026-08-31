#!/usr/bin/env python3
"""
Bring an episode built on the old pipeline up to the current standard.

ep05-ep11 predate everything learned since: their wides collapsed to
close-ups, their dialogue closes are seeded from bare portraits and so are set
nowhere, they have no camera on any shot, and they were upscaled with lanczos
because the ESRGAN path checked for a binary that was never installed.

ep12-ep16 have all of that fixed. This applies the same treatment to an older
episode, in the order that matters:

    1  wides re-rendered from GENERATED plates      0.83 -> 0.97 p(wide)
    2  dialogue closes re-seeded IN their location  and held to the authored
                                                    length so they install
    3  a camera pass                                1.43x motion, free
    4  re-stitch                                    grade, ESRGAN, audio kept

Every step writes beside the original with a higher sequence number, so
nothing is destroyed and `produce --resume` picks up the newest take.

    modernise_episode.py <series> --episode 7
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

HERE = Path(__file__).parent
PY = sys.executable


def run(label, cmd, tail=12):
    print(f"\n  ── {label} ──", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = [l for l in r.stdout.splitlines() if l.strip()][-tail:]
    for l in out:
        print(f"    {l[:120]}", flush=True)
    if r.returncode != 0:
        err = (r.stderr or "").strip().splitlines()[-3:]
        for l in err:
            print(f"    ERR {l[:120]}")
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("--skip-closes", action="store_true")
    a = ap.parse_args()
    e, s = a.episode, a.series

    run(f"ep{e:02d} · wides from generated plates",
        [PY, str(HERE / "upgrade_wides.py"), s, "--episode", str(e)], 16)

    if not a.skip_closes:
        run(f"ep{e:02d} · closes re-seeded in location",
            [PY, str(HERE / "repair_dialogue_closes.py"), s, "--episode", str(e)], 14)
        run(f"ep{e:02d} · install closes",
            [PY, str(HERE / "install_repaired_closes.py"), s, "--episode", str(e)], 14)

    run(f"ep{e:02d} · camera pass",
        [PY, str(HERE / "add_camera_to_episode.py"), s, "--episode", str(e)], 6)

    run(f"ep{e:02d} · re-stitch",
        [PY, str(HERE / "showrunner.py"), "produce", s, "--episode", str(e),
         "--quality", "final", "--upscale", "--resume"], 10)

    f = Path("output") / s / f"ep{e:02d}" / f"ep{e:02d}_final.mp4"
    if f.exists():
        st = sorted(sr._streams(f))
        print(f"\n  ep{e:02d}: {sr._get_video_duration(f):6.1f}s {st} "
              f"{'OK' if 'audio' in st else 'MISSING AUDIO'}")
    else:
        print(f"\n  ep{e:02d}: no final produced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
