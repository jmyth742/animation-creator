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


def subject_for(n):
    """Resolve the subject from a possibly suffixed name (niamh_ap, niamh_open2).
    This used to be SUBJ.get(name, SUBJ["oisin"]), which meant every suffixed name
    silently drew Oisin -- the 'Niamh' character sheet, mesh, texture and rig were all
    Oisin, and nothing in the logs said so."""
    for key in SUBJ:
        if n == key or n.startswith(key + "_") or n.startswith(key):
            return SUBJ[key]
    sys.exit("STYLETEST: no subject matches %r (known: %s)" % (n, ", ".join(SUBJ)))
STYLE = {
 "chibi": "chibi anime style, head about one third of body height, very simple rounded body, big eyes",
 # chibi2 exists because the reconstruction cannot build a hand. Drawn with separate
 # fingers it comes back as a flattened lump of fused, splayed stubs, and in motion that
 # lump reads as a spike thrown across the silhouette. Drawn as a mitten there is nothing
 # to splay. The arms are also longer and held clear of the body, because short arms
 # pressed against the torso give the auto-rigger nothing to find.
 # chibi3: arms down AND no cloak over the shoulders. A cape carries arm weight, so any
 # pose conversion drags it across the back, and it hides the shoulder the rig needs.
 "chibi3": ("chibi anime style, head about one third of body height, simple rounded body, big eyes, "
            "wearing a simple fitted tunic with short sleeves and bare shoulders, no cape and no hood, "
            "hands drawn as simple rounded mittens with no separate fingers, "
            "arms a little longer than usual and held clearly away from the body"),
 "chibi2": ("chibi anime style, head about one third of body height, simple rounded body, big eyes, "
            "hands drawn as simple rounded mittens with no separate fingers, smooth closed oval hands, "
            "arms a little longer than usual and held clearly away from the body"),
 "cel":   "clean modern anime cel style, simple flat colours, bold clean outline, rounded simplified forms",
 "hooded":"clean anime style, wearing a simple fitted hood over the head, simple closed forms",
 "toy":   "chunky vinyl toy figure style, thick simple limbs, large rounded head, smooth closed volumes",
 "thickline":"thick bold outline cartoon style, flat colour blocks, very simple chunky shapes",
}
# positive phrasing only — naming a thing to avoid summons it
# POSE_MODE=apose draws the character the way it will be ANIMATED rather than the way
# it is easiest to reconstruct. A T-pose mesh binds arms-out, every clip in the motion
# library has the arms down, and closing that ~125 degree gap through linear blend
# skinning is what collapses the sleeve into the shoulder. Drawn arms-down the bind
# pose already matches the library and nothing has to be baked. The arms stay ~25
# degrees off the body so the reconstruction does not fuse them to the torso.
_POSE = os.environ.get("POSE_MODE", "tpose")
if _POSE == "apose":
    BASE = ("standing straight with both arms hanging down at the sides, upper arms about "
            "twenty five degrees away from the body with a clear gap of empty background "
            "between each arm and the torso, elbows straight, palms facing the thighs, "
            "fingers relaxed and slightly apart, feet shoulder width apart, "
            "whole body visible head to feet, centred, "
            "flat even studio lighting, pure white empty background, clean artwork")
else:
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
    prompt = "%s, %s, %s, %s" % (subject_for(name), STYLE[tag], VIEW[view], BASE)
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
