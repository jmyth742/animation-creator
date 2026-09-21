"""
NEW PLATE ANGLES by structural conditioning.

The valley's five "setups" converged during generation into near-copies of the master,
so Episode 1 and 2 effectively have ONE painted angle. That forces the shot language:
every camera has to stay near the master heading or the projection falls apart.

Free img2img from the master gives a different picture, not a different viewpoint. So
condition on the STRUCTURE instead: render the actual set geometry from the camera we
want, and use that render as the img2img base at moderate denoise. The output is a new
painted angle that still describes the same geometry, which means painter.py keeps
projecting correctly with no recalibration — the same trick the winter plate used for
season, applied to viewpoint.

  blender -b --factory-startup --python plate_angle.py -- <set> <setup> <loc> <tgt> [denoise=0.62]
    set   : valley | cliff
    setup : the plate name to write (reverse, side, wider, ...)
    loc/tgt: "x,y,z" for the painter camera that will own this plate

Writes sets/<location>/<setup>.png (640x360) and <setup>_4x.png, ready for painter.py.
"""
import json, os, sys, time, math, shutil, urllib.request
from pathlib import Path
import bpy, mathutils

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
sys.path.insert(0, "/workspace/text-to-video/scripts")
sys.path.append("/workspace/venv/lib/python3.11/site-packages")
import showrunner as sr                                        # noqa: E402
from PIL import Image                                          # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
which, setup = argv[0], argv[1]
loc = [float(v) for v in argv[2].split(",")]
tgt = [float(v) for v in argv[3].split(",")]
denoise = float(argv[4]) if len(argv) > 4 else 0.62
COMFY = Path("/workspace/text-to-video/ComfyUI")
SETS = Path("/workspace/text-to-video/series/tir-na-nog-legend/sets")

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x, sc.render.resolution_y = 832, 480

os.environ["SET_BACKDROP"] = "0"          # bare geometry: we want STRUCTURE, not the plate
if which == "valley":
    import valley_set, set_assets
    valley_set.build_set(sc)
    set_assets.dress_valley(sc, lambda x, y: 0.0)
    folder, desc = "tir_na_nog", ("a hidden Irish valley of Tir na nOg, golden hall with "
                                 "celtic knotwork, tall waterfall into a still lake, green "
                                 "mountains, wildflower meadow, standing cross")
else:
    import cliff_set
    cliff_set.build_set(sc)
    folder, desc = "farewell_cliff", ("an Irish sea cliff at sunset, wind-bent tree on the "
                                      "headland, sea stacks, calm golden ocean, grass shelf")

cam = bpy.data.objects.new("pc", bpy.data.cameras.new("pc"))
cam.data.lens = 32
sc.collection.objects.link(cam)
sc.camera = cam
cam.location = loc
cam.rotation_euler = (mathutils.Vector(tgt) - mathutils.Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
struct = COMFY / "input" / ("plateangle_%s_%s.png" % (folder, setup))
sc.render.filepath = str(struct)
bpy.ops.render.render(write_still=True)
print("PLATEANGLE structure render", struct.name, flush=True)

prompt = ("Painted anime background, %s, studio anime background painting, soft painterly "
          "brushwork, warm natural light, rich depth, no people, no text" % desc)
wf = sr.build_t2i_workflow(prompt, seed=int(os.environ.get("ANGLE_SEED", "8100")),
                           prefix="plateangle/%s_%s" % (folder, setup), width=832, height=480)
wf["5"] = {"class_type": "LoadImage", "inputs": {"image": struct.name}}
wf["5b"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}}
wf["10"]["inputs"]["steps"] = int(os.environ.get("ANGLE_STEPS", "16"))
wf["10"]["inputs"]["denoise"] = denoise
wf["11"]["inputs"]["latent_image"] = ["5b", 0]
pid = sr.queue_prompt(wf)
print("PLATEANGLE queued", setup, "denoise", denoise, flush=True)
t0 = time.time(); got = None
while time.time() - t0 < 1200:
    with urllib.request.urlopen("http://127.0.0.1:8188/history/%s" % pid, timeout=10) as r:
        h = json.loads(r.read())
    if pid in h and h[pid].get("outputs"):
        for node in h[pid]["outputs"].values():
            for im in node.get("images", []):
                got = COMFY / "output" / im.get("subfolder", "") / im["filename"]
        break
    time.sleep(4)
if got is None:
    sys.exit("PLATEANGLE: FLUX timed out")

dst = SETS / folder / ("%s.png" % setup)
Image.open(got).convert("RGB").resize((640, 360), Image.LANCZOS).save(dst)
side = Image.new("RGB", (832 * 2, 480))
side.paste(Image.open(struct).convert("RGB"), (0, 0))
side.paste(Image.open(got).convert("RGB").resize((832, 480)), (832, 0))
side.save("/workspace/review/plate_angle_%s_%s.png" % (folder, setup))
print("PLATEANGLE_DONE", dst, "| review plate_angle_%s_%s.png (structure | painted)" % (folder, setup), flush=True)
