"""
Character generated FROM AN IMAGE: FLUX portrait -> Hunyuan3D-2 mesh.

Shape only in this pass — texture painting is a second, heavier stage.
The mesh is the thing rigging needs; appearance can come later from paint
or from projected portrait texture.
"""
import sys
import time
import torch
from PIL import Image
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
from hy3dgen.rembg import BackgroundRemover

src, dst = sys.argv[1], sys.argv[2]

t0 = time.time()
img = Image.open(src).convert("RGBA")
img = BackgroundRemover()(img.convert("RGB"))
pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    "/workspace/training_models/hunyuan3d-2",
    subfolder="hunyuan3d-dit-v2-0", use_safetensors=True)
mesh = pipe(image=img, num_inference_steps=30,
            generator=torch.manual_seed(6100))[0]
mesh.export(dst)
print(f"MESH DONE {dst} verts={len(mesh.vertices)} faces={len(mesh.faces)} "
      f"in {time.time()-t0:.0f}s")
