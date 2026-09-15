"""TRELLIS.2 image -> GLB (+ turntable mp4), headless. Run inside the trellis2 venv
from the TRELLIS.2 checkout:  python trellis_infer.py <image.png> <out.glb> [decimation]
"""
import os, sys
os.environ.setdefault("HF_HOME", "/workspace/hf_cache")
os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
import cv2, imageio, torch
from PIL import Image
from trellis2.pipelines import Trellis2ImageTo3DPipeline
from trellis2.utils import render_utils
from trellis2.renderers import EnvMap
import o_voxel

src, out = sys.argv[1], sys.argv[2]
dec = int(sys.argv[3]) if len(sys.argv) > 3 else 200000
envmap = EnvMap(torch.tensor(cv2.cvtColor(cv2.imread('assets/hdri/forest.exr', cv2.IMREAD_UNCHANGED),
                                          cv2.COLOR_BGR2RGB), dtype=torch.float32, device='cuda'))
pipeline = Trellis2ImageTo3DPipeline.from_pretrained("microsoft/TRELLIS.2-4B")
pipeline.cuda()
image = Image.open(src)
mesh = pipeline.run(image)[0]
mesh.simplify(16777216)
try:
    video = render_utils.make_pbr_vis_frames(render_utils.render_video(mesh, envmap=envmap))
    imageio.mimsave(out.replace(".glb", "_turn.mp4"), video, fps=15)
except Exception as e:  # the GLB is the deliverable; the preview is optional
    print("preview render skipped:", e)
glb = o_voxel.postprocess.to_glb(vertices=mesh.vertices, faces=mesh.faces, attr_volume=mesh.attrs,
                                 coords=mesh.coords, attr_layout=mesh.layout, voxel_size=mesh.voxel_size,
                                 aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]], decimation_target=dec,
                                 texture_size=2048, remesh=True, remesh_band=1, remesh_project=0, verbose=True)
glb.export(out, extension_webp=False)
print("TRELLIS DONE", out, os.path.getsize(out))
