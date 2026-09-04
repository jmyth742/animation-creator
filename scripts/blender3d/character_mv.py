"""True multi-view character mesh: front + left + back sheets -> 2mv model."""
import sys
import time
import torch
from PIL import Image
from hy3dgen.rembg import BackgroundRemover
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

front, left, back, out = sys.argv[1:5]
t0 = time.time()
rb = BackgroundRemover()
views = {k: rb(Image.open(p).convert("RGB"))
         for k, p in (("front", front), ("left", left), ("back", back))}
pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    "/workspace/training_models/hunyuan3d-2mv",
    subfolder="hunyuan3d-dit-v2-mv", use_safetensors=True)
mesh = pipe(image=views, num_inference_steps=40,
            generator=torch.manual_seed(6100))[0]
mesh.export(out)
print(f"MV MESH DONE {out} verts={len(mesh.vertices)} in {time.time()-t0:.0f}s")
