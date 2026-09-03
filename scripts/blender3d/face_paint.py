"""
Texture-space faces: draw crisp eyes and viseme mouths INTO the painted
texture, through the mesh's own UV triangles. No cards, no plate edges —
the face is simply part of the surface and lights like it.

Emits: <name>_face_base.png (redrawn eyes, closed mouth)
       <name>_face_m{1..5}.png (mouth visemes over the base)
       <name>_face_blink.png (lids closed)

Run: blender -b --factory-startup --python face_paint.py -- \
       <painted.glb> <face_calib.json> <height> <outdir> <name> <iris_r,g,b>
"""
import json
import sys
import bpy
import numpy as np
import mathutils

glb, calib_f, height, outdir, name, iris_s = sys.argv[-6:]
height = float(height)
IRIS = tuple(float(c) for c in iris_s.split(","))
calib = json.load(open(calib_f))

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import character_kit as kit                                    # noqa: E402

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
char = kit.load_character(glb, name, height=height)
anchors = kit.probe_face(char)
n = len(char.data.vertices)
co = np.empty(n * 3)
char.data.vertices.foreach_get("co", co)
P = co.reshape(-1, 3)

def front_y(z, hw=0.026, dz=0.012):
    band = P[(np.abs(P[:, 0]) < hw) & (np.abs(P[:, 2] - z) < dz)]
    return float(band[:, 1].min()) if len(band) else -0.1

MZ, EZ, EX = calib["mouth_z"], calib["eye_z"], calib["eye_x"]
FX = calib.get("face_x", 0.0)      # the mesh's face midline vs x=0
MOUTH = np.array((FX, front_y(MZ), MZ))
EYE_L = np.array((FX + EX, front_y(EZ, hw=0.06), EZ))
EYE_R = np.array((FX - EX, front_y(EZ, hw=0.06), EZ))

img = None
for m in char.data.materials:
    for nd in m.node_tree.nodes:
        if nd.type == 'TEX_IMAGE' and nd.image:
            img = nd.image
W, H = img.size
base = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)

uvl = char.data.uv_layers[0]
loops_uv = np.empty(len(char.data.loops) * 2)
uvl.data.foreach_get("uv", loops_uv)
loops_uv = loops_uv.reshape(-1, 2)
loop_vi = np.empty(len(char.data.loops), dtype=np.int64)
char.data.loops.foreach_get("vertex_index", loop_vi)
tris = []
char.data.calc_loop_triangles()
for lt in char.data.loop_triangles:
    tris.append(tuple(lt.loops))
tris = np.array(tris)


def paint(dst, anchor, radius, draw_fn):
    """Rasterise draw_fn(h, v) -> (rgba or None) into dst near anchor.
    h = metres right of anchor on the face, v = metres above."""
    vids = loop_vi[tris]
    centers = P[vids].mean(axis=1)
    near = np.where(np.linalg.norm(centers - anchor, axis=1) < radius)[0]
    for ti in near:
        l0, l1, l2 = tris[ti]
        uv = np.array([loops_uv[l0], loops_uv[l1], loops_uv[l2]])
        p3 = P[loop_vi[[l0, l1, l2]]]
        px = uv * (W, H)
        x0, y0 = np.floor(px.min(axis=0)).astype(int)
        x1, y1 = np.ceil(px.max(axis=0)).astype(int)
        if x1 - x0 > W // 3 or y1 - y0 > H // 3:
            continue                     # degenerate island jump
        for yy in range(max(0, y0), min(H, y1 + 1)):
            for xx in range(max(0, x0), min(W, x1 + 1)):
                q = np.array((xx + 0.5, yy + 0.5))
                d = px[1:] - px[0]
                den = d[0, 0] * d[1, 1] - d[1, 0] * d[0, 1]
                if abs(den) < 1e-9:
                    continue
                r = q - px[0]
                w1 = (r[0] * d[1, 1] - r[1] * d[1, 0]) / den
                w2 = (r[1] * d[0, 0] - r[0] * d[0, 1]) / den
                w0 = 1 - w1 - w2
                if min(w0, w1, w2) < -0.02:
                    continue
                p = w0 * p3[0] + w1 * p3[1] + w2 * p3[2]
                col = draw_fn(p[0] - anchor[0], p[2] - anchor[2])
                if col is not None:
                    a = col[3]
                    dst[yy, xx, :3] = (1 - a) * dst[yy, xx, :3] + a * np.array(col[:3])


def soft(d, edge=0.0012):
    return float(np.clip(1 - d / edge, 0, 1))


SK = None  # sampled around the mouth for lids

def eye_plate(h, v):
    """Erase the original smudged eye before drawing the new one."""
    d = math.hypot(h / (1.35 * EX), v / (0.85 * EX))
    if d <= 1.0:
        return (SK[0], SK[1], SK[2], min(1.0, 1.6 - d * 0.8))
    return None


def eye_draw(h, v):
    """Calm anime construction: a wide almond aperture, the iris filling
    most of its height, the upper lid cutting the iris flat. Big-sclera
    small-iris circles read as startled ("googly") — measured on film."""
    sw, sh = 0.58 * EX, 0.335 * EX
    d = math.hypot(h / sw, v / sh)
    lid_v = 0.42 * sh                  # the flat upper lid line
    lash_t = 0.16 * EX
    if d <= 1.0 and v <= lid_v:
        ir = math.hypot(h, (v + 0.04 * EX) * 1.05)
        hl = math.hypot(h - 0.10 * EX, v - 0.06 * EX)
        if hl < 0.045 * EX:
            return (0.98, 0.98, 0.97, 1)
        if ir < 0.135 * EX:
            return (0.05, 0.04, 0.04, 1)
        if ir < 0.285 * EX:
            f = ir / (0.285 * EX)
            top_shade = 0.75 if v > lid_v - 0.10 * EX else 1.0
            return (IRIS[0] * (1.1 - 0.55 * f) * top_shade,
                    IRIS[1] * (1.1 - 0.55 * f) * top_shade,
                    IRIS[2] * (1.1 - 0.55 * f) * top_shade, 1)
        sc = 0.955
        return (sc, sc, sc * 0.99, soft((d - 0.97) * sh, 0.06 * sh)
                if d > 0.97 else 1)
    # the upper lid + lash: a soft dark band along the top of the aperture
    if d <= 1.12 and lid_v < v < lid_v + lash_t:
        a = soft(abs(v - lid_v - lash_t * 0.35), lash_t * 0.5)
        return (0.10, 0.07, 0.07, a)
    # lower lash hint at the outer third
    if 0.95 < d < 1.10 and v < 0 and abs(h) > 0.30 * EX:
        return (0.35, 0.28, 0.26, 0.5)
    return None


import math
math_hypot = math.hypot


def lid_draw(h, v):
    sw, sh = 0.74 * EX, 0.54 * EX
    d = math.hypot(h / sw, v / sh)
    if d <= 1.05:
        f = min(1.0, 1.15 - d * 0.15)
        return (SK[0], SK[1], SK[2], f)
    return None


def lash_line(h, v):
    sw = 0.60 * EX
    if abs(h) < sw and abs(v + 0.05 * EX) < 0.035 * EX:
        return (0.10, 0.07, 0.07, 0.9)
    return None


def mouth_draw(shape):
    LIP = (SK[0] * 0.62, SK[1] * 0.45, SK[2] * 0.45)
    DARK = (0.10, 0.05, 0.05)
    TEETH = (0.94, 0.92, 0.88)
    dims = {"closed": (0.42, 0.055), "small": (0.26, 0.12),
            "mid": (0.34, 0.22), "open": (0.40, 0.34),
            "ee": (0.52, 0.14), "oo": (0.20, 0.26)}
    w, hgt = dims[shape]
    w *= EX; hgt *= EX

    def fn(h, v):
        # plate: gently blend a skin oval to erase the painted lips
        pd = math.hypot(h / (0.62 * EX), v / (0.42 * EX))
        out = None
        if pd <= 1.0:
            out = (SK[0], SK[1], SK[2], min(1.0, 1.3 - pd))
        d = math.hypot(h / w, v / hgt)
        if shape == "closed":
            if d <= 1.0:
                return (*LIP, 0.95)
            return out
        if d <= 1.0:
            rim = 0.16
            if d > 1.0 - rim:
                return (*LIP, 1)
            if shape in ("open", "ee") and v > hgt * 0.25:
                return (*TEETH, 1)
            return (*DARK, 1)
        if d <= 1.18:
            return (*LIP, soft((d - 1.0) * hgt, 0.18 * hgt))
        return out
    return fn


SK = kit._closest_uv_color(char, (0.0, MOUTH[1] + 0.004, MZ - 0.030))[:3]
if sum(SK) / 3 < 0.3:
    SK = kit._closest_uv_color(char, (0.5 * EX, front_y((MZ + EZ) / 2, hw=0.08) + 0.008, (MZ + EZ) / 2))[:3]

out = np.array(base)
for anchor in (EYE_L, EYE_R):
    paint(out, anchor, 0.07, eye_plate)
    paint(out, anchor, 0.06, eye_draw)
paint(out, MOUTH, 0.05, mouth_draw("closed"))
basefixed = np.array(out)

def save(arr, suffix):
    im = bpy.data.images.new(suffix, W, H, alpha=True)
    im.pixels = arr.ravel().tolist()
    im.filepath_raw = f"{outdir}/{name}_face_{suffix}.png"
    im.file_format = 'PNG'
    im.save()
    print("saved", suffix, flush=True)

save(basefixed, "base")
for i, shape in enumerate(("small", "mid", "open", "ee", "oo"), start=1):
    v = np.array(basefixed)
    paint(v, MOUTH, 0.05, mouth_draw(shape))
    save(v, f"m{i}")
b = np.array(basefixed)
for anchor in (EYE_L, EYE_R):
    paint(b, anchor, 0.07, eye_plate)
    paint(b, anchor, 0.06, lid_draw)
    paint(b, anchor, 0.06, lash_line)
save(b, "blink")
print("FACE PAINT DONE")
