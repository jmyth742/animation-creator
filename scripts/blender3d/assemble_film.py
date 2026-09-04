"""Assemble 'The Nine Waterfalls': shots -> edit -> audio -> cards -> master."""
import json
import subprocess
import sys
from pathlib import Path

S = Path(sys.argv[1])          # scratch dir with film/, film_audio/, film_shots.json
OUT = Path(sys.argv[2])
d = json.load(open(S / "film_shots.json"))
FPS = d["fps"]
lines = json.load(open(S / "film_audio/lines.json"))

# 1. one frame sequence in edit order
seq = S / "film_seq"
seq.mkdir(exist_ok=True)
for f in seq.glob("*.png"):
    f.unlink()
i, prev = 0, 0
for s in d["shots"]:
    f0 = max(s["f0"], prev + 1)
    prev = s["f1"]
    src = S / "film" / s["name"]
    for fr in range(f0, s["f1"] + 1):
        p = src / f"frame_{fr:04d}.png"
        if not p.exists():
            sys.exit(f"MISSING {p}")
        i += 1
        (seq / f"e_{i:05d}.png").symlink_to(p)
print("edit frames:", i)

# 2. picture
subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
                "-i", str(seq / "e_%05d.png"), "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-crf", "17", str(S / "picture.mp4")],
               check=True)

# 3. audio timeline: each line at its start frame, over a soft wind bed
dur = i / FPS
inputs, filters, amix = ["-f", "lavfi", "-t", str(dur),
                         "-i", "anoisesrc=colour=brown:amplitude=0.035"], [], []
filters.append("[0]lowpass=f=280,volume=0.5[wind]")
amix.append("[wind]")
for k, (L, f0) in enumerate(zip(lines, d["line_starts"]), start=1):
    inputs += ["-i", str(S / f"film_audio/l{L['i']}.mp3")]
    ms = int((f0 - 1) / FPS * 1000)
    filters.append(f"[{k}]adelay={ms}|{ms}[l{k}]")
    amix.append(f"[l{k}]")
fc = ";".join(filters) + ";" + "".join(amix) + \
    f"amix=inputs={len(amix)}:duration=first:normalize=0[mix]"
subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs,
                "-filter_complex", fc, "-map", "[mix]", "-ar", "48000",
                str(S / "audio.wav")], check=True)

# 4. mux + title/end cards + grade
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
vf = (
    "colorbalance=rh=0.06:gh=0.02:bh=-0.08:rm=0.03:bm=-0.04,"
    "eq=saturation=1.02:gamma=0.99,"
    "vignette=PI/5.2,"
    "split[base][h];[h]gblur=sigma=7,curves=all='0/0 0.82/0.06 1/0.35'[glow];"
    "[base][glow]blend=all_mode=screen:all_opacity=0.07,"
    "noise=alls=5:allf=t,"
    f"drawtext=fontfile={FONT}:text='TIR NA NOG':fontcolor=white:fontsize=64:"
    "x=(w-text_w)/2:y=h*0.38:alpha='if(lt(t,0.8),t/0.8,if(lt(t,4),1,if(lt(t,5),(5-t),0)))',"
    f"drawtext=fontfile={FONT}:text='The Nine Waterfalls':fontcolor=white:fontsize=30:"
    "x=(w-text_w)/2:y=h*0.55:alpha='if(lt(t,1.2),0,if(lt(t,2),(t-1.2)/0.8,if(lt(t,4),1,if(lt(t,5),(5-t),0))))',"
    "fade=t=in:st=0:d=1.0"
)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(S / "picture.mp4"),
                "-i", str(S / "audio.wav"), "-vf", vf,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17",
                "-c:a", "aac", "-b:a", "192k", "-shortest",
                str(S / "graded.mp4")], check=True)
# end card: 4s black with title, concat
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-t", "4",
                "-i", "color=c=black:s=832x480:r=16",
                "-f", "lavfi", "-t", "4", "-i", "anullsrc=r=48000:cl=stereo",
                "-vf", f"drawtext=fontfile={FONT}:text='TIR NA NOG':fontcolor=white:"
                "fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2:"
                "alpha='if(lt(t,1),t,if(lt(t,3),1,4-t))'",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", str(S / "endcard.mp4")], check=True)
concat = S / "concat.txt"
concat.write_text(f"file '{S}/graded.mp4'\nfile '{S}/endcard.mp4'\n")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat), "-c", "copy", str(S / "cut.mp4")],
               check=True)

# 5. loudness master (two-pass helper from the episode chain)
sys.path.insert(0, "/workspace/text-to-video/scripts")
import master_audio as ma                                      # noqa: E402
import shutil                                                  # noqa: E402
shutil.copy(S / "cut.mp4", OUT)
class _F:                                                       # tiny shim
    pass
m1 = ma.measure(OUT)
tmp = OUT.with_suffix(".m.mp4")
if ma._linear_pass(OUT, tmp, m1):
    m2 = ma.measure(tmp)
    if abs(float(m2.get("input_i", -99)) - ma.TARGET_I) <= 1.0:
        shutil.move(tmp, OUT)
    else:
        m3 = ma.measure(tmp)
        tmp2 = OUT.with_suffix(".m2.mp4")
        if ma._linear_pass(tmp, tmp2, m3):
            shutil.move(tmp2, OUT)
        tmp.unlink(missing_ok=True)
print("FILM ASSEMBLED", OUT)
