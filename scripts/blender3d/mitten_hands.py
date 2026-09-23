"""
MITTEN HANDS — rescue the chibi's hands without regenerating the character.

The reconstruction gives these characters a flattened lump with half-formed, splayed
fingers. It is the single worst-reading part of the mesh in motion: any arm rotation
throws the splay across the silhouette and it reads as a spike. A chibi does not need
fingers; it needs a clean rounded mitt, which is also what the 2D style draws.

The hand is found from geometry, not from the skeleton (the predicted hand bone owns
almost nothing on these builds): fit the arm's axis from the vertices the arm chain owns,
then take the outer end of that cloud. Those vertices are pulled onto an ellipsoid around
the palm centre, with the pull ramping from nothing at the wrist to full at the
fingertips, so the wrist stays continuous with the forearm.

  blender -b --factory-startup --python mitten_hands.py -- <rigged.glb> <out.glb>
Env: MH_CUT (0.78 of the arm axis), MH_R (0.62 of the hand radius), MH_LONG (1.25),
     MH_STRENGTH (1.0)
"""
import sys, os
import bpy, mathutils
import numpy as np

sys.path.insert(0, "/workspace/text-to-video/scripts/day4")
from rig_map import map_unirig                                      # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
SRC, DST = a[0], a[1]
CUT = float(os.environ.get("MH_CUT", "0.86"))  # fraction of the arm cloud kept as "not hand"
RFAC = float(os.environ.get("MH_R", "0.46"))
LONG = float(os.environ.get("MH_LONG", "1.08"))
STR = float(os.environ.get("MH_STRENGTH", "1.0"))

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=SRC)
rig = [o for o in sc.objects if o.type == 'ARMATURE'][0]
meshes = [o for o in sc.objects if o.type == 'MESH' and any(m.type == 'ARMATURE' for m in o.modifiers)]
char = max(meshes, key=lambda m: len(m.data.vertices))
roles = map_unirig(rig)
roles.pop("_height", None)

n = len(char.data.vertices)
co = np.empty(n * 3)
char.data.vertices.foreach_get("co", co)
L = co.reshape(-1, 3)                                    # object space, which is what we write back
M3 = np.array(char.matrix_world.to_3x3())
T3 = np.array(char.matrix_world.translation)
P = L @ M3.T + T3
M3inv = np.linalg.inv(M3)

report = {}
for side in ("L", "R"):
    up = roles.get("%s_upperarm" % side)
    if up is None or up not in rig.data.bones:
        continue
    names, stack = [], [rig.data.bones[up]]
    while stack:
        b = stack.pop()
        names.append(b.name)
        stack.extend(b.children)
    idx = {char.vertex_groups[nm].index for nm in names if nm in char.vertex_groups}
    sel = []
    for v in char.data.vertices:
        for g in v.groups:
            if g.group in idx and g.weight > 0.35:
                sel.append(v.index)
                break
    if len(sel) < 80:
        report[side] = "no arm cloud"
        continue
    # THE HAND IS THE FAR END OF THE ARM, measured from the torso, not from a fitted axis.
    # A PCA axis through the arm cloud is unreliable here: the sleeve and the cloth near
    # the shoulder dominate it, and the "far 20 per cent" then selects most of the arm.
    torso_roles = [r for r in ("hips", "spine0", "spine1", "spine2", "neck") if r in roles]
    tseg = []
    for r in torso_roles:
        b = rig.data.bones[roles[r]]
        tseg.append((np.array(rig.matrix_world @ b.head_local), np.array(rig.matrix_world @ b.tail_local)))

    def seg_dist(Q, segs):
        best = None
        for aa, bb in segs:
            ab = bb - aa
            L2 = float(ab @ ab)
            if L2 < 1e-12:
                dd = np.linalg.norm(Q - aa, axis=1)
            else:
                tt = np.clip(((Q - aa) @ ab) / L2, 0.0, 1.0)
                dd = np.linalg.norm(Q - (aa + np.outer(tt, ab)), axis=1)
            best = dd if best is None else np.minimum(best, dd)
        return best

    A = P[sel]
    dt = seg_dist(A, tseg)
    hi = float(dt.max())
    cut = float(np.percentile(dt, 100 - 100 * (1.0 - CUT)))
    hand = [i for i, d0 in zip(sel, dt) if d0 > cut]
    dmap = {i: float(d0) for i, d0 in zip(sel, dt)}
    if len(hand) < 30:
        report[side] = "no hand cloud"
        continue
    # the wrist is the centroid of the band just inside the hand
    band = [i for i, d0 in zip(sel, dt) if cut * 0.86 < d0 <= cut]
    wrist = P[band].mean(axis=0) if len(band) > 10 else P[hand].mean(axis=0)
    if os.environ.get("MH_DEBUG", "0") not in ("", "0"):
        if not char.data.color_attributes:
            char.data.color_attributes.new(name="sel", type='FLOAT_COLOR', domain='POINT')
        ca = char.data.color_attributes[0]
        hs = set(hand); bs = set(band)
        for v in char.data.vertices:
            c = (1, 0.15, 0.15, 1) if v.index in hs else ((0.2, 0.6, 1, 1) if v.index in bs else (0.75, 0.75, 0.75, 1))
            ca.data[v.index].color = c
        report["%s_selected" % side] = len(hand)
        report["%s_band" % side] = len(band)
        moved = 0
        R = 0.0
        report["%s_hand_verts" % side] = len(hand)
        report["%s_pulled_in" % side] = 0
        report["%s_mitt_radius_mm" % side] = 0
        continue
    KMIN = float(os.environ.get("MH_K", "0.45"))
    span = max(1e-6, hi - cut)
    for i in hand:
        f = min(1.0, max(0.0, (dmap[i] - cut) / span))
        f = f * f * (3 - 2 * f)
        k = 1.0 - (1.0 - KMIN) * f * STR
        P[i] = wrist + (P[i] - wrist) * k
    moved = len(hand)
    R = float(np.percentile(np.linalg.norm(P[hand] - P[hand].mean(axis=0), axis=1), 60))
    ITER = int(os.environ.get("MH_SMOOTH", "6"))
    if ITER > 0:
        if 'NBR' not in globals():
            globals()['NBR'] = [[] for _ in range(n)]
            for e in char.data.edges:
                x, y = e.vertices
                NBR[x].append(y)
                NBR[y].append(x)
        ramp = {}
        for i in hand:
            f = min(1.0, max(0.0, (dmap[i] - cut) / span))
            ramp[i] = f * f * (3 - 2 * f)
        for _ in range(ITER):
            newpos = {}
            for i in hand:
                nb = NBR[i]
                if nb:
                    newpos[i] = P[i] + (P[nb].mean(axis=0) - P[i]) * (0.35 * ramp[i])
            for i, q in newpos.items():
                P[i] = q
    report["%s_hand_verts" % side] = len(hand)
    report["%s_pulled_in" % side] = moved
    report["%s_mitt_radius_mm" % side] = int(round(R * 1000))

L2 = (P - T3) @ M3inv.T
char.data.vertices.foreach_set("co", L2.reshape(-1))
char.data.update()
# glTF meshes carry CUSTOM SPLIT NORMALS. Moving vertices leaves those normals pointing
# the way the old surface faced, and the region renders as a shattered mess of facets --
# which looks exactly like a broken mesh and is not one. Clear them and let Blender
# recompute.
bpy.ops.object.select_all(action='DESELECT')
char.select_set(True)
bpy.context.view_layer.objects.active = char
try:
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
    print("MITTEN cleared custom split normals")
except Exception as e:                                              # noqa: BLE001
    print("MITTEN could not clear split normals:", e)
for poly in char.data.polygons:
    poly.use_smooth = True
char.data.update()
print("MITTEN", report, flush=True)

bpy.ops.object.select_all(action='DESELECT')
char.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.export_scene.gltf(filepath=DST, use_selection=True, export_apply=False,
                          export_animations=False, export_format='GLB')
print("MITTEN_DONE", DST, os.path.getsize(DST), flush=True)
