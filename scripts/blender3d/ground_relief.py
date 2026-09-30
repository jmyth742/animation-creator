"""
GROUND RELIEF from the plate's depth map, so the cast walks the terrain the plate paints.

Given the painter camera and a per-pixel relative depth (Depth-Anything, saved by
plate_heightfield.py as 'far' in 0..1 with its inverse-depth in 1-far), every floor
vertex that the camera sees gets the height of the point where its view ray meets the
predicted depth. The monocular depth is affine in INVERSE depth, so the two unknowns are
fitted on pixels we know are flat: the bottom band of the frame (near path and bank) and
the lake. Heights are clamped and smoothed on the grid.

    ground_relief.apply(sc, floor, painter_cam, depth_npy)   -> number of raised vertices
    ground_relief.ground_z(x, y)                              -> ray-cast height on the floor
"""
import os, math
import bpy, mathutils
import numpy as np
from bpy_extras.object_utils import world_to_camera_view as w2c

_FLOOR = None


def apply(sc, floor, cam, depth_npy, lake_center=None, lake_radius=0.0, zmax=2.5, zmin=-0.9):
    global _FLOOR
    far = np.load(depth_npy).astype(np.float32)
    inv = 1.0 - far
    H, W = inv.shape
    me = floor.data
    M = floor.matrix_world
    verts = [(v, M @ v.co) for v in me.vertices]
    cam_loc = cam.matrix_world.translation
    # observed inverse depth and plane depth for every visible vertex
    rows = []
    for v, p in verts:
        co = w2c(sc, cam, p)
        if not (0.0 <= co.x < 1.0 and 0.0 <= co.y < 1.0) or co.z <= 0:
            rows.append(None); continue
        px, py = min(W - 1, int(co.x * W)), min(H - 1, int((1.0 - co.y) * H))
        t_plane = (p - cam_loc).length
        rows.append((inv[py, px], t_plane, co.y, p))
    # fit 1/t = a*inv + b on points KNOWN to be at ground level: explicit anchors on the
    # meadow, at the cross and on the lake (they span the depth range, which is what pins
    # both unknowns), plus the bottom 12 per cent of the frame. The first version used the
    # bottom 30 per cent, which includes the raised near bank and the steps, and it lifted
    # the whole meadow: the cast stood a metre above the painted path.
    anchors = [(0.15, 6.9), (-1.55, 8.0), (-2.6, 19.0), (-8.0, 19.0), (2.5, 12.0)]
    xs, ys = [], []
    for ax, ay in anchors:
        p = mathutils.Vector((ax, ay, 0.0)); co = w2c(sc, cam, p)
        if 0.0 <= co.x < 1.0 and 0.0 <= co.y < 1.0 and co.z > 0:
            px, py = min(W - 1, int(co.x * W)), min(H - 1, int((1.0 - co.y) * H))
            for _ in range(6):                       # weight the anchors
                xs.append(inv[py, px]); ys.append(1.0 / (p - cam_loc).length)
    for r in rows:
        if r is None: continue
        i, t, cy, p = r
        if cy < 0.12:
            xs.append(i); ys.append(1.0 / t)
    A = np.vstack([np.array(xs), np.ones(len(xs))]).T
    (a, b), *_ = np.linalg.lstsq(A, np.array(ys), rcond=None)
    print("RELIEF fit 1/t = %.4f*inv + %.4f on %d ground samples" % (a, b, len(xs)), flush=True)
    GAIN = float(os.environ.get("SET_RELIEF_GAIN", "0.6"))     # monocular relief is over-stated; keep it conservative
    # heights
    raised = 0
    zs = np.zeros(len(verts), dtype=np.float32)
    for k, r in enumerate(rows):
        if r is None: continue
        i, t_plane, cy, p = r
        inv_t = a * i + b
        if inv_t <= 1e-4: continue
        t_pred = 1.0 / inv_t
        d = (p - cam_loc).normalized()
        z = (cam_loc + d * t_pred).z
        zs[k] = float(min(zmax, max(zmin, z * GAIN)))
    # smooth on the grid (the floor is a regular grid: neighbours by index distance)
    n = int(round(math.sqrt(len(verts))))
    if n * n == len(verts):
        g = zs.reshape(n, n)
        for _ in range(2):
            gp = np.pad(g, 1, mode='edge')
            g = (gp[1:-1, 1:-1] * 4 + gp[:-2, 1:-1] + gp[2:, 1:-1] + gp[1:-1, :-2] + gp[1:-1, 2:]) / 8.0
        zs = g.ravel()
    Minv = M.inverted()
    for k, (v, p) in enumerate(verts):
        if abs(zs[k]) > 0.02:
            raised += 1
        v.co = Minv @ mathutils.Vector((p.x, p.y, float(zs[k])))
    me.update()
    _FLOOR = floor
    print("RELIEF applied: %d of %d vertices moved, z range %.2f..%.2f" % (raised, len(verts), zs.min(), zs.max()), flush=True)
    return raised


def ground_z(x, y):
    fl = _FLOOR or bpy.data.objects.get("floor")
    if fl is None:
        return 0.0
    Minv = fl.matrix_world.inverted()
    o = Minv @ mathutils.Vector((x, y, 60.0)); d = (Minv.to_3x3() @ mathutils.Vector((0, 0, -1))).normalized()
    res = fl.ray_cast(o, d)
    return (fl.matrix_world @ res[1]).z if res[0] else 0.0
