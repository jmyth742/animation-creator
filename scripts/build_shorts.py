#!/usr/bin/env python3
"""
Short-form assets: 1080x1920, one idea per video.

A short is not a shortened segment. The long-form folders carry evidence plus
narration beats, which is the right shape for a chapter inside a ten-minute
video and the wrong shape for thirty seconds. A short is hook, one number,
payoff -- no setup, no context, and it has to land in the first two seconds
because that is when people leave.

So this does not crop the existing assets. Cropping kills both kinds:
cel-shaded wides ARE their composition (Oisin small against a headland becomes
a torso), and terminal cards are wide monospace tables that lose half of every
line. Cards are re-set for the shape; clips are placed on a dark ground with
the claim above and the number below, which uses the vertical space rather
than fighting it.

Only stories with a VISUAL hook are included. The ones whose evidence is a
stack trace make a slide, not a video, and are deliberately left out.

    build_shorts.py
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("/workspace/video_assets/shorts")
W, H = 1080, 1920
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SERIF_B = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
BG, INK, DIM, HOT = (13, 14, 17), (233, 230, 221), (132, 129, 123), (233, 150, 88)


def _wrap(d, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textbbox((0, 0), t, font=font)[2] > maxw and cur:
            lines.append(cur); cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def hook_card(title: str, number: str, sub: str, out: Path) -> Path:
    """The first frame. It has about two seconds to work."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    ft = ImageFont.truetype(SERIF_B, 74)
    fn = ImageFont.truetype(MONO_B, 150)
    fs = ImageFont.truetype(MONO, 34)
    y = 300
    for ln in _wrap(d, title, ft, W - 140)[:4]:
        d.text((70, y), ln, font=ft, fill=INK); y += 92
    y += 90
    bb = d.textbbox((0, 0), number, font=fn)
    d.text(((W - (bb[2] - bb[0])) / 2, y), number, font=fn, fill=HOT)
    y += 220
    for ln in _wrap(d, sub, fs, W - 140)[:5]:
        d.text((70, y), ln, font=fs, fill=DIM); y += 48
    img.save(out)
    return out


def clip_frame(clip: str, out: Path, top: str, bottom: str,
               seconds: float = 6.0) -> Path | None:
    """A 16:9 clip on a vertical ground: claim above, number below."""
    if not Path(clip).exists():
        return None
    vid_w, vid_h = W, int(W * 480 / 832)
    top_pad = 430
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    ft = ImageFont.truetype(MONO_B, 44)
    fb = ImageFont.truetype(MONO_B, 92)
    tl = _wrap(d, top, ft, W - 120)[:3]
    txt = Image.new("RGB", (W, H), BG)
    dd = ImageDraw.Draw(txt)
    y = 150
    for ln in tl:
        dd.text((60, y), ln, font=ft, fill=INK); y += 58
    by = top_pad + vid_h + 120
    bb = dd.textbbox((0, 0), bottom, font=fb)
    dd.text(((W - (bb[2] - bb[0])) / 2, by), bottom, font=fb, fill=HOT)
    plate = out.with_suffix(".plate.png")
    txt.save(plate)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(plate),
         "-i", clip, "-filter_complex",
         f"[1:v]scale={vid_w}:{vid_h}[v];[0:v][v]overlay=0:{top_pad}:shortest=1,"
         f"format=yuv420p[o]",
         "-map", "[o]", "-t", f"{seconds}", "-r", "16",
         "-c:v", "libx264", "-crf", "18", str(out)], check=True)
    plate.unlink(missing_ok=True)
    return out


SHORTS = [
 dict(slug="01_told_it_not_to_move",
      title="I spent weeks wondering why the characters wouldn't move",
      number="6 words",
      sub="My negative prompt contained: fast movement, erratic motion, motion "
          "blur, camera shake, shaky camera, extreme camera movement. "
          "I was telling it to hold still.",
      clip=None,
      script="""HOOK (0-2s): "I spent weeks wondering why my characters wouldn't move."

BEAT (2-12s): Show a still shot, then a walking one. Same model, same day.

TURN (12-22s): WAN ships a default negative prompt. Three of its terms mean
static, motionless, and a completely still picture. It fights stillness for you.

PUNCH (22-30s): A custom negative REPLACES that, it doesn't add to it. Mine
deleted all three and added six terms that suppress motion. On 80% of every
shot I was instructing it to hold still, then blaming the model."""),

 dict(slug="02_talking_after_the_line",
      title="They kept talking after they'd stopped talking",
      number="1.62x",
      sub="The mouth moved MORE in the silence than during the speech. "
          "80 seconds of a 233-second film had no audio under it at all.",
      clip="/workspace/video_assets/01_lips_in_silence/s06_BEFORE.mp4",
      clip_top="the line ends at 6.4s. watch the mouth.",
      clip_bottom="1.62x",
      script="""HOOK (0-2s): Play the shot. Say nothing. Let them see the mouth.

BEAT (2-10s): "The line ended four seconds ago."

TURN (10-20s): Speech-to-video drives the mouth from audio. Shots were held
longer than their lines, so a third of every shot had no audio covering it.
The model invented movement to fill the gap.

PUNCH (20-30s): Nothing errored. Right length, right person, right style."""),

 dict(slug="03_three_strangers",
      title="I blamed the model for two hours. The bug was in the reference image.",
      number="0.316",
      sub="Two renders came back with a man who shouldn't exist. The reference "
          "plate had three figures standing in its central arch. It passed the "
          "contamination check at 0.316 against a 0.75 threshold.",
      clip=None,
      script="""HOOK (0-2s): The render with the invented man. "Who is that?"

BEAT (2-10s): Remove the character from the scene. Put "people" in the negative.
Render again. Still there.

TURN (10-22s): Show the reference plate. Zoom the arch. Three people.

PUNCH (22-30s): The model was reproducing exactly what it was shown. And the
check meant to catch this scored it 0.316 and passed it."""),

 dict(slug="04_eighty_six_seconds",
      title="A seven-minute film that played in eighty-six seconds",
      number="80fps",
      sub="Every frame was present and the count was right. The container said "
          "80fps instead of 16, because the upscaler read r_frame_rate — a "
          "heuristic that rises when timestamps are irregular.",
      clip=None,
      script="""HOOK (0-3s): Play the film sped up 5x. "This is the finished cut."

BEAT (3-12s): 144 segments, all present. 6910 frames, correct count.

TURN (12-22s): The container said 80fps. The film runs at 16.

PUNCH (22-30s): r_frame_rate is the smallest rate that can express every
timestamp. A few irregular ones from a faded title card pushed it to 80. I
read the wrong field."""),

 dict(slug="05_camera_doing_nothing",
      title="Half my film had a camera move that did nothing",
      number="2.920 / 2.918",
      sub="ffmpeg's crop filter evaluates width and height ONCE. Only x and y "
          "are per-frame. My push froze at frame zero's size and came out "
          "bit-identical to a locked-off shot.",
      clip=None,
      script="""HOOK (0-3s): Two clips side by side. "One of these has a camera move."

BEAT (3-10s): They are identical. 2.920 against 2.918.

TURN (10-20s): crop evaluates w and h once at init. Only x and y update per
frame. A push written as a shrinking crop window never shrinks.

PUNCH (20-30s): Seventeen of twenty-seven shots, in a cut I'd already called
finished. Drift worked only because it happens to move x."""),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    for s in SHORTS:
        d = OUT / s["slug"]
        d.mkdir(exist_ok=True)
        hook_card(s["title"], s["number"], s["sub"], d / "hook.png")
        if s.get("clip"):
            clip_frame(s["clip"], d / "clip_vertical.mp4",
                       s.get("clip_top", ""), s.get("clip_bottom", ""))
        (d / "script.md").write_text(
            f"# {s['title']}\n\n**Number on screen: {s['number']}**\n\n"
            f"{s['script']}\n\n---\n\n"
            f"Target 25-30s. Hook must land in the first two seconds.\n"
            f"`hook.png` is the opening frame at 1080x1920.\n")
        made.append(d)
        print(f"  {s['slug']}")
    (OUT / "README.md").write_text(
        "# Short-form\n\n1080x1920, one idea each, 25-30 seconds.\n\n"
        "A short is not a shortened segment: hook, one number, payoff, no\n"
        "setup. `hook.png` is the opening frame and carries the number, because\n"
        "the number is the reason to keep watching.\n\n"
        "Only stories with a VISUAL hook are here. The ones whose evidence is a\n"
        "stack trace make a slide, not a video, and are left in the long-form\n"
        "folders where they work.\n\n"
        + "\n".join(f"- `{d.name}`" for d in made) + "\n\n"
        "## Still needed\n\n"
        "Vertical b-roll. 480x832 portrait is a native WAN resolution, so key\n"
        "shots can be RE-RENDERED vertical rather than cropped -- cel-shaded\n"
        "wides lose their composition when cropped.\n")
    print(f"\n  {len(made)} shorts in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
