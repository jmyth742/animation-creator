"""
PLATE FROM GEOMETRY -- paint the set plate so that it OBEYS the set's real geometry.

Input: the depth guide rendered from the set geometry (set_depth_guide.py) and the current
plate for palette/subject continuity. SDXL (anime checkpoint) img2img from the old plate,
conditioned on the geometry depth with ControlNet-depth, so the path, lake, steps, rise and
hall in the painting sit exactly where the 3D set has them. The result is then checked by
running Depth-Anything over it and correlating with the guide: the number that says whether
the painting agrees with the geometry.

  python plate_from_geometry.py <depth_guide.png> <old_plate.png> <out_prefix> [strength ...]
Env: PG_PROMPT, PG_CN (controlnet scale, 0.8), PG_STEPS (30), PG_SEED (6100)
"""
import os, sys, time
os.environ.setdefault("HF_HOME", "/workspace/hf_cache")
import numpy as np, torch
from PIL import Image
from diffusers import StableDiffusionXLControlNetImg2ImgPipeline, ControlNetModel, AutoencoderKL

guide_p, old_p, out = sys.argv[1], sys.argv[2], sys.argv[3]
strengths = [float(s) for s in sys.argv[4:]] or [0.55, 0.75]
W, H = 1344, 768                     # SDXL's native megapixel at ~16:9; upscaled after
PROMPT = os.environ.get("PG_PROMPT",
    "anime background art, painted cel background, lush green valley of Tir na nOg, a golden stone hall "
    "with round celtic emblems and battlements standing on a grassy rise, a tall standing celtic stone cross "
    "beside a still lake, a high waterfall pouring from green cliffs, a winding earthen footpath through a "
    "wildflower meadow, distant mountains, soft summer daylight, clean flat colours, masterpiece, best quality")
NEG = "people, characters, figures, text, watermark, signature, photo, photorealistic, 3d render, blurry, lowres, noise"
CN = float(os.environ.get("PG_CN", "0.8")); STEPS = int(os.environ.get("PG_STEPS", "30")); SEED = int(os.environ.get("PG_SEED", "6100"))

guide = Image.open(guide_p).convert("RGB").resize((W, H), Image.LANCZOS)
old = Image.open(old_p).convert("RGB").resize((W, H), Image.LANCZOS)
t0 = time.time()
cn = ControlNetModel.from_pretrained("diffusers/controlnet-depth-sdxl-1.0-small", torch_dtype=torch.float16)
pipe = StableDiffusionXLControlNetImg2ImgPipeline.from_pretrained(
    "cagliostrolab/animagine-xl-3.1", controlnet=cn, torch_dtype=torch.float16, variant=None)
pipe.to("cuda"); pipe.enable_vae_tiling()
print("PG models loaded %.0fs" % (time.time() - t0), flush=True)
outs = []
for s in strengths:
    g = torch.Generator("cuda").manual_seed(SEED)
    im = pipe(prompt=PROMPT, negative_prompt=NEG, image=old, control_image=guide, strength=s,
              controlnet_conditioning_scale=CN, num_inference_steps=STEPS, guidance_scale=6.0,
              generator=g, width=W, height=H).images[0]
    p = "%s_s%02d.png" % (out, int(s * 100)); im.save(p); outs.append((s, p, im))
    print("PG plate strength %.2f -> %s (%.0fs)" % (s, p, time.time() - t0), flush=True)
del pipe, cn; torch.cuda.empty_cache()

# agreement with the geometry: Depth-Anything over each plate vs the guide (Pearson on inverse depth)
from transformers import pipeline as hfp
dp = hfp("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf", device=0)
gd = np.asarray(guide.convert("L"), dtype=np.float32) / 255.0
def agree(im):
    d = np.asarray(dp(im)["depth"].resize((W, H)), dtype=np.float32); d = (d - d.min()) / (np.ptp(d) + 1e-6)
    m = gd > 0.02                     # ignore sky
    return float(np.corrcoef(d[m], gd[m])[0, 1])
rows = [("old plate", old, agree(old))] + [("strength %.2f" % s, im, agree(im)) for s, p, im in outs]
for n, _, a in rows: print("PG agreement %-14s r=%.3f" % (n, a), flush=True)
import json
json.dump({"old": rows[0][2], "plates": {p: a for (s, p, im), (_, _, a) in zip(outs, rows[1:])}, "cn": CN, "seed": SEED},
          open(out + "_agree.json", "w"), indent=1)
# contact sheet: guide | old | new...
tiles = [guide] + [im for _, im, _ in rows]
sw, sh = 560, 320
sheet = Image.new("RGB", (sw * len(tiles), sh + 22), "white")
from PIL import ImageDraw
dr = ImageDraw.Draw(sheet)
labels = ["geometry depth"] + ["%s  r=%.2f" % (n, a) for n, _, a in rows]
for i, (t, l) in enumerate(zip(tiles, labels)):
    sheet.paste(t.resize((sw, sh), Image.LANCZOS), (i * sw, 22)); dr.text((i * sw + 6, 4), l, fill="black")
sheet.save(out + "_sheet.png"); print("PG_DONE", out + "_sheet.png", flush=True)
