"""
STYLE TEST — build a real mesh from a candidate style and see what survives.

Picking a character style by looking at 2D art is how we got here. The only question that
matters is what the reconstruction, the rig and the lip-sync can actually use, so this
takes one style, generates the three views it needs, builds the mesh, and renders a
turntable. Judge the turntable, not the drawing.

  python style_test.py <style_tag> <name>
Env: TEST_SEED (6400), TEST_STEPS (18)
"""
import json, os, sys, time, shutil, subprocess, urllib.request
from pathlib import Path
sys.path.insert(0, "/workspace/text-to-video/scripts")
import showrunner as sr
from PIL import Image, ImageDraw

tag = sys.argv[1]
name = sys.argv[2] if len(sys.argv) > 2 else "oisin"
SEED = int(os.environ.get("TEST_SEED", "6400"))
STEPS = int(os.environ.get("TEST_STEPS", "18"))
COMFY = Path("/workspace/text-to-video/ComfyUI")
PROPS = Path("/workspace/text-to-video/series/tir-na-nog-legend/meshes/props")
REVIEW = Path("/workspace/review")

SUBJ = {"oisin": "a young Celtic warrior man, dark hair, short beard, green tunic, brown trousers",
        "niamh": "a young fae princess, long golden hair, green and white dress"}
STYLE = {
 "chibi": "chibi anime style, head about one third of body height, very simple rounded body, big eyes",
 "cel":   "clean modern anime cel style, simple flat colours, bold clean outline, rounded simplified forms",
 "hooded":"clean anime style, wearing a simple fitted hood over the head, simple closed forms",
 "toy":   "chunky vinyl toy figure style, thick simple limbs, large rounded head, smooth closed volumes",
 "thickline":"thick bold outline cartoon style, flat colour blocks, very simple chunky shapes",
}
# positive phrasing only — naming a thing to avoid summons it
BASE = ("standing in a T-pose with both arms stretched straight out horizontally to the sides "
        "at shoulder height, elbows straight, palms facing forward, fingers spread wide apart, "
        "feet shoulder width apart, whole body visible head to feet, centred, "
        "flat even studio lighting, pure white empty background, clean artwork")
# OPEN_MOUTH=1: draw the character mid-speech. A closed mouth reconstructs as a closed
# surface, so any mouth we want later has to be cut into it by hand. Drawn open, the
# reconstruction builds real mouth topology — lips, an opening, the inside — which is
# what blendshapes and visemes actually need to deform.
if os.environ.get("OPEN_MOUTH", "0") not in ("", "0"):
    BASE += (", MOUTH OPEN wide as if speaking, upper and lower lips clearly separated, "
             "dark open mouth interior visible, upper teeth visible")
VIEW = {"front": "seen from directly in front, facing the viewer",
        "left":  "exact side profile seen from the character's left, body turned ninety degrees",
        "back":  "seen from directly behind, the back of the head and the back of the body"}


def gen(view):
    prompt = "%s, %s, %s, %s" % (SUBJ.get(name, SUBJ["oisin"]), STYLE[tag], VIEW[view], BASE)
    wf = sr.build_t2i_workflow(prompt, seed=SEED, prefix="styletest/%s_%s_%s" % (name, tag, view),
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
                sys.exit("STYLETEST error on %s" % view)
        time.sleep(4)
    sys.exit("STYLETEST timeout on %s" % view)


views = {}
for v in ("front", "left", "back"):
    p = gen(v)
    dst = PROPS / ("st_%s_%s_%s.png" % (tag, name, v))
    shutil.copy(p, dst)
    views[v] = dst
    print("STYLETEST view", tag, v, dst.name, flush=True)

out = PROPS / ("st_%s_%s.glb" % (tag, name))
r = subprocess.run(["/workspace/venv/bin/python", "scripts/blender3d/character_mv.py",
                    str(views["front"]), str(views["left"]), str(views["back"]), str(out)],
                   capture_output=True, text=True, cwd="/workspace/text-to-video")
print("STYLETEST mesh", tag, (r.stdout or r.stderr).strip().splitlines()[-1][:120] if (r.stdout or r.stderr) else "?", flush=True)
if out.exists():
    subprocess.run(["/workspace/blender42/blender", "-b", "--factory-startup", "--python",
                    "scripts/blender3d/mesh_turntable.py", "--", str(out),
                    str(REVIEW / ("styletest_%s_%s.png" % (tag, name))), tag],
                   capture_output=True, text=True, cwd="/workspace/text-to-video")
    print("STYLETEST_DONE", tag, REVIEW / ("styletest_%s_%s.png" % (tag, name)), flush=True)
else:
    print("STYLETEST_DONE", tag, "NO MESH", flush=True)
