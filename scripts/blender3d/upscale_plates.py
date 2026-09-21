"""Upscale the concept plates 4x with the anime ESRGAN (ComfyUI) -> <setup>_4x.png beside each plate.
The painted world projects these onto the set, so a 640x360 master must not be the master's resolution."""
import json, sys, time, shutil, urllib.request
from pathlib import Path
sys.path.insert(0, "/workspace/text-to-video/scripts"); import showrunner as sr
COMFY = Path("/workspace/text-to-video/ComfyUI"); MODEL = "4x-AnimeSharp.pth"
for plate in [Path(p) for p in sys.argv[1:]]:
    dst = plate.with_name(plate.stem + "_4x.png")
    if dst.exists(): print("have", dst); continue
    inp = COMFY / "input" / f"plate_{plate.parent.name}_{plate.name}"; shutil.copy(plate, inp)
    wf = {"1": {"class_type": "LoadImage", "inputs": {"image": inp.name}},
          "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": MODEL}},
          "3": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
          "4": {"class_type": "SaveImage", "inputs": {"images": ["3", 0], "filename_prefix": f"plates4x/{plate.parent.name}_{plate.stem}"}}}
    pid = sr.queue_prompt(wf); t0 = time.time(); out = None
    while time.time() - t0 < 600:
        with urllib.request.urlopen(f"http://127.0.0.1:8188/history/{pid}", timeout=10) as r: h = json.loads(r.read())
        if pid in h and h[pid].get("outputs"):
            for node in h[pid]["outputs"].values():
                for im in node.get("images", []): out = COMFY / "output" / im.get("subfolder", "") / im["filename"]
            break
        time.sleep(3)
    if out is None: print("TIMEOUT", plate); continue
    shutil.copy(out, dst); print("UPSCALED", dst)
