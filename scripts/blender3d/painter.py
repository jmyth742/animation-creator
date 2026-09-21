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
        # SET_FLATTEN=<levels>: posterise the plate. DEFAULT OFF, and it should stay off.
        # This was written on an inverted diagnosis. In hand-painted-BG anime the CHARACTER
        # carries more information than the background, not less: drawn fold lines, hair
        # strand lines, designed shadow shapes, varied line weight. Background painters
        # simplify near contact points precisely so the character reads. So the plate/cast
        # gap must be closed from the CAST side; flattening the plate attacks the one part
        # of this pipeline that is unambiguously working. Kept only as an experiment hook.
        _lv = int(os.environ.get("SET_FLATTEN", "0") or 0)
        if _lv > 1:
            import numpy as _np
            _px = _np.asarray(self.plate.pixels[:], dtype=_np.float32).reshape(-1, 4)
            _rgb = _px[:, :3]
            _q = _np.clip(_np.round(_rgb * (_lv - 1)) / (_lv - 1), 0.0, 1.0)
            _px[:, :3] = _q
            self.plate.pixels = _px.ravel().tolist()
            print("PLATE flattened to", _lv, "levels", flush=True)
        pc = bpy.data.cameras.new("painter"); pc.lens = lens; pc.sensor_width = 36
        self.cam = bpy.data.objects.new("painter_cam", pc); sc.collection.objects.link(self.cam)
        self.cam.location = loc
        self.cam.rotation_euler = (mathutils.Vector(tgt) - self.cam.location).to_track_quat('-Z', 'Y').to_euler()
        # a second camera that film.py never moves: surfaces tagged ob['painter_fixed'] project from the
        # calibrated pose, so the plate's LAKE stays on the lake from every shot (per-shot projection put
        # the hall's steps on it from a sideways camera); it stretches a little off-angle, but as water
        mc = bpy.data.cameras.new("painter_master"); mc.lens = lens; mc.sensor_width = 36
        self.master_cam = bpy.data.objects.new("painter_master", mc); sc.collection.objects.link(self.master_cam)
        self.master_cam.location = loc; self.master_cam.rotation_euler = self.cam.rotation_euler
        self.projected = []
        print("BACKDROP plate", plate_path.split("/")[-2], "painter", tuple(loc), "->", tuple(tgt))

    def dome(self, sc, center, radius=160.0):
        """Far sphere carrying the plate unshaded: sky and horizon with no seam."""
        bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=64, ring_count=32, location=center)
        d = bpy.context.object; d.name = "backdrop"
        d.visible_shadow = False   # a sky never shadows the stage (a closed sphere around the sun did)
        for poly in d.data.polygons: poly.use_smooth = True
        d.data.materials.append(self.painted("p_dome", None, shade=False))
        return d

    def painted(self, name, fallback, sat=1.0, val=1.0, shade=True, flat=None):
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
        if flat is not None:
            # GRAZING FADE: where the surface is edge-on to the camera the projection streaks
            # (cliff foot, sea near the cliff); fade to a flat colour sampled from the plate
            geo = nt.nodes.new("ShaderNodeNewGeometry")
            dot = nt.nodes.new("ShaderNodeVectorMath"); dot.operation = 'DOT_PRODUCT'
            nt.links.new(geo.outputs["Normal"], dot.inputs[0]); nt.links.new(geo.outputs["Incoming"], dot.inputs[1])
            ab = nt.nodes.new("ShaderNodeMath"); ab.operation = 'ABSOLUTE'; nt.links.new(dot.outputs["Value"], ab.inputs[0])
            lo, hi = (flat[3], flat[4]) if len(flat) >= 5 else (0.12, 0.35); flat = flat[:3]
            mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs["From Min"].default_value = lo; mr.inputs["From Max"].default_value = hi
            nt.links.new(ab.outputs["Value"], mr.inputs["Value"])
            fm = nt.nodes.new("ShaderNodeMixRGB"); fm.inputs["Color1"].default_value = (*flat, 1)
            src = em.inputs["Color"].links[0].from_socket
            nt.links.new(src, fm.inputs["Color2"]); nt.links.new(mr.outputs["Result"], fm.inputs["Fac"])
            nt.links.new(fm.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        m["painter_projected"] = True
        return m

    def billboard(self, name, loc, size):
        """A plane that always faces the painter camera (film.py parks it at the shot camera), wearing the
        plate unshaded: for a painted feature the set has no geometry for (the valley's hall). Without it
        the plate's high-contrast steps stretch across the far floor whenever a shot looks sideways."""
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=loc); ob = bpy.context.object; ob.name = name
        ob.scale = (size[0], size[1], 1.0)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        c = ob.constraints.new('TRACK_TO'); c.target = self.cam; c.track_axis = 'TRACK_Z'; c.up_axis = 'UP_Y'
        ob.visible_shadow = False
        ob.data.materials.append(self.painted(name + "_m", None, shade=False))
        return ob

    def tiled(self, name, box, size_m=4.0, shade=True):
        """A material that TILES a crop of the plate (box = u0,v0,u1,v1 in image fractions, v from the top)
        in world space: for the ground the cast walks on, which must read as the painting's grass from
        every camera — a projection puts sea under their feet when the shot swings off the master."""
        import sys as _s; _s.path.append("/workspace/venv/lib/python3.11/site-packages")
        from PIL import Image as _I
        src = bpy.path.abspath(self.plate.filepath); im = _I.open(src).convert("RGB"); W, H = im.size
        crop = im.crop((int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)))
        os.makedirs("/workspace/loopwork/plate_crops", exist_ok=True)
        path = f"/workspace/loopwork/plate_crops/{os.path.basename(src)[:-4]}_{name}.png"; crop.save(path)
        img = bpy.data.images.load(path)
        m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
        tc = nt.nodes.new("ShaderNodeTexCoord"); mp = nt.nodes.new("ShaderNodeMapping")
        asp = crop.size[0] / crop.size[1]; mp.inputs["Scale"].default_value = (1 / (size_m * asp), 1 / size_m, 1 / size_m)
        tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = img; tx.extension = 'MIRROR'
        nt.links.new(tc.outputs["Object"], mp.inputs["Vector"]); nt.links.new(mp.outputs["Vector"], tx.inputs["Vector"])
        em = nt.nodes.new("ShaderNodeEmission"); out = nt.nodes.new("ShaderNodeOutputMaterial")
        if shade:
            diff = nt.nodes.new("ShaderNodeBsdfDiffuse"); torgb = nt.nodes.new("ShaderNodeShaderToRGB")
            ramp = nt.nodes.new("ShaderNodeValToRGB"); ramp.color_ramp.interpolation = 'CONSTANT'
            k = float(os.environ.get("SET_SHADE", "0.82"))
            ramp.color_ramp.elements[0].color = (k, k * 0.97, k * 1.06, 1); ramp.color_ramp.elements[1].position = 0.5
            mix = nt.nodes.new("ShaderNodeMixRGB"); mix.blend_type = 'MULTIPLY'; mix.inputs["Fac"].default_value = 1.0
            nt.links.new(diff.outputs["BSDF"], torgb.inputs["Shader"]); nt.links.new(torgb.outputs["Color"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], mix.inputs["Color1"]); nt.links.new(tx.outputs["Color"], mix.inputs["Color2"])
            nt.links.new(mix.outputs["Color"], em.inputs["Color"])
        else:
            nt.links.new(tx.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
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
            # projected UVs are per-VERTEX and interpolated across each face, so a 40 m cone or a
            # one-face lake shows the plate offset from the dome (env_painted_ep1t_probes.png):
            # subdivide (simple) to ~1.5 m faces first, capped at level 6
            import math as _m
            mw = ob.matrix_world; vs = [mw @ v.co for v in ob.data.vertices]
            emax = max(((vs[e.vertices[0]] - vs[e.vertices[1]]).length for e in ob.data.edges), default=0.0)
            lv = int(min(2 if ob.name == "backdrop" else 6, max(0, _m.ceil(_m.log2(max(emax / 1.5, 1.0))))))
            if lv > 0:
                sd = ob.modifiers.new("painter_sub", 'SUBSURF'); sd.subdivision_type = 'SIMPLE'; sd.levels = lv; sd.render_levels = lv
            md = ob.modifiers.new("painter", 'UV_PROJECT'); md.uv_layer = "Painter"; md.projector_count = 1
            md.projectors[0].object = self.master_cam if ob.get("painter_fixed") else self.cam
            md.aspect_x = asp; md.aspect_y = 1.0; md.scale_x = 1.0; md.scale_y = 1.0
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
