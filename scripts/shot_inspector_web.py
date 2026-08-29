#!/usr/bin/env python3
"""
The shot inspector as a single self-contained page, for a phone.

Same data as shot_inspector.py -- clip, prompt, negative, seed image, model,
measurements -- but every asset is embedded as a data URI so the page is one
file that works from a URL with nothing beside it. Clips are re-encoded small
(416px, mono 48k) because the question on a phone is "what did this shot do",
not "is the grain right".

    shot_inspector_web.py <series> --episode 13 -o page.html
"""
import argparse
import base64
import html
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import shot_inspector as si                                    # noqa: E402
import showrunner as sr                                        # noqa: E402


def b64_video(src, td):
    dst = Path(td) / (Path(src).stem + ".mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
                    "scale=416:240", "-c:v", "libx264", "-crf", "33",
                    "-preset", "veryfast", "-c:a", "aac", "-b:a", "48k",
                    "-ac", "1", "-movflags", "+faststart", str(dst)], check=False)
    if not dst.exists():
        return None
    return "data:video/mp4;base64," + base64.b64encode(dst.read_bytes()).decode()


def b64_image(src, td, w=380):
    dst = Path(td) / (Path(src).stem + ".jpg")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
                    f"scale={w}:-1", "-q:v", "6", str(dst)], check=False)
    if not dst.exists():
        return None
    return "data:image/jpeg;base64," + base64.b64encode(dst.read_bytes()).decode()


CSS = """
:root{
  --ground:#F3F4F1; --card:#FFFFFF; --edge:#DCDFD9; --rule:#E7E9E4;
  --ink:#171C19; --body:#3E453F; --dim:#6D766E;
  --acc:#3C5F7E; --good:#3E7A48; --warn:#8A6510; --bad:#9E3C34;
  --acc-bg:#E3EAF1; --good-bg:#E2EFE4; --warn-bg:#F2E9D4; --bad-bg:#F5E1DE;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#0E1211; --card:#171D1A; --edge:#2A332E; --rule:#232B27;
  --ink:#E8EBE6; --body:#BAC2BB; --dim:#8B948C;
  --acc:#7FA6C9; --good:#78BE82; --warn:#DEB05C; --bad:#D66058;
  --acc-bg:#152230; --good-bg:#15251A; --warn-bg:#271F12; --bad-bg:#2A1613;
}}
:root[data-theme="dark"]{
  --ground:#0E1211; --card:#171D1A; --edge:#2A332E; --rule:#232B27;
  --ink:#E8EBE6; --body:#BAC2BB; --dim:#8B948C;
  --acc:#7FA6C9; --good:#78BE82; --warn:#DEB05C; --bad:#D66058;
  --acc-bg:#152230; --good-bg:#15251A; --warn-bg:#271F12; --bad-bg:#2A1613;
}
*{box-sizing:border-box}
body{background:var(--ground);color:var(--body);margin:0;
  font-family:"Source Sans 3",system-ui,-apple-system,sans-serif;
  font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}
header{padding:22px 16px 18px;border-bottom:1px solid var(--rule)}
h1{font-family:Newsreader,Georgia,serif;color:var(--ink);margin:0;
   font-size:1.6rem;font-weight:600;line-height:1.15;text-wrap:balance}
.sub{color:var(--dim);font-size:.9rem;margin-top:5px}
.legend{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
main{padding:16px;display:flex;flex-direction:column;gap:16px;max-width:1100px;margin:0 auto}
.shot{background:var(--card);border:1px solid var(--edge);border-radius:6px;padding:14px}
@media(min-width:860px){
  .shot{display:grid;grid-template-columns:400px 1fr;gap:22px;padding:18px}
  header{padding:30px 32px 24px} main{padding:24px 32px}
}
video{width:100%;border-radius:4px;background:#000;display:block}
.seedimg{width:100%;border-radius:4px;border:1px solid var(--edge);margin-top:10px;display:block}
.num{font-family:"JetBrains Mono",ui-monospace,monospace;font-weight:700;
     font-size:1.05rem;color:var(--ink);font-variant-numeric:tabular-nums}
.tags{display:flex;gap:6px;flex-wrap:wrap;margin:9px 0 13px}
.tag{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.66rem;
     font-weight:700;letter-spacing:.09em;text-transform:uppercase;
     padding:4px 8px;border-radius:3px;background:var(--rule);color:var(--dim);
     white-space:nowrap}
.tag.mode{background:var(--acc-bg);color:var(--acc)}
.tag.good{background:var(--good-bg);color:var(--good)}
.tag.warn{background:var(--warn-bg);color:var(--warn)}
.tag.bad{background:var(--bad-bg);color:var(--bad)}
.lab{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.63rem;
     font-weight:700;letter-spacing:.12em;text-transform:uppercase;
     color:var(--dim);margin-bottom:5px}
.field{margin-bottom:13px}
.val{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:12.5px;
     line-height:1.5;color:var(--ink);background:var(--ground);
     border:1px solid var(--edge);border-radius:4px;padding:9px 11px;
     white-space:pre-wrap;overflow-wrap:anywhere}
details.neg summary{font-family:"JetBrains Mono",ui-monospace,monospace;
     font-size:.63rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
     color:var(--dim);cursor:pointer;padding:4px 0}
details.neg .val{color:var(--dim);margin-top:5px}
.line{font-family:Newsreader,Georgia,serif;font-style:italic;font-size:1.08rem;
      line-height:1.5;color:var(--ink)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(104px,1fr));gap:9px}
.m{background:var(--ground);border:1px solid var(--edge);border-radius:4px;padding:8px 10px}
.m .k{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.6rem;
      font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--dim)}
.m .v{font-family:"JetBrains Mono",ui-monospace,monospace;font-weight:700;
      font-size:1.12rem;font-variant-numeric:tabular-nums;color:var(--ink)}
footer{padding:26px 16px 60px;color:var(--dim);font-size:.85rem;max-width:1100px;margin:0 auto}
"""


def tag(t, cls=""):
    return f'<span class="tag {cls}">{html.escape(str(t))}</span>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    ep = sr.load_json(sr.episode_path(a.series, a.episode))
    res = sr.get_resolution_config("480p", "wan")
    mc = sr.get_model_config("wan")

    body = []
    with tempfile.TemporaryDirectory() as td:
        for i, scene in enumerate(ep["scenes"], 1):
            sid = scene["id"]
            mode = sr.classify_scene_type(scene)
            seed_img = sr.get_scene_seed_image(scene, a.series, None)
            clip = sr.find_latest_clip(sid)
            vo = (Path("output") / a.series / f"ep{a.episode:02d}" / "audio" / f"{sid}.mp3")
            sc = si.measure(clip, vo) if clip else {}
            dur = sr._get_video_duration(clip) if clip else 0.0
            line = (scene.get("dialogue") or [{}])[0].get("line", "")
            who = (scene.get("dialogue") or [{}])[0].get("character", "")

            t = [tag(mode.upper(), "mode"), tag(scene.get("location", "—")),
                 tag(f"{dur:.1f}s")]
            if "reads_as" in sc:
                ok = (sc["reads_as"] == "wide") == (not line)
                t.append(tag(f"reads {sc['reads_as']}", "good" if ok else "bad"))
            if "lip_ratio" in sc:
                lr = sc["lip_ratio"]
                t.append(tag(f"lip {lr}×",
                             "good" if lr >= 2 else "warn" if lr >= 1.3 else "bad"))

            vid = ""
            if clip:
                u = b64_video(clip, td)
                if u:
                    vid = (f"<div class='lab'>rendered</div>"
                           f"<video src='{u}' controls preload='none' playsinline></video>")
            seed = ""
            if seed_img:
                src = sr.COMFYUI_INPUT / str(seed_img)
                if src.exists():
                    u = b64_image(src, td)
                    if u:
                        seed = (f"<div class='lab' style='margin-top:12px'>seed — "
                                f"{html.escape(str(seed_img))}</div>"
                                f"<img class='seedimg' src='{u}' loading='lazy'>")
            metrics = ""
            if sc:
                cells = "".join(f"<div class='m'><div class='k'>{html.escape(k)}</div>"
                                f"<div class='v'>{v}</div></div>"
                                for k, v in sc.items() if k != "reads_as")
                metrics = (f"<div class='field'><div class='lab'>measured</div>"
                           f"<div class='grid'>{cells}</div></div>")
            linehtml = (f"<div class='field'><div class='lab'>line — {html.escape(who)}</div>"
                        f"<div class='line'>&ldquo;{html.escape(line)}&rdquo;</div></div>"
                        if line else "")
            unet = (sr._s2v_unet(res) if mode == "s2v"
                    else mc.get("unet_high") or "wan 2.2 i2v dual-model")
            body.append(f"""<article class='shot'>
<div>{vid}{seed}</div>
<div>
  <div class='num'>{i:02d} · {html.escape(sid)}</div>
  <div class='tags'>{''.join(t)}</div>
  <div class='field'><div class='lab'>authored</div>
    <div class='val'>{html.escape(scene.get('visual',''))}</div></div>
  {linehtml}
  <div class='field'><div class='lab'>prompt sent</div>
    <div class='val'>{html.escape(sr.build_scene_prompt(scene, bible))}</div></div>
  <details class='neg'><summary>negative prompt</summary>
    <div class='val'>{html.escape(sr.build_negative_prompt(scene))}</div></details>
  <div class='field' style='margin-top:13px'><div class='lab'>model</div>
    <div class='val'>{html.escape(str(unet))}
{html.escape(str(mc.get('sampler')))} · cfg {mc.get('cfg')} · shift {res.get('shift')}</div></div>
  {metrics}
</div></article>""")

    page = f"""<title>Shot Inspector · ep{a.episode:02d}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400&family=Source+Sans+3:wght@400;600&family=JetBrains+Mono:wght@400;700&display=swap">
<style>{CSS}</style>
<header>
  <h1>{html.escape(ep.get('title',''))}</h1>
  <div class="sub">ep{a.episode:02d} · {len(ep['scenes'])} shots · what was generated, and what generated it</div>
  <div class="legend">{tag('reads wide/close','good')}{tag('wrong framing','bad')}{tag('lip ≥2×','good')}{tag('lip &lt;1.3×','bad')}</div>
</header>
<main>{''.join(body)}</main>
<footer>Prompts are produced by the same functions the renderer calls, so what is
shown is what was sent. Clips are re-encoded small for the page; the masters are
on the pod. &ldquo;reads&rdquo; is CLIP framing; &ldquo;lip&rdquo; is how much more the mouth moves
while there is speech than while there is none — under 1.3× means the sync is
not working on that shot.</footer>"""
    Path(a.out).write_text(page)
    mb = Path(a.out).stat().st_size / 1048576
    print(f"  {a.out}  {mb:.1f} MB  ({len(ep['scenes'])} shots embedded)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
