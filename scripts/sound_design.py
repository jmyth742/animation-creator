#!/usr/bin/env python3
"""
Layered sound design, built locally with FFmpeg.

WHY THIS EXISTS
The pipeline's ambience was one filtered-noise bed per location, mono, at a
constant level, laid flat under the whole episode. That reads as hiss. What
makes a scene sound like it was designed rather than generated is not a better
noise source; it is four things this module adds:

  1. LAYERS at different distances. A headland is sea swell below you, wind
     around you, grass and cloth close to the mic, and gulls somewhere else
     entirely. One bed collapses all of that into a single plane.

  2. MOVEMENT that does not repeat. `tremolo` is a periodic LFO, so it loops
     audibly within seconds. Gusts here are the sum of three sine terms with
     incommensurate periods (7.3s, 3.1s, 11.7s), which does not repeat inside
     any shot length we render.

  3. PERSPECTIVE per shot. A close-up on a face should not carry the same wind
     as the wide that preceded it -- cutting between identical beds is what
     makes cuts feel unmotivated. Each shot gets a `presence` value: 0.0 is the
     wide (air, distance, more high end), 1.0 is the close-up (less wind, more
     low body, tighter stereo).

  4. DUCKING. Dialogue has to sit in front. The bed is sidechain-compressed by
     the voice, so it steps back while a line runs and returns underneath it.

The whole thing is FFmpeg and lavfi -- no samples to license, no model to load,
nothing that needs the GPU. That matters because the GPU is the bottleneck and
audio work should never queue behind a render.

    sound_design.py bed --preset headland --seconds 12 -o bed.wav
    sound_design.py score --seconds 56 -o score.wav
    sound_design.py mix <series> --episode 5 -o mix.wav
"""
import argparse
import subprocess
import sys
from pathlib import Path

SR = 48000

# A gust envelope that does not audibly loop. Three incommensurate periods, so
# the pattern's true cycle is longer than any shot we render.
def _gust(base: float, depth: float, rate: float = 1.0) -> str:
    p1, p2, p3 = 7.3 / rate, 3.1 / rate, 11.7 / rate
    return (f"volume=eval=frame:volume='{base:.4f}"
            f"+{depth * 0.55:.4f}*sin(2*PI*t/{p1:.3f})"
            f"+{depth * 0.30:.4f}*sin(2*PI*t/{p2:.3f})"
            f"+{depth * 0.15:.4f}*sin(2*PI*t/{p3:.3f})'")


# Each layer is (name, colour, filter chain, base level, gust depth, gust rate).
# Levels are deliberately low: the sum of four quiet layers reads as a place,
# where one loud layer reads as an effect.
PRESETS: dict[str, list[dict]] = {
    # An inland valley of waterfalls: no swell, no horizon. The low layer is
    # falling water rather than sea, so it is steadier and sits higher; the
    # air is close rather than open, so there is no long echo.
    "valley": [
        {"name": "falls",  "colour": "white",
         "chain": "lowpass=f=3200,highpass=f=140,aecho=0.4:0.35:60|110:0.18|0.10",
         "level": 0.165, "depth": 0.030, "rate": 0.5, "width": 0.9,
         "presence_hp": (140, 200), "presence_gain": (1.0, 0.8)},
        {"name": "pool",   "colour": "brown",
         "chain": "lowpass=f=500,highpass=f=60",
         "level": 0.105, "depth": 0.024, "rate": 0.3, "width": 0.7,
         "presence_hp": (60, 80), "presence_gain": (1.0, 1.2)},
        {"name": "breeze", "colour": "pink",
         "chain": "lowpass=f=1400,highpass=f=180",
         "level": 0.032, "depth": 0.026, "rate": 0.8, "width": 0.75,
         "presence_hp": (180, 260), "presence_gain": (1.0, 0.5)},
        {"name": "leaves", "colour": "white",
         "chain": "highpass=f=2600,lowpass=f=9000",
         "level": 0.020, "depth": 0.016, "rate": 1.5, "width": 0.5,
         "presence_hp": (2600, 1900), "presence_gain": (0.7, 1.35)},
    ],
    # A bleak ruin under flat overcast. The defining quality is ABSENCE: no
    # sea, no birds, no people. A thin cold wind, drizzle, and bare branches.
    # Levels sit well below the other two beds on purpose -- the silence is
    # the point, and filling it would say the opposite of what the scene says.
    "ruin": [
        {"name": "lowwind", "colour": "brown",
         "chain": "lowpass=f=420,highpass=f=45",
         "level": 0.115, "depth": 0.055, "rate": 0.45, "width": 0.8,
         "presence_hp": (45, 65), "presence_gain": (1.0, 1.15)},
        {"name": "gust",    "colour": "pink",
         "chain": "lowpass=f=1000,highpass=f=110",
         "level": 0.058, "depth": 0.048, "rate": 0.9, "width": 0.8,
         "presence_hp": (110, 170), "presence_gain": (1.0, 0.45)},
        {"name": "drizzle", "colour": "white",
         "chain": "highpass=f=3000,lowpass=f=10000",
         "level": 0.016, "depth": 0.006, "rate": 2.6, "width": 0.6,
         "presence_hp": (3000, 2300), "presence_gain": (0.8, 1.3)},
        {"name": "thorn",   "colour": "pink",
         "chain": "highpass=f=900,lowpass=f=3800",
         "level": 0.011, "depth": 0.014, "rate": 1.9, "width": 0.4,
         "presence_hp": (900, 700), "presence_gain": (0.5, 1.4)},
    ],
    "headland": [
        {"name": "swell",  "colour": "brown",
         "chain": "lowpass=f=380,highpass=f=35,aecho=0.7:0.55:450|780:0.35|0.22",
         "level": 0.30, "depth": 0.10, "rate": 0.35, "width": 1.0,
         # Distance is mostly a high-frequency question: far things lose top.
         "presence_hp": (35, 55), "presence_gain": (1.0, 1.25)},
        {"name": "wind",   "colour": "pink",
         "chain": "lowpass=f=1100,highpass=f=90",
         "level": 0.16, "depth": 0.085, "rate": 1.0, "width": 0.85,
         "presence_hp": (90, 150), "presence_gain": (1.0, 0.45)},
        {"name": "grass",  "colour": "white",
         "chain": "highpass=f=2200,lowpass=f=8000",
         "level": 0.030, "depth": 0.020, "rate": 1.7, "width": 0.55,
         "presence_hp": (2200, 1600), "presence_gain": (0.7, 1.3)},
        {"name": "cloth",  "colour": "pink",
         "chain": "highpass=f=700,lowpass=f=4500",
         "level": 0.014, "depth": 0.012, "rate": 2.3, "width": 0.35,
         "presence_hp": (700, 500), "presence_gain": (0.35, 1.5)},
    ],
}


def _lerp(pair, t):
    return pair[0] + (pair[1] - pair[0]) * t


def build_bed(preset: str, seconds: float, out: Path, presence: float = 0.0,
              seed: int = 7) -> Path:
    """One stereo ambience bed. `presence` 0=wide/distant, 1=close/intimate."""
    layers = PRESETS[preset]
    inputs, filters, mixed = [], [], []
    for i, L in enumerate(layers):
        # Left and right are INDEPENDENT noise sources. Filtering one mono
        # source into two channels leaves them correlated, which collapses to
        # the centre of the image and sounds like headphones rather than air.
        for ch, side in enumerate("LR"):
            inputs += ["-f", "lavfi", "-i",
                       f"anoisesrc=r={SR}:c={L['colour']}:a=0.9:"
                       f"seed={seed + i * 17 + ch}:d={seconds:.3f}"]
        li, ri = 2 * i, 2 * i + 1
        hp = _lerp(L["presence_hp"], presence)
        gain = L["level"] * _lerp(L["presence_gain"], presence)
        # Stereo width narrows as a shot gets closer.
        w = L["width"] * (1.0 - 0.45 * presence)
        chain = L["chain"].replace("highpass=f=%d" % L["presence_hp"][0],
                                   "highpass=f=%d" % int(hp))
        for src, tag in ((li, f"l{i}"), (ri, f"r{i}")):
            filters.append(f"[{src}:a]{chain},{_gust(gain, L['depth'], L['rate'])}[{tag}]")
        filters.append(f"[l{i}][r{i}]join=inputs=2:channel_layout=stereo,"
                       f"stereotools=mlev={1.0 - w * 0.5:.3f}:slev={w:.3f}[y{i}]")
        mixed.append(f"[y{i}]")
    filters.append("".join(mixed) +
                   f"amix=inputs={len(layers)}:normalize=0,"
                   # A gentle shelf keeps the sum from getting brittle, and a
                   # limiter stops two gusts peaking together.
                   "treble=g=-2:f=6000,alimiter=limit=0.85:level=disabled[out]")
    cmd = (["ffmpeg", "-v", "error", "-y"] + inputs +
           ["-filter_complex", ";".join(filters), "-map", "[out]",
            "-t", f"{seconds:.3f}", "-ar", str(SR), "-ac", "2", str(out)])
    subprocess.run(cmd, check=True)
    return out


# A drone in D, entering under the scene. Sparse on purpose: one sustained
# chord that never resolves does more for a farewell than a melody, and it
# cannot fight dialogue for attention the way a tune does.
SCORE_PARTIALS = [(73.42, 0.30), (110.0, 0.22), (146.83, 0.16),
                  (220.0, 0.09), (293.66, 0.055)]     # D2 A2 D3 A3 D4


def build_score(seconds: float, out: Path, fade_in: float = 6.0,
                root: float = 73.42) -> Path:
    inputs, filters, tags = [], [], []
    ratio = root / SCORE_PARTIALS[0][0]
    for i, (hz0, lvl) in enumerate(SCORE_PARTIALS):
        hz = hz0 * ratio
        # Two sines a fraction apart per partial: the beating between them is
        # what stops a synth drone sounding like a test tone.
        for k, det in enumerate((-0.13, 0.11)):
            inputs += ["-f", "lavfi", "-i",
                       f"sine=frequency={hz + det:.4f}:sample_rate={SR}:"
                       f"duration={seconds:.3f}"]
            idx = len(tags)          # one input per tag, in order
            filters.append(
                f"[{idx}:a]{_gust(lvl * 0.5, lvl * 0.16, 0.22 + 0.05 * i)}[p{i}_{k}]")
            tags.append(f"[p{i}_{k}]")
    filters.append("".join(tags) + f"amix=inputs={len(tags)}:normalize=0,"
                   "lowpass=f=2400,"
                   f"afade=t=in:st=0:d={fade_in:.2f},"
                   f"afade=t=out:st={max(0.0, seconds - 5.0):.2f}:d=5.0,"
                   "alimiter=limit=0.8:level=disabled[out]")
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + inputs +
                   ["-filter_complex", ";".join(filters), "-map", "[out]",
                    "-t", f"{seconds:.3f}", "-ar", str(SR), "-ac", "2", str(out)],
                   check=True)
    return out


def duck_under(bed: Path, voice: Path, out: Path, amount: float = 5.0) -> Path:
    """Sidechain the bed with the voice so dialogue sits in front of it."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(bed), "-i", str(voice),
         "-filter_complex",
         f"[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asplit=2[key][vo];"
         f"[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[b0];[b0][key]sidechaincompress=threshold=0.03:ratio={amount}:"
         f"attack=25:release=420:makeup=1[duckedbed];"
         f"[duckedbed][vo]amix=inputs=2:duration=first:normalize=0,"
         f"alimiter=limit=0.95:level=disabled[out]",
         "-map", "[out]", "-ar", str(SR), "-ac", "2", str(out)], check=True)
    return out


# How close the microphone feels for each framing. A cut from a wide to a
# close-up that keeps identical ambience reads as a jump; changing perspective
# with the picture is what makes the cut feel motivated.
# Which bed a location gets. A location with no entry is a real decision to
# make, not a default to fall through -- the old ambience system defaulted
# every unrecognised place to city rain, which is how a desolate ruin ended up
# sounding like Belfast on a wet Tuesday.
PRESET_BY_LOCATION = {
    "farewell_cliff": "headland",
    "storm_cliffs": "headland",
    "stormy_sea": "headland",
    "sunlight_path": "headland",
    "tir_na_nog": "valley",
    "ruined_ireland": "ruin",
}

# The drone's root, per location. D minor for the otherworld; a semitone-flat,
# lower root for the ruin so the return does not sound like the same place.
SCORE_ROOT = {"headland": 73.42, "valley": 82.41, "ruin": 61.74}   # D2 / E2 / B1


PRESENCE_BY_STAGING = {
    "full_body": 0.0, "walking_away": 0.05, "wider": 0.05,
    "three_quarter": 0.45, "medium": 0.45, "over_shoulder": 0.55,
    "low_angle": 0.4, "close": 0.85, "ecu": 1.0,
}


def mix_episode(scenes: list[dict], vo_dir: Path, out: Path,
                preset: str = "headland", crossfade: float = 0.05,
                offsets: list[float] | None = None,
                vo_lead: float = 0.0) -> Path:
    """Build the whole episode's audio: per-shot beds, score, ducked VO.

    Each scene needs "id" and "seconds" (the PICTURE duration of that shot).
    Runs entirely on the CPU, so it can be judged before any GPU is spent --
    which is the point: audio decisions should never queue behind a render.
    """
    # Voice placement must use the STITCHER's offsets, never a second
    # cumulative sum computed here. Recomputing them put the voice 1.70s ahead
    # of picture by the last shot of a six-shot piece -- the identical drift
    # that already bit subtitles, arrived at the identical way.
    if offsets is None:
        offsets, _t = [], 0.0
        for i, sc in enumerate(scenes):
            offsets.append(_t)
            _t += sc["seconds"] - (crossfade if i < len(scenes) - 1 else 0)
    if len(offsets) != len(scenes):
        raise ValueError(f"{len(offsets)} offsets for {len(scenes)} scenes")
    tmp = out.parent / "_sd"
    tmp.mkdir(parents=True, exist_ok=True)
    total = sum(sc["seconds"] for sc in scenes) - crossfade * (len(scenes) - 1)

    # ── 1. a bed per shot, at that shot's perspective ────────────────────
    beds = []
    for i, sc in enumerate(scenes):
        pres = PRESENCE_BY_STAGING.get(sc.get("staging", "medium"), 0.45)
        # A cross-cut moves between locations every shot, so the bed is a
        # per-shot property, not a per-episode one. `preset` stays the default
        # for a single-location piece.
        shot_preset = sc.get("preset") or preset
        b = tmp / f"bed_{sc['id']}.wav"
        # Overlap by the crossfade so the joins have material to work with.
        build_bed(shot_preset, sc["seconds"] + crossfade, b, presence=pres,
                  seed=11 + i * 31)
        beds.append((b, pres))

    # ── 2. join them with short crossfades ───────────────────────────────
    # A hard splice between two noise beds clicks; a crossfade at the cut lets
    # the perspective change without announcing itself.
    ins, filt, cur = [], [], None
    for i, (b, _) in enumerate(beds):
        ins += ["-i", str(b)]
        if cur is None:
            cur = f"{i}:a"
        else:
            filt.append(f"[{cur}][{i}:a]acrossfade=d={crossfade}:c1=tri:c2=tri[x{i}]")
            cur = f"x{i}"
    filt.append(f"[{cur}]anull[amb]")
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + ins +
                   ["-filter_complex", ";".join(filt), "-map", "[amb]",
                    "-ar", str(SR), "-ac", "2", str(tmp / "amb.wav")], check=True)

    # ── 3. score across the whole piece ──────────────────────────────────
    build_score(total, tmp / "score.wav", root=SCORE_ROOT.get(preset, 73.42))

    # ── 4. voice, laid at each shot's start offset ───────────────────────
    # Voice files may live in different episode directories once shots from
    # several pieces are cut together, so a shot can name its own path.
    vo_ins, vo_filt, vo_tags = [], [], []
    for i, sc in enumerate(scenes):
        t = offsets[i]
        f = Path(sc["vo"]) if sc.get("vo") else vo_dir / f"{sc['id']}.mp3"
        if f.exists():
            vo_ins += ["-i", str(f)]
            k = len(vo_tags)
            vo_filt.append(
                f"[{k}:a]aformat=channel_layouts=stereo:sample_rates={SR},"
                # vo_lead MUST stay 0 for S2V footage. The mouth in the picture
                # was generated FROM this audio starting at frame 0 of the clip,
                # so nudging the voice later to avoid landing on the cut pushes
                # the sound off the lips -- breaking the exact thing S2V is for.
                # A lead is only safe on footage whose mouths were not driven by
                # this track.
                f"adelay={int((t + vo_lead) * 1000)}|{int((t + vo_lead) * 1000)}[v{k}]")
            vo_tags.append(f"[v{k}]")
    vo_filt.append("".join(vo_tags) +
                   f"amix=inputs={len(vo_tags)}:normalize=0:dropout_transition=0,"
                   f"apad,atrim=duration={total:.3f}[vo]")
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + vo_ins +
                   ["-filter_complex", ";".join(vo_filt), "-map", "[vo]",
                    "-ar", str(SR), "-ac", "2", str(tmp / "vo.wav")], check=True)

    # ── 5. bed + score ducked under the voice, then mastered ─────────────
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-i", str(tmp / "amb.wav"), "-i", str(tmp / "score.wav"),
         "-i", str(tmp / "vo.wav"),
         "-filter_complex",
         # sidechaincompress refuses to negotiate formats across its two
         # inputs; without an explicit aformat on each leg the graph dies with
         # "could not choose their formats".
         "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume=1.0[a];[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume=0.42[s];"
         "[a][s]amix=inputs=2:normalize=0[bedmix];"
         "[2:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asplit=2[key][voice];"
         "[bedmix][key]sidechaincompress=threshold=0.025:ratio=6:"
         "attack=20:release=450:makeup=1[ducked];"
         "[ducked][voice]amix=inputs=2:duration=first:normalize=0,"
         # Broadcast loudness, so it does not arrive quieter than everything
         # else on the platform and get turned up into its own noise floor.
         "loudnorm=I=-16:TP=-1.5:LRA=11,"
         "alimiter=limit=0.97:level=disabled[out]",
         "-map", "[out]", "-ar", str(SR), "-ac", "2", str(out)], check=True)
    return out


def _rms(p: Path) -> float:
    # astats logs at INFO; at -v error the numbers never appear and this
    # silently reported 0.0 dB for every file.
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(p), "-af",
                        "astats=metadata=1:reset=0", "-f", "null", "-"],
                       capture_output=True, text=True)
    for line in reversed(r.stderr.splitlines()):
        if "RMS level dB" in line:
            try:
                return float(line.split(":")[-1].strip())
            except ValueError:
                pass
    return 0.0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bed"); b.add_argument("--preset", default="headland")
    b.add_argument("--seconds", type=float, default=10.0)
    b.add_argument("--presence", type=float, default=0.0)
    b.add_argument("-o", "--out", required=True)
    s = sub.add_parser("score"); s.add_argument("--seconds", type=float, default=56.0)
    s.add_argument("-o", "--out", required=True)
    m = sub.add_parser("mix"); m.add_argument("plan")
    m.add_argument("--vo", required=True); m.add_argument("-o", "--out", required=True)
    m.add_argument("--preset", default="headland")
    m.add_argument("--offsets", help="comma-separated absolute shot start times "
                                     "from the stitcher")
    m.add_argument("--vo-lead", type=float, default=0.0,
                   help="delay each line into its shot. Leave at 0 for S2V "
                        "footage: the mouths were driven by this audio at "
                        "frame 0 and any lead breaks lip sync.")
    a = ap.parse_args()
    if a.cmd == "bed":
        p = build_bed(a.preset, a.seconds, Path(a.out), a.presence)
    elif a.cmd == "score":
        p = build_score(a.seconds, Path(a.out))
    else:
        import json
        plan = json.loads(Path(a.plan).read_text())
        offs = ([float(x) for x in a.offsets.split(",")] if a.offsets else None)
        p = mix_episode(plan, Path(a.vo), Path(a.out), preset=a.preset,
                        offsets=offs, vo_lead=a.vo_lead)
    print(f"  {p}  {_rms(p):.1f} dB RMS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
