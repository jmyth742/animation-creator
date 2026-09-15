"""
Texture discipline: turn a patchy multi-view-fused character texture into
clean flat cel colour. The 'papier-mache' look comes from hundreds of
slightly-different fused patches; real cel characters wear a handful of
flat fills. This clusters the texture into N dominant colours, snaps every
pixel to its cluster's colour, then lightly feathers the boundaries.

Run: python flatten_texture.py <in.png> <out.png> [n_colors=14] [smooth=2]
"""
import sys

import numpy as np
from PIL import Image, ImageFilter

src, dst = sys.argv[1], sys.argv[2]
K = int(sys.argv[3]) if len(sys.argv) > 3 else 14
SM = int(sys.argv[4]) if len(sys.argv) > 4 else 2

im = Image.open(src).convert("RGBA")
# pre-smooth so cluster assignment ignores patch noise
base = im.convert("RGB").filter(ImageFilter.MedianFilter(5))
a = np.asarray(base, dtype=np.float32).reshape(-1, 3)

# k-means (numpy, deterministic seed)
rng = np.random.default_rng(6100)
idx = rng.choice(len(a), size=min(20000, len(a)), replace=False)
sample = a[idx]
centers = sample[rng.choice(len(sample), K, replace=False)]
for _ in range(12):
    d = ((sample[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
    lab = d.argmin(1)
    for k in range(K):
        pts = sample[lab == k]
        if len(pts):
            centers[k] = pts.mean(0)
# assign full image in chunks
out = np.empty_like(a)
for i in range(0, len(a), 200000):
    chunk = a[i:i + 200000]
    d = ((chunk[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
    out[i:i + 200000] = centers[d.argmin(1)]
W, H = im.size
flat = Image.fromarray(out.reshape(H, W, 3).astype(np.uint8))
# feather the fills slightly so boundaries aren't aliased stairsteps
flat = flat.filter(ImageFilter.GaussianBlur(SM))
flat = Image.composite(flat, im.convert("RGB"), Image.new("L", im.size, 255))
res = flat.convert("RGBA")
res.putalpha(im.getchannel("A"))
res.save(dst)
print(f"FLATTENED {dst} to {K} colours")
