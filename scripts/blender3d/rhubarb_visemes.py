"""wav -> Rhubarb mouth shapes -> per-frame viseme columns for the
texture-face switch. Phoneme-accurate; replaces amplitude guessing.

Rhubarb shapes: A closed (M B P) / B clenched consonant / C mid-open /
D wide open / E rounded / F puckered oo / G F-V teeth / H L tongue / X rest.
Our columns: 0 closed, 1 small, 2 mid, 3 open, 4 wide-ee, 5 round-oo.
"""
import json
import subprocess
import sys
import numpy as np

RB = "/workspace/tools/Rhubarb-Lip-Sync-1.13.0-Linux/rhubarb"
MAP = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 5, "F": 5, "G": 1, "H": 2, "X": 0}

def visemes_for(wav, frames, fps=16):
    r = subprocess.run([RB, "-f", "json", "--machineReadable", wav],
                       capture_output=True, text=True, timeout=300)
    cues = json.loads(r.stdout)["mouthCues"]
    cols = np.zeros(frames, dtype=np.int64)
    for cue in cues:
        f0 = int(cue["start"] * fps)
        f1 = max(f0 + 1, int(cue["end"] * fps))
        cols[f0:min(frames, f1)] = MAP.get(cue["value"], 2)
    # wide-open sustained vowels get the 'ee' stretch occasionally for range
    return cols

if __name__ == "__main__":
    wav, out, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    np.save(out, visemes_for(wav, n))
    print("visemes:", np.bincount(np.load(out), minlength=6).tolist())
