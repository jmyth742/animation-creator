"""
TEXTURE with Hunyuan3D's own paint pipeline — the correct tool for this job.

Projecting the source drawings back onto the mesh cannot fully work, because the
reconstruction INTERPRETS the drawing rather than copying it: the drawing's arms are at
one angle and the mesh's at another, so pixels land on the wrong surface and the limbs
come out black. Measured on the cel sheet, the figure is centred and the arm span sits
21% down the figure, but the mesh's arms are elsewhere.

The paint pipeline conditions on the MESH GEOMETRY as well as the reference image, so the
correspondence is solved rather than guessed. It delights the reference, renders the mesh
from several viewpoints, generates consistent multi-view colour and bakes an atlas.

  python texture_hy3d.py <mesh.glb> <reference.png> <out.glb>
"""
import sys, os, time
import torch
from PIL import Image

mesh_p, ref_p, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
MODELS = "/workspace/training_models/hunyuan3d-2"

from hy3dgen.texgen import Hunyuan3DPaintPipeline
from hy3dgen.rembg import BackgroundRemover

t0 = time.time()
img = Image.open(ref_p).convert("RGB")
if img.mode == "RGB":
    img = BackgroundRemover()(img)          # the plate must not become part of the skin
print("TEXHY reference ready", img.size, flush=True)

pipe = Hunyuan3DPaintPipeline.from_pretrained(MODELS)
print("TEXHY pipeline loaded in %.0fs" % (time.time() - t0), flush=True)

import trimesh
mesh = trimesh.load(mesh_p, force="mesh")
print("TEXHY mesh faces in:", len(mesh.faces), flush=True)

# DECIMATE FIRST. The pipeline's first act is mesh_uv_wrap, a single-threaded unwrap whose
# cost explodes with face count: at 544k faces it pinned one core with the GPU idle and no
# output for ten minutes. These meshes are 10-20x denser than the pipeline expects, and
# they have to come down for rigging anyway, so reduce before texturing rather than after.
BUDGET = int(os.environ.get("TEXHY_FACES", "40000"))
if len(mesh.faces) > BUDGET:
    # trimesh versions disagree here: some take a face count, some a 0-1 reduction ratio
    _n = len(mesh.faces)
    try:
        mesh = mesh.simplify_quadric_decimation(face_count=BUDGET)
    except TypeError:
        mesh = mesh.simplify_quadric_decimation(max(0.01, min(0.99, 1.0 - BUDGET / float(_n))))
    print("TEXHY decimated to:", len(mesh.faces), "in %.0fs" % (time.time() - t0), flush=True)

# the pipeline prints nothing between its stages, so wrap the slow ones to stop us
# flying blind again
import hy3dgen.texgen.pipelines as _pl
_orig_wrap = getattr(_pl, "mesh_uv_wrap", None)
if _orig_wrap:
    def _wrapped(m):
        t = time.time(); print("TEXHY stage: uv_wrap ...", flush=True)
        r = _orig_wrap(m); print("TEXHY stage: uv_wrap done in %.0fs" % (time.time() - t), flush=True)
        return r
    _pl.mesh_uv_wrap = _wrapped

print("TEXHY painting ...", flush=True)
painted = pipe(mesh, image=img)
painted.export(out_p)
print("TEXHY_DONE", out_p, "in %.0fs" % (time.time() - t0), flush=True)
