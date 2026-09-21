"""
MULTI-ANGLE face bake — the fix for "the faces look deformed at three-quarter".

face_project.py bakes the FLUX face from ONE front-on camera. A single projection is
only correct where the surface faces that camera; everywhere else it stretches along the
surface, which is exactly why the face reads warped the moment the head turns.

So bake from three cameras — front and both three-quarters — and blend them per-pixel by
how squarely the surface faces each one. Every part of the face is then taken from the
camera that saw it most directly, and no region is stretched.

  1. three orthographic cameras around the head's vertical axis (-40, 0, +40 degrees);
  2. a flat unlit albedo render from each, redrawn by FLUX img2img (same seed, and the
     side views at a lower denoise so they stay anchored to the geometry);
  3. a UV Project layer per camera, applied so the UVs are real data;
  4. one Cycles EMIT bake whose material weights the three projections by
     max(0, dot(N, -view_i)) ** k, normalised, and fades to the original atlas away from
     the face;
  5. <props>/<name>_face_hdbase.png at FACE_HD_SCALE x resolution.

Run (CHAR_NORMALFIX must be 0):
  blender -b --factory-startup --python face_project_mv.py -- <painted.glb> <face_calib.json> <height> <name> [denoise=0.55]
Env: FACE_HD_SCALE (2), FACE_HD_STEPS (12), FACE_HD_SEED (6100), FACE_MV_ANGLE (40),
     FACE_MV_SIDE_DENOISE (0.42), FACE_MV_POWER (3.0), FACE_HD_TAG
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
glb, calib_f, height, name = argv[0], argv[1], float(argv[2]), argv[3]
denoise = float(argv[4]) if len(argv) > 4 else 0.55
SC = int(os.environ.get("FACE_HD_SCALE", "2"))
STEPS = int(os.environ.get("FACE_HD_STEPS", "12"))
SEED = int(os.environ.get("FACE_HD_SEED", "6100"))
ANG = float(os.environ.get("FACE_MV_ANGLE", "40"))
SIDE_DN = float(os.environ.get("FACE_MV_SIDE_DENOISE", "0.42"))
POWER = float(os.environ.get("FACE_MV_POWER", "3.0"))
TAG = os.environ.get("FACE_HD_TAG", "")
PROPS = Path("/workspace/text-to-video/series/tir-na-nog-legend/meshes/props")
REVIEW = Path("/workspace/review"); REVIEW.mkdir(exist_ok=True)
COMFY = Path("/workspace/text-to-video/ComfyUI")
calib = json.load(open(calib_f))

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
char = kit.load_character(glb, name, height=height)
base_img = next(nd.image for m in char.data.materials for nd in m.node_tree.nodes
                if nd.type == 'TEX_IMAGE' and nd.image)
W, H = base_img.size
uv0 = char.data.uv_layers[0].name
print("FACEMV", name, "atlas", W, H, flush=True)

# --- the face frame, from the calibration
co_arr = np.empty(len(char.data.vertices) * 3)
char.data.vertices.foreach_get("co", co_arr)
P = co_arr.reshape(-1, 3) @ np.array(char.matrix_world.to_3x3()).T + np.array(char.matrix_world.translation)
MZ, EZ = calib["mouth_z"], calib["eye_z"]
FX = calib.get("face_x", 0.0)
cz = (EZ + MZ) / 2
band = P[(np.abs(P[:, 0] - FX) < 0.05) & (np.abs(P[:, 2] - cz) < 0.04)]
fy = float(band[:, 1].min()) if len(band) else -0.1
face_h = abs(EZ - MZ)
ortho = 4.2 * face_h
centre = mathutils.Vector((FX, fy + 0.5 * face_h, cz + 0.08 * face_h))
print("FACEMV frame front_y %.3f cz %.3f ortho %.3f" % (fy, cz, ortho), flush=True)

# --- three cameras around the head's vertical axis
VIEWS = [("l", -ANG, SIDE_DN), ("c", 0.0, denoise), ("r", ANG, SIDE_DN)]
cams = {}
for tag, deg, _dn in VIEWS:
    cd = bpy.data.cameras.new("fc_" + tag)
    cd.type = 'ORTHO'
    cd.ortho_scale = ortho
    cd.clip_start, cd.clip_end = 0.01, 6.0
    cam = bpy.data.objects.new("fc_" + tag, cd)
    sc.collection.objects.link(cam)
    r = math.radians(deg)
    # start 1 m in front (-Y) of the face centre, rotate about Z through the centre
    offs = mathutils.Vector((math.sin(r) * -1.0, -math.cos(r) * 1.0, 0.0))
    cam.location = centre + offs
    cam.rotation_euler = (centre - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cams[tag] = cam

# --- flat albedo, one render per camera
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

DESC = {"oisin": "a young Celtic warrior's face, warm brown eyes, dark hair framing the face",
        "niamh": "a Celtic princess's face, large bright green eyes, golden hair framing the face"}
key = "niamh" if "niamh" in name else "oisin"
VIEWDESC = {"l": "three-quarter view from the left", "c": "front view", "r": "three-quarter view from the right"}

flux_imgs = {}
flux_paths = {}
for tag, deg, dn in VIEWS:
    sc.camera = cams[tag]
    src_png = COMFY / "input" / ("face_mv_%s_%s.png" % (name, tag))
    sc.render.filepath = str(src_png)
    bpy.ops.render.render(write_still=True)
    prompt = ("Anime character portrait, %s, neutral expression, mouth closed, %s, clean crisp "
              "linework, large expressive eyes, soft flat cel colours, studio anime key visual, "
              "plain grey background, no text" % (VIEWDESC[tag], DESC[key]))
    wf = sr.build_t2i_workflow(prompt, seed=SEED, prefix="face_mv_%s_%s" % (name, tag),
                               width=1024, height=1024)
    wf["5"] = {"class_type": "LoadImage", "inputs": {"image": src_png.name}}
    wf["5b"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}}
    wf["10"]["inputs"]["steps"] = STEPS
    wf["10"]["inputs"]["denoise"] = dn
    wf["11"]["inputs"]["latent_image"] = ["5b", 0]
    pid = sr.queue_prompt(wf)
    print("FACEMV queued", tag, "deg", deg, "denoise", dn, flush=True)
    t0 = time.time(); got = None
    while time.time() - t0 < 1800:
        with urllib.request.urlopen("http://127.0.0.1:8188/history/%s" % pid, timeout=10) as r:
            h = json.loads(r.read())
        if pid in h and h[pid].get("outputs"):
            for node in h[pid]["outputs"].values():
                for im2 in node.get("images", []):
                    got = COMFY / "output" / im2.get("subfolder", "") / im2["filename"]
            break
        time.sleep(5)
    if got is None:
        sys.exit("FACEMV: FLUX timed out on view %s" % tag)
    flux_imgs[tag] = bpy.data.images.load(str(got))
    flux_paths[tag] = got
    print("FACEMV flux", tag, got.name, flush=True)

# COLOUR-MATCH the side views to the centre. FLUX redraws each view independently, so the
# three outputs do not share a colour balance; blending them then leaves a visible patch
# of another skin tone down one side of the face (review/haze_fix_ab.png showed a green
# left cheek). Match each side view's central-region mean to the centre view's.
def _mean(path):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
    h, w, _ = a.shape
    c = a[int(h * 0.30):int(h * 0.75), int(w * 0.30):int(w * 0.70)]
    return c.reshape(-1, 3).mean(axis=0)


_ref = _mean(flux_paths["c"])
for tag in ("l", "r"):
    m = _mean(flux_paths[tag])
    gain = np.clip(_ref / np.maximum(m, 1e-3), 0.75, 1.35)
    a = np.asarray(Image.open(flux_paths[tag]).convert("RGB"), dtype=np.float32) / 255.0
    a = np.clip(a * gain, 0.0, 1.0)
    fixed = Path("/workspace/loopwork") / ("facemv_%s_%s_cm.png" % (name, tag))
    Image.fromarray((a * 255).astype(np.uint8)).save(fixed)
    flux_imgs[tag] = bpy.data.images.load(str(fixed))
    print("FACEMV colour-match", tag, "gain", tuple(round(float(g), 3) for g in gain), flush=True)

# --- a projected UV layer per camera
bpy.ops.object.select_all(action='DESELECT')
char.select_set(True)
bpy.context.view_layer.objects.active = char
for tag, _deg, _dn in VIEWS:
    lname = "Proj_" + tag
    if lname not in char.data.uv_layers:
        char.data.uv_layers.new(name=lname)
    md = char.modifiers.new("mv_" + tag, 'UV_PROJECT')
    md.uv_layer = lname
    md.projector_count = 1
    md.projectors[0].object = cams[tag]
    md.aspect_x = md.aspect_y = 1.0
    bpy.ops.object.modifier_apply(modifier=md.name)
char.data.uv_layers.active = char.data.uv_layers[uv0]

# --- one bake material: weight each projection by how squarely the surface faces it
bm = bpy.data.materials.new(name + "_mvbake")
bm.use_nodes = True
nt2 = bm.node_tree
nt2.nodes.clear()
geo = nt2.nodes.new("ShaderNodeNewGeometry")
uvA = nt2.nodes.new("ShaderNodeUVMap"); uvA.uv_map = uv0
txA = nt2.nodes.new("ShaderNodeTexImage"); txA.image = base_img
nt2.links.new(uvA.outputs["UV"], txA.inputs["Vector"])

acc_col = None
acc_w = None
face_w = None
for tag, deg, _dn in VIEWS:
    r = math.radians(deg)
    view_dir = (0.0, -math.cos(r), 0.0)
    vx = math.sin(r) * -1.0
    vlen = math.hypot(vx, math.cos(r))
    view = (-vx / vlen, math.cos(r) / vlen, 0.0)       # surface normal should point AT the camera
    uvp = nt2.nodes.new("ShaderNodeUVMap"); uvp.uv_map = "Proj_" + tag
    txp = nt2.nodes.new("ShaderNodeTexImage")
    txp.image = flux_imgs[tag]
    txp.extension = 'EXTEND'
    nt2.links.new(uvp.outputs["UV"], txp.inputs["Vector"])
    dot = nt2.nodes.new("ShaderNodeVectorMath")
    dot.operation = 'DOT_PRODUCT'
    dot.inputs[1].default_value = view
    nt2.links.new(geo.outputs["Normal"], dot.inputs[0])
    clamp = nt2.nodes.new("ShaderNodeMath"); clamp.operation = 'MAXIMUM'
    clamp.inputs[1].default_value = 0.0
    nt2.links.new(dot.outputs["Value"], clamp.inputs[0])
    powr = nt2.nodes.new("ShaderNodeMath"); powr.operation = 'POWER'
    powr.inputs[1].default_value = POWER
    nt2.links.new(clamp.outputs["Value"], powr.inputs[0])
    # weighted colour
    scale = nt2.nodes.new("ShaderNodeVectorMath"); scale.operation = 'SCALE'
    nt2.links.new(txp.outputs["Color"], scale.inputs[0])
    nt2.links.new(powr.outputs["Value"], scale.inputs["Scale"])
    if acc_col is None:
        acc_col, acc_w = scale.outputs["Vector"], powr.outputs["Value"]
    else:
        add = nt2.nodes.new("ShaderNodeVectorMath"); add.operation = 'ADD'
        nt2.links.new(acc_col, add.inputs[0]); nt2.links.new(scale.outputs["Vector"], add.inputs[1])
        acc_col = add.outputs["Vector"]
        aw = nt2.nodes.new("ShaderNodeMath"); aw.operation = 'ADD'
        nt2.links.new(acc_w, aw.inputs[0]); nt2.links.new(powr.outputs["Value"], aw.inputs[1])
        acc_w = aw.outputs["Value"]
    if tag == "c":
        face_w = powr.outputs["Value"]

safe = nt2.nodes.new("ShaderNodeMath"); safe.operation = 'MAXIMUM'
safe.inputs[1].default_value = 1e-4
nt2.links.new(acc_w, safe.inputs[0])
norm = nt2.nodes.new("ShaderNodeVectorMath"); norm.operation = 'DIVIDE'
nt2.links.new(acc_col, norm.inputs[0])
div = nt2.nodes.new("ShaderNodeCombineXYZ")
for sock in ("X", "Y", "Z"):
    nt2.links.new(safe.outputs["Value"], div.inputs[sock])
nt2.links.new(div.outputs["Vector"], norm.inputs[1])

# fade to the original atlas outside the face: projected distance from the front camera's centre
uvc = nt2.nodes.new("ShaderNodeUVMap"); uvc.uv_map = "Proj_c"
sub = nt2.nodes.new("ShaderNodeVectorMath"); sub.operation = 'SUBTRACT'
sub.inputs[1].default_value = (0.5, 0.5, 0.0)
nt2.links.new(uvc.outputs["UV"], sub.inputs[0])
ln = nt2.nodes.new("ShaderNodeVectorMath"); ln.operation = 'LENGTH'
nt2.links.new(sub.outputs["Vector"], ln.inputs[0])
mapB = nt2.nodes.new("ShaderNodeMapRange")
mapB.inputs["From Min"].default_value = 0.46
mapB.inputs["From Max"].default_value = 0.36
nt2.links.new(ln.outputs["Value"], mapB.inputs["Value"])
# and only where SOME camera saw the surface at a decent angle
seen = nt2.nodes.new("ShaderNodeMapRange")
seen.inputs["From Min"].default_value = 0.05
seen.inputs["From Max"].default_value = 0.30
nt2.links.new(acc_w, seen.inputs["Value"])
mul = nt2.nodes.new("ShaderNodeMath"); mul.operation = 'MULTIPLY'
nt2.links.new(mapB.outputs["Result"], mul.inputs[0])
nt2.links.new(seen.outputs["Result"], mul.inputs[1])

mix = nt2.nodes.new("ShaderNodeMixRGB")
nt2.links.new(mul.outputs["Value"], mix.inputs["Fac"])
nt2.links.new(txA.outputs["Color"], mix.inputs["Color1"])
nt2.links.new(norm.outputs["Vector"], mix.inputs["Color2"])
em2 = nt2.nodes.new("ShaderNodeEmission")
out2 = nt2.nodes.new("ShaderNodeOutputMaterial")
nt2.links.new(mix.outputs["Color"], em2.inputs["Color"])
nt2.links.new(em2.outputs["Emission"], out2.inputs["Surface"])

target = bpy.data.images.new("hd_mv", W * SC, H * SC, alpha=False)
tgt_node = nt2.nodes.new("ShaderNodeTexImage")
tgt_node.image = target
nt2.nodes.active = tgt_node
char.data.materials.clear()
char.data.materials.append(bm)

sc.render.engine = 'CYCLES'
sc.cycles.samples = 1
try:
    sc.cycles.device = 'GPU'
except Exception:                                              # noqa: BLE001
    pass
sc.render.bake.use_selected_to_active = False
sc.render.bake.margin = 8 * SC
sc.render.bake.use_clear = True
bpy.ops.object.bake(type='EMIT')

dst = PROPS / ("%s_face_hdbase%s.png" % (name, TAG))
target.filepath_raw = str(dst)
target.file_format = 'PNG'
target.save()
print("FACEMV BAKED", dst, flush=True)

# --- review: the same head at front and three-quarter, old base vs multi-angle
def closeup(img, path, yaw):
    char.data.materials.clear()
    char.data.materials.append(kit.cel_material(name + "_r", img, uv0))
    if bpy.data.objects.get("rsun") is None:
        s2 = bpy.data.objects.new("rsun", bpy.data.lights.new("s2", 'SUN'))
        s2.data.energy = 3.5
        s2.data.color = (1.0, 0.85, 0.65)
        s2.rotation_euler = (math.radians(60), 0, math.radians(25))
        sc.collection.objects.link(s2)
    wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.62, 0.60, 0.58, 1)
    c2 = bpy.data.objects.get("rcam")
    if c2 is None:
        c2 = bpy.data.objects.new("rcam", bpy.data.cameras.new("rc"))
        sc.collection.objects.link(c2)
        c2.data.lens = 85
    yr = math.radians(yaw)
    d = 0.85
    c2.location = (centre.x + math.sin(yr) * -d, centre.y - math.cos(yr) * d, centre.z)
    c2.rotation_euler = (centre - mathutils.Vector(c2.location)).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = c2
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.render.resolution_x = sc.render.resolution_y = 760
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


LW = "/workspace/loopwork"
old_base = PROPS / ("%s_face_hdbase.png" % name)
old_img = bpy.data.images.load(str(old_base)) if old_base.exists() and TAG else base_img
shots = []
for yaw in (0, 35):
    closeup(old_img, "%s/mv_old_%d.png" % (LW, yaw), yaw)
    closeup(target, "%s/mv_new_%d.png" % (LW, yaw), yaw)
    shots += ["%s/mv_old_%d.png" % (LW, yaw), "%s/mv_new_%d.png" % (LW, yaw)]
ims = [Image.open(p).convert("RGB") for p in shots]
sheet = Image.new("RGB", (760 * 4, 760))
for i, im in enumerate(ims):
    sheet.paste(im, (i * 760, 0))
sheet.save(REVIEW / ("face_mv_%s.png" % name))
print("FACEMV REVIEW", REVIEW / ("face_mv_%s.png" % name), "(front old|new, 3/4 old|new)", flush=True)
