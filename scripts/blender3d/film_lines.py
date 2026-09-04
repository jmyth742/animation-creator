"""TTS + envelopes for 'The Nine Waterfalls' — a talk piece in the valley."""
import asyncio
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import edge_tts

OUT = Path(sys.argv[1])
SCRIPT = Path(sys.argv[2]) if len(sys.argv) > 2 else None
OUT.mkdir(parents=True, exist_ok=True)
bible = json.load(open("series/tir-na-nog-legend/bible.json"))
V = {c: bible["characters"][c].get("voice", "en-IE-EmilyNeural")
     for c in ("niamh", "oisin")}

LINES = json.load(open(SCRIPT)) if SCRIPT else [
    ("niamh", "You took the long way again. The lake path is shorter, and you have known that for three hundred years."),
    ("oisin", "The long way keeps the hall in sight. I like the walk back better when I can see where it ends."),
    ("niamh", "You walk the borders like a sentry on a wall. We have no enemies here. What is it you are guarding?"),
    ("oisin", "Nothing. I count the waterfalls. Nine this morning. Nine yesterday. As long as the number holds, I can believe the place is real."),
    ("niamh", "Then walk every morning, love. And on the morning you forget the number, I will remember it for you."),
]

async def make():
    meta = []
    for i, (who, text) in enumerate(LINES):
        mp3 = OUT / f"l{i}.mp3"
        await edge_tts.Communicate(text, V[who]).save(str(mp3))
        wav = OUT / f"l{i}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3),
                        "-ar", "16000", "-ac", "1", str(wav)], check=True)
        w = wave.open(str(wav))
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float)
        sr, fps = w.getframerate(), 16
        n = len(a) // (sr // fps)
        env = np.array([np.sqrt((a[j*sr//fps:(j+1)*sr//fps]**2).mean()) for j in range(n)])
        env = env / (env.max() + 1e-9)
        env = np.convolve(env, [0.25, 0.5, 0.25], mode="same")
        env = np.clip((env - 0.08) / 0.6, 0, 1)
        np.save(OUT / f"l{i}_env.npy", env)
        meta.append({"i": i, "who": who, "frames": int(n),
                     "seconds": round(len(a) / sr, 2), "text": text})
        print(who, round(len(a)/sr, 2), "s")
    json.dump(meta, open(OUT / "lines.json", "w"), indent=1)

asyncio.run(make())
