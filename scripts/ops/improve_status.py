#!/usr/bin/env python3
"""Write review/IMPROVE_STATUS.md: what the GPU loop has adopted, what it has settled, what
it is working on, and the card's measured duty cycle. The ledger is the log; this is the
answer to "is anything actually improving?"."""
import json, os, time, glob
W = "/workspace/loopwork"; R = "/workspace/review"; REPO = "/workspace/text-to-video"
st = json.load(open(W + "/improve/state.json")) if os.path.exists(W + "/improve/state.json") else {}
now = time.time()
# duty cycle from the sampler: a job "running" is not the same as the card working
util = []
if os.path.exists(W + "/gpu_util.csv"):
    for l in open(W + "/gpu_util.csv"):
        try:
            t, u, m = l.strip().split(","); t = int(t)
            if now - t < 86400: util.append(int(u))
        except ValueError: pass
def env(p):
    d = {}
    if os.path.exists(p):
        for l in open(p):
            if "=" in l and not l.startswith("#"): k, v = l.strip().split("=", 1); d[k] = v
    return d
walk = env(REPO + "/configs/walk_defaults.env"); scene = env(REPO + "/configs/scene_defaults.env")
led = open(R + "/IMPROVE_LEDGER.md").read().strip().splitlines() if os.path.exists(R + "/IMPROVE_LEDGER.md") else []
led = [l for l in led if l.startswith("- ")]
masters = sorted(glob.glob(R + "/nine_waterfalls_*_web.mp4"), key=os.path.getmtime)
out = ["# Improvement status", "", "Updated %s. Cycle %d." % (time.strftime("%F %H:%M"), st.get("cycle", 0)), ""]
out += ["## GPU duty cycle (last 24 h, 1-min samples)", ""]
if util:
    busy = sum(1 for u in util if u >= 20)
    # a missing sample is a minute the sampler could not write (full disk, dead pod): count it as idle
    out += ["- card working (>=20%%) **%d%%** of the last 24 h (%d busy minutes; %d minutes unsampled, counted idle); mean utilisation of sampled minutes %d%%" % (100 * busy // 1440, busy, max(0, 1440 - len(util)), sum(util) / len(util))]
else:
    out += ["- sampler has no data yet"]
out += ["", "## Adopted (what the masters are rendered with)", ""]
out += ["- walk: " + ", ".join("%s=%s" % kv for kv in walk.items()) + " (defaults v%s)" % st.get("defaults_ver", 0)]
out += ["- scene: " + (", ".join("%s=%s" % kv for kv in scene.items()) or "flat floor, original plate") + " (plate v%s)" % st.get("plate_ver", 0)]
for who, (n, s) in st.get("adopted", {}).items(): out += ["- cast %s: %s (hand compactness %.2f, lower is better)" % (who, n, s)]
out += ["- masters: %s" % (", ".join(os.path.basename(m) for m in masters[-3:]) or "none"), "- masters built at inputs: %s; current inputs: %s" % (st.get("masters_ver", "-"), st.get("inputs_ver", "-"))]
out += ["", "## Settled (not re-run until an input changes)", ""]
for k, v in sorted(st.get("memo", {}).items()):
    out += ["- %s: %s @ %s" % (k, v.get("result", "done"), v.get("ver", "?"))]
knobs = st.get("knobs", {})
for k, v in knobs.items(): out += ["- walk knob %s: %s (lo %s, hi %s, step %s)" % (k, "settled" if v.get("done") else "refining", v.get("lo"), v.get("hi"), v.get("step"))]
out += ["", "## Awaiting a human pick", ""]
out += ["- %s" % os.path.basename(p) for p in sorted(glob.glob(R + "/AB_*.png"))] or ["- none"]
out += ["", "## Last 12 experiments", ""] + led[-12:]
open(R + "/IMPROVE_STATUS.md", "w").write("\n".join(out) + "\n")
print("STATUS written", R + "/IMPROVE_STATUS.md")
