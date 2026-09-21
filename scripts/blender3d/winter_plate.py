"""Derive the WINTER plate from the valley master by FLUX img2img (layout kept, season changed),
so Episode 2's painted world shares the summer plate's geometry calibration.
  venv python winter_plate.py [denoise=0.55] -> sets/tir_na_nog/master_winter.png (+ _4x via upscale_plates.py)"""
import json, sys, time, shutil, urllib.request
from pathlib import Path
sys.path.insert(0, "/workspace/text-to-video/scripts"); import showrunner as sr
COMFY = Path("/workspace/text-to-video/ComfyUI"); SETS = Path("/workspace/text-to-video/series/tir-na-nog-legend/sets/tir_na_nog")
dn = float(sys.argv[1]) if len(sys.argv) > 1 else 0.55
src = SETS / "master_4x.png" if (SETS / "master_4x.png").exists() else SETS / "master.png"
inp = COMFY / "input" / "winter_src.png"; shutil.copy(src, inp)
prompt = ("The same valley in deep winter: snow-covered meadow and path, frozen lake, icicles on the waterfall, "
          "snow on the golden hall's roofs and battlements, bare frosted trees, pale winter sky, soft cold light, "
          "painted anime background, cel-shaded key visual, no people")
import os
SEED = int(os.environ.get("WINTER_SEED", "6100"))
wf = sr.build_t2i_workflow(prompt, seed=SEED, prefix="plates4x/tir_na_nog_winter", width=1664, height=960)
wf["5"] = {"class_type": "LoadImage", "inputs": {"image": inp.name}}
wf["5r"] = {"class_type": "ImageScale", "inputs": {"image": ["5", 0], "upscale_method": "lanczos", "width": 1664, "height": 960, "crop": "disabled"}}
wf["5b"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["5r", 0], "vae": ["3", 0]}}
wf["10"]["inputs"]["steps"] = 12; wf["10"]["inputs"]["denoise"] = dn
wf["11"]["inputs"]["latent_image"] = ["5b", 0]
pid = sr.queue_prompt(wf); print("queued", pid, "denoise", dn, flush=True); t0 = time.time(); out = None
while time.time() - t0 < 1200:
    with urllib.request.urlopen(f"http://127.0.0.1:8188/history/{pid}", timeout=10) as r: h = json.loads(r.read())
    if pid in h and h[pid].get("outputs"):
        for node in h[pid]["outputs"].values():
            for im in node.get("images", []): out = COMFY / "output" / im.get("subfolder", "") / im["filename"]
        break
    time.sleep(4)
if out is None: sys.exit("winter plate timed out")
dst = SETS / f"master_winter_dn{dn}_s{SEED}.png"; shutil.copy(out, dst); print("WINTER PLATE", dst)
