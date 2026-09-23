"""
GEOMETRIC FACE CALIBRATION.

auto_face_calib finds the eyes by looking for bright sclera in the texture. On a
character painted with dark anime eyes it reports "sclera not found", falls back to
dark-iris detection, and lands on the beard: it put the eye anchors 3 cm above the mouth
anchor, both down at the jaw.

Geometry is more reliable here. The head is the mass above the neck, and the neck is the
narrowest horizontal slice between the shoulders and the skull. Within that head box the
anime convention is stable: eyes a little above the middle, mouth about a third of the
way up. That is what this writes.

  blender -b --factory-startup --python face_calib_geom.py -- <mesh.glb> <height> <out.json> [check.png]
Env: FCG_EYE (0.50 of head height), FCG_MOUTH (0.27), FCG_EYEX (0.30 of head half-width)
"""
import sys, os, json, math
import bpy, mathutils
import numpy as np

sys.path.insert(0, "/workspace/text-to-video/scripts/blender3d")
import character_kit as kit                                        # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
GLB, H, OUT = a[0], float(a[1]), a[2]
CHECK = a[3] if len(a) > 3 else None

sc = bpy.context.scene
for ob in list(sc.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
char = kit.load_character(GLB, "cal", height=H)
n = len(char.data.vertices)
co = np.empty(n * 3)
char.data.vertices.foreach_get("co", co)
P = co.reshape(-1, 3) @ np.array(char.matrix_world.to_3x3()).T + np.array(char.matrix_world.translation)
ztop = float(P[:, 2].max())
zbot = float(P[:, 2].min())
Htot = ztop - zbot

# width profile over the top 45 per cent of the figure
zs = np.linspace(zbot + 0.55 * Htot, ztop, 90)
w = []
for z in zs:
    m = np.abs(P[:, 2] - z) < 0.01 * Htot
    w.append(float(np.percentile(np.abs(P[m, 0]), 96)) if m.sum() > 8 else np.nan)
w = np.array(w)
ok = ~np.isnan(w)
zs, w = zs[ok], w[ok]

# the skull is the widest slice in the upper half; the neck is the narrowest slice below it
top_half = zs > zs[0] + 0.45 * (zs[-1] - zs[0])
i_skull = int(np.argmax(np.where(top_half, w, -1)))
below = zs < zs[i_skull]
if below.sum() > 4:
    i_neck = int(np.argmin(np.where(below, w, 1e9)))
    z_neck = float(zs[i_neck])
else:
    z_neck = float(zs[0])
head_h = ztop - z_neck
half_w = float(w[i_skull])

EYE = float(os.environ.get("FCG_EYE", "0.50"))
MOU = float(os.environ.get("FCG_MOUTH", "0.27"))
EYX = float(os.environ.get("FCG_EYEX", "0.30"))
cal = {
    "mouth_z": round(z_neck + MOU * head_h, 4),
    "eye_z": round(z_neck + EYE * head_h, 4),
    "eye_x": round(EYX * half_w, 4),
    "face_x": round(float(np.median(P[P[:, 2] > z_neck][:, 0])), 4),
}
json.dump(cal, open(OUT, "w"), indent=1)
print("FCG head from z=%.3f to %.3f (h=%.3f, half width %.3f)" % (z_neck, ztop, head_h, half_w), flush=True)
print("FCG", json.dumps(cal), flush=True)

if CHECK:
    # mark the anchors on a front render so the result can be judged rather than trusted
    for nm, col in (("eL", (1, 0.2, 0.2)), ("eR", (0.2, 0.5, 1)), ("mo", (1, 0.9, 0.2))):
        me = bpy.data.meshes.new(nm)
        import bmesh
        bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.012 * H)
        bm.to_mesh(me); bm.free()
        o = bpy.data.objects.new(nm, me); sc.collection.objects.link(o)
        if nm == "mo":
            o.location = (cal["face_x"], -half_w * 1.6, cal["mouth_z"])
        else:
            sgn = 1 if nm == "eL" else -1
            o.location = (cal["face_x"] + sgn * cal["eye_x"], -half_w * 1.6, cal["eye_z"])
        m = bpy.data.materials.new(nm); m.use_nodes = True
        nt = m.node_tree; nt.nodes.clear()
        e = nt.nodes.new("ShaderNodeEmission"); e.inputs["Color"].default_value = (*col, 1)
        oo = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(e.outputs["Emission"], oo.inputs["Surface"])
        me.materials.append(m)
    sun = bpy.data.objects.new("s", bpy.data.lights.new("s", 'SUN')); sun.data.energy = 3.2
    sun.rotation_euler = (math.radians(60), 0, math.radians(20)); sc.collection.objects.link(sun)
    wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
    wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.58, 0.62, 1)
    cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); cam.data.lens = 75
    sc.collection.objects.link(cam); sc.camera = cam
    ctr = mathutils.Vector((cal["face_x"], 0.0, z_neck + 0.55 * head_h))
    cam.location = (ctr.x, ctr.y - 1.1 * head_h * 2.2, ctr.z)
    cam.rotation_euler = (ctr - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.view_settings.view_transform = 'Standard'
    sc.render.resolution_x = sc.render.resolution_y = 700
    sc.render.filepath = CHECK
    bpy.ops.render.render(write_still=True)
    print("FCG_CHECK", CHECK, flush=True)
