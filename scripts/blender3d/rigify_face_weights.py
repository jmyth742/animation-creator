"""
Deterministic face weights on a Rigify-fitted character.

Bone heat spreads the head over 90 tiny face bones and gives each so little that no
control visibly moves the surface. For a stylised character with a painted face the
motion that has to be geometric is the JAW (audio-driven opening), with the lips riding
on it: assign the lower front of the head to the jaw deform bone by a falloff from a
pivot line at the mouth, take that weight from the head bone, and leave the rest of the
face rigid to the head (the painted expressions carry brows and eyes).

  blender -b <fit_face.blend> --python rigify_face_weights.py -- <out.blend>
Env: FW_MOUTH (0.195), FW_EYE (0.44): mouth and eye heights as fractions of head height.
"""
import sys, os, math
import bpy, mathutils
import numpy as np

OUT = sys.argv[sys.argv.index("--") + 1]
rig = bpy.data.objects["rig"]; char = bpy.data.objects["hero"]
names = {b.name for b in rig.data.bones}
JAW = next((n for n in ("DEF-jaw", "DEF-jaw_master", "DEF-chin") if n in names), None)
HEAD = "DEF-spine.006"
print("FW jaw bone", JAW, flush=True)
n = len(char.data.vertices)
co = np.empty(n * 3); char.data.vertices.foreach_get("co", co)
P = co.reshape(-1, 3) @ np.array(char.matrix_world.to_3x3()).T + np.array(char.matrix_world.translation)
zmin, zmax = P[:, 2].min(), P[:, 2].max()
# head box: everything above the narrowest slice (same rule as the fitters)
zs = np.linspace(zmin + 0.5 * (zmax - zmin), zmax, 120)
hw = np.array([np.percentile(np.abs(P[np.abs(P[:, 2] - z) < 0.012 * (zmax - zmin), 0]), 96)
               if (np.abs(P[:, 2] - z) < 0.012 * (zmax - zmin)).sum() > 8 else np.nan for z in zs])
ok = ~np.isnan(hw); top = zs > zs[0] + 0.45 * (zs[-1] - zs[0])
i_sk = int(np.argmax(np.where(top & ok, hw, -1))); below = (zs < zs[i_sk]) & ok
z_neck = float(zs[int(np.argmin(np.where(below, hw, 1e9)))]); head_h = zmax - z_neck
mouth_z = z_neck + float(os.environ.get("FW_MOUTH", "0.195")) * head_h
eye_z = z_neck + float(os.environ.get("FW_EYE", "0.44")) * head_h
head = P[:, 2] > z_neck
y_c = float(np.median(P[head, 1]))
# jaw: below a line rising from the mouth corners, on the front half of the head, fading
# in over the height of the lips so the upper lip stays put
pivot_z = mouth_z + 0.06 * head_h
front = P[:, 1] < y_c - 0.05 * head_h
lat = np.abs(P[:, 0]) / max(1e-6, float(np.percentile(np.abs(P[head, 0]), 97)))
fall = np.clip((pivot_z - P[:, 2]) / (0.10 * head_h), 0, 1)           # 1 well below the pivot
side = np.clip(1.4 - lat * 1.6, 0, 1)                                    # fades out at the jaw hinge
w = np.where(head & front & (P[:, 2] < pivot_z) & (P[:, 2] > z_neck - 0.02 * head_h), fall * side, 0.0)
w = w ** 0.8
vg_j = char.vertex_groups.get(JAW) or char.vertex_groups.new(name=JAW)
vg_h = char.vertex_groups.get(HEAD)
moved = 0
for i in np.where(w > 0.02)[0]:
    i = int(i); wi = float(w[i])
    # take it from every group this vertex has, proportionally, and give it to the jaw
    v = char.data.vertices[i]
    for g in list(v.groups):
        vg = char.vertex_groups[g.group]
        if vg.name == JAW:
            continue
        vg.add([i], g.weight * (1 - wi), 'REPLACE')
    vg_j.add([i], wi, 'REPLACE')
    moved += 1
print("FW jaw verts", moved, "pivot z %.3f mouth z %.3f neck %.3f" % (pivot_z, mouth_z, z_neck), flush=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("FW_DONE", OUT, flush=True)
