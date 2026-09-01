#!/usr/bin/env python3
"""
Directed line readings, as an A/B set for judgement — installed nowhere.

Every line in the series is rendered at one fixed rate and pitch, which is
why the performances read flat: the TTS is a teleprompter, not an actor. A
studio read varies pace inside the line and puts silence where the weight is.

edge-tts cannot act, but it can be DIRECTED per sentence: split the line at
sentence boundaries, give each sentence its own rate and pitch from simple
cues, and rejoin with sized pauses. "I was right. Being right is worth
nothing at all." gains a beat before the second sentence and slows through
it -- which is most of what a reader would do.

This renders pairs (flat as shipped / directed) for a sample of real lines
so the difference can be HEARD before anything is regenerated. Changing VO
durations re-times shots, so nothing installs from here.

    voice_direction.py <series> -o /workspace/review/voice_direction
"""
import argparse
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

VOICES = {"oisin": "en-IE-ConnorNeural", "niamh": "en-IE-EmilyNeural"}


def split_sentences(line):
    parts = re.split(r'(?<=[.!?])\s+', line.strip())
    return [p for p in parts if p]


def direct(sentences):
    """(text, rate, pitch, pause_after_s) per sentence, from cheap cues."""
    out = []
    n = len(sentences)
    for i, t in enumerate(sentences):
        rate, pitch, pause = "+4%", "+0Hz", 0.28
        words = len(t.split())
        if t.rstrip().endswith("?"):
            pitch = "+12Hz"
        if i == n - 1 and n > 1:
            rate = "-6%"                    # land the last sentence
            pause = 0.0
        if words <= 5 and n > 1:
            rate = "-10%"                   # short sentences carry weight
        if i == n - 2 and n > 1:
            pause = 0.55                    # a beat before the landing
        out.append((t, rate, pitch, pause))
    return out


async def tts(text, voice, path, rate, pitch):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(path)


def silence(path, seconds):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "anullsrc=r=24000:cl=mono", "-t", f"{seconds:.2f}",
                    "-c:a", "libmp3lame", path], check=True)


def render_directed(line, voice, out, tmp):
    parts, files = direct(split_sentences(line)), []
    for i, (t, rate, pitch, pause) in enumerate(parts):
        f = f"{tmp}/s{i}.mp3"
        asyncio.run(tts(t, voice, f, rate, pitch))
        files.append(f)
        if pause > 0.05:
            g = f"{tmp}/p{i}.mp3"
            silence(g, pause)
            files.append(g)
    lst = f"{tmp}/list.txt"
    Path(lst).write_text("".join(f"file '{f}'\n" for f in files))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe",
                    "0", "-i", lst, "-c:a", "libmp3lame", str(out)], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("-o", "--out", default="/workspace/review/voice_direction")
    ap.add_argument("--per-episode", type=int, default=2)
    a = ap.parse_args()
    sr.set_current_series(a.series)
    outd = Path(a.out); outd.mkdir(parents=True, exist_ok=True)
    made = []
    import tempfile
    for e in (13, 14, 15, 16, 17):
        ep = sr.load_json(sr.episode_path(a.series, e))
        picked = 0
        for s in ep["scenes"]:
            dl = s.get("dialogue") or []
            if not dl or picked >= a.per_episode:
                continue
            line, who = dl[0]["line"], dl[0]["character"]
            if len(split_sentences(line)) < 2:
                continue                     # direction shows in multi-sentence lines
            voice = VOICES.get(who)
            if not voice:
                continue
            flat = outd / f"{s['id']}_flat.mp3"
            dird = outd / f"{s['id']}_directed.mp3"
            asyncio.run(tts(line, voice, str(flat), "+4%", "+0Hz"))
            with tempfile.TemporaryDirectory() as td:
                render_directed(line, voice, dird, td)
            d0 = sr._get_video_duration(str(flat))
            d1 = sr._get_video_duration(str(dird))
            made.append({"id": s["id"], "who": who, "flat_s": round(d0, 2),
                         "directed_s": round(d1, 2), "line": line})
            print(f"  {s['id']}: flat {d0:.1f}s / directed {d1:.1f}s "
                  f"({who})", flush=True)
            picked += 1
    (outd / "manifest.json").write_text(json.dumps(made, indent=2))
    print(f"\n  {len(made)} A/B pairs in {outd} — listen before deciding; "
          f"nothing installed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
