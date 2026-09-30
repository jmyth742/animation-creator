"""
A HEIGHTFIELD FOR THE PAINTED GROUND, from the plate itself.

The painted world's floor is a flat plane; the plate paints a path climbing to the hall,
banks, the lake basin. Characters walking on the flat plane therefore float over the
painted rises and sink into the painted dips, and nothing in the ground ever occludes
them. Monocular depth on the plate gives relative depth per pixel; with the painter camera
known, that becomes a height for every ground point the camera sees.

  python plate_heightfield.py <plate.png> <out_prefix>
Writes <out>_depth.png (visual), <out>_depth.npy (relative depth, 0 near .. 1 far).
The Blender side (valley_set) turns it into floor displacement.
"""
import sys, numpy as np, torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
src, outp = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGB")
name = "depth-anything/Depth-Anything-V2-Small-hf"
proc = AutoImageProcessor.from_pretrained(name); model = AutoModelForDepthEstimation.from_pretrained(name).to("cuda").eval()
with torch.no_grad():
    inp = proc(images=im, return_tensors="pt").to("cuda")
    d = model(**inp).predicted_depth[0]
    d = torch.nn.functional.interpolate(d[None, None], size=(im.height, im.width), mode="bicubic", align_corners=False)[0, 0].cpu().numpy()
# Depth-Anything predicts inverse depth (bigger = nearer). Normalise to 0 near .. 1 far.
inv = (d - d.min()) / max(1e-6, d.max() - d.min())
far = 1.0 - inv
np.save(outp + "_depth.npy", far.astype(np.float32))
Image.fromarray((inv * 255).astype(np.uint8)).save(outp + "_depth.png")
print("HF_DONE", outp + "_depth.npy", far.shape, "near/far", float(far.min()), float(far.max()))
