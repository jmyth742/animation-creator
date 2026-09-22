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
print("TEXHY mesh faces", len(mesh.faces), flush=True)

painted = pipe(mesh, image=img)
painted.export(out_p)
print("TEXHY_DONE", out_p, "in %.0fs" % (time.time() - t0), flush=True)
