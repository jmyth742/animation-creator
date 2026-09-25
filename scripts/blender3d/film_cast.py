"""
One cast loader for all three episode builders, so a rig change is made once.

    oisin, orig, niamh, nrig = film_cast.load_cast(sc, MESHES, FPS)
    film_cast.apply_walk(rig, path_fn, f0, f1, fps=..., stride_hz=...)
    film_cast.apply_idle(rig, f0, f1, pos, heading, fps=..., look_at_fn=..., gestures=...)
    film_cast.apply_talk_tex(rig, ctrl, env, f0, fps=..., blinks=..., visemes=...)
    film_cast.face_variants(char, name_hint, faces_dir)
    film_cast.close_scale(rig)    # 1.0 for the 1.75 m kit cast, H/1.75 for a Rigify character

FILM_RIG=numpy   the kit's own rig (the 3 Sep film)
FILM_RIG=unirig  the UniRig-skinned cast
FILM_RIG=rigify  Rigify-fitted characters appended from .blend files:
                 FILM_RIGIFY_O / FILM_RIGIFY_N (default the mitten-hand cast oisin4/niamh4,
                 face blends), faces FILM_RIGIFY_FACE_O / _N (default cand_<name>_kit)
Each Rigify character is driven by a RigifyActor; the kit rigs by character_kit. The
dispatch is by rig object, so the builders' call sites do not care which is which.
"""
import os, math
import bpy
import numpy as np
import character_kit as kit

_ACTORS = {}          # rig object name -> RigifyActor
_FACES = {}           # char object name -> face set name


def _append_rigify(blend, rig_name, char_name, tag):
    before = set(bpy.data.objects.keys())
    with bpy.data.libraries.load(blend, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in ("rig", "hero")]
    new = [o for o in dst.objects if o is not None]
    sc = bpy.context.scene
    for ob in new:
        if ob.name not in sc.collection.objects:
            sc.collection.objects.link(ob)
    rig = next(o for o in new if o.type == 'ARMATURE')
    char = next(o for o in new if o.type == 'MESH')
    # a second append arrives as rig.001 / hero.001; give both real names now
    rig.name = rig_name; char.name = char_name
    for o in bpy.data.objects:
        if o.name.startswith("metarig") and o.name not in before:
            o.hide_render = True; o.hide_viewport = True
    return char, rig


def load_cast(sc, MESHES, FPS):
    mode = os.environ.get("FILM_RIG", "numpy")
    MS = os.environ.get("FILM_MESH_SUFFIX", "")
    CAST = os.environ.get("FILM_CAST", "mv")
    if mode == "rigify":
        import rigify_anim
        RB_O = os.environ.get("FILM_RIGIFY_O", "/workspace/loopwork/rigify/oisin4_face.blend")
        RB_N = os.environ.get("FILM_RIGIFY_N", "/workspace/loopwork/rigify/niamh4_face.blend")
        oisin, orig = _append_rigify(RB_O, "oisin_rigify", "oisin_mv", "o")
        niamh, nrig = _append_rigify(RB_N, "niamh_rigify", "niamh_mv", "n")
        _ACTORS[orig.name] = rigify_anim.RigifyActor(orig, oisin, fps=FPS)
        _ACTORS[nrig.name] = rigify_anim.RigifyActor(nrig, niamh, fps=FPS)
        _FACES[oisin.name] = os.environ.get("FILM_RIGIFY_FACE_O", "cand_" + os.path.basename(RB_O).split("_face")[0].split(".")[0] + "_kit")
        _FACES[niamh.name] = os.environ.get("FILM_RIGIFY_FACE_N", "cand_" + os.path.basename(RB_N).split("_face")[0].split(".")[0] + "_kit")
        print("FILM_CAST rigify:", RB_O, RB_N, "faces", _FACES, flush=True)
        return oisin, orig, niamh, nrig
    if mode == "unirig":
        ON, NN = ("cg_oisin", "cg_niamh") if CAST == "cg" else ("oisin_mv", "niamh_mv")
        oisin, orig = kit.load_rigged_character(f"{MESHES}/props/{ON}{MS}_rigged.glb", ON, height=1.75)
        niamh, nrig = kit.load_rigged_character(f"{MESHES}/props/{NN}{MS}_rigged.glb", NN, height=1.68, skirt=True)
        return oisin, orig, niamh, nrig
    oisin = kit.load_character(f"{MESHES}/props/oisin_mv_painted.glb", "oisin_mv")
    orig = kit.rig_character(oisin, "oisin_mv")
    niamh = kit.load_character(f"{MESHES}/props/niamh_mv_painted.glb", "niamh_mv", height=1.68)
    nrig = kit.rig_character(niamh, "niamh_mv")
    return oisin, orig, niamh, nrig


def face_variants(char, name_hint, faces_dir):
    return kit.enable_face_variants(char, _FACES.get(char.name, name_hint), faces_dir)


def close_scale(rig):
    a = _ACTORS.get(rig.name)
    return (a.H / 1.75) if a else 1.0


def scale_close(c, rig):
    """A close-up shot dict was framed for a 1.75 m character; scale its camera and target
    heights to this rig's character so a 1.6 m lead is not shot at the hairline."""
    k = close_scale(rig)
    if abs(k - 1.0) < 1e-3:
        return c
    out = dict(c)
    for key in ("cam", "tgt"):
        x, y, z = (float(v) for v in c[key].split(","))
        out[key] = "%.3f,%.3f,%.3f" % (x, y, z * k)
    return out


def apply_walk(rig, path_fn, f0, f1, fps=16, stride_hz=1.45):
    a = _ACTORS.get(rig.name)
    if a:
        a.walk(f0, f1, path_fn)
    else:
        kit.apply_walk(rig, path_fn, f0, f1, fps=fps, stride_hz=stride_hz)


def apply_idle(rig, f0, f1, pos, heading, fps=16, look_at_fn=None, gestures=None):
    a = _ACTORS.get(rig.name)
    if a:
        a.idle(f0, f1, pos, heading, gestures=gestures, look_at_fn=look_at_fn)
    else:
        kit.apply_idle(rig, f0, f1, pos, heading, fps=fps, look_at_fn=look_at_fn, gestures=gestures)


def apply_talk_tex(rig, fc, env, f0, fps=16, blinks=True, visemes=None):
    a = _ACTORS.get(rig.name)
    if not a:
        return kit.apply_talk_tex(rig, fc, env, f0, fps=fps, blinks=blinks, visemes=visemes)
    keys = ("m1", "m2", "m3", "m4", "m5")
    for i, v in enumerate(env):
        f = f0 + i
        if visemes is not None:
            col = int(visemes[i]) if i < len(visemes) else 0
            sel = None if col == 0 else "m%d" % col
        else:
            v = float(v)
            sel = None if v < 0.04 else "m1" if v < 0.25 else "m2" if v < 0.48 else "m3" if v < 0.72 else "m4"
        for k in keys:
            fc[k].default_value = 1.0 if k == sel else 0.0
            fc[k].keyframe_insert("default_value", frame=f)
    a.talk(f0, [min(1.0, float(v)) for v in env])
    if blinks:
        fc["blink"].default_value = 0.0; fc["blink"].keyframe_insert("default_value", frame=f0)
        for t0 in np.arange(f0 + 11, f0 + len(env), 3.4 * fps):
            b = int(t0)
            for f, on in ((b - 1, 0.0), (b, 1.0), (b + 1, 1.0), (b + 2, 0.0)):
                fc["blink"].default_value = on; fc["blink"].keyframe_insert("default_value", frame=f)
    nt = fc["_tree"]
    if nt.animation_data and nt.animation_data.action:
        for fcu in nt.animation_data.action.fcurves:
            for kp in fcu.keyframe_points:
                kp.interpolation = 'CONSTANT'
