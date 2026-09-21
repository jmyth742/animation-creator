"""
Face HD by CAMERA PROJECTION (replaces face_repaint.py's UV-patch repaint).

Why: the AI meshes' auto-UV atlas scatters the face over many small islands,
so a "face patch" cut from the atlas is not a face (review/face_flux_patch_*.png)
and FLUX repaints it into nonsense. Instead:

  1. render the face FRONT-ON, unlit albedo, orthographic (a coherent image);
  2. FLUX img2img redraws it as a crisp anime face (layout kept, detail added);
  3. project that image back onto the head from the same camera (UV Project,
     exactly the technique of the painted sets) and BAKE it into the atlas at
     FACE_HD_SCALE x resolution, masked to front-facing surface near the face.

Output: <props>/<name>_face_hdbase.png — the drop-in base texture that
face_paint.py consumes through FACE_BASE (visemes/blinks paint on top as before).
Review: review/face_proj_<name>.png = front render | FLUX | close-up base | close-up HD.

Run inside blender (CHAR_NORMALFIX must be 0: no transfer modifier in the stack):
  blender -b --factory-startup --python face_project.py -- <painted.glb> <face_calib.json> <height> <name> [denoise=0.55]
Env: FACE_HD_SCALE (2), FACE_HD_STEPS (12), FACE_HD_SEED (6100), FACE_HD_RADIUS (1.0 = face-fit)
Requires ComfyUI on :8188 with the FLUX nodes.
"""
import json, os, sys, time, math, urllib.request
from pathlib import Path
import bpy, mathutils
import numpy as np

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
sys.path.append("/workspace/venv/lib/python3.11/site-packages")   # PIL for Blender's python
sys.path.insert(0, "/workspace/text-to-video/scripts")
os.environ["CHAR_NORMALFIX"] = "0"
import character_kit as kit                                    # noqa: E402
import showrunner as sr                                        # noqa: E402
from PIL import Image                                          # noqa: E402

glb, calib_f, height, name = sys.argv[-5:-1]
denoise = float(sys.argv[-1]) if sys.argv[-1].replace(".", "").isdigit() else 0.55
height = float(height); calib = json.load(open(calib_f))
SC = int(os.environ.get("FACE_HD_SCALE", "2")); STEPS = int(os.environ.get("FACE_HD_STEPS", "12"))
SEED = int(os.environ.get("FACE_HD_SEED", "6100")); RADK = float(os.environ.get("FACE_HD_RADIUS", "1.0"))
PROPS = Path("/workspace/text-to-video/series/tir-na-nog-legend/meshes/props")
REVIEW = Path("/workspace/review"); REVIEW.mkdir(exist_ok=True)
COMFY = Path("/workspace/text-to-video/ComfyUI")

sc = bpy.context.scene
for ob in list(sc.objects): bpy.data.objects.remove(ob, do_unlink=True)
char = kit.load_character(glb, name, height=height)
base_img = next(nd.image for m in char.data.materials for nd in m.node_tree.nodes if nd.type == 'TEX_IMAGE' and nd.image)
W, H = base_img.size
uv0 = char.data.uv_layers[0].name
print("FACEPROJ", name, "atlas", W, H, "uv", uv0, flush=True)

# --- face frame from the calibration (mesh faces -Y; mouth/eye heights in metres)
co = np.empty(len(char.data.vertices) * 3); char.data.vertices.foreach_get("co", co); P = co.reshape(-1, 3)
P = P @ np.array(char.matrix_world.to_3x3()).T + np.array(char.matrix_world.translation)
MZ, EZ, EX = calib["mouth_z"], calib["eye_z"], calib["eye_x"]; FX = calib.get("face_x", 0.0)
cz = (EZ + MZ) / 2
band = P[(np.abs(P[:, 0] - FX) < 0.05) & (np.abs(P[:, 2] - cz) < 0.04)]
fy = float(band[:, 1].min()) if len(band) else -0.1          # the face's front y
face_h = abs(EZ - MZ)                                        # eye-to-mouth
ortho = 4.2 * face_h * RADK                                  # frame: hairline to chin, ear to ear
cam_d = bpy.data.cameras.new("facecam"); cam_d.type = 'ORTHO'; cam_d.ortho_scale = ortho
cam_d.clip_start = 0.01; cam_d.clip_end = 5.0
cam = bpy.data.objects.new("facecam", cam_d); sc.collection.objects.link(cam)
cam.location = (FX, fy - 1.0, cz + 0.08 * face_h)
cam.rotation_euler = (math.radians(90), 0, 0)                 # look along +Y
print("FACEPROJ frame: front y", round(fy, 3), "centre z", round(cz, 3), "ortho", round(ortho, 3), flush=True)

# --- 1. flat albedo front render
flat = bpy.data.materials.new("flat"); flat.use_nodes = True; nt = flat.node_tree; nt.nodes.clear()
uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = uv0
tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = base_img; nt.links.new(uvn.outputs["UV"], tx.inputs["Vector"])
em = nt.nodes.new("ShaderNodeEmission"); out = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(tx.outputs["Color"], em.inputs["Color"]); nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
cel_mats = list(char.data.materials)
char.data.materials.clear(); char.data.materials.append(flat)
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.5, 0.5, 1)
sc.camera = cam; sc.render.engine = 'BLENDER_EEVEE_NEXT'; sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = sc.render.resolution_y = 1024; sc.render.film_transparent = False
front_png = COMFY / "input" / f"face_front_{name}.png"
sc.render.filepath = str(front_png); bpy.ops.render.render(write_still=True)
print("FACEPROJ front render", front_png, flush=True)

# --- 2. FLUX img2img
DESC = {"oisin": "a young Celtic warrior's face, warm brown eyes, dark hair framing the face",
        "niamh": "a Celtic princess's face, large bright green eyes, golden hair framing the face"}
key = "niamh" if "niamh" in name else "oisin"
prompt = (f"Anime character portrait, front view, {DESC[key]}, clean crisp linework, large expressive eyes, "
          "soft flat cel colours, studio anime key visual, symmetrical face, plain grey background, no text")
wf = sr.build_t2i_workflow(prompt, seed=SEED, prefix=f"face_proj_{name}", width=1024, height=1024)
wf["5"] = {"class_type": "LoadImage", "inputs": {"image": front_png.name}}
wf["5b"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}}
wf["10"]["inputs"]["steps"] = STEPS; wf["10"]["inputs"]["denoise"] = denoise
wf["11"]["inputs"]["latent_image"] = ["5b", 0]
pid = sr.queue_prompt(wf); print("FACEPROJ queued", pid, "denoise", denoise, "steps", STEPS, flush=True)
t0 = time.time(); out_png = None
while time.time() - t0 < 1800:
    with urllib.request.urlopen(f"http://127.0.0.1:8188/history/{pid}", timeout=10) as r: h = json.loads(r.read())
    if pid in h and h[pid].get("outputs"):
        for node in h[pid]["outputs"].values():
            for im2 in node.get("images", []):
                out_png = COMFY / "output" / im2.get("subfolder", "") / im2["filename"]
        break
    time.sleep(5)
if out_png is None: sys.exit("FACEPROJ: FLUX timed out")
flux_img = bpy.data.images.load(str(out_png)); print("FACEPROJ flux", out_png, flush=True)

# --- 3. project back + bake into the atlas
if "Proj" not in char.data.uv_layers: char.data.uv_layers.new(name="Proj")
bpy.ops.object.select_all(action='DESELECT'); char.select_set(True); bpy.context.view_layer.objects.active = char
md = char.modifiers.new("faceproj", 'UV_PROJECT'); md.uv_layer = "Proj"; md.projector_count = 1
md.projectors[0].object = cam; md.aspect_x = md.aspect_y = 1.0
bpy.ops.object.modifier_apply(modifier="faceproj")            # the Proj UVs are now data
char.data.uv_layers.active = char.data.uv_layers[uv0]         # bake target = the atlas UVs

bm = bpy.data.materials.new("bake"); bm.use_nodes = True; nt = bm.node_tree; nt.nodes.clear()
uvA = nt.nodes.new("ShaderNodeUVMap"); uvA.uv_map = uv0
txA = nt.nodes.new("ShaderNodeTexImage"); txA.image = base_img; nt.links.new(uvA.outputs["UV"], txA.inputs["Vector"])
uvP = nt.nodes.new("ShaderNodeUVMap"); uvP.uv_map = "Proj"
txP = nt.nodes.new("ShaderNodeTexImage"); txP.image = flux_img; txP.extension = 'CLIP'; nt.links.new(uvP.outputs["UV"], txP.inputs["Vector"])
# mask A: surface facing the camera (normal . -Y), soft from 0.25 to 0.55
geo = nt.nodes.new("ShaderNodeNewGeometry")
dotn = nt.nodes.new("ShaderNodeVectorMath"); dotn.operation = 'DOT_PRODUCT'; dotn.inputs[1].default_value = (0, -1, 0)
nt.links.new(geo.outputs["Normal"], dotn.inputs[0])
mapA = nt.nodes.new("ShaderNodeMapRange"); mapA.inputs["From Min"].default_value = 0.25; mapA.inputs["From Max"].default_value = 0.55
nt.links.new(dotn.outputs["Value"], mapA.inputs["Value"])
# mask B: inside the face frame (projected UV distance from centre), soft 0.36 -> 0.46
sub = nt.nodes.new("ShaderNodeVectorMath"); sub.operation = 'SUBTRACT'; sub.inputs[1].default_value = (0.5, 0.5, 0)
nt.links.new(uvP.outputs["UV"], sub.inputs[0])
ln = nt.nodes.new("ShaderNodeVectorMath"); ln.operation = 'LENGTH'; nt.links.new(sub.outputs["Vector"], ln.inputs[0])
mapB = nt.nodes.new("ShaderNodeMapRange"); mapB.inputs["From Min"].default_value = 0.46; mapB.inputs["From Max"].default_value = 0.36
nt.links.new(ln.outputs["Value"], mapB.inputs["Value"])
mul = nt.nodes.new("ShaderNodeMath"); mul.operation = 'MULTIPLY'
nt.links.new(mapA.outputs["Result"], mul.inputs[0]); nt.links.new(mapB.outputs["Result"], mul.inputs[1])
mix = nt.nodes.new("ShaderNodeMixRGB"); nt.links.new(mul.outputs["Value"], mix.inputs["Fac"])
nt.links.new(txA.outputs["Color"], mix.inputs["Color1"]); nt.links.new(txP.outputs["Color"], mix.inputs["Color2"])
em = nt.nodes.new("ShaderNodeEmission"); out = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(mix.outputs["Color"], em.inputs["Color"]); nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
target = bpy.data.images.new("hd", W * SC, H * SC, alpha=False)
tgt_node = nt.nodes.new("ShaderNodeTexImage"); tgt_node.image = target; nt.nodes.active = tgt_node
char.data.materials.clear(); char.data.materials.append(bm)
sc.render.engine = 'CYCLES'; sc.cycles.samples = 1; sc.cycles.device = 'GPU'
sc.render.bake.margin = 8 * SC; sc.render.bake.use_clear = True
bpy.ops.object.bake(type='EMIT')
dst = PROPS / f"{name}_face_hdbase{os.environ.get('FACE_HD_TAG', '')}.png"
target.filepath_raw = str(dst); target.file_format = 'PNG'; target.save()
print("FACEPROJ BAKED", dst, flush=True)

# --- review: close-up base vs HD through the cel shader
def closeup(img, path):
    for m in list(char.data.materials): pass
    char.data.materials.clear(); char.data.materials.append(kit.cel_material(name + "_r", img, uv0))
    sun = bpy.data.objects.get("sun")
    if sun is None:
        sun = bpy.data.objects.new("sun", bpy.data.lights.new("s", 'SUN')); sun.data.energy = 3.5; sun.data.color = (1.0, 0.85, 0.65)
        sun.rotation_euler = (math.radians(60), 0, math.radians(25)); sc.collection.objects.link(sun)
    wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.62, 0.60, 0.58, 1)
    c2 = bpy.data.objects.get("rcam")
    if c2 is None:
        c2 = bpy.data.objects.new("rcam", bpy.data.cameras.new("rc")); sc.collection.objects.link(c2); c2.data.lens = 85
        zs = P[:, 2]; mx = zs.max(); size = mx - zs.min()
        c2.location = (0, -0.85, mx - 0.13 * size); t = mathutils.Vector((0, 0, mx - 0.14 * size))
        c2.rotation_euler = (t - c2.location).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = c2; sc.render.engine = 'BLENDER_EEVEE_NEXT'; sc.render.resolution_x = sc.render.resolution_y = 900
    sc.render.filepath = path; bpy.ops.render.render(write_still=True)
os.environ["CHAR_NORMALFIX"] = "0"
closeup(base_img, f"/workspace/loopwork/faceproj_{name}_base.png")
closeup(target, f"/workspace/loopwork/faceproj_{name}_hd.png")
ims = [Image.open(p).convert("RGB").resize((900, 900)) for p in (front_png, out_png, f"/workspace/loopwork/faceproj_{name}_base.png", f"/workspace/loopwork/faceproj_{name}_hd.png")]
strip = Image.new("RGB", (3600, 900)); [strip.paste(im, (i * 900, 0)) for i, im in enumerate(ims)]
strip.save(REVIEW / f"face_proj_{name}.png"); print("FACEPROJ REVIEW", REVIEW / f"face_proj_{name}.png", flush=True)
