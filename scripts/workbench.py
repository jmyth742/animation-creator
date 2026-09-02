#!/usr/bin/env python3
"""
The Workbench: the series, editable and browsable, served from the pod.

Three needs, one address:
    Compose   the episode builder, with drafts saved SERVER-SIDE and every
              save kept as a version -- "the different things I've tried"
              survive the browser
    Episodes  every authored episode, its shots, and EVERY take ever
              rendered for each shot, playable side by side, with a
              promote button to make any take the live one
    Act       import a draft through the gates, queue a render, watch logs

Runs on :8888 (the one port RunPod proxies), key-gated because that proxy
URL is on the open internet. Media is served straight from the output
tree -- no copies, no staleness.
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

from flask import (Flask, request, send_file, jsonify, abort,
                   make_response, redirect)

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

DEFAULT_SHOW = "tir-na-nog-legend"


def S():
    """The selected show, per request."""
    from flask import request
    v = request.cookies.get("wbshow") or DEFAULT_SHOW
    return v if (Path("series") / v / "bible.json").exists() else DEFAULT_SHOW


def CLIPS_D():
    return Path("ComfyUI/output/video") / S()


def OUT_D():
    return Path("output") / S()

ROOT = Path(__file__).parent
WB = ROOT / "workbench_data"
DRAFTS = WB / "drafts"
DRAFTS.mkdir(parents=True, exist_ok=True)
KEYFILE = WB / "key.txt"
if not KEYFILE.exists():
    KEYFILE.write_text(secrets.token_urlsafe(9))
KEY = KEYFILE.read_text().strip()
SEQ = re.compile(r"^(?P<stem>.+?)_(?P<n>\d+)_?\.mp4$")

app = Flask(__name__)


@app.before_request
def _select_show():
    try:
        sr.set_current_series(S())
    except Exception:
        pass


@app.before_request
def gate():
    if request.path == "/health":
        return
    if request.args.get("key") == KEY:
        r = redirect(request.path or "/")
        r.set_cookie("wbkey", KEY, max_age=86400 * 30, httponly=True)
        return r
    if request.cookies.get("wbkey") != KEY:
        abort(401)


@app.get("/health")
def health():
    return "ok"


@app.get("/")
def index():
    r = make_response(send_file(ROOT / "workbench.html"))
    r.headers["Cache-Control"] = "no-store"          # a cached console hid
    return r                                          # whole tabs from its user


@app.get("/api/shows")
def shows():
    out = []
    for d in sorted(Path("series").iterdir()):
        if (d / "bible.json").exists():
            b = json.loads((d / "bible.json").read_text())
            eps = len(list((d / "episodes").glob("ep*.json"))) \
                if (d / "episodes").exists() else 0
            out.append({"id": d.name,
                        "title": b.get("series", {}).get("title", d.name),
                        "episodes": eps,
                        "characters": len(b.get("characters", {}))})
    return jsonify({"shows": out, "current": S()})


@app.post("/api/shows")
def new_show():
    d = request.get_json(force=True)
    sid = re.sub(r"[^a-z0-9_-]", "", (d.get("id") or "").lower())
    if not sid or (Path("series") / sid).exists():
        abort(400)
    root = Path("series") / sid
    for sub in ("episodes", "reference_images", "sets/_generated"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    bible = {"series": {"title": d.get("title") or sid,
                        "style": d.get("style") or
                        "Cel-shaded 2D animation, clean confident linework, "
                        "flat blocks of colour with simple shading, painted "
                        "background art"},
             "characters": {}, "world": {"locations": {}}}
    (root / "bible.json").write_text(json.dumps(bible, indent=2))
    return jsonify({"created": sid})


@app.post("/api/selectshow")
def select_show():
    sid = request.get_json(force=True).get("id", "")
    if not (Path("series") / sid / "bible.json").exists():
        abort(404)
    r = jsonify({"selected": sid})
    r.set_cookie("wbshow", sid, max_age=86400 * 90)
    return r


@app.get("/api/data")
def data():
    blob = f"/tmp/builder_data_{S()}.json"
    if not Path(blob).exists() or request.args.get("fresh"):
        import build_builder_data
        build_builder_data.build(S(), blob)
    return send_file(blob)


@app.get("/api/episodes")
def episodes():
    out = []
    for p in sorted((sr.series_path(S()) / "episodes").glob("ep*.json")):
        d = json.loads(p.read_text())
        n = int(p.stem[2:])
        final = OUT_D() / p.stem / f"{p.stem}_final.mp4"
        out.append({"n": n, "id": p.stem, "title": d.get("title", ""),
                    "shots": len(d.get("scenes", [])),
                    "rendered": final.exists(),
                    "seconds": round(sr._get_video_duration(final), 1)
                    if final.exists() else None})
    return jsonify(out)


@app.get("/api/episode/<int:n>")
def episode(n):
    p = sr.series_path(S()) / "episodes" / f"ep{n:02d}.json"
    if not p.exists():
        abort(404)
    d = json.loads(p.read_text())
    for s in d["scenes"]:
        takes = sorted(CLIPS_D().glob(f"{s['id']}_*.mp4"),
                       key=lambda f: f.stat().st_mtime)
        live = sr.find_latest_clip(s["id"])
        s["takes"] = [{"file": t.name, "live": str(t) == live,
                       "mtime": int(t.stat().st_mtime)} for t in takes]
    final = OUT_D() / f"ep{n:02d}" / f"ep{n:02d}_final.mp4"
    d["final"] = f"ep{n:02d}/ep{n:02d}_final.mp4" if final.exists() else None
    return jsonify(d)


@app.get("/media/clip/<path:name>")
def clip(name):
    p = (CLIPS / name).resolve()
    if not str(p).startswith(str(CLIPS_D().resolve())) or not p.exists():
        abort(404)
    return send_file(p, conditional=True)


@app.get("/media/final/<path:rel>")
def final(rel):
    p = (OUT_D() / rel).resolve()
    if not str(p).startswith(str(OUT_D().resolve())) or not p.exists():
        abort(404)
    return send_file(p, conditional=True)


@app.post("/api/promote")
def promote():
    body = request.get_json(force=True)
    name = body.get("file", "")
    src = (CLIPS / name).resolve()
    m = SEQ.match(name)
    if not m or not src.exists() or \
            not str(src).startswith(str(CLIPS_D().resolve())):
        abort(400)
    stem, n = m.group("stem"), 1
    while (CLIPS / f"{stem}_{n:05d}_.mp4").exists():
        n += 1
    dst = CLIPS / f"{stem}_{n:05d}_.mp4"
    shutil.copy(src, dst)
    return jsonify({"promoted": dst.name,
                    "note": "re-stitch the episode to pick it up"})


# ── drafts with version history ──────────────────────────────────────
def _slug(s):
    return re.sub(r"[^a-z0-9_-]+", "-", (s or "untitled").lower())[:48]


@app.get("/api/drafts")
def drafts():
    out = []
    for d in sorted(DRAFTS.iterdir()):
        if d.is_dir():
            vs = sorted(d.glob("v*.json"))
            if vs:
                latest = json.loads(vs[-1].read_text())
                out.append({"slug": d.name, "title": latest.get("title", d.name),
                            "versions": len(vs),
                            "shots": len(latest.get("scenes", [])),
                            "updated": int(vs[-1].stat().st_mtime)})
    return jsonify(out)


@app.post("/api/draft")
def save_draft():
    doc = request.get_json(force=True)
    slug = _slug(doc.get("slug") or doc.get("title"))
    d = DRAFTS / slug
    d.mkdir(exist_ok=True)
    n = len(list(d.glob("v*.json"))) + 1
    (d / f"v{n:03d}.json").write_text(json.dumps(doc, indent=2))
    return jsonify({"slug": slug, "version": n})


@app.get("/api/draft/<slug>")
def get_draft(slug):
    d = DRAFTS / _slug(slug)
    vs = sorted(d.glob("v*.json"))
    if not vs:
        abort(404)
    v = request.args.get("v")
    p = d / f"v{int(v):03d}.json" if v else vs[-1]
    doc = json.loads(p.read_text())
    doc["_versions"] = [int(x.stem[1:]) for x in vs]
    return jsonify(doc)


# ── actions ──────────────────────────────────────────────────────────
@app.post("/api/import")
def do_import():
    doc = request.get_json(force=True)
    tmp = "/tmp/wb_import.json"
    Path(tmp).write_text(json.dumps(doc))
    r = subprocess.run([sys.executable, str(ROOT / "import_episode.py"),
                        S(), "--file", tmp],
                       capture_output=True, text=True, timeout=600)
    return jsonify({"ok": r.returncode == 0,
                    "log": (r.stdout + r.stderr)[-4000:]})


@app.post("/api/render")
def do_render():
    n = int(request.get_json(force=True).get("episode"))
    log = f"/workspace/wb_render_ep{n}.log"
    cmd = (f"cd {ROOT.parent} && {sys.executable} scripts/showrunner.py "
           f"produce {S()} --episode {n} --quality final --upscale "
           f">> {log} 2>&1 && {sys.executable} scripts/master_audio.py "
           f"{S()} --episode {n} >> {log} 2>&1")
    subprocess.Popen(["bash", "-c", cmd], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return jsonify({"queued": n, "log": log})


@app.get("/api/log")
def taillog():
    p = request.args.get("f", "")
    if not re.fullmatch(r"/workspace/wb_render_ep\d+\.log", p) \
            or not Path(p).exists():
        return jsonify({"log": "(no log yet)"})
    return jsonify({"log": Path(p).read_text()[-6000:]})



# ── the lineage graph ────────────────────────────────────────────────
@app.get("/media/asset/<path:rel>")
def asset(rel):
    base = sr.series_path(S()).resolve()
    q = (base / rel).resolve()
    if not str(q).startswith(str(base)) or not q.exists():
        abort(404)
    return send_file(q, conditional=True)


def _seed_lineage(seed_path):
    """A seed image's parents: how the picture the shot grew from was made."""
    base = sr.series_path(S())
    p = Path(seed_path)
    rel = None
    try:
        rel = str(p.resolve().relative_to(base.resolve()))
    except ValueError:
        pass
    name = p.name
    if name.endswith("__inplace.png"):
        setup = name.split("__")[0]
        loc = p.parent.name
        return {"kind": "composite", "label": name.replace(".png", ""),
                "rel": rel, "parents": [
                    {"kind": "staged", "label": name.replace("__inplace", ""),
                     "rel": f"sets/{loc}/{name.replace('__inplace', '')}"},
                    {"kind": "location", "label": f"{loc}/{setup}",
                     "rel": f"sets/{loc}/{setup}.png"}]}
    if name.startswith("gen__"):
        return {"kind": "generated", "label": name.replace(".png", ""),
                "rel": rel, "parents": [
                    {"kind": "flux", "label": "FLUX text-to-image", "rel": None}]}
    if "__" in name:
        loc = p.parent.name
        return {"kind": "staged", "label": name.replace(".png", ""),
                "rel": rel, "parents": [
                    {"kind": "portrait", "label": name.split("__")[1].split("_")[0],
                     "rel": None},
                    {"kind": "location", "label": f"{loc}/master",
                     "rel": f"sets/{loc}/master.png"}]}
    if name.startswith("char_") or "reference_images" in str(p):
        return {"kind": "portrait", "label": p.stem, "rel": rel, "parents": []}
    return {"kind": "location", "label": p.stem, "rel": rel, "parents": []}


@app.get("/api/graph/<int:n>")
def graph(n):
    p = sr.series_path(S()) / "episodes" / f"ep{n:02d}.json"
    if not p.exists():
        abort(404)
    ep = json.loads(p.read_text())
    bible = sr.load_json(sr.series_path(S()) / "bible.json")
    res = sr.get_resolution_config("480p", "wan")
    mc = sr.get_model_config("wan")
    shots, assets = [], {}
    for sc in ep["scenes"]:
        mode = sr.classify_scene_type(sc)
        seed = sr.get_scene_seed_image(sc, S(), None)
        seed_key = None
        if seed:
            src = sr.COMFYUI_INPUT / str(seed)
            lin = _seed_lineage(src if src.exists() else Path(str(seed)))
            seed_key = lin["label"]
            if seed_key not in assets:
                assets[seed_key] = lin
        clip = sr.find_latest_clip(sc["id"])
        unet = (sr._s2v_unet(res) if mode == "s2v"
                else "wan2.2 i2v 14B dual")
        shots.append({
            "id": sc["id"], "mode": mode,
            "hold": float(sc.get("hold_seconds") or 6.0),
            "visual": sc.get("visual", ""),
            "line": (sc.get("dialogue") or [{}])[0].get("line"),
            "who": (sc.get("dialogue") or [{}])[0].get("character"),
            "prompt": sr.build_scene_prompt(sc, bible),
            "negative": sr.build_negative_prompt(sc)[:400],
            "model": f"{unet} · {mc.get('sampler')} · cfg {mc.get('cfg')} "
                     f"· shift {res.get('shift')}",
            "seed_asset": seed_key,
            "clip": Path(clip).name if clip else None,
            "takes": len(list(CLIPS_D().glob(f"{sc['id']}_*.mp4"))),
        })
    return jsonify({"title": ep.get("title", ""), "shots": shots,
                    "assets": assets})



# ── the forge: cast and sets from the console ────────────────────────
VOICES = ["en-IE-ConnorNeural", "en-IE-EmilyNeural", "en-GB-RyanNeural",
          "en-GB-SoniaNeural", "en-GB-ThomasNeural", "en-GB-LibbyNeural",
          "en-US-GuyNeural", "en-US-AriaNeural"]
FORGE_LOG = "/workspace/wb_forge.log"


@app.get("/api/bible")
def bible():
    b = sr.load_json(sr.series_path(S()) / "bible.json")
    chars = {k: {"visual": v.get("visual", ""), "voice": v.get("voice"),
                 "personality": v.get("personality", "")}
             for k, v in b.get("characters", {}).items()}
    locs = b.get("world", {}).get("locations", {})
    return jsonify({"characters": chars, "locations": locs, "voices": VOICES})


def _forge(args):
    Path(FORGE_LOG).write_text("")
    cmd = [sys.executable, str(ROOT / "forge_assets.py")] + args
    subprocess.Popen(cmd, stdout=open(FORGE_LOG, "a"),
                     stderr=subprocess.STDOUT, start_new_session=True,
                     cwd=str(ROOT.parent))


@app.post("/api/forge/character")
def forge_char():
    d = request.get_json(force=True)
    cid = re.sub(r"[^a-z0-9_]", "", (d.get("id") or "").lower())
    if not cid or not d.get("visual") or not d.get("voice"):
        abort(400)
    _forge(["character", cid, "--series", S(), "--visual", d["visual"],
            "--voice", d["voice"], "--personality", d.get("personality", "")])
    return jsonify({"forging": cid, "log": FORGE_LOG})


@app.post("/api/forge/location")
def forge_loc():
    d = request.get_json(force=True)
    lid = re.sub(r"[^a-z0-9_]", "", (d.get("id") or "").lower())
    if not lid or not d.get("desc"):
        abort(400)
    _forge(["location", lid, "--series", S(), "--desc", d["desc"]])
    return jsonify({"forging": lid, "log": FORGE_LOG})


@app.get("/api/forge/log")
def forge_log():
    t = Path(FORGE_LOG).read_text()[-5000:] if Path(FORGE_LOG).exists() else ""
    done = "[forge] DONE" in t or "FAILED" in t
    return jsonify({"log": t, "done": done})


@app.post("/api/voicetest")
def voicetest():
    d = request.get_json(force=True)
    v = d.get("voice", "")
    if v not in VOICES:
        abort(400)
    text = (d.get("text") or "The sea gives nothing back, and I have "
            "stopped asking it to.")[:200]
    out = "/tmp/wb_voicetest.mp3"
    import asyncio, edge_tts
    asyncio.run(edge_tts.Communicate(text, v, rate="+4%").save(out))
    return send_file(out, mimetype="audio/mpeg")



# ── full control: save-in-place, single-shot reroll, bible edits ─────
@app.post("/api/episode/<int:n>")
def save_episode(n):
    doc = request.get_json(force=True)
    tmp = "/tmp/wb_save.json"
    Path(tmp).write_text(json.dumps(doc))
    r = subprocess.run([sys.executable, str(ROOT / "import_episode.py"),
                        S(), "--file", tmp, "--number", str(n)],
                       capture_output=True, text=True, timeout=600)
    return jsonify({"ok": r.returncode == 0,
                    "log": (r.stdout + r.stderr)[-4000:]})


@app.post("/api/reroll")
def reroll():
    shot = request.get_json(force=True).get("shot", "")
    if not re.fullmatch(r"ep\d+_s\d+[a-z]?", shot):
        abort(400)
    log = f"/workspace/wb_reroll_{shot}.log"
    subprocess.Popen([sys.executable, str(ROOT / "reroll_shot.py"), S(), shot],
                     stdout=open(log, "w"), stderr=subprocess.STDOUT,
                     start_new_session=True, cwd=str(ROOT.parent))
    return jsonify({"rolling": shot, "log": log})


@app.get("/api/reroll/log")
def reroll_log():
    shot = request.args.get("shot", "")
    log = Path(f"/workspace/wb_reroll_{shot}.log")
    t = log.read_text()[-3000:] if log.exists() else ""
    return jsonify({"log": t, "done": "DONE" in t or "FAILED" in t})


@app.post("/api/edit/character")
def edit_character():
    d = request.get_json(force=True)
    cid = d.get("id", "")
    b = sr.load_json(sr.series_path(S()) / "bible.json")
    if cid not in b.get("characters", {}):
        abort(404)
    for k in ("visual", "voice", "personality"):
        if d.get(k) is not None:
            b["characters"][cid][k] = d[k]
    bp = sr.series_path(S()) / "bible.json"
    shutil.copy(bp, bp.with_suffix(f".json.bak.{int(time.time())}"))
    bp.write_text(json.dumps(b, indent=2))
    return jsonify({"saved": cid})


@app.post("/api/edit/location")
def edit_location():
    d = request.get_json(force=True)
    lid = d.get("id", "")
    b = sr.load_json(sr.series_path(S()) / "bible.json")
    if lid not in b.get("world", {}).get("locations", {}):
        abort(404)
    b["world"]["locations"][lid] = d.get("desc", "")
    bp = sr.series_path(S()) / "bible.json"
    shutil.copy(bp, bp.with_suffix(f".json.bak.{int(time.time())}"))
    bp.write_text(json.dumps(b, indent=2))
    return jsonify({"saved": lid})


if __name__ == "__main__":
    print(f"workbench key: {KEY}")
    app.run(host="0.0.0.0", port=8888, threaded=True)
