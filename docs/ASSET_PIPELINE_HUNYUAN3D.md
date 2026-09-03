# Asset Pipeline — Hunyuan3D 2.1 → QuadriFlow → Blender

Implementation spec for the **prop and set asset pipeline**. Companion to
`DETERMINISTIC_RENDER_PATH.md`.

## Scope

**In scope:** props, set dressing, architecture, vehicles, non-deforming background
objects. Anything that is static or animated only by object transform.

**Out of scope:** characters. Characters come from VRoid/MPFB2 with clean topology and
existing blendshapes. Do not run character meshes through this pipeline — generated
topology cannot carry facial deformation, and retopologising a face by hand costs more
than building the character parametrically in the first place.

---

## Stage flow

```
concept prompt (from script/set bible)
      │
      ▼
[1] FLUX.1-schnell  ──► concept image (single object, plain bg, 3/4 view)
      │
      ▼
[2] Hunyuan3D-2.1 shape  ──► raw mesh (dense triangles, ~200k–1.5M faces)
      │
      ▼
[3] Hunyuan3D-2.1 paint  ──► PBR textures on raw mesh
      │
      ▼
[4] Blender: cleanup  ──► floaters removed, manifold, scaled, oriented
      │
      ▼
[5] Blender: QuadriFlow remesh  ──► clean quad topology at face budget
      │
      ▼
[6] Blender: UV unwrap + bake raw→clean  ──► basecolor/roughness/metallic/normal
      │
      ▼
[7] Blender: LOD + collection wrap  ──► asset .blend, ready to link
      │
      ▼
[8] manifest write + QA gate
```

Every stage is content-addressed and cached. Stage N reruns only if its inputs changed.

---

## Directory layout

```
assets/
  concepts/          <hash>.png            stage 1 output
  raw/               <hash>/mesh.glb       stage 2+3 output (never edited by hand)
  clean/             <slug>.blend          stage 7 output — this is what scenes link
  textures/          <slug>/*.png          baked maps
  manifest.json      registry of every asset
cache/
  <stage>/<hash>/    intermediate artifacts
```

Scenes **link** (not append) from `clean/`. One source of truth per asset; regenerate an
asset and every scene picks it up.

---

## Stage 1 — Concept image

Reuse the existing FLUX setup. Constraints that materially improve stage 2:

- Single object, centred, **plain neutral background**
- Three-quarter view, slight elevation
- Even diffuse lighting, no hard shadows, no strong rim light
- No motion blur, no depth of field
- Full object in frame with margin — no cropping

Bake these into a fixed suffix appended to every asset prompt. Background removal happens
in stage 2 but a clean plate makes it reliable.

---

## Stage 2+3 — Hunyuan3D 2.1

Repo: `Tencent-Hunyuan/Hunyuan3D-2`, branch/release **2.1** (fully open weights + training
code + PBR paint). Note the 2.1 release restructured modules relative to 2.0 — verify the
import paths against the repo's `demo.py` before wiring, they moved to `hy3dshape` /
`hy3dpaint`.

Skeleton:

```python
# tools/gen_asset.py
from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline
from hy3dshape.rembg import BackgroundRemover
from hy3dpaint import Hunyuan3DPaintPipeline

shape = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained("tencent/Hunyuan3D-2.1")
paint = Hunyuan3DPaintPipeline.from_pretrained("tencent/Hunyuan3D-2.1")

img  = BackgroundRemover()(load(concept_png))
mesh = shape(image=img, num_inference_steps=50, octree_resolution=380,
             generator=torch.manual_seed(seed))[0]
mesh = paint(mesh, image=img)
mesh.export(raw_dir / "mesh.glb")
```

**Pin the seed** and store it in the manifest. Asset generation must be reproducible or
you cannot regenerate a set six months into production and get the same thing.

Run this out-of-process from Blender — separate venv, separate GPU allocation. Blender's
bundled Python and the torch stack do not want to share an environment.

---

## Stage 4 — Cleanup (Blender, headless)

Before remeshing. Order matters.

1. Import GLB, join into a single object
2. **Remove floaters** — separate by loose parts, drop parts under a volume threshold
   relative to the largest part (~0.5%)
3. Merge by distance (0.0001) to weld duplicate verts
4. Delete degenerate faces, recalculate normals outside
5. **Scale to real-world units** from the manifest's `real_height_m`. Generators output
   arbitrary scale; a chair that is 40m tall breaks lighting, DOF and physics.
6. Orient: -Y forward, +Z up. Origin to base centre, not bounding-box centre — assets sit
   on floors.

Steps 5 and 6 are the ones that get skipped and then cause a week of confusing bugs.

---

## Stage 5 — QuadriFlow remesh

```python
bpy.ops.object.quadriflow_remesh(
    mode='FACES',
    target_faces=budget,
    use_preserve_sharp=True,
    use_preserve_boundary=True,
    use_mesh_symmetry=False,
    seed=0,
)
```

Face budgets by asset class — set these in the manifest, not by feel:

| Class | Target faces | Notes |
|---|---|---|
| Hero prop (handled, appears in CU) | 15,000–25,000 | |
| Set dressing (mid-ground) | 4,000–8,000 | |
| Background filler | 1,000–2,000 | |
| Architecture / large static | 8,000–20,000 | often better hand-modelled |

QuadriFlow caveats to code around:

- It fails or produces garbage on **non-manifold** input. Stage 4 must guarantee manifold;
  add an explicit assertion and fail the asset rather than passing junk downstream.
- It struggles with very thin geometry (wires, blades, plant leaves). For those, skip
  QuadriFlow and use decimate + planar cleanup instead. Flag the class in the manifest.
- It ignores UVs entirely, which is why baking is a separate stage.
- It is single-threaded and slow on high face counts. Decimate to ~150k before remeshing
  if the raw mesh is over ~500k; the quad result is indistinguishable and it's 10x faster.

---

## Stage 6 — UV + bake

1. Smart UV Project on the clean mesh (island margin 0.02), or Blender's UV packing with
   an angle-based unwrap for hero props
2. Load raw mesh (with Hunyuan's PBR textures) as the *source*, clean mesh as *active*
3. Bake selected-to-active with cage extrusion ≈ 2% of the object's bounding radius
4. Bake channels: `basecolor`, `roughness`, `metallic`, `normal` (tangent space)
5. Texture sizes: 2K hero, 1K dressing, 512 background
6. Denoise/dilate the baked maps, write to `textures/<slug>/`

Cage extrusion is the parameter that will cause artifacts. Make it per-asset overridable
in the manifest rather than a global constant.

---

## Stage 7 — Asset .blend

Wrap the result so scenes can link it:

- One **collection** named `asset_<slug>`, containing the mesh + material
- Empty named `origin` at the base, for placement
- Optional named empties for attach points (`handle`, `seat`, `top_surface`) — the scene
  compiler uses these for character interaction
- Custom properties on the collection: `slug`, `class`, `real_height_m`, `source_hash`
- Save to `clean/<slug>.blend`

---

## Manifest entry

```jsonc
{
  "slug": "kitchen_kettle",
  "class": "hero_prop",
  "concept_prompt": "a dented steel stovetop kettle, ...",
  "concept_hash": "a3f1...",
  "seed": 1234,
  "hunyuan": { "version": "2.1", "octree_resolution": 380, "steps": 50 },
  "real_height_m": 0.24,
  "target_faces": 18000,
  "remesh": "quadriflow",
  "texture_size": 2048,
  "cage_extrusion": 0.004,
  "attach_points": ["handle"],
  "final_faces": 17842,
  "status": "approved"
}
```

`status` gates it into scenes. Nothing renders from an unapproved asset.

---

## Stage 8 — QA gates

Fail the asset (don't silently pass) if any of these trip:

- Non-manifold edges > 0 after stage 4
- Final face count more than 20% off budget
- Any face area below epsilon (degenerates survived)
- Bounding box height deviates >10% from `real_height_m`
- Baked normal map is flat (bake silently failed — very common, catch it)
- UV islands overlap above threshold

Render a six-angle turntable contact sheet per asset into `qa/<slug>.png` for eyeball
review. This is the cheapest quality control in the whole pipeline.

---

## Execution notes

- Blender runs `--background --python`. Keep each stage a separate script with a JSON
  in/JSON out contract so stages are individually testable and rerunnable.
- Hunyuan3D 2.1 has an official Blender addon and community ComfyUI wrappers. Both are for
  interactive use — for the pipeline, call the Python API directly and stay headless.
- Batch stage 2 on RunPod alongside the existing musubi-tuner work; stages 4–7 are CPU and
  run locally.
- Budget roughly: generation minutes per asset, remesh seconds to minutes, bake seconds.
  The bottleneck is your GPU queue, so generate a whole set's props in one batch.

---

## Open items

- Thin-geometry class needs a separate path (decimate, not QuadriFlow) — decide the
  detection heuristic
- Whether to keep the raw mesh as a hidden LOD0 for extreme close-ups
- Material convention: one shared toon shader node group driven by baked maps, so a global
  look change is one edit rather than N

---

## Fit assessment (code session, 2026-09-03)

**Adopted as the props/sets track.** This spec is the industrial version of
the `prop_sheet.py` sketch: content-addressed stages, the stage-4 cleanup
order, QuadriFlow with budgeted face counts, bake, link-don't-append, and
QA gates that fail loudly — all congruent with this repo's silent-failure
doctrine. Implementation begins with the three props whose FLUX concepts
are already rendered (hall, tree, cross) and `valley_set.py` switches its
primitives for linked assets as they pass QA.

**One deviation, deliberate:** the spec puts characters out of scope
because "generated topology cannot carry facial deformation." Correct —
and this pipeline no longer asks it to. Faces here are TEXTURE-SPACE
(drawn eyes, viseme variants, blink frames rasterised through the UV
triangles — `face_paint.py`), so Hunyuan characters stay viable for the
current stylised look. VRoid/MPFB2 remains the upgrade path if we ever
need true blendshape acting; MPFB2 is scriptable headless and is the
candidate to trial first (parametric body + clean topology + real rig).

**Version note:** we run Hunyuan3D **2.0** (installed, proven); the spec
targets **2.1** (PBR paint, `hy3dshape`/`hy3dpaint` module split). Adopt
2.1 with the props track — its PBR outputs then feed stage 6 baking as
specified. Characters stay on 2.0 until a 2.1 A/B on the same sheets.
