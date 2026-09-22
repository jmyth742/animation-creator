"""
STYLISE — a deterministic post pass in the Spider-Verse / Arcane direction.

Our measured defect is information density: the cast carry roughly half the
high-frequency detail of the painted plates, which is why they read as pasted on. Clean
anime cel makes that worse, because it is a style of large flat areas. Comic and
painterly styles fix it from the other side: halftone, hatching and brushwork ADD
structure to the flat regions, and they hide mesh imperfection rather than exposing it.

Everything here is a fixed function of the frame, so it is deterministic and
frame-stable — no diffusion, no flicker. Applied to the CAST only where a matte is
supplied, so the painted backgrounds keep their own handwriting.

  python stylise.py <in.png> <out.png> [style] [matte.png]
Styles: halftone, hatch, comic (halftone+hatch+ink+chromatic), paint (Arcane-ish)
Env: ST_DOT (4.0), ST_HATCH (0.45), ST_CHROMA (1.2), ST_INK (0.55), ST_STRENGTH (1.0)
"""
import sys, os
import numpy as np
from PIL import Image, ImageFilter

src, dst = sys.argv[1], sys.argv[2]
style = sys.argv[3] if len(sys.argv) > 3 else "comic"
matte_p = sys.argv[4] if len(sys.argv) > 4 else None

DOT = float(os.environ.get("ST_DOT", "4.0"))
HATCH = float(os.environ.get("ST_HATCH", "0.45"))
CHROMA = float(os.environ.get("ST_CHROMA", "1.2"))
INK = float(os.environ.get("ST_INK", "0.55"))
K = float(os.environ.get("ST_STRENGTH", "1.0"))

im = Image.open(src).convert("RGB")
a = np.asarray(im, dtype=np.float32) / 255.0
h, w, _ = a.shape
lum = a @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

if matte_p and os.path.exists(matte_p):
    m = np.asarray(Image.open(matte_p).convert("L").resize((w, h)), dtype=np.float32) / 255.0
else:
    m = np.ones((h, w), dtype=np.float32)
m = (m * K)[..., None]

yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
out = a.copy()

if style in ("halftone", "comic"):
    # Ben-Day dots: a rotated dot grid whose coverage tracks luminance, so shadow reads as
    # dense dots and light as sparse. This is the single biggest density gain available.
    th = np.radians(15.0)
    u = (xx * np.cos(th) - yy * np.sin(th)) / DOT
    v = (xx * np.sin(th) + yy * np.cos(th)) / DOT
    cell = np.sqrt((u - np.floor(u) - 0.5) ** 2 + (v - np.floor(v) - 0.5) ** 2) * 2.0
    radius = np.clip(1.15 - lum, 0.0, 1.0)
    dots = np.clip((cell - radius) * 3.0 + 0.5, 0.0, 1.0)           # 0 inside dot
    shade = 0.55 + 0.45 * dots
    out = out * shade[..., None]

if style in ("hatch", "comic"):
    # cross-hatching that only appears in the darker half, as an inker would lay it
    h1 = np.sin((xx + yy) * (np.pi / 3.0))
    h2 = np.sin((xx - yy) * (np.pi / 3.0))
    dark = np.clip((0.55 - lum) * 2.2, 0.0, 1.0)
    hatch = np.clip(1.0 - HATCH * dark * (np.clip(h1, 0, 1) + np.clip(h2, 0, 1) * (dark > 0.55)), 0.0, 1.0)
    out = out * hatch[..., None]

if style in ("paint", "paint2"):
    # Arcane-ish. Quantise into painted value steps, then push the detail that quantising
    # removed back in, so flat areas gain brush-like structure instead of dead colour.
    # ST_LEVELS is deliberately generous: too few steps and MOVING footage flickers as
    # pixels cross a threshold, which is the classic failure of posterised video.
    lv = float(os.environ.get("ST_LEVELS", "12"))
    gain = float(os.environ.get("ST_DETAIL", "1.7"))
    sat = float(os.environ.get("ST_SAT", "1.12"))
    q = np.clip(np.round(out * lv) / lv, 0, 1)
    soft = np.asarray(Image.fromarray((q * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(1.2)), dtype=np.float32) / 255.0
    out = np.clip(soft + (out - soft) * gain, 0, 1)
    if sat != 1.0:
        g = (out @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))[..., None]
        out = np.clip(g + (out - g) * sat, 0, 1)

if style == "comic":
    gx = np.abs(np.gradient(lum, axis=1))
    gy = np.abs(np.gradient(lum, axis=0))
    edge = np.clip((gx + gy) * 6.0, 0, 1)
    out = out * (1.0 - INK * edge)[..., None]
    if CHROMA > 0:                       # print misregistration
        sh = int(max(1, round(CHROMA)))
        out[:, sh:, 0] = out[:, :-sh, 0]
        out[:, :-sh, 2] = out[:, sh:, 2]

out = np.clip(a * (1 - m) + out * m, 0, 1)
Image.fromarray((out * 255).astype(np.uint8)).save(dst)
print("STYLISED", style, "->", dst)
