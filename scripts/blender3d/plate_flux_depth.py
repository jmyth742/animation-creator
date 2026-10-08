"""
PLATE FROM GEOMETRY, FLUX ROUTE. Same idea as plate_from_geometry.py (paint the plate so it
obeys the set's real depth) but with FLUX.1-dev + ControlNet-Union-Pro depth through ComfyUI,
because the plates ARE FLUX images: SDXL could match the geometry (r 0.84) or the look (CLIP
0.93) but never both, and every SDXL plate that improved geometry failed the style gate.

  python plate_flux_depth.py <out_prefix> <denoise ...>      env PF_CN (0.7), PF_SEED (6100), PF_STEPS (24)
Inputs are staged in ComfyUI/input as geo_plate_old.png and geo_depth.png (1344x768).
Writes <out_prefix>_d<NN>.png and <out_prefix>_agree.json (agreement + CLIP style per plate).
"""
import json, os, sys, time, shutil, urllib.request
os.environ.setdefault("HF_HOME", "/workspace/hf_cache")
import numpy as np, torch
from PIL import Image
COMFY = "/workspace/text-to-video/ComfyUI"
out = sys.argv[1]; dens = [float(d) for d in sys.argv[2:]] or [0.6, 0.75, 0.9]
CN = float(os.environ.get("PF_CN", "0.7")); SEED = int(os.environ.get("PF_SEED", "6100")); STEPS = int(os.environ.get("PF_STEPS", "24"))
W, H = int(os.environ.get("PF_W", "1344")), int(os.environ.get("PF_H", "768"))     # hires pass: 2016x1152
# PF_INIT_PATH: an absolute image to use as the init (staged into ComfyUI/input at W x H)
if os.environ.get("PF_INIT_PATH"):
    _n = "geo_init_" + os.path.basename(out) + ".png"
    Image.open(os.environ["PF_INIT_PATH"]).convert("RGB").resize((W, H), Image.LANCZOS).save(os.path.join(COMFY, "input", _n))
    os.environ["PF_INIT_COMFY"] = _n
if os.environ.get("PF_GUIDE") and (W, H) != (1344, 768):
    _g = "geo_guide_" + os.path.basename(out) + ".png"
    Image.open(os.environ["PF_GUIDE"]).convert("RGB").resize((W, H), Image.LANCZOS).save(os.path.join(COMFY, "input", _g))
    os.environ["PF_GUIDE_COMFY"] = _g
PROMPT = os.environ.get("PG_PROMPT",
    "anime background art, painted cel background, lush green valley of Tir na nOg, a golden stone hall "
    "with round celtic emblems and battlements standing on a grassy rise, a tall standing celtic stone cross "
    "beside a still lake, a high waterfall pouring from green cliffs, a winding earthen footpath through a "
    "wildflower meadow, distant mountains, soft summer daylight, clean flat colours, masterpiece, best quality")

def wf(den, seed, prefix):
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "flux1-dev-Q8_0.gguf"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "clip_l.safetensors", "clip_name2": "t5xxl_fp8_e4m3fn.safetensors", "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": PROMPT}},
        "4n": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
        "4g": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": 3.5}},
        "20": {"class_type": "LoadImage", "inputs": {"image": os.environ.get("PF_INIT_COMFY", "geo_plate_old.png")}},
        "21": {"class_type": "LoadImage", "inputs": {"image": os.environ.get("PF_GUIDE_COMFY", "geo_depth2.png")}},
        "22": {"class_type": "VAEEncode", "inputs": {"pixels": ["20", 0], "vae": ["3", 0]}},
        "23": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "flux_union_pro2.safetensors"}},
        "24": {"class_type": "SetUnionControlNetType", "inputs": {"control_net": ["23", 0], "type": "depth"}},
        "25": {"class_type": "ControlNetApplyAdvanced", "inputs": {"positive": ["4g", 0], "negative": ["4n", 0], "control_net": ["24", 0], "image": ["21", 0],
                                                                    "strength": CN, "start_percent": 0.0, "end_percent": float(os.environ.get("PF_END", "0.6")), "vae": ["3", 0]}},
        "6": {"class_type": "ModelSamplingFlux", "inputs": {"model": ["1", 0], "max_shift": 1.15, "base_shift": 0.5, "width": W, "height": H}},
        "7": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "8": {"class_type": "BasicGuider", "inputs": {"model": ["6", 0], "conditioning": ["25", 0]}},
        "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "10": {"class_type": "BasicScheduler", "inputs": {"model": ["6", 0], "scheduler": "simple", "steps": STEPS, "denoise": den}},
        "11": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["7", 0], "guider": ["8", 0], "sampler": ["9", 0], "sigmas": ["10", 0], "latent_image": ["22", 0]}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "13": {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": prefix}},
    }

def run(w):
    req = urllib.request.Request("http://127.0.0.1:8188/prompt", json.dumps({"prompt": w}).encode(), {"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=30).read())
    if "prompt_id" not in r: sys.exit("PF comfy rejected: %s" % json.dumps(r)[:400])
    pid = r["prompt_id"]; t0 = time.time()
    while time.time() - t0 < 1800:
        h = json.loads(urllib.request.urlopen("http://127.0.0.1:8188/history/%s" % pid, timeout=10).read())
        if pid in h:
            if h[pid].get("status", {}).get("status_str") == "error": sys.exit("PF comfy error: %s" % json.dumps(h[pid]["status"])[:600])
            for node in h[pid].get("outputs", {}).values():
                for im in node.get("images", []): return os.path.join(COMFY, "output", im.get("subfolder", ""), im["filename"])
        time.sleep(3)
    sys.exit("PF timeout")

outs = []
for den in dens:
    t0 = time.time(); p = run(wf(den, SEED, "geo/pf_%s_%d_%02d" % (os.path.basename(out), SEED, int(den * 100))))
    dst = "%s_d%02d.png" % (out, int(den * 100)); shutil.copy(p, dst); outs.append((den, dst, Image.open(dst).convert("RGB")))
    print("PF plate denoise %.2f -> %s (%.0fs)" % (den, dst, time.time() - t0), flush=True)

# scoring: geometry agreement (Depth-Anything vs the guide) and CLIP style vs the original plate
from transformers import pipeline as hfp, CLIPModel, CLIPProcessor
guide = Image.open(os.environ.get("PF_GUIDE", "/workspace/loopwork/geo/valley2_depth.png")).convert("L").resize((W, H), Image.LANCZOS)
old = Image.open(COMFY + "/input/" + os.environ.get("PF_INIT_COMFY", "geo_plate_old.png")).convert("RGB")
style_ref = Image.open(os.environ.get("PF_STYLE_REF", COMFY + "/input/geo_plate_old.png")).convert("RGB").resize((W, H), Image.LANCZOS)
dp = hfp("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf", device=0)
gd = np.asarray(guide, dtype=np.float32) / 255.0
def agree(im):
    d = np.asarray(dp(im)["depth"].resize((W, H)), dtype=np.float32); d = (d - d.min()) / (np.ptp(d) + 1e-6)
    m = gd > 0.02; m[: int(H * 0.45)] = False           # ground band: below the horizon, where the cast walks
    return float(np.corrcoef(d[m], gd[m])[0, 1])
cm = CLIPModel.from_pretrained("openai/clip-vit-base-patch32", use_safetensors=True); cp = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
def cemb(im):
    with torch.no_grad(): e = cm.get_image_features(**cp(images=im, return_tensors="pt"))
    e = e if torch.is_tensor(e) else e.pooler_output
    return torch.nn.functional.normalize(e, dim=-1)
oe = cemb(style_ref)      # style is judged against the adopted master plate, not the init image
def style(im): return float((cemb(im) @ oe.T).item())
old_r = agree(old); print("PF agreement old plate r=%.3f" % old_r, flush=True)
def sharp(im):
    g = np.asarray(im.convert("L"), dtype=np.float32)
    lap = g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(lap.var())
res = {"old": old_r, "plates": {}, "style": {}, "sharp": {}, "old_sharp": sharp(old), "cn": CN, "seed": SEED, "size": [W, H]}
for den, dst, im in outs:
    res["plates"][dst] = agree(im); res["style"][dst] = style(im); res["sharp"][dst] = sharp(im)
    print("PF agreement denoise %.2f r=%.3f  CLIP style %.3f" % (den, res["plates"][dst], res["style"][dst]), flush=True)
json.dump(res, open(out + "_agree.json", "w"), indent=1); print("PF_DONE", out + "_agree.json", flush=True)
