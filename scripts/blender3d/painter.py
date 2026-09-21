"""
The PAINTED WORLD (hybrid set): a painter's camera frames the stage the way
the concept plate does; every near surface samples the plate at its own
screen position under that camera (Blender's UV Project modifier = the exact
render projection), and a far dome carries the same projection for sky and
horizon. The cast walks on geometry that IS the painting.

    P = painter.setup(sc, plate, loc, tgt)          # None when no plate / SET_BACKDROP=0
    grass = P.painted("p_grass", grass)              # material that samples the plate
    ...build geometry...
    P.project_all(sc)                                # LAST: adds the UV Project modifiers

Env: SET_PLATE overrides the plate path; SET_BACKDROP=0 disables (primitive set).
Calibration: render from the painter camera and overlay the plate
(loopwork/painter_calib*.py -> review/env_painter_calib*.png).
"""
import os
import bpy
import mathutils


class Painter:
    def __init__(self, sc, plate_path, loc, tgt, lens=32.0):
        self.plate = bpy.data.images.load(plate_path)
        pc = bpy.data.cameras.new("painter"); pc.lens = lens; pc.sensor_width = 36
        self.cam = bpy.data.objects.new("painter_cam", pc); sc.collection.objects.link(self.cam)
        self.cam.location = loc
        self.cam.rotation_euler = (mathutils.Vector(tgt) - self.cam.location).to_track_quat('-Z', 'Y').to_euler()
        self.projected = []
        print("BACKDROP plate", plate_path.split("/")[-2], "painter", tuple(loc), "->", tuple(tgt))

    def dome(self, sc, center, radius=160.0):
        """Far sphere carrying the plate unshaded: sky and horizon with no seam."""
        bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=64, ring_count=32, location=center)
        d = bpy.context.object; d.name = "backdrop"
        for poly in d.data.polygons: poly.use_smooth = True
        d.data.materials.append(self.painted("p_dome", None, shade=False))
        return d

    def painted(self, name, fallback, sat=1.0, val=1.0, shade=True):
        """Material sampling the plate through the 'Painter' UV map (filled by
        project_all), through HSV and, if shade, the two-tone cel ramp."""
        m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
        uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = "Painter"
        tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = self.plate; tx.extension = 'EXTEND'
        nt.links.new(uvn.outputs["UV"], tx.inputs["Vector"])
        hsv = nt.nodes.new("ShaderNodeHueSaturation")
        hsv.inputs["Saturation"].default_value = sat; hsv.inputs["Value"].default_value = val
        nt.links.new(tx.outputs["Color"], hsv.inputs["Color"])
        em = nt.nodes.new("ShaderNodeEmission"); out = nt.nodes.new("ShaderNodeOutputMaterial")
        if shade:
            diff = nt.nodes.new("ShaderNodeBsdfDiffuse"); torgb = nt.nodes.new("ShaderNodeShaderToRGB")
            ramp = nt.nodes.new("ShaderNodeValToRGB"); ramp.color_ramp.interpolation = 'CONSTANT'
            k = float(os.environ.get("SET_SHADE", "0.82"))    # shadow multiplier on the painting (1 = none)
            ramp.color_ramp.elements[0].color = (k, k * 0.97, k * 1.06, 1); ramp.color_ramp.elements[1].position = 0.5
            mix = nt.nodes.new("ShaderNodeMixRGB"); mix.blend_type = 'MULTIPLY'; mix.inputs["Fac"].default_value = 1.0
            nt.links.new(diff.outputs["BSDF"], torgb.inputs["Shader"]); nt.links.new(torgb.outputs["Color"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], mix.inputs["Color1"]); nt.links.new(hsv.outputs["Color"], mix.inputs["Color2"])
            nt.links.new(mix.outputs["Color"], em.inputs["Color"])
        else:
            nt.links.new(hsv.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        m["painter_projected"] = True
        return m

    def project_all(self, sc):
        """After the geometry exists: a 'Painter' UV layer + UV Project modifier
        (from the painter camera, plate aspect) on every object wearing a
        painted material. modifiers.new appends, so it sits last in the stack
        and sees the final surface."""
        asp = self.plate.size[0] / self.plate.size[1]
        for ob in list(sc.objects):
            if ob.type != 'MESH' or not any(m and m.get("painter_projected") for m in ob.data.materials): continue
            if "Painter" not in ob.data.uv_layers: ob.data.uv_layers.new(name="Painter")
            md = ob.modifiers.new("painter", 'UV_PROJECT'); md.uv_layer = "Painter"; md.projector_count = 1
            md.projectors[0].object = self.cam; md.aspect_x = asp; md.aspect_y = 1.0; md.scale_x = 1.0; md.scale_y = 1.0
            assert ob.modifiers[-1].name == md.name   # never compare RNA wrappers with `is`
            self.projected.append(ob.name)
        print("PAINTER projected onto", self.projected)


def setup(sc, default_plate, loc, tgt, lens=32.0):
    """Painter for the set, or None (no plate on disk / SET_BACKDROP=0)."""
    plate = os.environ.get("SET_PLATE", default_plate or "")
    if not plate or not os.path.exists(plate) or os.environ.get("SET_BACKDROP", "1") in ("", "0"):
        return None
    up = plate[:-4] + "_4x.png"          # upscale_plates.py output: the projected plate must out-resolve the frame
    if plate.endswith(".png") and os.path.exists(up): plate = up
    return Painter(sc, plate, loc, tgt, lens)
