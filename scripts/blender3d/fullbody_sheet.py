"""Full-body A-pose character sheet for image->3D. Plain ground, no scene."""
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import showrunner as sr                                        # noqa: E402

who, out = sys.argv[1], sys.argv[2]
PROMPTS = {
    "oisin": ("Character sheet, full body, head to feet fully visible. A young "
              "Celtic warrior standing straight in a relaxed A-pose, arms held "
              "slightly away from his sides, legs straight, feet apart, facing "
              "camera. Dark shoulder-length hair, warm brown eyes, short "
              "trimmed beard, brown leather jerkin, dark green cloak, boots. "
              "Cel-shaded 2D animation, clean confident linework, flat blocks "
              "of colour, plain light grey studio background, no scenery, "
              "no props, no staff, no text, no watermark."),
    "niamh": ("Character sheet, full body, head to feet fully visible. A "
              "Celtic princess standing straight in a relaxed A-pose, arms "
              "held slightly away from her sides, facing camera. Long flowing "
              "golden hair, bright green eyes, emerald green gown to the "
              "ankle, slippers. Cel-shaded 2D animation, clean confident "
              "linework, flat blocks of colour, plain light grey studio "
              "background, no scenery, no props, no text, no watermark."),
}
wf = sr.build_t2i_workflow(PROMPTS[who], seed=6300 + hash(who) % 100,
                           prefix=f"sheet_{who}", width=480, height=832)
pid = sr.queue_prompt(wf)
print("queued", pid, flush=True)
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
