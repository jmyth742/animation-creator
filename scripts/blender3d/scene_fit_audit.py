"""
SCENE FIT AUDIT. Do the characters obey the place?

For every frame of an episode blend: where is the lowest foot relative to the ground
under it (float / sink, mm); is the character standing on the PAINTED PATH, grass or
water (the plate sampled through the painter camera); how big is the character against
the hall door in the establishing shot. Writes a text report and a strip of the worst
frames, so "they don't fit the scene" becomes numbers.

  blender -b <episode.blend> --python scene_fit_audit.py -- <shots.json> <out_prefix>
"""
import sys, os, json, math, colorsys
import bpy, mathutils
from bpy_extras.object_utils import world_to_camera_view as w2c

a = sys.argv[sys.argv.index("--") + 1:]
SHOTS, OUTP = a[0], a[1]
sc = bpy.context.scene
shots = json.load(open(SHOTS))["shots"]
rigs = [o for o in sc.objects if o.type == 'ARMATURE' and o.name not in ("metarig",) and not o.name.startswith("metarig")]
floor = bpy.data.objects.get("floor")
pc = bpy.data.objects.get("painter_cam")
plate_img = None
if pc is not None:
    _pp = os.environ.get("SET_PLATE", "/workspace/text-to-video/ComfyUI/input/plate_tir_na_nog_master.png")
    plate_img = bpy.data.images.load(_pp) if os.path.exists(_pp) else None
print("SF rigs", [r.name for r in rigs], "floor", bool(floor), "painter", bool(pc), "plate", plate_img.name if plate_img else None, flush=True)
dg = bpy.context.evaluated_depsgraph_get()
W, H = (plate_img.size[0], plate_img.size[1]) if plate_img else (0, 0)
px = list(plate_img.pixels) if plate_img else None


def ground_z(x, y):
    if floor is None:
        return 0.0
    # against the FLOOR only: a scene ray from above hits the character's own head first
    Minv = floor.matrix_world.inverted()
    o = Minv @ mathutils.Vector((x, y, 50.0)); d = (Minv.to_3x3() @ mathutils.Vector((0, 0, -1))).normalized()
    res = floor.ray_cast(o, d)
    return (floor.matrix_world @ res[1]).z if res[0] else 0.0


def plate_class(x, y, z):
    """What the plate paints under this world point: path / grass / water / other."""
    if pc is None or px is None:
        return "?"
    co = w2c(sc, pc, mathutils.Vector((x, y, z)))
    if not (0 <= co.x < 1 and 0 <= co.y < 1):
        return "off"
    i = (int(co.y * H) * W + int(co.x * W)) * 4
    r, g, b = px[i], px[i + 1], px[i + 2]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.25 and v > 0.45: return "path"          # pale stone / sand
    if 0.10 < h < 0.22 and s > 0.30 and v > 0.5: return "path"   # tan/ochre track
    if 0.20 <= h < 0.45: return "grass"
    if 0.45 <= h < 0.70: return "water"
    return "other"


def foot_bones(rig):
    return [b for b in rig.pose.bones if b.name in ("DEF-foot.L", "DEF-foot.R", "foot.L", "foot.R")]


report = []; worst = []
for rig in rigs:
    fb = foot_bones(rig)
    if not fb: continue
    stats = {"path": 0, "grass": 0, "water": 0, "other": 0, "off": 0, "?": 0}
    floats, sinks = [], []
    for s_ in shots:
        for f in range(s_["f0"], s_["f1"] + 1, 2):
            sc.frame_set(f)
            pts = [rig.matrix_world @ b.head for b in fb]
            low = min(pts, key=lambda p: p.z)
            gz = ground_z(low.x, low.y)
            d = (low.z - gz) * 1000.0          # mm above ground (foot bone head sits ~ankle: subtract rest offset)
            floats.append((d, f, s_["name"]))
            root = rig.matrix_world.translation
            stats[plate_class(root.x, root.y, gz)] += 1
    # the ankle bone sits above the sole; use the clip's own minimum as the sole offset
    base = min(d for d, _, _ in floats)
    floats = [(d - base, f, n) for d, f, n in floats]
    hi = sorted(floats, reverse=True)[:3]
    tot = sum(stats.values()) or 1
    line = "%s: on path %.0f%%, grass %.0f%%, water %.0f%%; stance foot float p50 %.0f mm, p95 %.0f mm, worst %.0f mm at %s f%d" % (
        rig.name, 100 * stats["path"] / tot, 100 * stats["grass"] / tot, 100 * stats["water"] / tot,
        sorted(d for d, _, _ in floats)[len(floats) // 2], sorted(d for d, _, _ in floats)[int(len(floats) * 0.95)], hi[0][0], hi[0][2], hi[0][1])
    print("SF", line, flush=True); report.append(line); worst += [(rig.name, f, n) for _, f, n in hi]

# scale: character height vs the hall in the establishing shot
est = next((s_ for s_ in shots if "est" in s_["name"]), shots[0])
cam = bpy.data.objects.new("audit_cam", bpy.data.cameras.new("ac")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = est["lens"]
cam.location = tuple(float(v) for v in est["cam"].split(","))
tgt = mathutils.Vector(tuple(float(v) for v in est["tgt"].split(",")))
cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
sc.frame_set((est["f0"] + est["f1"]) // 2)
hall = bpy.data.objects.get("hall_bb") or bpy.data.objects.get("hall")
for rig in rigs:
    ch = next((o for o in sc.objects if o.type == 'MESH' and any(m.type == 'ARMATURE' and m.object == rig for m in o.modifiers)), None)
    if ch is None: continue
    zs = [(ch.matrix_world @ ch.data.vertices[i].co) for i in range(0, len(ch.data.vertices), 50)]
    top, bot = max(zs, key=lambda p: p.z), min(zs, key=lambda p: p.z)
    ht = (w2c(sc, cam, top).y - w2c(sc, cam, bot).y) * sc.render.resolution_y
    hh = 0
    if hall:
        hz = [(hall.matrix_world @ v.co) for v in hall.data.vertices]
        hh = (w2c(sc, cam, max(hz, key=lambda p: p.z)).y - w2c(sc, cam, min(hz, key=lambda p: p.z)).y) * sc.render.resolution_y
    line = "scale in %s: %s %.0f px tall, hall %.0f px -> character/hall %.2f (a 1.6 m person against a ~9 m hall should be ~0.18 at equal depth)" % (est["name"], rig.name, ht, hh, (ht / hh) if hh else -1)
    print("SF", line, flush=True); report.append(line)
open(OUTP + ".txt", "w").write("\n".join(report) + "\n")
# strip of the worst float frames from the shot cameras
sc.render.resolution_x, sc.render.resolution_y = 640, 368
outs = []
for (rn, f, n) in worst[:4]:
    s_ = next(x for x in shots if x["name"] == n)
    cam.data.lens = s_["lens"]; cam.location = tuple(float(v) for v in s_["cam"].split(","))
    t2 = mathutils.Vector(tuple(float(v) for v in s_["tgt"].split(",")))
    cam.rotation_euler = (t2 - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.frame_set(f); sc.render.filepath = "%s_worst_%s_%d" % (OUTP, rn, f); bpy.ops.render.render(write_still=True); outs.append(sc.render.filepath + ".png")
print("SF_DONE", OUTP + ".txt", outs, flush=True)
