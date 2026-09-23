"""
Body landmarks measured from a character mesh, shared by the rig fitters.

Anchored on the head, the one thing that can be measured reliably on these characters
(the skull is the widest slice in the upper body, the neck the narrowest below it).
Everything else is laid out below the neck by standard ratios, which hold for chibi and
adult alike once the head is taken out of the measurement, plus widths from the
silhouette and the arm axis fitted from the far half of the arm.
"""
import numpy as np


def measure(P):
    """P: (n,3) world-space vertex positions, feet on z=0-ish. Returns a dict."""
    zmin, zmax = float(P[:, 2].min()), float(P[:, 2].max())
    Ht = zmax - zmin

    def halfwidth_profile(lo, hi, k=140, band=0.012):
        zz = np.linspace(lo, hi, k)
        out = []
        for z in zz:
            m = np.abs(P[:, 2] - z) < band * Ht
            out.append(float(np.percentile(np.abs(P[m, 0]), 96)) if m.sum() > 8 else np.nan)
        return zz, np.array(out)

    zz, hw = halfwidth_profile(zmin + 0.50 * Ht, zmax)
    ok = ~np.isnan(hw)
    top_half = zz > zz[0] + 0.45 * (zz[-1] - zz[0])
    i_skull = int(np.argmax(np.where(top_half & ok, hw, -1)))
    below = (zz < zz[i_skull]) & ok
    z_neck = float(zz[int(np.argmin(np.where(below, hw, 1e9)))]) if below.sum() > 4 else float(zz[0])
    head_h = zmax - z_neck
    body = z_neck - zmin
    z_sh = z_neck - 0.10 * body
    crotch = zmin + 0.50 * body
    z_knee = zmin + 0.26 * body
    z_ankle = zmin + 0.045 * body

    def torso_halfwidth(z, band=0.02):
        m = np.abs(P[:, 2] - z) < band * body
        if m.sum() < 12:
            return np.nan
        xs = np.sort(np.abs(P[m, 0]))
        gaps = np.diff(xs)
        big = np.where(gaps > 0.035 * body)[0]
        if len(big):
            xs = xs[:big[0] + 1]
        return float(np.percentile(xs, 97))

    w_sh = 1.05 * float(np.nanmedian([torso_halfwidth(z) for z in np.linspace(z_sh - 0.30 * body, z_sh - 0.12 * body, 9)]))
    if not np.isfinite(w_sh):
        w_sh = 0.20 * body
    w_hip = float(np.nanmedian([torso_halfwidth(z) for z in np.linspace(crotch, crotch + 0.14 * body, 7)]))
    if not np.isfinite(w_hip):
        w_hip = 0.18 * body
    sh_x = 0.78 * w_sh
    hip_x = 0.52 * w_hip

    # depth (y) of the body centre at a few heights, so bones sit inside the mesh
    def centre_y(z, band=0.03):
        m = (np.abs(P[:, 2] - z) < band * body) & (np.abs(P[:, 0]) < 0.5 * w_hip)
        return float(np.median(P[m, 1])) if m.sum() > 8 else 0.0

    def arm_axis(sign):
        """Shoulder joint to fingertip, through the middle of the arm.

        Arms out (T-pose): the far half of the arm is unambiguous, fit its axis.
        Arms down (A-pose): the arm hangs beside the torso, so instead walk down in
        height slices from the shoulder, take the centroid of the geometry lateral to
        the torso in each slice, and follow that medial line to its lowest slice, which
        is the hand. A PCA fit on the hanging arm caught the sleeve edge and pointed the
        bone 45 degrees out from a vertical arm."""
        m = ((P[:, 2] > z_sh - 0.10 * body) & (P[:, 2] < z_sh + 0.55 * body) &
             (P[:, 0] * sign > w_sh * 1.35))
        root = np.array((sh_x * sign, centre_y(z_sh), z_sh))
        if m.sum() >= 60:
            A = P[m]
            c = A.mean(axis=0)
            u = np.linalg.svd(A - c, full_matrices=False)[2][0]
            if ((c - root) @ u) < 0:
                u = -u
            t = (A - c) @ u
            tip = c + u * float(np.percentile(t, 98))
            return root, tip
        line = []
        for z in np.linspace(z_sh, crotch - 0.05 * body, 26):
            mm = (np.abs(P[:, 2] - z) < 0.02 * body) & (P[:, 0] * sign > w_sh * 0.90)
            if mm.sum() >= 6:
                line.append(P[mm].mean(axis=0))
        if len(line) < 4:
            return None
        line = np.array(line)
        # drop trailing slices that are much closer in than the arm (belt, tunic hem)
        widths = np.abs(line[:, 0])
        keep = widths > 0.85 * float(np.median(widths[: max(3, len(widths) // 2)]))
        last = int(np.where(keep)[0].max())
        line = line[: last + 1]
        tip = line[-1].copy()
        # the hand reaches a little below the lowest slice centroid
        tip[2] -= 0.03 * body
        return root, tip

    # foot: forward direction is where the toes are (the long axis of the foot slice)
    m = (P[:, 2] < zmin + 0.06 * body) & (P[:, 0] > 0)
    foot_y = P[m, 1] if m.sum() > 8 else np.array([0.0, -0.1])
    toe_y = float(np.percentile(foot_y, 3))
    heel_y = float(np.percentile(foot_y, 97))
    if abs(toe_y - float(np.median(foot_y))) < abs(heel_y - float(np.median(foot_y))):
        toe_y, heel_y = heel_y, toe_y          # toes are the far end from the centre

    return dict(zmin=zmin, zmax=zmax, Ht=Ht, z_neck=z_neck, head_h=head_h, body=body,
                z_sh=z_sh, crotch=crotch, z_knee=z_knee, z_ankle=z_ankle,
                w_sh=w_sh, w_hip=w_hip, sh_x=sh_x, hip_x=hip_x,
                y_hip=centre_y(crotch + 0.1 * body), y_chest=centre_y(z_sh - 0.2 * body),
                y_neck=centre_y(z_neck, 0.02), toe_y=toe_y, heel_y=heel_y,
                arm_L=arm_axis(1), arm_R=arm_axis(-1))
