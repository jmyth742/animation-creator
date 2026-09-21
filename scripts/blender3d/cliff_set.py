"""
The FAREWELL CLIFF stage (Episode 3): a grass headland ending in a cliff face
over the sea, a seastack offshore, a bent tree at the edge, rocks, and the boat
waiting on the shore below. Shelf top is FLOOR_Z; the sea is at SEA_Z.
build_set(sc) -> None. floor_fn(x, y) -> FLOOR_Z. OBSTACLES for plan_path.
"""
import math
import bpy, mathutils
import valley_set
import set_assets

FLOOR_Z = 4.5
SEA_Z = -5.5
OBSTACLES = [(-4.0, 14.0, 1.2), (5.5, 16.0, 1.4), (-8.5, 8.0, 1.1)]
PROPS = "/workspace/text-to-video/series/tir-na-nog-legend/meshes/props"

def floor_fn(x, y):
    return FLOOR_Z

def build_set(sc):
    grass = valley_set.toon_tex("cg", "grasstex.png", tile=1.6) if __import__("os").path.exists(valley_set.TEX + "/grasstex.png") else valley_set.toon("cg", (0.24, 0.40, 0.20))
    rock = valley_set.toon("cr", (0.35, 0.36, 0.38), shadow_mult=0.5)
    sea = valley_set.toon_tex("cs", "watertex.png", tile=14.0, shadow_mult=0.85) if __import__("os").path.exists(valley_set.TEX + "/watertex.png") else valley_set.toon("cs", (0.15, 0.30, 0.40), shadow_mult=0.8)
    sky = bpy.data.worlds.new("w"); sc.world = sky; sky.use_nodes = True
    sky.node_tree.nodes["Background"].inputs["Color"].default_value = (0.62, 0.70, 0.82, 1)
    # PAINTED WORLD (hybrid set): a PAINTER'S CAMERA frames the stage the way
    # the concept plate does; every near surface samples the plate at its own
    # screen position under that camera (camera projection), and a far
    # cyclorama carries the same projection for sky/sea. So the shelf top
    # takes the painting's grass, the cliff face its rock, the horizon its sea,
    # and the cast walks on geometry that IS the painting.
    import os as _os, math as _m
    plate_path = _os.environ.get("SET_PLATE", "/workspace/text-to-video/series/tir-na-nog-legend/sets/farewell_cliff/master.png")
    PLATE = None; PCAM = None
    if _os.path.exists(plate_path) and _os.environ.get("SET_BACKDROP", "1") not in ("", "0"):
        PLATE = bpy.data.images.load(plate_path)
        pc = bpy.data.cameras.new("painter"); pc.lens = 32; pc.sensor_width = 36
        PCAM = bpy.data.objects.new("painter_cam", pc); sc.collection.objects.link(PCAM)
        # framing chosen so the headland's cliff edge (y ~ 20.5) and the sea beyond
        # land where the plate paints them: from the left, slightly above the shelf
        # the plate paints the shelf from slightly above eye line, looking along
        # the edge; the horizon (44% up the image) must land at the film eye line
        # pose h from the calibration overlays (review/env_painter_calib.png)
        PCAM.location = (-17.0, -12.0, 8.0)
        tgt = mathutils.Vector((7.0, 20.0, 4.8)); PCAM.rotation_euler = (tgt - PCAM.location).to_track_quat('-Z', 'Y').to_euler()
        # a far dome for sky and sea, also camera-projected (no seam with the geometry)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=160.0, segments=64, ring_count=32, location=(0, 30, FLOOR_Z)); dome = bpy.context.object; dome.name = "backdrop"
        for poly in dome.data.polygons: poly.use_smooth = True
        print("BACKDROP plate", plate_path.split("/")[-2])
    PROJECTED = []   # objects that get a UV Project modifier from the painter camera (Blender's own projection = exact)
    def painted(name, fallback, sat=1.0, val=1.0, shade=True):
        if PLATE is None: return fallback
        m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
        uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = "Painter"
        tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = PLATE; tx.extension = 'EXTEND'; nt.links.new(uvn.outputs["UV"], tx.inputs["Vector"])
        hsv = nt.nodes.new("ShaderNodeHueSaturation"); hsv.inputs["Saturation"].default_value = sat; hsv.inputs["Value"].default_value = val
        nt.links.new(tx.outputs["Color"], hsv.inputs["Color"])
        em = nt.nodes.new("ShaderNodeEmission"); out = nt.nodes.new("ShaderNodeOutputMaterial")
        if shade:
            diff = nt.nodes.new("ShaderNodeBsdfDiffuse"); torgb = nt.nodes.new("ShaderNodeShaderToRGB"); ramp = nt.nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.interpolation = 'CONSTANT'; ramp.color_ramp.elements[0].color = (0.70, 0.68, 0.78, 1); ramp.color_ramp.elements[1].position = 0.5
            mix = nt.nodes.new("ShaderNodeMixRGB"); mix.blend_type = 'MULTIPLY'; mix.inputs["Fac"].default_value = 1.0
            nt.links.new(diff.outputs["BSDF"], torgb.inputs["Shader"]); nt.links.new(torgb.outputs["Color"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], mix.inputs["Color1"]); nt.links.new(hsv.outputs["Color"], mix.inputs["Color2"]); nt.links.new(mix.outputs["Color"], em.inputs["Color"])
        else:
            nt.links.new(hsv.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        m["painter_projected"] = True
        return m
    def project_all():
        """After the geometry exists: give every object wearing a painted material
        a 'Painter' UV layer and a UV Project modifier from the painter camera with
        the plate's aspect — the same matrix the renderer uses, so the overlay
        calibration is exact."""
        if PLATE is None: return
        asp = PLATE.size[0] / PLATE.size[1]
        for ob in list(sc.objects):
            if ob.type != 'MESH' or not any(m and m.get("painter_projected") for m in ob.data.materials): continue
            if "Painter" not in ob.data.uv_layers: ob.data.uv_layers.new(name="Painter")
            md = ob.modifiers.new("painter", 'UV_PROJECT'); md.uv_layer = "Painter"; md.projector_count = 1
            md.projectors[0].object = PCAM; md.aspect_x = asp; md.aspect_y = 1.0; md.scale_x = 1.0; md.scale_y = 1.0
            # the projection must see the FINAL surface: modifiers.new appends, so it
            # is already last; assert by name (RNA wrappers are fresh objects each
            # access, so an `is` comparison would spin forever)
            assert ob.modifiers[-1].name == md.name
            PROJECTED.append(ob.name)
        print("PAINTER projected onto", PROJECTED)
    if PLATE is not None:
        # the dome: the plate straight, unshaded. Where the painter camera sees
        # near geometry the dome is occluded anyway; the plate's own painted
        # cliff shows through only where geometry is missing (the log tells).
        dome.data.materials.append(painted("p_dome", None, shade=False))
    # headland shelf (top at FLOOR_Z), cliff face, sea
    rocktex = valley_set.toon_tex("crt", "rocktex.png", tile=6.0, shadow_mult=0.55) if __import__("os").path.exists(valley_set.TEX + "/rocktex.png") else rock
    for mat in (rocktex, grass, sea):
        # images are sampled by XY: vertical faces streak. Box projection.
        if mat.use_nodes:
            for nd in mat.node_tree.nodes:
                if nd.type == 'TEX_IMAGE':
                    nd.projection = 'BOX'; nd.projection_blend = 0.25
    def _uv_scale(ob, k):
        # toon_tex samples OBJECT-local coordinates: bake the object scale into
        # the mesh so a 36 m slab tiles like the valley floor (unscaled grid)
        bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.ops.mesh.primitive_cube_add(location=(0, 8, FLOOR_Z - 3)); ob = bpy.context.object
    ob.name = "headland"; ob.scale = (18, 8, 3); ob.location.y = 12.0; ob.data.materials.append(painted("p_grass", grass)); _uv_scale(ob, 22)
    # round the far (sea-side) corners into the plate's promontory
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='DESELECT'); bpy.ops.object.mode_set(mode='OBJECT')
    for v in ob.data.vertices: v.select = (v.co.y > 12.0 + 7.0)
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.bevel(offset=7.0, segments=6, affect='VERTICES'); bpy.ops.object.mode_set(mode='OBJECT')
    # the cliff face: three staggered rock slabs, not one flat wall
    for i, (x, y, sx, sy, sz, rz) in enumerate([(-7, 20.6, 8, 0.9, 5.6, 0.05), (4, 20.3, 9, 1.1, 5.8, -0.07), (13, 20.8, 7, 0.8, 5.4, 0.12)]):
        bpy.ops.mesh.primitive_cube_add(location=(x, y, -1)); ob = bpy.context.object
        ob.name = f"cliff{i}"; ob.scale = (sx, sy, sz); ob.rotation_euler = (0.06 * (i - 1), 0, rz)
        ob.data.materials.append(painted("p_rock", rocktex, sat=0.85, val=0.95)); _uv_scale(ob, 6)
    # the cliff FOOT: the plate's rock bulges toward the viewer at the base; a
    # lower, forward slab catches those pixels on a near-vertical face instead
    # of letting them streak across the sea plane (env_painter_proj_check.png)
    bpy.ops.mesh.primitive_cube_add(location=(0, 18.6, SEA_Z - 0.5)); ob = bpy.context.object
    ob.name = "cliff_foot"; ob.scale = (14, 1.6, 2.6); ob.rotation_euler = (0.35, 0, 0.03)
    ob.data.materials.append(painted("p_rock", rocktex, sat=0.85, val=0.95)); _uv_scale(ob, 6)
    bpy.ops.mesh.primitive_cube_add(location=(24, 6, FLOOR_Z - 3.5)); ob = bpy.context.object
    ob.name = "shoulder"; ob.scale = (7, 9, 3); ob.location.y = 8.0; ob.rotation_euler.z = 0.2; ob.data.materials.append(painted("p_grass2", grass)); _uv_scale(ob, 12)
    bpy.ops.mesh.primitive_plane_add(size=260, location=(0, 60, SEA_Z)); ob = bpy.context.object
    ob.name = "sea"; ob.data.materials.append(painted("p_sea", sea, sat=1.05)); _uv_scale(ob, 1)
    # a shingle shore at the cliff foot, where the boat waits
    bpy.ops.mesh.primitive_cube_add(location=(6, 24, SEA_Z + 0.15)); ob = bpy.context.object
    ob.name = "shore"; ob.scale = (7, 3.5, 0.3); ob.data.materials.append(painted("p_shore", rocktex, sat=0.85, val=0.95)); _uv_scale(ob, 1)
    set_assets.place(f"{PROPS}/benttree_painted.glb", "bent", (5.5, 16), 4.2, rot_z=0.6, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/seastack_painted.glb", "stack", (-14, 38), 9.5, floor_fn=lambda x, y: SEA_Z)
    set_assets.place(f"{PROPS}/seastack_painted.glb", "stack2", (26, 40), 6.5, rot_z=1.9, floor_fn=lambda x, y: SEA_Z)
    set_assets.place(f"{PROPS}/rock_painted.glb", "r1", (-4, 14), 1.1, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/rock_v2_painted.glb", "r2", (-8.5, 8), 0.9, rot_z=2.1, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/stones_painted.glb", "st1", (9, 10), 0.7, rot_z=0.8, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/bush_painted.glb", "b1", (-12, 12), 1.3, floor_fn=floor_fn)
    set_assets.place(f"{PROPS}/boat_painted.glb", "boat", (7.5, 24.5), 1.4, rot_z=0.35, floor_fn=lambda x, y: SEA_Z + 0.3)
    sun = bpy.data.lights.new("sun", "SUN"); sun.energy = 4.0; sun.color = (1.0, 0.84, 0.62)
    so = bpy.data.objects.new("sun", sun); so.rotation_euler = (math.radians(70), 0, math.radians(60))
    sc.collection.objects.link(so)
    if PLATE is not None: project_all()
    print("CLIFF SET BUILT")
