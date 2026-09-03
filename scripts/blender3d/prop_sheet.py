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
    "snowtree": ("A single rowan tree under heavy snow, bare dark branches "
                 "with thick white snow lining every limb, whole tree "
                 "visible, three-quarter view. Painted storybook animation "
                 "style, soft hand-painted texture, plain light grey "
                 "background, even diffuse light, no scenery, no text, "
                 "no watermark."),
    "snowbush": ("A round hawthorn bush buried under smooth snow, dark twigs "
                 "showing through, whole bush visible, three-quarter view. "
                 "Painted storybook animation style, soft hand-painted "
                 "texture, plain light grey background, even diffuse light, "
                 "no scenery, no text, no watermark."),
    "snowrock": ("A cluster of grey granite boulders capped with snow, whole "
                 "cluster visible, three-quarter view. Painted storybook "
                 "animation style, soft hand-painted texture, plain light "
                 "grey background, even diffuse light, no scenery, no text, "
                 "no watermark."),
    "frozenwell": ("A small round stone well with icicles under its slate "
                   "roof and snow on every surface, whole well visible, "
                   "three-quarter view. Painted storybook animation style, "
                   "soft hand-painted texture, plain light grey background, "
                   "even diffuse light, no scenery, no text, no watermark."),
    "ruinfort": ("A collapsed ancient Irish ring-fort of moss-covered grey "
                 "stone, broken circular wall with one surviving arched "
                 "doorway, whole ruin visible, three-quarter view. Painted "
                 "storybook animation style, soft hand-painted texture, plain "
                 "light grey background, even diffuse light, no scenery, no "
                 "text, no watermark."),
    "benttree": ("A single ancient wind-bent hawthorn tree, trunk swept "
                 "sideways by years of sea wind, sparse leaves, whole tree "
                 "visible, three-quarter view. Painted storybook animation "
                 "style, soft hand-painted texture, plain light grey "
                 "background, even diffuse light, no scenery, no text, "
                 "no watermark."),
    "seastack": ("A tall grey sea stack of layered rock rising to a narrow "
                 "grassy top, whole formation visible, three-quarter view. "
                 "Painted storybook animation style, soft hand-painted "
                 "texture, plain light grey background, even diffuse light, "
                 "no scenery, no text, no watermark."),
    "boat": ("A small traditional Irish currach boat of dark tarred hide "
             "over a wooden frame, beached, whole boat visible, "
             "three-quarter view. Painted storybook animation style, soft "
             "hand-painted texture, plain light grey background, even "
             "diffuse light, no scenery, no text, no watermark."),
    "well": ("A small round stone well with a mossy slate roof on two "
             "wooden posts and a rope bucket, whole well visible, "
             "three-quarter view. Painted storybook animation style, soft "
             "hand-painted texture, plain light grey background, even "
             "diffuse light, no scenery, no text, no watermark."),
    "bridge": ("A small arched stone footbridge of weathered grey blocks "
               "over nothing, whole bridge visible, three-quarter view. "
               "Painted storybook animation style, soft hand-painted "
               "texture, plain light grey background, even diffuse light, "
               "no scenery, no text, no watermark."),
    "niamh34": ("Character sheet, full body, head to feet fully visible. A "
                "Celtic princess standing in a relaxed A-pose seen from a "
                "THREE-QUARTER view (turned 30 degrees), arms slightly away "
                "from her sides. Long flowing golden hair, bright green eyes, "
                "emerald green gown to the ankle, slippers. Cel-shaded 2D "
                "animation, clean linework, flat colour blocks, plain light "
                "grey background, even diffuse light, no scenery, no props, "
                "no text, no watermark."),
    "stones": ("A small circle of five ancient weathered standing stones of "
               "grey granite, mossy, different heights, whole group visible, "
               "three-quarter view. Painted storybook animation style, soft "
               "hand-painted texture, plain light grey background, even "
               "diffuse light, no scenery, no text, no watermark."),
    "bush": ("A round flowering hawthorn bush with white blossom clusters on "
             "deep green foliage, whole bush visible, three-quarter view. "
             "Painted storybook animation style, soft hand-painted texture, "
             "plain light grey background, even diffuse light, no scenery, "
             "no text, no watermark."),
    "oisin34": ("Character sheet, full body, head to feet fully visible. A "
                "young Celtic warrior standing in a relaxed A-pose seen from "
                "a THREE-QUARTER view (turned 30 degrees), arms slightly away "
                "from his sides. Dark shoulder-length hair, warm brown eyes, "
                "short trimmed beard, brown leather jerkin, dark green cloak, "
                "boots. Cel-shaded 2D animation, clean linework, flat colour "
                "blocks, plain light grey background, even diffuse light, no "
                "scenery, no props, no text, no watermark."),
    "rock": ("A cluster of three mossy grey granite boulders of different "
             "sizes, weathered and rounded, whole cluster visible, "
             "three-quarter view. Cel-shaded painted animation style, "
             "soft painted texture, plain light grey background, even "
             "diffuse light, no scenery, no text, no watermark."),
    "hall": ("A small golden Celtic great hall with carved knotwork medallions, "
             "an arched doorway, crenellated parapet and one square tower with "
             "a peaked roof, seen in three-quarter view from ground level. "
             "Warm yellow stone. Cel-shaded 2D animation, clean linework, flat "
             "colour blocks, isolated on a plain light grey background, no "
             "scenery, no text, no watermark."),
    "tree": ("A single wind-shaped rowan tree with a gnarled trunk and a full "
             "green canopy in clumped leaf masses, whole tree visible. "
             "Painted storybook animation style, soft hand-painted texture, "
             "isolated on a plain light grey background, even diffuse light, "
             "no scenery, no text, no watermark."),
    "cross": ("An ancient weathered Celtic high cross of grey stone with a "
              "ring around the crossing and worn carvings, whole monument "
              "visible, slightly mossy. Painted storybook animation style, soft "
              "hand-painted texture, isolated on a plain light grey "
              "background, even diffuse light, no scenery, no text, "
              "no watermark."),
}

name, out = sys.argv[1], sys.argv[2]
base = sys.argv[3] if len(sys.argv) > 3 else name        # tree_v2 reuses "tree"
shift = int(sys.argv[4]) if len(sys.argv) > 4 else 0     # fresh seed per variant
wf = sr.build_t2i_workflow(PROPS[base], seed=6400 + hash(base) % 100 + shift,
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
