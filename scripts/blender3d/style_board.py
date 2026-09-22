"""
STYLE BOARD — candidate character looks chosen for what the 3D path can actually build.

Every failure today traces to a style that fights reconstruction: a cape that hides the
body, arms flat against the torso, loose hair strands, closed fingers, and fine costume
detail that marching cubes turns to mush. So instead of designing a character and hoping
it survives, these candidates are engineered around the constraints:

  * closed simple volumes, nothing thin or floating (no cape, no loose cloth);
  * arms held clear, so the reconstruction never fuses arm to torso;
  * hair as one solid shape, not strands;
  * simple hands, because fingers are the first thing lost;
  * a large, clearly readable head, because that is where the eye goes and where our
    texture-space visemes have to work;
  * flat even light on white, no shadow, so depth comes from form and not from shading.

Run:  python style_board.py <name> [count]
Writes review/style_board_<name>.png and props/style_<id>_<name>.png
"""
import json, os, sys, time, shutil, urllib.request
from pathlib import Path
sys.path.insert(0, "/workspace/text-to-video/scripts")
import showrunner as sr
from PIL import Image, ImageDraw

name = sys.argv[1] if len(sys.argv) > 1 else "oisin"
SEED = int(os.environ.get("BOARD_SEED", "4200"))
STEPS = int(os.environ.get("BOARD_STEPS", "18"))
COMFY = Path("/workspace/text-to-video/ComfyUI")
PROPS = Path("/workspace/text-to-video/series/tir-na-nog-legend/meshes/props")
REVIEW = Path("/workspace/review")

WHO = {"oisin": "a young Celtic warrior man, dark hair, short beard, green and brown clothing",
       "niamh": "a young fae princess, long golden hair, green and white clothing"}
sub = WHO.get(name, WHO["oisin"])

# the constraints, stated the same way for every candidate so the STYLE is the variable
# POSITIVE PHRASING ONLY. The first board asked for "no cape" and "arms away from the
# body" and returned capes and folded arms in seven of eight panels: naming a thing
# summons it. Everything the reconstruction needs is now described as something present,
# never as something absent.
RULES = ("standing in a T-pose with both arms stretched straight out horizontally to the "
         "sides at shoulder height, elbows straight, palms facing forward, fingers spread "
         "wide apart and clearly separated, feet shoulder width apart, "
         "wearing a simple close-fitting sleeveless tunic and fitted trousers and short "
         "boots, short hair cropped close to the head in one solid shape, "
         "whole body visible from head to feet, centred, "
         "flat even studio lighting, pure white empty background, clean vector-like edges")

STYLES = [
 ("toy",      "chunky vinyl toy figure style, thick simple limbs, large rounded head, "
              "smooth closed volumes, bold simple shapes, minimal surface detail"),
 ("chibi",    "chibi anime style, head about one third of body height, very simple body, "
              "big eyes, tiny simple hands, smooth rounded forms"),
 ("clay",     "stop-motion clay puppet style, solid sculpted volumes, matte clay surface, "
              "simple chunky proportions, visible sculpted planes"),
 ("cel",      "clean modern anime cel style, simple flat colours, bold clean outline, "
              "rounded simplified forms, head about one fifth of body height"),
 ("thickline","thick bold outline cartoon style, flat colour blocks, very simple shapes, "
              "chunky proportions, no gradients"),
 ("hooded",   "clean anime style, character wears a SIMPLE FITTED HOOD covering the hair, "
              "face in shadow under the hood, simple closed forms, no loose fabric"),
 ("lowpoly",  "stylised faceted low-poly game character look, clean geometric planes, "
              "flat colours, simple blocky forms"),
 ("storybook","painted storybook illustration style, soft simple shapes, warm flat colours, "
              "gentle rounded proportions, minimal detail"),
]

def gen(prompt, tag):
    wf = sr.build_t2i_workflow(prompt, seed=SEED, prefix="board2/%s_%s" % (name, tag),
                               width=768, height=1024)
    wf["10"]["inputs"]["steps"] = STEPS
    pid = sr.queue_prompt(wf)
    t0 = time.time()
    while time.time() - t0 < 900:
        h = json.loads(urllib.request.urlopen("http://127.0.0.1:8188/history/%s" % pid, timeout=10).read())
        if pid in h:
            if h[pid].get("outputs"):
                for node in h[pid]["outputs"].values():
                    for im in node.get("images", []):
                        return COMFY / "output" / im.get("subfolder", "") / im["filename"]
            if h[pid].get("status", {}).get("status_str") == "error":
                print("  ERROR on", tag, flush=True); return None
        time.sleep(4)
    print("  TIMEOUT on", tag, flush=True); return None

got = []
for tag, style in STYLES:
    p = gen("%s, %s, %s, clean uncropped artwork with no logo and no signature" % (sub, style, RULES), tag)
    if p:
        dst = PROPS / ("style2_%s_%s.png" % (tag, name))
        shutil.copy(p, dst)
        got.append((tag, dst))
        print("BOARD", tag, dst.name, flush=True)

if got:
    cols = 4
    tw, th = 384, 512
    rows = (len(got) + cols - 1) // cols
    sheet = Image.new("RGB", (tw * cols, (th + 28) * rows), (245, 245, 245))
    d = ImageDraw.Draw(sheet)
    for i, (tag, p) in enumerate(got):
        x, y = (i % cols) * tw, (i // cols) * (th + 28)
        d.rectangle([x, y, x + tw, y + 26], fill=(28, 28, 32))
        d.text((x + 8, y + 7), tag, fill=(255, 225, 110))
        sheet.paste(Image.open(p).convert("RGB").resize((tw, th)), (x, y + 28))
    sheet.save(REVIEW / ("style_board2_%s.png" % name))
    print("BOARD_DONE", REVIEW / ("style_board2_%s.png" % name), len(got), "candidates", flush=True)
