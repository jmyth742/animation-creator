"""
CHARACTER SHEET v2 — fix the input, because the input is what is wrong.

The 2D designs in this project are competent (see props/oisin_left.png: clean line, real
proportions, a beard, a hooded cape). The 3D versions are not. The loss happens in
image-to-3D, and it happens because the sheets break the rules that step depends on:

  * the arms hang ALONG the body, so the reconstruction fuses arm to torso — which is
    why the shoulders shear and why a voxel remesh bridges the armpit;
  * a full cape covers the silhouette, so the body underneath is guessed;
  * the fingers are closed, so the hand becomes one mass;
  * the views are generated independently, so they disagree and the model averages them
    into mush.

This regenerates the sheet properly: a clean A-pose with the arms held clear and the
fingers spread, no cape (accessories belong on a bone afterwards), and the side and back
views DERIVED from the front by img2img so the three agree.

  python char_sheet.py <name> [denoise_side=0.55]
Writes props/<name>_v2_{front,left,back}.png and review/char_sheet_<name>.png
Env: SHEET_SEED (9100), SHEET_STEPS (18)
"""
import json, os, sys, time, shutil, urllib.request
from pathlib import Path
sys.path.insert(0, "/workspace/text-to-video/scripts")
import showrunner as sr
from PIL import Image

name = sys.argv[1]
dn_side = float(sys.argv[2]) if len(sys.argv) > 2 else 0.55
SEED = int(os.environ.get("SHEET_SEED", "9100"))
STEPS = int(os.environ.get("SHEET_STEPS", "18"))
COMFY = Path("/workspace/text-to-video/ComfyUI")
PROPS = Path("/workspace/text-to-video/series/tir-na-nog-legend/meshes/props")
REVIEW = Path("/workspace/review")

WHO = {
 "oisin": ("a young Celtic warrior man, short dark brown hair, short trimmed beard, "
           "olive green sleeveless tunic over a linen shirt, brown leather belt and "
           "straps, dark green trousers, worn brown leather boots"),
 "niamh": ("a young fae princess, very long straight golden hair, emerald green long "
           "gown with a white and gold embroidered bodice, gold circlet, bare feet"),
}
key = "niamh" if "niamh" in name else "oisin"

# Every rule the reconstruction depends on is stated explicitly and negatively reinforced.
RULES = ("full body from head to feet, standing straight in a relaxed A-pose, "
         "ARMS HELD CLEARLY AWAY FROM THE BODY with a wide gap either side, "
         "palms forward, FINGERS SPREAD APART, legs slightly apart, "
         "no cape, no cloak, no coat, no held objects, no weapon, "
         "clean flat anime character sheet, crisp black linework, flat cel colours, "
         "even neutral lighting, no shadows, no depth of field, plain white background")
STYLE = ("anime character design sheet, studio anime model sheet, "
         "head about one seventh of total height, large expressive eyes")

def gen(prompt, tag, init=None, denoise=1.0, seed=SEED):
    wf = sr.build_t2i_workflow(prompt, seed=seed, prefix="sheet/%s_%s" % (name, tag),
                               width=768, height=1024)
    if init is not None:
        wf["5"] = {"class_type": "LoadImage", "inputs": {"image": Path(init).name}}
        wf["5b"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}}
        wf["11"]["inputs"]["latent_image"] = ["5b", 0]
        wf["10"]["inputs"]["denoise"] = denoise
    wf["10"]["inputs"]["steps"] = STEPS
    pid = sr.queue_prompt(wf)
    t0 = time.time()
    while time.time() - t0 < 1200:
        with urllib.request.urlopen("http://127.0.0.1:8188/history/%s" % pid, timeout=10) as r:
            h = json.loads(r.read())
        if pid in h and h[pid].get("outputs"):
            for node in h[pid]["outputs"].values():
                for im in node.get("images", []):
                    return COMFY / "output" / im.get("subfolder", "") / im["filename"]
        time.sleep(4)
    sys.exit("SHEET timed out on %s" % tag)

# IDENTITY: seed the front from the EXISTING approved design, so the pose and the rules
# change but the character does not. Generating from text alone returns a different
# person entirely (review/char_sheet_oisin.png, first attempt: new face, new costume).
ident = PROPS / ("%s34_sheet.png" % key)
out = {}
if ident.exists():
    seed_img = COMFY / "input" / ("sheet_ident_%s.png" % name)
    shutil.copy(ident, seed_img)
    front = gen("%s, front view facing the viewer, %s, %s" % (WHO[key], RULES, STYLE),
                "front", init=seed_img, denoise=float(os.environ.get("SHEET_IDENT_DN", "0.5")))
else:
    front = gen("%s, front view facing the viewer, %s, %s" % (WHO[key], RULES, STYLE), "front")
shutil.copy(front, PROPS / ("%s_v2_front.png" % name))
out["front"] = PROPS / ("%s_v2_front.png" % name)
print("SHEET front", front.name, flush=True)

# VIEWS: generated INDEPENDENTLY, not img2img from the front. Image-to-image cannot
# rotate a character — at any strength that preserves the design it simply reproduces the
# front, and three front views make multi-view reconstruction worthless. Consistency
# instead comes from one fixed seed and an identical, very specific description.
for tag, desc in (("left", "EXACT SIDE PROFILE, the character seen from their left side, "
                           "body turned 90 degrees, only one eye visible, nose in profile"),
                  ("back", "SEEN FROM DIRECTLY BEHIND, back of the head and shoulders, "
                           "face not visible at all, back of the costume")):
    g = gen("%s, %s, %s, %s" % (WHO[key], desc, RULES, STYLE), tag, seed=SEED)
    shutil.copy(g, PROPS / ("%s_v2_%s.png" % (name, tag)))
    out[tag] = PROPS / ("%s_v2_%s.png" % (name, tag))
    print("SHEET", tag, g.name, flush=True)

ims = [Image.open(out[k]).convert("RGB").resize((512, 683)) for k in ("front", "left", "back")]
sheet = Image.new("RGB", (512 * 3, 683), (250, 250, 250))
for i, im in enumerate(ims):
    sheet.paste(im, (i * 512, 0))
sheet.save(REVIEW / ("char_sheet_%s.png" % name))
print("SHEET_DONE", REVIEW / ("char_sheet_%s.png" % name), flush=True)
