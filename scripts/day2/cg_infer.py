"""
CharacterGen headless: one character sheet -> 4 calibrated views -> GLB.
Mirrors the repo's webui.py wiring exactly (view order [v1, v3, v0, v2] into
the 3D stage, back-projection on). Run inside the charactergen venv:
    python cg_infer.py <sheet.png> <outdir>
Writes <outdir>/view{0..3}.png, views.png (strip), output.glb, output.obj.
"""
import os, sys, shutil
os.environ.setdefault("HF_HOME", "/workspace/hf_cache")
src, out = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
os.chdir("/workspace/CharacterGen")
sys.path += [".", "2D_Stage", "3D_Stage"]
import numpy as np
from PIL import Image
from omegaconf import OmegaConf
import webui as W

os.makedirs(out, exist_ok=True)
def as_pil(v):
    return v if isinstance(v, Image.Image) else Image.fromarray(np.asarray(v))

api2d = W.Inference2D_API(**OmegaConf.load("2D_Stage/configs/infer.yaml"))
rm = W.rm_bg_api()
img = Image.open(src).convert("RGBA")
img = rm.remove_background(imgs=[np.array(img)], alpha_min=0.1, alpha_max=0.9)[0]
as_pil(img).save(f"{out}/input_nobg.png")
views = rm.remove_background(imgs=api2d.inference(img, 512, 768, crop=True, seed=2333, timestep=40),
                             alpha_min=0.2, alpha_max=0.9)
views = [as_pil(v).convert("RGBA") for v in views]
for i, v in enumerate(views):
    v.save(f"{out}/view{i}.png")
strip = Image.new("RGBA", (sum(v.width for v in views), max(v.height for v in views)), (200, 200, 200, 255))
x = 0
for v in views:
    strip.paste(v, (x, 0), v); x += v.width
strip.convert("RGB").save(f"{out}/views.png")
print("CG 2D DONE", [v.size for v in views])

api3d = W.Inference3D_API()
save_dir, obj, glb = api3d.process_images(views[1], views[3], views[0], views[2], True, 2)
shutil.copy(glb, f"{out}/output.glb"); shutil.copy(obj, f"{out}/output.obj")
print("CG 3D DONE", f"{out}/output.glb", os.path.getsize(f"{out}/output.glb"))
