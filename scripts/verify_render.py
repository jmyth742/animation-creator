#!/usr/bin/env python3
"""
Does each rendered shot actually resemble what it was seeded from?

validate_clip() checks file size, duration, black and frozen frames -- technical
faults. It cannot see a different person, a modern interior, or a shot that
collapsed into cel-shaded cartoon, which are the failures that have actually
reached finished episodes here.

Every shot has an anchor: a character portrait, a location plate, or nothing
(pure T2V). This scores each shot against its anchor so drift surfaces without
waiting for someone to watch the episode.

Default backend is CLIP (--backend hist keeps the old colour/detail statistics
as a fallback). Three signals per shot:

  * identity -- cosine similarity, frames vs the anchor image
  * setting  -- does the intended location beat a set of interior/studio
                distractors, as a zero-shot contest
  * cel      -- does the frame read as cel-shaded or as photoreal

What each signal is actually worth, measured against the known-bad ep04-v1
pass (17 shots, failures already diagnosed by eye):

  setting   VALIDATED. ep04_s02 -- a real green headland over the sea -- scored
            1.000. ep04_s08, which is a modern woman in a yellow blazer against
            clapboard siding, scored 0.000. That is the modern-interior failure
            the histogram backend scored as fine, and the reason this file was
            demoted to triage before. This is the signal to trust.

  identity  WEAK on that set: 0.598 for the good shot vs 0.622 for the bad one,
            i.e. inverted and meaningless. Anchor style dominates the score, so
            it is only comparable when clips and anchors share a style. Treat it
            as advisory, not as a gate.

  cel       Uniform 0.000 across all 17 v1 shots. Correct in aggregate (that
            pass was photoreal) but it carries no discrimination WITHIN a set
            rendered in one style. Useful for catching a style split between
            shots, not for ranking shots inside a consistent pass.

So: a flagged "wrong setting" is worth acting on; a flagged "drift" is worth a
look, not a regeneration.

    python scripts/verify_render.py <series> --episode 4
    python scripts/verify_render.py <series> --episode 4 --clips-dir <dir>
"""
import argparse, json, math, statistics, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr
from PIL import Image

SAMPLES = 3


def _frames(clip: Path, n: int = SAMPLES):
    dur = sr._get_video_duration(str(clip)) or 0
    if dur <= 0:
        return []
    tmp = Path(tempfile.mkdtemp())
    out = []
    for k in range(1, n + 1):
        t = dur * k / (n + 1)
        f = tmp / f"f{k}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(clip),
                        "-frames:v", "1", str(f)], timeout=60)
        if f.exists():
            out.append(f)
    return out


def _hsv_hist(img: Image.Image, bins: int = 12):
    hsv = img.convert("RGB").resize((64, 64)).convert("HSV")
    h, s, v = [list(ch.getdata()) for ch in hsv.split()]
    def hist(vals):
        b = [0] * bins
        for x in vals:
            b[min(bins - 1, x * bins // 256)] += 1
        tot = sum(b) or 1
        return [c / tot for c in b]
    return hist(h) + hist(s) + hist(v)


def _detail(img: Image.Image) -> float:
    """Mean gradient magnitude — photoreal texture scores high, flat cel-shading low."""
    g = img.convert("L").resize((96, 96))
    px = list(g.getdata())
    w = 96
    tot = 0
    for y in range(w - 1):
        for x in range(w - 1):
            i = y * w + x
            tot += abs(px[i] - px[i + 1]) + abs(px[i] - px[i + w])
    return tot / ((w - 1) * (w - 1) * 2)


def _corr(a, b) -> float:
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else 0.0


def _border(img: Image.Image) -> Image.Image:
    """Outer frame only — the setting, with the subject's face excluded."""
    im = img.convert("RGB").resize((96, 96))
    px = im.load()
    keep = []
    for y in range(96):
        for x in range(96):
            if x < 22 or x > 73 or y < 16:      # sides and top: background
                keep.append(px[x, y])
    out = Image.new("RGB", (len(keep), 1))
    out.putdata(keep)
    return out


# ══════════════════════════════════════════════════════════════════════
#  CLIP backend
#
#  The histogram signals above were wrong twice in a row on real footage: a
#  visibly worse pass scored BETTER than the one it replaced, and the setting
#  check flagged 15 of 17 shots including good ones. Colour and gradient
#  statistics simply do not encode "is this the same person" or "is this a
#  cliff or a hotel lobby", so the tool was demoted to triage.
#
#  CLIP does encode that. Three questions per shot, each answered by cosine
#  similarity in a shared image/text space:
#
#    identity  image<->anchor portrait   -- is this the same character?
#    setting   image<->caption set       -- is this the intended place, or an
#                                           interior/studio the model invented?
#    style     image<->caption set       -- cel-shaded, or a photoreal shot
#                                           that will not cut with the rest?
#
#  Runs on CPU by default so it never contends with a render for VRAM.
_CLIP = {}


def _clip():
    """Lazy-load CLIP. Returns (model, processor) or None if unavailable."""
    if "m" in _CLIP:
        return _CLIP["m"]
    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor
        name = "openai/clip-vit-base-patch32"
        # transformers 5.x refuses .bin weights on torch < 2.6 (CVE-2025-32434);
        # the repo ships safetensors, so ask for them explicitly.
        model = CLIPModel.from_pretrained(name, use_safetensors=True).eval()
        proc = CLIPProcessor.from_pretrained(name)
        _CLIP["m"] = (model, proc, torch)
    except Exception as e:                                    # noqa: BLE001
        print(f"  CLIP unavailable ({type(e).__name__}: {str(e)[:80]}) — "
              f"falling back to histogram scoring", file=sys.stderr)
        _CLIP["m"] = None
    return _CLIP["m"]


def _feats(out, torch):
    """transformers 5.x returns BaseModelOutputWithPooling; 4.x returned a tensor.
    pooler_output is the projected 512-d embedding in both towers, so image and
    text vectors live in the same space and cosine similarity is meaningful."""
    v = out if torch.is_tensor(out) else out.pooler_output
    return v / v.norm(dim=-1, keepdim=True)


def _embed_images(imgs):
    model, proc, torch = _clip()
    with torch.no_grad():
        inp = proc(images=imgs, return_tensors="pt")
        return _feats(model.get_image_features(**inp), torch)


def _embed_texts(texts):
    model, proc, torch = _clip()
    with torch.no_grad():
        inp = proc(text=texts, return_tensors="pt", padding=True, truncation=True)
        return _feats(model.get_text_features(**inp), torch)


# Distractors are what the model actually drifted TO in past failures: modern
# rooms, studio backdrops, and photoreal renders that would not cut together.
_INTERIOR_DISTRACTORS = [
    "a modern indoor room with furniture",
    "a plain white studio backdrop",
    "an office interior",
    "a contemporary living room",
]
_STYLE_OPTIONS = [
    "a cel-shaded 2D animation frame with flat colour and clean linework",
    "a photorealistic live-action film photograph of real people",
]


def clip_score(clip: Path, anchor: Path, setting_text: str | None = None):
    """Identity / setting / style scores for one shot, or None."""
    if not _clip():
        return None
    frame_paths = _frames(clip)
    if not frame_paths:
        return None
    imgs = []
    for f in frame_paths:
        with Image.open(f) as im:
            imgs.append(im.convert("RGB").copy())
        f.unlink(missing_ok=True)
    with Image.open(anchor) as a:
        anchor_img = a.convert("RGB").copy()

    fv = _embed_images(imgs)
    av = _embed_images([anchor_img])
    identity = float((fv @ av.T).mean())

    out = {"identity": round(identity, 3)}

    # Setting: the intended place must beat every interior distractor. Framed
    # as a contest rather than a threshold, because absolute CLIP similarity
    # varies with caption wording and is not comparable across scenes.
    if setting_text:
        opts = [setting_text] + _INTERIOR_DISTRACTORS
        tv = _embed_texts(opts)
        sims = (fv @ tv.T).mean(dim=0)
        probs = (sims * 100).softmax(dim=-1)
        out["setting"] = round(float(probs[0]), 3)
        out["setting_best"] = opts[int(sims.argmax())][:40]

    sv = _embed_texts(_STYLE_OPTIONS)
    ssims = (fv @ sv.T).mean(dim=0)
    sprobs = (ssims * 100).softmax(dim=-1)
    out["cel"] = round(float(sprobs[0]), 3)
    return out


def score(clip: Path, anchor: Path, plate: Path | None = None):
    frames = _frames(clip)
    if not frames:
        return None
    with Image.open(anchor) as a:
        a = a.copy()
    ah, ad = _hsv_hist(a), _detail(a)
    cols, dets = [], []
    for f in frames:
        with Image.open(f) as im:
            cols.append(_corr(ah, _hsv_hist(im)))
            dets.append(_detail(im))
        f.unlink(missing_ok=True)
    colour = statistics.mean(cols)
    detail_ratio = statistics.mean(dets) / ad if ad else 0.0
    out = {"colour": round(colour, 3), "detail_ratio": round(detail_ratio, 3)}

    # Setting check. A portrait anchor says nothing about where the scene is, so
    # a character in a white studio room scored fine against it -- exactly the
    # v1 failure this tool missed. Compare the FRAME BORDER (background, face
    # excluded) against the location plate instead.
    if plate:
        with Image.open(plate) as pl:
            ph = _hsv_hist(_border(pl.copy()))
        bg = []
        for f in _frames(clip):
            with Image.open(f) as im:
                bg.append(_corr(ph, _hsv_hist(_border(im))))
            f.unlink(missing_ok=True)
        if bg:
            out["setting"] = round(statistics.mean(bg), 3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, default=1)
    ap.add_argument("--clips-dir", default=None,
                    help="override where clips are read from (for scoring an archived pass)")
    ap.add_argument("--backend", choices=["clip", "hist"], default="clip",
                    help="clip = semantic (default); hist = the old colour/detail "
                         "statistics, kept only as a fallback when CLIP cannot load")
    ap.add_argument("--identity-min", type=float, default=0.55,
                    help="cosine similarity to the anchor below which a shot is called drifted")
    ap.add_argument("--setting-min", type=float, default=0.50,
                    help="probability the intended setting beats the interior distractors")
    ap.add_argument("--cel-min", type=float, default=0.50,
                    help="probability the frame reads as cel-shaded rather than photoreal")
    ap.add_argument("--colour-min", type=float, default=0.55)
    ap.add_argument("--detail-min", type=float, default=0.45)
    ap.add_argument("--check-setting", action="store_true",
                    help="hist backend only: compare frame background to the location plate")
    ap.add_argument("--flag", action="store_true", help="write failures into flags.json")
    a = ap.parse_args()
    sr.set_current_series(a.series)

    ep = sr.load_json(sr.episode_path(a.series, a.episode))
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    locations = bible.get("world", {}).get("locations", {})
    ref_dir = sr.series_path(a.series) / "reference_images"
    clips_dir = Path(a.clips_dir) if a.clips_dir else None
    use_clip = a.backend == "clip" and _clip() is not None

    rows = []
    for scene in ep["scenes"]:
        sid = scene["id"]
        if clips_dir:
            found = sorted(clips_dir.glob(f"{sid}_*.mp4"))
            clip = found[-1] if found else None
        else:
            c = sr.find_latest_clip(sid)
            clip = Path(c) if c else None
        if not clip:
            rows.append((sid, "-", None, ["NO CLIP"])); continue

        anchor = None
        for cid in scene.get("characters", []):
            anchor = sr._find_ref(ref_dir, cid, "char")
            if anchor:
                break
        if not anchor and scene.get("location"):
            anchor = sr._find_ref(ref_dir, scene["location"], "loc")
        if not anchor:
            rows.append((sid, "none", None, [])); continue

        if use_clip:
            loc_desc = locations.get(scene.get("location", ""), "")
            setting_text = loc_desc.split(".")[0].strip()[:180] if loc_desc else None
            sc = clip_score(clip, anchor, setting_text)
            if not sc:
                rows.append((sid, anchor.stem, None, ["unreadable"])); continue
            bad = []
            if sc["identity"] < a.identity_min:
                bad.append("drift")
            # The setting signal needs a visible setting. On a tight close-up
            # the face fills the frame and the background is a few blurred
            # pixels, so the intended location loses to the distractors on
            # almost every good shot -- it flagged 7 of 17 correct close-ups.
            # Score it and print it, but do not fail on it where it cannot see.
            shot = sr._infer_shot_type(scene.get("visual", ""))
            setting_meaningful = shot != "closeup"
            if "setting" in sc and sc["setting"] < a.setting_min:
                if setting_meaningful:
                    bad.append("wrong setting")
                else:
                    sc["setting_note"] = "close-up: no visible setting to judge"
            if sc["cel"] < a.cel_min:
                bad.append("not cel-shaded")
            rows.append((sid, anchor.stem, sc, bad))
        else:
            plate = sr._find_ref(ref_dir, scene["location"], "loc") if scene.get("location") else None
            sc = score(clip, anchor, plate if anchor != plate else None)
            if not sc:
                rows.append((sid, anchor.stem, None, ["unreadable"])); continue
            bad = []
            if sc["colour"] < a.colour_min:
                bad.append("colour")
            if sc["detail_ratio"] < a.detail_min:
                bad.append("flat")
            if a.check_setting and "setting" in sc and sc["setting"] < a.setting_min:
                bad.append("wrong setting")
            rows.append((sid, anchor.stem, sc, bad))

    key_id = "identity" if use_clip else "colour"
    label = "identity" if use_clip else "colour"
    print(f"\n  backend: {'CLIP (semantic)' if use_clip else 'histogram (fallback)'}")
    print(f"\n  {'scene':14} {'anchor':20} {label:>8} {'setting':>8} {'cel':>6}  verdict")
    print("  " + "─" * 72)

    fails = []
    ranked = sorted(rows, key=lambda r: (r[2] or {}).get(key_id, 9))
    for sid, anc, sc, bad in ranked:
        v = f"{sc[key_id]:.3f}" if sc and key_id in sc else "   -  "
        st = f"{sc['setting']:.3f}" if sc and "setting" in sc else "   -  "
        ce = f"{sc['cel']:.3f}" if sc and "cel" in sc else "  -  "
        verdict = ",".join(bad) if bad else ("no anchor" if anc == "none" else "ok")
        if not bad and sc and sc.get("setting_note"):
            verdict = "ok (setting n/a — close-up)"
        mark = "  <<" if bad else ""
        print(f"  {sid:14} {anc:20} {v:>8} {st:>8} {ce:>6}  {verdict}{mark}")
        if bad and bad != ["NO CLIP"]:
            fails.append(sid)

    print(f"\n  {len(fails)} shot(s) flagged: {', '.join(fails) or 'none'}")
    if a.flag and fails:
        ep_out = sr.OUTPUT_DIR / a.series / f"ep{a.episode:02d}"
        cur = sr.load_flags(ep_out)
        sr.save_flags(ep_out, cur | set(fails))
        print(f"  written to {ep_out}/flags.json — regenerate with --flagged-only")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
