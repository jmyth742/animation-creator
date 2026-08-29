#!/usr/bin/env python3
"""
A page that shows what was actually generated, and what generated it.

Everything that went wrong in this project went wrong invisibly. A plate named
full_body was a head-and-shoulders portrait. A wide shot came back a close-up.
A character rendered bald. In every case the configuration looked right, the
job reported success, and the only way to find out was to watch the finished
episode and squint.

This puts the shot and its cause on the same screen: the clip that rendered,
the exact prompt that was sent, the negative, the seed image it started from,
which checkpoint ran, and the measurements. Nothing is summarised or
reconstructed from memory -- the prompts come from the same functions the
renderer calls, so what is displayed is what was sent.

    shot_inspector.py <series> --episode 13
    shot_inspector.py <series> --episode 13 --measure     # slower, adds scores

Writes a self-contained folder: open index.html locally, the media sits beside
it, no server needed.
"""
import argparse
import html
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

OUT_ROOT = Path("/workspace/review/inspector")


def measure(clip: str, vo: Path | None):
    """Framing, and how much the mouth moves when there is speech."""
    import numpy as np
    from PIL import Image
    out = {}
    try:
        import wide_dialogue_test as wd
        p, label = wd.framing(clip)
        out["p_wide"] = round(p, 3); out["reads_as"] = label
    except Exception:                                          # noqa: BLE001
        pass
    if vo and vo.exists():
        try:
            import wave
            with tempfile.TemporaryDirectory() as td:
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip, "-vf",
                                "fps=4,crop=iw*0.30:ih*0.16:iw*0.36:ih*0.36,"
                                "scale=64:-1", f"{td}/m_%03d.png"], check=True)
                fr = [np.asarray(Image.open(f).convert("L"), dtype=np.float32)
                      for f in sorted(Path(td).glob("m_*.png"))]
                mo = np.array([np.abs(fr[i+1]-fr[i]).mean()
                               for i in range(len(fr)-1)]) if len(fr) > 1 else np.array([0.])
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(vo),
                                "-ac", "1", "-ar", "8000", f"{td}/a.wav"], check=True)
                w = wave.open(f"{td}/a.wav")
                a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
            st = 2000
            env = np.array([np.abs(a[i*st:(i+1)*st]).mean() for i in range(len(a)//st)])
            n = min(len(mo), len(env))
            if n >= 4 and env[:n].max() > 0:
                m, e = mo[:n], env[:n]
                sp = e > e.max() * 0.15
                if (~sp).any() and m[~sp].mean() > 0:
                    out["lip_ratio"] = round(float(m[sp].mean() / m[~sp].mean()), 2)
        except Exception:                                      # noqa: BLE001
            pass
    return out


CSS = """
:root{--bg:#0e1211;--card:#161b19;--edge:#28312d;--ink:#e7eae5;--dim:#8a938c;
      --good:#78be82;--bad:#d66058;--warn:#deb05c;--acc:#7fa6c9;}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);margin:0;
     font:15px/1.55 -apple-system,system-ui,sans-serif}
header{padding:28px 32px;border-bottom:1px solid var(--edge)}
h1{margin:0;font-size:1.5rem;font-weight:600}
.sub{color:var(--dim);font-size:.9rem;margin-top:4px}
.wrap{padding:24px 32px;display:flex;flex-direction:column;gap:20px}
.shot{background:var(--card);border:1px solid var(--edge);border-radius:5px;
      display:grid;grid-template-columns:380px 1fr;gap:20px;padding:18px}
@media(max-width:900px){.shot{grid-template-columns:1fr}}
video{width:100%;border-radius:3px;background:#000;display:block}
.seed{margin-top:10px}
.seed img{width:100%;border-radius:3px;border:1px solid var(--edge)}
.seed .lab,.vid .lab{font:600 .66rem ui-monospace,monospace;letter-spacing:.12em;
     text-transform:uppercase;color:var(--dim);margin-bottom:5px}
.id{font:700 1.05rem ui-monospace,monospace;color:var(--ink)}
.tags{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 12px}
.tag{font:700 .64rem ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase;
     padding:3px 8px;border-radius:2px;background:#1f2725;color:var(--dim)}
.tag.mode{background:#1a2733;color:var(--acc)}
.tag.good{background:#16241a;color:var(--good)}
.tag.bad{background:#2a1614;color:var(--bad)}
.tag.warn{background:#282013;color:var(--warn)}
.field{margin-bottom:12px}
.field .lab{font:600 .66rem ui-monospace,monospace;letter-spacing:.12em;
     text-transform:uppercase;color:var(--dim);margin-bottom:4px}
.field .val{font:13px/1.5 ui-monospace,monospace;color:var(--ink);
     background:#111614;border:1px solid var(--edge);border-radius:3px;
     padding:9px 11px;white-space:pre-wrap;word-break:break-word}
.field .val.neg{color:var(--dim);max-height:110px;overflow:auto}
.line{font:italic 1.02rem/1.5 Georgia,serif;color:var(--ink)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}
.m{background:#111614;border:1px solid var(--edge);border-radius:3px;padding:8px 10px}
.m .k{font:600 .62rem ui-monospace,monospace;letter-spacing:.1em;
     text-transform:uppercase;color:var(--dim)}
.m .v{font:700 1.1rem ui-monospace,monospace;font-variant-numeric:tabular-nums}
"""


def tag(txt, cls=""):
    return f'<span class="tag {cls}">{html.escape(str(txt))}</span>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("--measure", action="store_true")
    a = ap.parse_args()
    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    ep = sr.load_json(sr.episode_path(a.series, a.episode))
    res = sr.get_resolution_config("480p", "wan")
    mc = sr.get_model_config("wan")

    out = OUT_ROOT / f"ep{a.episode:02d}"
    media = out / "media"
    media.mkdir(parents=True, exist_ok=True)

    rows = []
    for i, scene in enumerate(ep["scenes"], 1):
        sid = scene["id"]
        mode = sr.classify_scene_type(scene)
        seed_img = sr.get_scene_seed_image(scene, a.series, None)
        prompt = sr.build_scene_prompt(scene, bible)
        neg = sr.build_negative_prompt(scene)
        clip = sr.find_latest_clip(sid)
        vo = (Path("output") / a.series / f"ep{a.episode:02d}" / "audio" / f"{sid}.mp3")

        vid_rel = seed_rel = None
        if clip:
            shutil.copy(clip, media / f"{sid}.mp4")
            vid_rel = f"media/{sid}.mp4"
        if seed_img:
            src = sr.COMFYUI_INPUT / str(seed_img)
            if src.exists():
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src),
                                "-vf", "scale=420:-1", str(media / f"{sid}_seed.png")],
                               check=False)
                if (media / f"{sid}_seed.png").exists():
                    seed_rel = f"media/{sid}_seed.png"

        unet = (sr._s2v_unet(res) if mode == "s2v"
                else mc.get("unet_high") or mc.get("unet") or "wan i2v dual")
        dur = sr._get_video_duration(clip) if clip else 0.0
        scores = measure(clip, vo) if (a.measure and clip) else {}

        rows.append(dict(n=i, sid=sid, mode=mode, seed_img=str(seed_img or "—"),
                         prompt=prompt, neg=neg, vid=vid_rel, seed_thumb=seed_rel,
                         unet=str(unet), dur=dur, scores=scores,
                         loc=scene.get("location", "—"),
                         setup=scene.get("setup") or "—",
                         staging=scene.get("staging") or "—",
                         visual=scene.get("visual", ""),
                         line=(scene.get("dialogue") or [{}])[0].get("line", ""),
                         who=(scene.get("dialogue") or [{}])[0].get("character", ""),
                         cfg=mc.get("cfg"), shift=res.get("shift"),
                         sampler=mc.get("sampler")))

    parts = [f"<style>{CSS}</style>",
             f"<header><h1>{html.escape(ep.get('title', ''))} "
             f"<span style='color:var(--dim);font-weight:400'>· ep{a.episode:02d}</span></h1>"
             f"<div class='sub'>{len(rows)} shots · what was generated, and what generated it"
             f"</div></header><div class='wrap'>"]
    for r in rows:
        t = [tag(r["mode"].upper(), "mode"), tag(r["loc"]),
             tag(f"{r['dur']:.2f}s"), tag(f"setup {r['setup']}"),
             tag(f"staging {r['staging']}")]
        sc = r["scores"]
        if "reads_as" in sc:
            good = (sc["reads_as"] == "wide") == (not r["line"])
            t.append(tag(f"reads {sc['reads_as']}", "good" if good else "bad"))
        if "lip_ratio" in sc:
            lr = sc["lip_ratio"]
            t.append(tag(f"lip {lr}x", "good" if lr >= 2 else ("warn" if lr >= 1.3 else "bad")))
        vid = (f"<div class='vid'><div class='lab'>rendered</div>"
               f"<video src='{r['vid']}' controls preload='metadata' muted></video></div>"
               if r["vid"] else "<div class='lab'>no clip</div>")
        seed = (f"<div class='seed'><div class='lab'>seed image — {html.escape(r['seed_img'])}</div>"
                f"<img src='{r['seed_thumb']}'></div>" if r["seed_thumb"] else
                f"<div class='seed'><div class='lab'>seed image</div>"
                f"<div class='val'>{html.escape(r['seed_img'])}</div></div>")
        metrics = ""
        if sc:
            cells = "".join(f"<div class='m'><div class='k'>{html.escape(k)}</div>"
                            f"<div class='v'>{v}</div></div>"
                            for k, v in sc.items() if k != "reads_as")
            metrics = f"<div class='field'><div class='lab'>measured</div><div class='grid'>{cells}</div></div>"
        line = (f"<div class='field'><div class='lab'>line — {html.escape(r['who'])}</div>"
                f"<div class='line'>&ldquo;{html.escape(r['line'])}&rdquo;</div></div>"
                if r["line"] else "")
        parts.append(f"""<div class='shot'>
<div>{vid}{seed}</div>
<div>
  <div class='id'>{r['n']:02d} · {html.escape(r['sid'])}</div>
  <div class='tags'>{''.join(t)}</div>
  <div class='field'><div class='lab'>authored</div><div class='val'>{html.escape(r['visual'])}</div></div>
  {line}
  <div class='field'><div class='lab'>prompt sent</div><div class='val'>{html.escape(r['prompt'])}</div></div>
  <div class='field'><div class='lab'>negative</div><div class='val neg'>{html.escape(r['neg'])}</div></div>
  <div class='field'><div class='lab'>model</div><div class='val'>{html.escape(r['unet'])}
 · {html.escape(str(r['sampler']))} · cfg {r['cfg']} · shift {r['shift']}</div></div>
  {metrics}
</div></div>""")
    parts.append("</div>")
    (out / "index.html").write_text("\n".join(parts))
    (out / "shots.json").write_text(json.dumps(rows, indent=2, default=str))
    n = sum(1 for _ in out.rglob("*") if _.is_file())
    print(f"  {out}/index.html  ({len(rows)} shots, {n} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
