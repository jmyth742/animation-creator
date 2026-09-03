"""One-frame style-pass trial: FLUX img2img over a Blender frame.

Answers the phase-4 question on a still before anyone builds the video
version: does low-denoise diffusion dress crude 3D geometry in the show's
look while keeping the plate-projected composition?
"""
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import showrunner as sr                                        # noqa: E402

frame, out_dir, denoise = sys.argv[1], sys.argv[2], float(sys.argv[3])

PROMPT = ("Cel-shaded 2D animation, clean confident linework, flat blocks of "
          "colour with simple shading, painted background art, animated film "
          "still. A lush Celtic valley of eternal summer, tall silver "
          "waterfalls, a still lake, a golden hall, wildflowers, warm light. "
          "A young Celtic warrior in a dark green hooded cloak walks away "
          "from the camera along the winding path, small in the frame, "
          "mid-stride. Rich saturated palette of vivid greens and gold.")

inp = Path("ComfyUI/input/b3d_style_src.png")
shutil.copy(frame, inp)

wf = sr.build_t2i_workflow(PROMPT, seed=777001, prefix="b3d_style", width=832, height=480)
# t2i -> img2img: encode the Blender frame instead of an empty latent
wf["5"] = {"class_type": "LoadImage", "inputs": {"image": "b3d_style_src.png"}}
wf["5b"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}}
wf["10"]["inputs"]["steps"] = 8
wf["10"]["inputs"]["denoise"] = denoise
wf["11"]["inputs"]["latent_image"] = ["5b", 0]

pid = sr.queue_prompt(wf)
print("queued", pid, "denoise", denoise, flush=True)
t0 = time.time()
while time.time() - t0 < 3600:
    with urllib.request.urlopen(f"http://127.0.0.1:8188/history/{pid}", timeout=10) as r:
        h = json.loads(r.read())
    if pid in h and h[pid].get("outputs"):
        for node in h[pid]["outputs"].values():
            for im in node.get("images", []):
                src = Path("ComfyUI/output") / im.get("subfolder", "") / im["filename"]
                dst = Path(out_dir) / f"styled_d{int(denoise*100)}.png"
                shutil.copy(src, dst)
                print("DONE", dst, f"{time.time()-t0:.0f}s wait", flush=True)
                sys.exit(0)
    time.sleep(10)
print("TIMED OUT waiting for the queue")
