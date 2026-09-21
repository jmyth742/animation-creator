"""
BODY texture enrichment by multi-angle projection.

The faces are fixed; the bodies are not. A cloak that is one flat olive field, a tunic
with no weave, boots with no leather grain and hair with no strands is why a character
still reads as a cut-out against a painted background. The background carries dozens of
value steps per square inch and the character carries one.

This is the face bake widened to the whole figure: render the character from four
orthographic cameras, have FLUX redraw each at LOW denoise (the silhouette and the
costume design must survive — we want painted detail added, not a new character),
colour-match the side and back views to the front, project all four back and blend by
how squarely each surface faces its camera, then bake to a single atlas.

Low denoise is the whole trick. At 0.5 FLUX redesigns the costume and the views stop
agreeing; at ~0.32 it keeps the shapes and adds folds, seams, trim and texture.

  blender -b --factory-startup --python body_project.py -- <mesh.glb> <name> [denoise=0.32]

Writes <props>/<name>_body_hd.png and review/body_hd_<name>.png.
Env: BODY_HD_SCALE (2), BODY_STEPS (14), BODY_SEED (7100), BODY_POWER (2.5), BODY_TAG
"""
import json
import os
import sys
import time
import math
import urllib.request
from pathlib import Path

import bpy
import mathutils
import numpy as np

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
sys.path.append("/workspace/venv/lib/python3.11/site-packages")
sys.path.insert(0, "/workspace/text-to-video/scripts")
os.environ["CHAR_NORMALFIX"] = "0"
import character_kit as kit                                    # noqa: E402
import showrunner as sr                                        # noqa: E402
from PIL import Image                                          # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
glb, name = argv[0], argv[1]
denoise = float(argv[2]) if len(argv) > 2 else 0.32
SC = int(os.environ.get("BODY_HD_SCALE", "2"))
STEPS = int(os.environ.get("BODY_STEPS", "14"))
SEED = int(os.environ.get("BODY_SEED", "7100"))
POWER = float(os.environ.get("BODY_POWER", "2.5"))
TAG = os.environ.get("BODY_TAG", "")
PROPS = Path("/workspace/text-to-video/series/tir-na-nog-legend/meshes/props")
REVIEW = Path("/workspace/review"); REVIEW.mkdir(exist_ok=True)
COMFY = Path("/workspace/text-to-video/ComfyUI")
LW = Path("/workspace/loopwork")

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
char = kit.load_character(glb, name, height=1.75)
base_img = next(nd.image for m in char.data.materials for nd in m.node_tree.nodes
                if nd.type == 'TEX_IMAGE' and nd.image)
W, H = base_img.size
uv0 = char.data.uv_layers[0].name
print("BODY", name, "atlas", W, H, "faces", len(char.data.polygons), flush=True)

co = np.empty(len(char.data.vertices) * 3)
char.data.vertices.foreach_get("co", co)
P = co.reshape(-1, 3) @ np.array(char.matrix_world.to_3x3()).T + np.array(char.matrix_world.translation)
lo, hi = P.min(axis=0), P.max(axis=0)
centre = mathutils.Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2))
span = float(max(hi[2] - lo[2], hi[0] - lo[0])) * 1.12

VIEWS = [("f", 0.0), ("l", -55.0), ("r", 55.0), ("b", 180.0)]
cams = {}
for tag, deg in VIEWS:
    cd = bpy.data.cameras.new("bc_" + tag)
    cd.type = 'ORTHO'
    cd.ortho_scale = span
    cd.clip_start, cd.clip_end = 0.01, 12.0
    cam = bpy.data.objects.new("bc_" + tag, cd)
    sc.collection.objects.link(cam)
    r = math.radians(deg)
    cam.location = centre + mathutils.Vector((math.sin(r) * -3.0, -math.cos(r) * 3.0, 0.0))
    cam.rotation_euler = (centre - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cams[tag] = cam

flat = bpy.data.materials.new("flat")
flat.use_nodes = True
nt = flat.node_tree
nt.nodes.clear()
uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = uv0
tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = base_img
nt.links.new(uvn.outputs["UV"], tx.inputs["Vector"])
em = nt.nodes.new("ShaderNodeEmission")
out = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(tx.outputs["Color"], em.inputs["Color"])
nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
char.data.materials.clear()
char.data.materials.append(flat)
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.5, 0.5, 1)
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = sc.render.resolution_y = 1024
sc.render.film_transparent = False

COSTUME = {
    "oisin": ("a young Celtic warrior standing, dark green wool cloak with heavy folds, "
              "brown leather jerkin with visible stitching and straps, linen tunic, "
              "worn brown leather boots, dark hair"),
    "niamh": ("a Celtic fae princess standing, long flowing green gown with soft fabric "
              "folds, white and gold embroidered bodice, gold trim and braid, long "
              "golden hair in strands"),
}
key = "niamh" if "niamh" in name else "oisin"
VD = {"f": "front view", "l": "three-quarter view from the left",
      "r": "three-quarter view from the right", "b": "view from behind"}

imgs, paths = {}, {}
for tag, deg in VIEWS:
    sc.camera = cams[tag]
    src = COMFY / "input" / ("body_%s_%s.png" % (name, tag))
    sc.render.filepath = str(src)
    bpy.ops.render.render(write_still=True)
    prompt = ("Anime character full body, %s, %s, painted cel shading with clear fabric "
              "folds and cloth shadow shapes, crisp clean linework, flat anime colours, "
              "studio anime key visual, plain grey background, no text"
              % (VD[tag], COSTUME[key]))
    wf = sr.build_t2i_workflow(prompt, seed=SEED, prefix="body_%s_%s" % (name, tag),
                               width=1024, height=1024)
    wf["5"] = {"class_type": "LoadImage", "inputs": {"image": src.name}}
    wf["5b"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}}
    wf["10"]["inputs"]["steps"] = STEPS
    wf["10"]["inputs"]["denoise"] = denoise
    wf["11"]["inputs"]["latent_image"] = ["5b", 0]
    pid = sr.queue_prompt(wf)
    print("BODY queued", tag, "denoise", denoise, flush=True)
    t0 = time.time(); got = None
    while time.time() - t0 < 1800:
        with urllib.request.urlopen("http://127.0.0.1:8188/history/%s" % pid, timeout=10) as r:
            h = json.loads(r.read())
        if pid in h and h[pid].get("outputs"):
            for node in h[pid]["outputs"].values():
                for im in node.get("images", []):
                    got = COMFY / "output" / im.get("subfolder", "") / im["filename"]
            break
        time.sleep(5)
    if got is None:
        sys.exit("BODY: FLUX timed out on %s" % tag)
    paths[tag] = got
    print("BODY flux", tag, got.name, flush=True)


def mean_of(path):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
    h, w, _ = a.shape
    c = a[int(h * 0.15):int(h * 0.9), int(w * 0.3):int(w * 0.7)]
    return c.reshape(-1, 3).mean(axis=0)


ref = mean_of(paths["f"])
for tag, _deg in VIEWS:
    if tag == "f":
        imgs[tag] = bpy.data.images.load(str(paths[tag]))
        continue
    gain = np.clip(ref / np.maximum(mean_of(paths[tag]), 1e-3), 0.8, 1.25)
    a = np.clip(np.asarray(Image.open(paths[tag]).convert("RGB"), dtype=np.float32) / 255.0 * gain, 0, 1)
    fx = LW / ("body_%s_%s_cm.png" % (name, tag))
    Image.fromarray((a * 255).astype(np.uint8)).save(fx)
    imgs[tag] = bpy.data.images.load(str(fx))
    print("BODY colour-match", tag, tuple(round(float(g), 3) for g in gain), flush=True)

bpy.ops.object.select_all(action='DESELECT')
char.select_set(True)
bpy.context.view_layer.objects.active = char
for tag, _deg in VIEWS:
    ln = "BProj_" + tag
    if ln not in char.data.uv_layers:
        char.data.uv_layers.new(name=ln)
    md = char.modifiers.new("bp_" + tag, 'UV_PROJECT')
    md.uv_layer = ln
    md.projector_count = 1
    md.projectors[0].object = cams[tag]
    md.aspect_x = md.aspect_y = 1.0
    bpy.ops.object.modifier_apply(modifier=md.name)
char.data.uv_layers.active = char.data.uv_layers[uv0]

bm = bpy.data.materials.new(name + "_bodybake")
bm.use_nodes = True
n2 = bm.node_tree
n2.nodes.clear()
geo = n2.nodes.new("ShaderNodeNewGeometry")
uvA = n2.nodes.new("ShaderNodeUVMap"); uvA.uv_map = uv0
txA = n2.nodes.new("ShaderNodeTexImage"); txA.image = base_img
n2.links.new(uvA.outputs["UV"], txA.inputs["Vector"])

acc_c = acc_w = None
for tag, deg in VIEWS:
    r = math.radians(deg)
    view = (math.sin(r), -math.cos(r), 0.0)        # normal should point at this camera
    uvp = n2.nodes.new("ShaderNodeUVMap"); uvp.uv_map = "BProj_" + tag
    txp = n2.nodes.new("ShaderNodeTexImage"); txp.image = imgs[tag]; txp.extension = 'EXTEND'
    n2.links.new(uvp.outputs["UV"], txp.inputs["Vector"])
    dot = n2.nodes.new("ShaderNodeVectorMath"); dot.operation = 'DOT_PRODUCT'
    dot.inputs[1].default_value = (-view[0], -view[1], 0.0)
    n2.links.new(geo.outputs["Normal"], dot.inputs[0])
    cl = n2.nodes.new("ShaderNodeMath"); cl.operation = 'MAXIMUM'; cl.inputs[1].default_value = 0.0
    n2.links.new(dot.outputs["Value"], cl.inputs[0])
    pw = n2.nodes.new("ShaderNodeMath"); pw.operation = 'POWER'; pw.inputs[1].default_value = POWER
    n2.links.new(cl.outputs["Value"], pw.inputs[0])
    sc_n = n2.nodes.new("ShaderNodeVectorMath"); sc_n.operation = 'SCALE'
    n2.links.new(txp.outputs["Color"], sc_n.inputs[0])
    n2.links.new(pw.outputs["Value"], sc_n.inputs["Scale"])
    if acc_c is None:
        acc_c, acc_w = sc_n.outputs["Vector"], pw.outputs["Value"]
    else:
        ad = n2.nodes.new("ShaderNodeVectorMath"); ad.operation = 'ADD'
        n2.links.new(acc_c, ad.inputs[0]); n2.links.new(sc_n.outputs["Vector"], ad.inputs[1])
        acc_c = ad.outputs["Vector"]
        aw = n2.nodes.new("ShaderNodeMath"); aw.operation = 'ADD'
        n2.links.new(acc_w, aw.inputs[0]); n2.links.new(pw.outputs["Value"], aw.inputs[1])
        acc_w = aw.outputs["Value"]

safe = n2.nodes.new("ShaderNodeMath"); safe.operation = 'MAXIMUM'; safe.inputs[1].default_value = 1e-4
n2.links.new(acc_w, safe.inputs[0])
div = n2.nodes.new("ShaderNodeCombineXYZ")
for s_ in ("X", "Y", "Z"):
    n2.links.new(safe.outputs["Value"], div.inputs[s_])
nrm = n2.nodes.new("ShaderNodeVectorMath"); nrm.operation = 'DIVIDE'
n2.links.new(acc_c, nrm.inputs[0]); n2.links.new(div.outputs["Vector"], nrm.inputs[1])

seen = n2.nodes.new("ShaderNodeMapRange")
seen.inputs["From Min"].default_value = 0.04
seen.inputs["From Max"].default_value = 0.25
n2.links.new(acc_w, seen.inputs["Value"])
mix = n2.nodes.new("ShaderNodeMixRGB")
n2.links.new(seen.outputs["Result"], mix.inputs["Fac"])
n2.links.new(txA.outputs["Color"], mix.inputs["Color1"])
n2.links.new(nrm.outputs["Vector"], mix.inputs["Color2"])
em2 = n2.nodes.new("ShaderNodeEmission")
out2 = n2.nodes.new("ShaderNodeOutputMaterial")
n2.links.new(mix.outputs["Color"], em2.inputs["Color"])
n2.links.new(em2.outputs["Emission"], out2.inputs["Surface"])

target = bpy.data.images.new("body_hd", W * SC, H * SC, alpha=False)
tn = n2.nodes.new("ShaderNodeTexImage"); tn.image = target
n2.nodes.active = tn
char.data.materials.clear()
char.data.materials.append(bm)

sc.render.engine = 'CYCLES'
sc.cycles.samples = 1
try:
    sc.cycles.device = 'GPU'
except Exception:                                               # noqa: BLE001
    pass
sc.render.bake.use_selected_to_active = False
sc.render.bake.margin = 8 * SC
sc.render.bake.use_clear = True
bpy.ops.object.bake(type='EMIT')

dst = PROPS / ("%s_body_hd%s.png" % (name, TAG))
target.filepath_raw = str(dst)
target.file_format = 'PNG'
target.save()
print("BODY BAKED", dst, flush=True)

# review: same figure, original albedo vs enriched
def shot(img, path):
    char.data.materials.clear()
    char.data.materials.append(kit.cel_material(name + "_r", img, uv0))
    if bpy.data.objects.get("bsun") is None:
        s2 = bpy.data.objects.new("bsun", bpy.data.lights.new("s", 'SUN'))
        s2.data.energy = 3.2
        s2.rotation_euler = (math.radians(58), 0, math.radians(30))
        sc.collection.objects.link(s2)
    wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.6, 0.6, 0.58, 1)
    c = bpy.data.objects.get("bcam2")
    if c is None:
        c = bpy.data.objects.new("bcam2", bpy.data.cameras.new("bc2"))
        sc.collection.objects.link(c)
        c.data.type = 'ORTHO'
        c.data.ortho_scale = span
        c.location = centre + mathutils.Vector((-1.1, -2.6, 0.0))
        c.rotation_euler = (centre - mathutils.Vector(c.location)).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = c
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.render.resolution_x, sc.render.resolution_y = 620, 900
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


shot(base_img, str(LW / ("bodyrev_%s_old.png" % name)))
shot(target, str(LW / ("bodyrev_%s_new.png" % name)))
a = Image.open(LW / ("bodyrev_%s_old.png" % name)).convert("RGB")
b = Image.open(LW / ("bodyrev_%s_new.png" % name)).convert("RGB")
sheet = Image.new("RGB", (a.width * 2, a.height))
sheet.paste(a, (0, 0)); sheet.paste(b, (a.width, 0))
sheet.save(REVIEW / ("body_hd_%s.png" % name))
print("BODY REVIEW", REVIEW / ("body_hd_%s.png" % name), "(original | enriched)", flush=True)
