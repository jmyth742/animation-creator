"""Plate -> depth map. CPU-only on purpose: never contend with a render."""
import sys
import numpy as np
from PIL import Image
from transformers import pipeline

src, dst = sys.argv[1], sys.argv[2]
pipe = pipeline("depth-estimation",
                model="depth-anything/Depth-Anything-V2-Small-hf", device=-1)
out = pipe(Image.open(src).convert("RGB"))
d = np.array(out["depth"], dtype=np.float32)
d = (d - d.min()) / (d.max() - d.min())          # 0=far 1=near (DA convention)
Image.fromarray((d * 65535).astype(np.uint16)).save(dst)
print("depth saved", dst, d.shape)
