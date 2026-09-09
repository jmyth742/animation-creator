"""
Recommendation 3: face-region HD repaint — the biggest quality-per-hour
lever for faces. Finds the face's UV region through the mesh triangles,
extracts that texture patch, upscales it, redraws it with FLUX img2img at
low denoise (layout preserved, detail added), and pastes it back.

Output: <props>/<name>_face_hdbase.png — a drop-in replacement base
texture. Wire-up for the variants: run face_paint.py with the environment
variable FACE_BASE pointing at this file (add a 3-line override where
face_paint loads `img` from the material: if os.environ.get("FACE_BASE"):
load that instead). QA-render before adopting.

Run inside blender:
  blender -b --factory-startup --python face_repaint.py -- \
      <painted.glb> <face_calib.json> <height> <name> <denoise=0.3>
Requires ComfyUI on :8188 with the FLUX nodes (same as gen_real_plates).
"""
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
sys.path.insert(0, "/workspace/text-to-video/scripts")
import character_kit as kit                                    # noqa: E402
import showrunner as sr                                        # noqa: E402

glb, calib_f, height, name = sys.argv[-5:-1]
denoise = float(sys.argv[-1]) if sys.argv[-1].replace(".", "").isdigit() else 0.3
height = float(height)
calib = json.load(open(calib_f))
PROPS = Path("/workspace/text-to-video/series/tir-na-nog-legend/meshes/props")

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
char = kit.load_character(glb, name, height=height)

img = None
for m in char.data.materials:
    for nd in m.node_tree.nodes:
        if nd.type == 'TEX_IMAGE' and nd.image:
            img = nd.image
W, H = img.size
tex = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)

# face center in 3D from the calibration
n = len(char.data.vertices)
co = np.empty(n * 3)
char.data.vertices.foreach_get("co", co)
P3 = co.reshape(-1, 3)
fx = calib.get("face_x", 0.0)
center = np.array((fx, P3[:, 1].min() * 0 - 0.10,
                   (calib["eye_z"] + calib["mouth_z"]) / 2))
# real front y at that height
band = P3[(np.abs(P3[:, 0] - fx) < 0.05) &
          (np.abs(P3[:, 2] - center[2]) < 0.04)]
if len(band):
    center[1] = float(band[:, 1].min()) + 0.01

# collect UVs of triangles near the face
uvl = char.data.uv_layers[0]
loops_uv = np.empty(len(char.data.loops) * 2)
uvl.data.foreach_get("uv", loops_uv)
loops_uv = loops_uv.reshape(-1, 2)
loop_vi = np.empty(len(char.data.loops), dtype=np.int64)
char.data.loops.foreach_get("vertex_index", loop_vi)
char.data.calc_loop_triangles()
face_uvs = []
R = 1.6 * abs(calib["eye_z"] - calib["mouth_z"]) + 0.05
for lt in char.data.loop_triangles:
    c3 = P3[loop_vi[list(lt.loops)]].mean(axis=0)
    if np.linalg.norm(c3 - center) < R and c3[1] < center[1] + 0.06:
        for li in lt.loops:
            face_uvs.append(loops_uv[li])
face_uvs = np.array(face_uvs)
# dominant island: reject UV outliers far from the median
med = np.median(face_uvs, axis=0)
keep = np.linalg.norm(face_uvs - med, axis=1) < 0.22
face_uvs = face_uvs[keep]
u0, v0 = np.clip(face_uvs.min(axis=0) - 0.01, 0, 1)
u1, v1 = np.clip(face_uvs.max(axis=0) + 0.01, 0, 1)
x0, x1 = int(u0 * W), int(u1 * W)
y0, y1 = int(v0 * H), int(v1 * H)
print(f"face UV patch: {x1-x0}x{y1-y0}px at ({x0},{y0})")

# extract, upscale to 768, hand to FLUX img2img
from PIL import Image                                          # noqa: E402
patch = (tex[y0:y1, x0:x1, :3] * 255).astype(np.uint8)[::-1]
pim = Image.fromarray(patch).resize((768, 768), Image.LANCZOS)
inp = Path("/workspace/text-to-video/ComfyUI/input/face_patch.png")
pim.save(inp)

DESC = {"oisin": "a young Celtic warrior's face, warm brown eyes, short "
                 "trimmed beard, dark hair framing the face",
        "niamh": "a Celtic princess's face, large bright green eyes, "
                 "golden hair framing the face"}
key = "niamh" if "niamh" in name else "oisin"
prompt = (f"Beautifully drawn anime face texture, {DESC[key]}, clean crisp "
          "features, soft painted cel shading, high detail, flat front-on "
          "face texture map, no text, no watermark")
wf = sr.build_t2i_workflow(prompt, seed=6100, prefix="face_hd",
                           width=768, height=768)
wf["5"] = {"class_type": "LoadImage", "inputs": {"image": "face_patch.png"}}
wf["5b"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}}
wf["10"]["inputs"]["steps"] = 8
wf["10"]["inputs"]["denoise"] = denoise
wf["11"]["inputs"]["latent_image"] = ["5b", 0]
pid = sr.queue_prompt(wf)
print("queued", pid, "denoise", denoise, flush=True)
t0 = time.time()
out_png = None
while time.time() - t0 < 1800:
    with urllib.request.urlopen(f"http://127.0.0.1:8188/history/{pid}",
                                timeout=10) as r:
        h = json.loads(r.read())
    if pid in h and h[pid].get("outputs"):
        for node in h[pid]["outputs"].values():
            for im2 in node.get("images", []):
                out_png = Path("/workspace/text-to-video/ComfyUI/output") / \
                    im2.get("subfolder", "") / im2["filename"]
        break
    time.sleep(8)
if out_png is None:
    sys.exit("FLUX repaint timed out")

hd = np.array(Image.open(out_png).convert("RGB")
              .resize((x1 - x0, y1 - y0), Image.LANCZOS),
              dtype=np.float32)[::-1] / 255
out = np.array(tex)
# soft-edged paste so the patch border never shows
yy, xx = np.mgrid[0:y1 - y0, 0:x1 - x0]
edge = np.minimum.reduce([yy, xx, (y1 - y0 - 1) - yy, (x1 - x0 - 1) - xx])
alpha = np.clip(edge / 24.0, 0, 1)[..., None]
out[y0:y1, x0:x1, :3] = (1 - alpha) * out[y0:y1, x0:x1, :3] + alpha * hd
dst = PROPS / f"{name}_face_hdbase.png"
im = bpy.data.images.new("hd", W, H, alpha=True)
im.pixels = out.ravel().tolist()
im.filepath_raw = str(dst)
im.file_format = 'PNG'
im.save()
print("FACE REPAINT DONE", dst)
