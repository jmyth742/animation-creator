"""Isolated prop images for image->3D: one object, plain ground, no scene."""
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import showrunner as sr                                        # noqa: E402

PROPS = {
    "hall": ("A small golden Celtic great hall with carved knotwork medallions, "
             "an arched doorway, crenellated parapet and one square tower with "
             "a peaked roof, seen in three-quarter view from ground level. "
             "Warm yellow stone. Cel-shaded 2D animation, clean linework, flat "
             "colour blocks, isolated on a plain light grey background, no "
             "scenery, no text, no watermark."),
    "tree": ("A single wind-shaped rowan tree with a gnarled trunk and a full "
             "green canopy in clumped leaf masses, whole tree visible. "
             "Cel-shaded 2D animation, clean linework, flat colour blocks, "
             "isolated on a plain light grey background, no scenery, no text, "
             "no watermark."),
    "cross": ("An ancient weathered Celtic high cross of grey stone with a "
              "ring around the crossing and worn carvings, whole monument "
              "visible, slightly mossy. Cel-shaded 2D animation, clean "
              "linework, flat colour blocks, isolated on a plain light grey "
              "background, no scenery, no text, no watermark."),
}

name, out = sys.argv[1], sys.argv[2]
wf = sr.build_t2i_workflow(PROPS[name], seed=6400 + hash(name) % 100,
                           prefix=f"prop_{name}", width=640, height=640)
pid = sr.queue_prompt(wf)
t0 = time.time()
while time.time() - t0 < 1800:
    with urllib.request.urlopen(f"http://127.0.0.1:8188/history/{pid}",
                                timeout=10) as r:
        h = json.loads(r.read())
    if pid in h and h[pid].get("outputs"):
        for node in h[pid]["outputs"].values():
            for im in node.get("images", []):
                src = Path("ComfyUI/output") / im.get("subfolder", "") / im["filename"]
                shutil.copy(src, out)
                print("SHEET DONE", out, flush=True)
                sys.exit(0)
    time.sleep(5)
print("TIMED OUT")
