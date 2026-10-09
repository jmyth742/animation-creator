#!/usr/bin/env python3
"""Score an improvement-loop experiment and record it in review/IMPROVE_LEDGER.md.
   cast  <cycle>              adopt a candidate that beats the current cast by 10%
   walk  <knob> <metrics.txt> composite of slide, knee range, reach; write a win to defaults
   craft <knob> "<vals>"      assemble the A/B sheet (human pick), log it
   face  <knob> "<vals>"      assemble the A/B sheet (human pick), log it
"""
import sys, os, re, json, glob, time, subprocess
R = "/workspace/review"; W = "/workspace/loopwork"; REPO = "/workspace/text-to-video"
LED = R + "/IMPROVE_LEDGER.md"
if not os.path.exists(LED):
    open(LED, "w").write("# Improvement ledger\n\nOne line per experiment the GPU loop ran, newest last.\n\n")
def log(line):
    open(LED, "a").write("- %s %s\n" % (time.strftime("%F %H:%M"), line)); print("LEDGER", line)
mode = sys.argv[1]

if mode == "cast":
    scores = {}
    for l in open(R + "/hand_scores.txt"):
        m = re.match(r"(\S+)\.glb\s+hand/arm spread ([\d.]+)", l)
        if m: scores[m.group(1)] = float(m.group(2))
    st = json.load(open(W + "/improve/state.json"))
    adopted = st.get("adopted", {"oisin": ("st_chibi3_oisin_m7302", 0.73), "niamh": ("st_chibi3_niamh_m7302", 0.74)})
    for who in ("oisin", "niamh"):
        cands = sorted((v, k) for k, v in scores.items() if who in k)
        if not cands: continue
        best_s, best = cands[0]
        cur_name, cur_s = adopted[who]
        seen = st.setdefault("candidates", {}).setdefault(who, [])
        if best != cur_name and best_s < 0.9 * cur_s and best not in seen:
            # 9 Oct: a candidate is PROPOSED, never adopted by itself. Hand compactness said
            # m23845/m20705 were better; their auto-built faces were far worse than the
            # hand-calibrated oisin4/niamh4 in the close-ups of the master they went into.
            # The rig + face + reel are built for review; a human promotes.
            log("cast: %s candidate %s hands %.2f beats %s (%.2f) -> rig+face+reel built for REVIEW (not adopted)" % (who, best, best_s, cur_name, cur_s))
            seen.append(best)
            # queue the promotion as its own job so the loop's job stays short
            open("%s/queue/91_promote_%s.sh" % (W, who), "w").write("""cd %s
P=series/tir-na-nog-legend/meshes/props; RG=/workspace/loopwork/rigify; N=%s
TEXHY_FACES=60000 /workspace/venv/bin/python -u scripts/blender3d/texture_hy3d.py $P/$N.glb $P/${N}_front.png $P/${N}_tex.glb
[ -s $P/${N}_tex.glb ] && /workspace/blender42/blender -b --factory-startup --python scripts/blender3d/retopo_character.py -- $P/${N}_tex.glb cand_$N 18000 4096
[ -s $P/cand_${N}_retopo.glb ] && /workspace/blender42/blender -b --python scripts/blender3d/rigify_fit.py -- $P/cand_${N}_retopo.glb $RG/$N 1.6
[ -s $RG/$N.blend ] && /workspace/blender42/blender -b $RG/$N.blend --python scripts/blender3d/rigify_check.py -- gate /workspace/review/RIGIFY_gate_${N}_45.png 45
[ -s $RG/$N.blend ] && { rm -rf $RG/show_$N; RW_RES=1080 RW_SHOTS=walk,idle /workspace/blender42/blender -b $RG/$N.blend --python scripts/blender3d/rigify_walk.py -- $RG/show_$N 96; bash scripts/ops/encode_showreel.sh $RG/show_$N /workspace/review/MOTION_${N}_rigify.mp4 20 "walk idle"; }
bash /workspace/export_outcomes.sh 2>&1 | tail -1
""" % (REPO, best))
        elif best in st.get("candidates", {}).get(who, []):
            log("cast: %s best candidate %s (%.2f) already built for review; adopted %s stands" % (who, best, best_s, cur_name))
        else:
            log("cast: %s best new candidate %s hands %.2f, adopted %s (%.2f) stands" % (who, best, best_s, cur_name, cur_s))
    st["adopted"] = adopted; json.dump(st, open(W + "/improve/state.json", "w"), indent=1)

elif mode == "walk":
    knob, path = sys.argv[2], sys.argv[3]
    cur = {}
    for l in open(REPO + "/configs/walk_defaults.env"):
        if "=" in l and not l.startswith("#"): k, v = l.strip().split("=", 1); cur[k] = v
    results = {}; v = None
    for l in open(path):
        m = re.match(r"== \w+=(\S+) ==", l)
        if m: v = m.group(1); results[v] = {"knee": [], "reach": [], "slide": None}; continue
        if v is None: continue
        m = re.match(r"WM\s+\d+\s+[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)", l)
        if m: results[v]["reach"].append(float(m.group(1))); results[v]["knee"].append(float(m.group(2)))
        m = re.match(r"RW foot slide walk ([\d.]+)", l)
        if m: results[v]["slide"] = float(m.group(1))
    def score(r):
        if not r["knee"]: return 1e9
        kmin, kmax = min(r["knee"]), max(r["knee"]); rmax = max(r["reach"]); sl = r["slide"] or 99
        pen = 0.0
        pen += max(0, 15 - kmin) * 2 + max(0, kmax - 80) * 2          # knee never locked, never folded
        pen += max(0, rmax - 1.05) * 400                                # no stretch
        pen += sl * 3                                                    # slide, mm/frame
        pen += abs(kmax - kmin - 45) * 0.3                               # a lively but plausible range
        return pen
    ranked = sorted((score(r), v) for v, r in results.items())
    best_s, best_v = ranked[0]
    cur_s = score(results.get(cur.get(knob, ""), {"knee": []}))
    line = "walk: %s sweep %s -> best %s (score %.1f), current %s (%.1f)" % (knob, ",".join(results), best_v, best_s, cur.get(knob), cur_s if cur_s < 1e9 else -1)
    st = json.load(open(W + "/improve/state.json")); kb = st.setdefault("knobs", {}).setdefault(knob, {"step": 0.04, "min": 0.01, "done": False})
    spread = max(sc for sc, _ in ranked if sc < 1e9) - best_s if ranked else 0
    if best_v != cur.get(knob) and best_s < cur_s - 1.0:
        cur[knob] = best_v
        open(REPO + "/configs/walk_defaults.env", "w").write("# adopted by improve_score.py\n" + "".join("%s=%s\n" % kv for kv in cur.items()))
        st["defaults_ver"] = st.get("defaults_ver", 0) + 1
        open(W + "/improve/defaults_ver", "w").write(str(st["defaults_ver"]))
        line += " ADOPTED"
    elif spread < 1.0:
        kb["done"] = True; line += " (no signal across the sweep: settled)"
    else:
        kb["step"] = kb["step"] / 2.0
        if kb["step"] < kb.get("min", 0.01): kb["done"] = True; line += " (step below minimum: settled at %s)" % cur.get(knob)
        else: line += " (step -> %g)" % kb["step"]
    # a refinement step must be able to run again for the same inputs
    st.setdefault("memo", {}).pop("walk_" + knob, None) if not kb["done"] and "ADOPTED" not in line else None
    json.dump(st, open(W + "/improve/state.json", "w"), indent=1)
    log(line)

elif mode in ("craft", "face"):
    knob, vals = sys.argv[2], sys.argv[3].split()
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    tiles = []
    for v in vals:
        if mode == "craft":
            for s in ("close", "ots", "wide"):
                fs = sorted(glob.glob("%s/improve/craft_%s_%s_%s/*.png" % (W, knob, v, s)))
                if fs: tiles.append(("%s=%s %s" % (knob, v, s), Image.open(fs[0]).convert("RGB")))
        else:
            n = "cand_oisin4_%s_%s" % (knob, v.replace(".", ""))
            fs = sorted(glob.glob("%s/rigify/face_%s/t_*.png" % (W, n)))
            for k in (12, 24):
                if len(fs) > k: tiles.append(("%s=%s f%d" % (knob, v, k), Image.open(fs[k]).convert("RGB")))
    if tiles:
        w = max(t[1].width for t in tiles); h = max(t[1].height for t in tiles); cols = 2; rows = (len(tiles) + 1) // 2
        s = Image.new("RGB", (w * cols, (h + 32) * rows), (14, 14, 18)); d = ImageDraw.Draw(s)
        for i, (lab, im) in enumerate(tiles):
            x, y = (i % cols) * w, (i // cols) * (h + 32); s.paste(im, (x, y + 32)); d.text((x + 10, y + 5), lab, font=f, fill=(255, 230, 110))
        out = "%s/AB_%s_%s.png" % (R, mode, knob); s.save(out)
        log("%s: %s A/B over %s -> %s (human pick)" % (mode, knob, ",".join(vals), os.path.basename(out)))
    else:
        log("%s: %s A/B produced no frames" % (mode, knob))

elif mode == "plate_geo":
    rnd = int(sys.argv[2]); setname = sys.argv[3] if len(sys.argv) > 3 else "valley"
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from improve_sets import SETS
    cfg = SETS[setname]; from PIL import Image
    st = json.load(open(W + "/improve/state.json"))
    STYLE_MIN = float(os.environ.get("PG_STYLE_MIN", "0.85"))      # FLUX plates that keep the look score 0.83-0.94; SDXL ones that lost it 0.75-0.80
    bk = "plate_best_r" if setname == "valley" else "plate_best_r_" + setname
    pattern = "%s/geo/r%d_cn*_agree.json" % (W, rnd) if setname == "valley" else "%s/geo/r%d_%s_cn*_agree.json" % (W, rnd, setname)
    # selection among plates that pass the gate: agreement, with style margin above the gate as a
    # tie-breaker worth up to ~0.06 -- a plate that keeps the golden hall at r=0.60 beats a muted
    # brown one at r=0.61 (5 Oct: the max-agreement pick drifted the palette)
    best = (st.get(bk, -1.0), None); best_r = None; best_style = None; old_r = None; rejected = 0
    for j in glob.glob(pattern):
        d = json.load(open(j)); old_r = d["old"]
        for p, r in d["plates"].items():
            sty = d.get("style", {}).get(p, 0.0)
            if sty < STYLE_MIN: rejected += 1; continue
            sc = r + 0.6 * (sty - STYLE_MIN)
            if sc > best[0]: best = (sc, p); best_r = r; best_style = sty
    cands = sum(len(json.load(open(j))["plates"]) for j in glob.glob(pattern))
    if old_r is None: log("plate_geo %s round %d: no results" % (setname, rnd))
    else:
        sc, p = best; r = best_r if best_r is not None else sc
        if p is not None and r > old_r + 0.08:
            im = Image.open(p).convert("RGB"); im.save(cfg["out"])
            im.resize((im.width * 2, im.height * 2), Image.LANCZOS).save(cfg["out"][:-4] + "_4x.png")
            cur = {}
            if os.path.exists(REPO + "/configs/scene_defaults.env"):
                for l in open(REPO + "/configs/scene_defaults.env"):
                    if "=" in l and not l.startswith("#"): k, v = l.strip().split("=", 1); cur[k] = v
            cur[cfg["key"]] = cfg["out"]
            if cfg["npy_key"]:
                subprocess.run(["/workspace/venv/bin/python", REPO + "/scripts/blender3d/plate_heightfield.py", cfg["out"], cfg["depth_out"]], capture_output=True)
                cur[cfg["npy_key"]] = cfg["depth_out"] + "_depth.npy"
            cur.setdefault("SET_RELIEF_GAIN", os.environ.get("SET_RELIEF_GAIN", "0.6"))
            open(REPO + "/configs/scene_defaults.env", "w").write("# adopted by improve_score.py (plate_geo)\n" + "".join("%s=%s\n" % kv for kv in cur.items()))
            st["plate_ver"] = st.get("plate_ver", 0) + 1; st[bk] = sc
            guide = Image.open(cfg["guide"]).convert("RGB"); oldp = Image.open(cfg["style_ref"]).convert("RGB")
            sw, sh = 560, 320; sheet = Image.new("RGB", (sw * 3, sh + 24), "white")
            from PIL import ImageDraw
            for i, (t, l) in enumerate(((guide, "set geometry depth"), (oldp, "old plate ground r=%.2f" % old_r), (im, "geometry plate ground r=%.2f style %.2f" % (r, best_style)))):
                sheet.paste(t.resize((sw, sh), Image.LANCZOS), (i * sw, 24)); ImageDraw.Draw(sheet).text((i * sw + 6, 5), l, fill="black")
            sheet.save(R + "/PLATE_FROM_GEOMETRY%s.png" % ("" if setname == "valley" else "_" + setname))
            log("plate_geo %s round %d: %d plates, best %s agreement r=%.3f style %.3f vs old plate r=%.3f -> ADOPTED as %s (plate v%d)" % (setname, rnd, cands, os.path.basename(p), r, best_style, old_r, os.path.basename(cfg["out"]), st["plate_ver"]))
        else:
            log("plate_geo %s round %d: %d plates (%d failed the style gate >=%.2f), best agreement r=%.3f vs old plate r=%.3f, adopted r=%.3f stands" % (setname, rnd, cands, rejected, STYLE_MIN, best[0], old_r, st.get(bk, -1)))
    json.dump(st, open(W + "/improve/state.json", "w"), indent=1)

elif mode == "scene_fit":
    cyc = sys.argv[2]; gk = sys.argv[3] if len(sys.argv) > 3 else "SET_RELIEF_GAIN"; ep = sys.argv[4] if len(sys.argv) > 4 else "1"
    rows = []
    for f in glob.glob(W + "/improve/sf%s_g*.txt" % ep):
        g = f.split("_g")[1][:-4]; onp = []; p95 = []
        for l in open(f):
            m = re.match(r"SF \S+: on path (\d+)%.*p95 (\d+) mm", l)
            if m: onp.append(int(m.group(1))); p95.append(int(m.group(2)))
        if onp: rows.append((sum(onp) / len(onp) - 0.5 * max(p95), g, sum(onp) / len(onp), max(p95)))
    if not rows: log("scene_fit ep%s @%s: no audits" % (ep, cyc))
    else:
        rows.sort(reverse=True); sc, g, onp, p95 = rows[0]
        open(W + "/improve/sf%s_best" % ep, "w").write(g)
        cur = {}
        if os.path.exists(REPO + "/configs/scene_defaults.env"):
            for l in open(REPO + "/configs/scene_defaults.env"):
                if "=" in l and not l.startswith("#"): k, v = l.strip().split("=", 1); cur[k] = v
        changed = cur.get(gk) != g; cur[gk] = g
        open(REPO + "/configs/scene_defaults.env", "w").write("# adopted by improve_score.py (scene_fit)\n" + "".join("%s=%s\n" % kv for kv in cur.items()))
        log("scene_fit ep%s @%s: gains %s -> best %s=%s (on path %.0f%%, foot float p95 %d mm)%s" % (ep, cyc, ",".join(r[1] for r in sorted(rows, key=lambda r: r[1])), gk, g, onp, p95, " ADOPTED" if changed else " (unchanged)"))

elif mode == "plate_shots":
    rnd = int(sys.argv[2]); suffix = sys.argv[3] if len(sys.argv) > 3 else "_geo"; from PIL import Image
    st = json.load(open(W + "/improve/state.json")); SETS = REPO + "/series/tir-na-nog-legend/sets/tir_na_nog"
    STYLE_MIN = float(os.environ.get("PS_STYLE_MIN", "0.86"))     # 9 Oct: at 0.80 the side plate's hall came out as a green block
    adopted = 0; parts = []
    for setup in ("side", "reverse", "closer"):
        best = (st.get("shot_best_%s%s" % (setup, suffix), -1.0), None); br = bs = None; rej = 0; n = 0
        for j in glob.glob("%s/geo/ps%d_%s%s_cn*_agree.json" % (W, rnd, setup, suffix)):
            d = json.load(open(j))
            for pth, r in d["plates"].items():
                n += 1; sty = d.get("style", {}).get(pth, 0.0)
                if sty < STYLE_MIN: rej += 1; continue
                sc = r + 0.6 * (sty - STYLE_MIN)
                if sc > best[0]: best = (sc, pth); br, bs = r, sty
        if best[1] is not None:
            im = Image.open(best[1]).convert("RGB"); im.save("%s/%s%s.png" % (SETS, setup, suffix))
            im.resize((im.width * 2, im.height * 2), Image.LANCZOS).save("%s/%s%s_4x.png" % (SETS, setup, suffix))
            st["shot_best_%s%s" % (setup, suffix)] = best[0]; adopted += 1
            parts.append("%s r=%.2f style=%.2f ADOPTED (%d/%d passed)" % (setup, br, bs, n - rej, n))
        else:
            parts.append("%s: none of %d beat the standing plate (%d failed style)" % (setup, n, rej))
    if adopted: st["plate_ver"] = st.get("plate_ver", 0) + 1
    log("plate_shots%s round %d: %s%s" % (suffix, rnd, "; ".join(parts), " -> plate v%d" % st["plate_ver"] if adopted else ""))
    json.dump(st, open(W + "/improve/state.json", "w"), indent=1)

elif mode == "plate_hires":
    # a refine pass over an adopted plate at 2016x1152: adopted as the projector's _4x only if it
    # is sharper than the Lanczos upscale AND still the same picture (style >= 0.95, ground r within 0.03)
    tag = sys.argv[2]; target = sys.argv[3]              # e.g. valley_master, path of the adopted plate (its _4x gets replaced)
    from PIL import Image
    st = json.load(open(W + "/improve/state.json")); rows = []
    for j in glob.glob("%s/geo/hr_%s_*_agree.json" % (W, tag)):
        d = json.load(open(j))
        for p, r in d["plates"].items():
            rows.append((d["sharp"][p] / max(1e-6, d["old_sharp"]), r - d["old"], d["style"][p], p))
    ok = [x for x in rows if x[2] >= 0.95 and x[1] >= -0.03]
    if not rows: log("plate_hires %s: no results" % tag)
    elif not ok: log("plate_hires %s: %d candidates, none kept the picture (style>=0.95, ground within 0.03)" % (tag, len(rows)))
    else:
        ok.sort(reverse=True); gain, dr, sty, p = ok[0]
        if gain > 1.15:
            im = Image.open(p).convert("RGB"); up = target[:-4] + "_4x.png"
            if os.path.exists(up) and not os.path.exists(up[:-4] + "_lanczos.png"): os.rename(up, up[:-4] + "_lanczos.png")
            im.resize((2688, 1536), Image.LANCZOS).save(up)
            st["plate_ver"] = st.get("plate_ver", 0) + 1; st.setdefault("hires", {})[tag] = os.path.basename(p)
            log("plate_hires %s: %s sharpness x%.2f vs the upscale, style %.3f, ground %+.3f -> ADOPTED as %s (plate v%d)" % (tag, os.path.basename(p), gain, sty, dr, os.path.basename(up), st["plate_ver"]))
        else:
            log("plate_hires %s: best sharpness x%.2f (need >1.15), style %.3f -> not adopted" % (tag, gain, sty))
    json.dump(st, open(W + "/improve/state.json", "w"), indent=1)
