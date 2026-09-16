"""
Geometric bone mapper for UniRig rigs (bones are unnamed bone_N).
map_unirig(rig) -> {role: bone_name} with roles:
  hips, spine0..spineN, neck, head,
  L_clav L_upperarm L_forearm L_hand, R_..., L_upperleg L_lowerleg L_foot L_toe, R_...
Rules (rest geometry, world space, x = lateral, z = up):
  hips = parentless bone; the spine is the chain of CENTRAL bones (|x| small)
  climbing from hips; arms = lateral chains leaving the top spine bones;
  legs = lateral DOWNWARD chains leaving hips or the lowest spine bones;
  central chains hanging off the head/torso (hair, dress) are ignored.
"""
import bpy, mathutils

def map_unirig(rig, lateral_frac=0.04):
    db = rig.data.bones
    W = lambda v: rig.matrix_world @ v
    zs = [W(b.head_local).z for b in db] + [W(b.tail_local).z for b in db]
    H = max(zs) - min(zs); lat = lateral_frac * H
    hx = lambda b: W(b.head_local).x
    hz = lambda b: W(b.head_local).z
    dz = lambda b: W(b.tail_local).z - W(b.head_local).z
    central = lambda b: abs(hx(b)) <= lat and abs(W(b.tail_local).x) <= lat * 1.5
    roles = {}
    root = next(b for b in db if b.parent is None)
    roles["hips"] = root.name
    def subtree(b):
        n = 0; st = list(b.children)
        while st: x = st.pop(); n += 1; st.extend(x.children)
        return n
    # spine: climb the CENTRAL child with the largest subtree (bust/hair chains are leaves)
    spine = []; cur = root
    while True:
        nxt = [c for c in cur.children if central(c) and dz(c) > 0.02 * H]
        if not nxt: break
        cur = max(nxt, key=lambda c: (subtree(c), dz(c))); spine.append(cur)
    def chain(b, n):
        out = [b]
        while len(out) < n and out[-1].children:
            out.append(max(out[-1].children, key=lambda c: (W(c.tail_local) - W(c.head_local)).length))
        return out
    # limbs: lateral chains. Legs leave the hips or the first spine bone pointing DOWN;
    # everything else lateral off the spine is an arm (clavicle or upper arm).
    legs, arms = [], []
    for i, b in enumerate([root] + spine):
        for c in b.children:
            if central(c): continue
            if i <= 1 and dz(c) < -0.1 * H: legs.append(c)
            elif i >= 1: arms.append((i - 1, c))
    # a real arm chain is LONG (hair/dress chains are short); arms branch from the
    # LOWEST spine bone that carries a long lateral chain on both sides
    def chain_len(b): return sum((W(x.tail_local) - W(x.head_local)).length for x in chain(b, 4))
    arms = [(i, c) for i, c in arms if chain_len(c) >= 0.22 * H]
    by_idx = {}
    for i, c in arms: by_idx.setdefault(i, []).append(c)
    both = [i for i, cs in sorted(by_idx.items()) if any(hx(c) + W(c.tail_local).x >= 0 for c in cs) and any(hx(c) + W(c.tail_local).x < 0 for c in cs)]
    arm_idx = both[0] if both else (min(by_idx) if by_idx else len(spine) - 1)
    arms = [(i, c) for i, c in arms if i == arm_idx]
    torso, upper = spine[:arm_idx + 1], spine[arm_idx + 1:]
    for i, b in enumerate(torso): roles[f"spine{i}"] = b.name
    if upper: roles["neck"] = upper[0].name
    if len(upper) > 1: roles["head"] = upper[1].name
    for _, c in arms:
        side = "L" if (hx(c) + W(c.tail_local).x) >= 0 else "R"
        ch = chain(c, 4)
        first_len = (W(ch[0].tail_local) - W(ch[0].head_local)).length
        names = ["clav", "upperarm", "forearm", "hand"] if first_len < 0.12 * H and len(ch) >= 3 else ["upperarm", "forearm", "hand"]
        for role, bone in zip(names, ch): roles[f"{side}_{role}"] = bone.name
    for c in legs:
        side = "L" if hx(c) >= 0 else "R"
        for role, bone in zip(["upperleg", "lowerleg", "foot", "toe"], chain(c, 4)): roles[f"{side}_{role}"] = bone.name
    roles["_height"] = H
    return roles

if __name__ == "__main__":
    import sys
    src = sys.argv[sys.argv.index("--") + 1]
    for ob in list(bpy.context.scene.objects): bpy.data.objects.remove(ob, do_unlink=True)
    bpy.ops.import_scene.gltf(filepath=src)
    rig = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE'][0]
    m = map_unirig(rig)
    for k in sorted(m): print("MAP", k, m[k])
