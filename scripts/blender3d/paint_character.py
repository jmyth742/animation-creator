"""Hunyuan3D-Paint: give the generated mesh a real all-around texture."""
import sys
import time
import trimesh
from PIL import Image
from hy3dgen.rembg import BackgroundRemover
from hy3dgen.texgen import Hunyuan3DPaintPipeline

mesh_in, image_in, mesh_out = sys.argv[1:4]
t0 = time.time()
mesh = trimesh.load(mesh_in, force="mesh")
# paint works best on a lighter mesh; decimate towards ~40k faces
if len(mesh.faces) > 60000:
    mesh = mesh.simplify_quadric_decimation(1 - 40000 / len(mesh.faces))
    print("decimated to", len(mesh.faces), "faces", flush=True)
img = BackgroundRemover()(Image.open(image_in).convert("RGB"))
pipe = Hunyuan3DPaintPipeline.from_pretrained("/workspace/training_models/hunyuan3d-2")
mesh = pipe(mesh, image=img)
mesh.export(mesh_out)
print(f"PAINT DONE {mesh_out} in {time.time()-t0:.0f}s")
