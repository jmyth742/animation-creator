# Tir na nOg — complete pipeline description, for external review

Written 21 Sep 2026 to be handed to a reviewer who has not seen this project. It
describes what we build, how, what we have measured, and where we are stuck. Failures
and rejected approaches are included deliberately — they are the most useful part.

---

## 1. What we are making

A cel-shaded / anime-styled animated series based on Irish myth. Three episodes exist
end to end, each roughly 80 seconds, rendered at 1664x960, 16 fps:

- **Ep1 "The Nine Waterfalls"** — a valley of gold halls, waterfalls, a lake.
- **Ep2 "The First Snow"** — the same valley in winter.
- **Ep3 "The Farewell Cliff"** — a headland over the sea at sunset.

Two leads: **Oisin** (young mortal warrior, dark hair, green cloak, brown boots) and
**Niamh** (fae princess, long golden hair, green dress with white/gold bodice). Dialogue
scenes with narration, walking, one farewell beat per episode.

**Intended look:** painted anime backgrounds with flat cel characters over them, in the
tradition of hand-painted-BG anime rather than fully-3D-rendered CG anime.

---

## 2. Architecture principle

Blender 4.2 (EEVEE Next) is the deterministic renderer. Generative AI is used at
**design time only**, to make assets that are then frozen as files:

- character meshes (image-to-3D), baked once;
- face textures (FLUX img2img, baked into a UV atlas once);
- background plates (FLUX, upscaled 4x with ESRGAN, saved as PNG).

**No diffusion model runs in the render path.** Every frame is a Blender render of
fixed geometry and fixed textures, so there is zero temporal flicker and character
identity is a file property, not a prompt property. We consider this non-negotiable
and it is the one thing the pipeline does unambiguously well.

Hardware: one pod, RTX-class 24 GB GPU, **~27 CPU cores** (cgroup-limited; `nproc`
misleadingly reports 256), ~125 GB RAM, ~390 GB quota on /workspace.

---

## 3. Character pipeline, stage by stage

### 3.1 Design sheets
FLUX generates a 4-view turnaround (front, side, three-quarter, back) per character.

### 3.2 Geometry
**Hunyuan3D-2mv** (multi-view) consumes the turnaround and produces a textured mesh,
`<name>_mv_painted.glb`, roughly **40,000 triangles** with a 2048x2048 painted UV atlas.
We also evaluated **CharacterGen** (`cg_<name>_painted.glb`): better body proportions,
worse faces. Both are marching-cubes-style outputs: dense, irregular triangles,
coincident shells, non-manifold edges, no edge loops.

### 3.3 Retopology (added 21 Sep, previously missing)
This stage existed for props and had been **skipped for characters**, which we now
believe was the single biggest structural error in the pipeline.

`scripts/blender3d/retopo_character.py`:
1. import, join;
2. **voxel remesh** (Remesh modifier, VOXEL, size = height/280) → watertight, manifold,
   all-quad, and it fuses the coincident shells;
3. **QuadriFlow** to a 15,000-quad budget;
4. Smart UV unwrap;
5. **Cycles EMIT bake** of the original painted atlas onto the new UVs, so the look
   survives the topology change;
6. export `<name>_retopo.glb` + `<name>_retopo_base.png`.

Result: ~**60,000 triangles**, clean quads, versus 40,000 irregular triangles before.

**Two traps found here, both worth knowing:**
- QuadriFlow **refuses non-manifold input, warns, and returns `FINISHED` having changed
  nothing**. It must be preceded by a voxel remesh. We shipped a silent no-op twice.
- `object.dimensions` is **stale on a freshly linked copy**; reading it before
  `view_layer.update()` produced a voxel 3.6x too coarse, which destroyed detail and
  produced a mesh 7x heavier than intended at the same time.
- glTF export **splits vertices at UV seams**, so a manifold mesh becomes non-manifold
  on re-import. Any manifold-dependent op must happen before export.

### 3.4 Rigging
**UniRig** (template-free) produces `<name>_rigged.glb`. Bones arrive unnamed; a
geometric mapper (`scripts/day4/rig_map.py`) renames them to a kit skeleton (hips,
spine, thigh/shin/foot.L/R, arm/fore.L/R, head) — 28 bones for Oisin, 47 for Niamh
(hers include skirt/cloth groups). `character_kit.load_rigged_character` bakes facing
from the toe bones, puts feet at origin, normalises height, adds a jaw bone.

When the mesh is retopologised we do **not** re-run UniRig (that would invalidate every
retargeted motion clip). Instead `reweight_retopo.py` transfers all vertex groups from
the old skinned mesh to the new topology with a **Data Transfer modifier**
(`POLYINTERP_NEAREST`, `layers_vgroup_select_src='ALL'`), then binds to the same
armature. Note the **operator** `bpy.ops.object.data_transfer` cannot do this — its
`layers_select_src` only accepts ACTIVE/NAME/INDEX, not ALL.

### 3.5 Faces — the hardest part
Faces are **texture-space**, not geometry. There is no facial rig, no shape keys, no
modelled eyes or mouth. The head is whatever the image-to-3D model produced.

Current method, `face_project_mv.py` (multi-angle camera projection):
1. three **orthographic cameras** around the head's vertical axis at -40°, 0°, +40°;
2. from each, a flat unlit albedo render at 1024²;
3. each is redrawn by **FLUX img2img** (same seed; the side views at denoise 0.42, front
   at 0.55, so they stay anchored to the geometry);
4. a UV Project layer per camera, applied;
5. **one Cycles EMIT bake** whose material weights the three projections by
   `max(0, dot(N, -view_i)) ** 3`, normalised, fading to the original atlas away from
   the face;
6. output `<name>_face_hdbase_mv.png` at 2x atlas resolution (4096²).

Then `face_paint.py --keep-eyes` paints **viseme and blink variants** on that base:
`<name>_face_{base,m1..m5,blink}.png`. At render time `enable_face_variants` swaps the
image datablock per frame, driven by lip-sync data.

**History of what did not work on faces, and why:**
- A 4K atlas changed nothing at a 900px close-up.
- Higher FLUX denoise changed nothing.
- Subdividing the head (`CHAR_HERO_SUBSURF`) gave a marginal silhouette gain only.
- The **original** `face_repaint.py` cut a "face patch" out of the UV atlas and sent
  that to FLUX. This was never a face: the auto-generated atlas **scatters the face
  across many small islands**, so FLUX was redrawing fragments and painting stray eyes
  into them. Measured difference between input and output atlas was 0.5/255 — a no-op.
  This is why "the face won't sharpen" persisted for a long time.
- Single-camera projection (the fix before the current one) is correct front-on but
  **stretches at three-quarter**, which is exactly when the face reads warped.

### 3.6 Animation
- **MoMask** text-to-motion generates clips → BVH.
- `scripts/day4/retarget.py` retargets onto the UniRig skeleton (full delta on the hips,
  swing-only aim on limbs).
- **LAM Audio2Expression** produces ARKit-52 curves from the voice track;
  `arkit_bridge.py` reduces them to 6 viseme columns + blink events.
- Voice is edge-tts. Rhubarb visemes exist as an alternative lip-sync path.
- `FILM_STEP_ANIM=2` applies a **Stepped f-modifier** to the cast's f-curves at render
  time (animate on twos), never to the camera. Implemented, **not yet judged**.

---

## 4. Environment pipeline

Backgrounds are **painted plates projected onto simple geometry** — a matte-painting
approach, not modelled sets.

- Plates: FLUX-generated per location and per setup (`master`, `reverse`, `side`,
  `wider`, `closer`), upscaled 4x with **4x-AnimeSharp** ESRGAN → `<setup>_4x.png`.
- `scripts/blender3d/painter.py` holds the shared implementation:
  - a **painter camera** placed so its view matches the plate's composition (calibrated
    by rendering the set from it and overlaying the plate);
  - every near surface wears a material that samples the plate through a `Painter` UV
    map, optionally through the cel ramp;
  - a **UV Project modifier** from that camera fills those UVs — Blender's own
    projection, so the match is exact;
  - a 160 m **dome** carries the plate unshaded for sky and horizon.
- `film.py` then does **per-shot projection**: at the shot's middle frame the projector
  is moved to the *shot* camera and the plate is chosen by the shot's heading relative to
  the master heading (<50° master, <130° side, else reverse; `closer` for long lenses),
  and by season (`master_winter` never falls back to the summer master).
- Geometry the plate already paints is **deleted** in painted mode (hall, trees, cross,
  flowers, relief on the floor). The hall is instead a **camera-facing billboard** so its
  painted steps never stretch across the floor.
- The cliff shelf top **tiles a crop of the plate's own grass** so the cast stand on
  grass from every camera; its sides keep the projection.
- The lake projects from a **fixed** master camera when the shot swings >50° off the
  master heading, because a per-shot projection put the hall's steps on the water.
- Surfaces seen edge-on **fade to a flat plate colour** (grazing fade), since a
  projection streaks there.
- `SET_FLATTEN=<levels>` posterises the plate (added today, effect so far marginal).

Winter plate is FLUX img2img of the summer master (denoise 0.65, seed 6100), so it
shares the geometry calibration.

**Key limitation:** the valley has effectively **one painted angle** — its five "setups"
converged to near-copies of the master during generation. The cliff has genuine reverse,
side and wider plates.

---

## 5. Shading and line art

### Cel shader (`character_kit.cel_material`)
Albedo → HSV (hue +0.08, sat 1.15, value 0.62 in shadow) → a **3-stop constant ramp**
(t0 = 0.42, mid band width 0.08). Driven either by a Diffuse BSDF through
**Shader-to-RGB** (scene lighting) or, with `CEL_LIGHTVEC="x,y,z"`, by a **dot product
of the surface normal against a fixed per-character light vector** (the Arc System Works
approach). Rim light and specular were tested and **rejected** — they wash faces white
and lay flat patches on cloth.

Custom **normal editing** at render time (`CHAR_NORMALFIX=1`, Data Transfer from a
smoothed proxy, POLYINTERP_NEAREST) softens the terminator on the irregular meshes.
This must never run during the *build* — the transfer re-evaluates per keyframe and the
build takes an hour.

### Lines
**Freestyle**, silhouette/external contour only, crease lines off (they scribbled on the
irregular meshes; untested since retopology), minimum chain length filter, culling on.
`FILM_LINES` is the effective stroke width in pixels (scene unit thickness pinned to 1.0).
Adopted: 4.0 px at 832x480, 8.0 px at 1664x960. Line colour is now a **dark tint**
(0.17,0.11,0.13) at 0.82 alpha rather than near-black.

**Inverted hull outlines — implemented and rejected twice.**
`character_kit.add_outline_hull` builds a separate shell object whose custom normals are
cleared and smoothed, faces flipped, displaced along those normals, wearing a black
backface-culled material, keeping the armature modifier. Width is compensated for camera
distance and FOV so it is constant in pixels, capped to a fraction of the subject's
on-screen height, and skipped below 300 px.
- On the **original** meshes it was blotchy — the shell pokes through wherever local
  curvature exceeds the offset.
- On **retopologised** meshes it draws a correct, continuous outline (this confirms the
  studio technique), but it is still **too heavy at medium range**, blobs cloth, and on a
  distant thin figure the shell's far side shows through and fills the character in as a
  dark mass.
Freestyle remains the shipping renderer; the hull is behind `FILM_HULL=0`.

**Pencil+ 4** was investigated and ruled out: the Blender add-on is free but requires a
proprietary Windows/macOS render app, and we are on headless Linux.

---

## 6. Integration (added today, in response to "characters look superimposed")

Until today there was **no compositor and no grade in the pipeline at all**.

- `FILM_INTEGRATE=<haze>` — `integrate_cast` mixes every cast material toward the
  **plate's own mean colour** by camera depth (atmospheric perspective), plus one
  compositor grade (black lift + soft fog glow) over the whole frame.
- `FILM_CONTACT=1` — `contact_shadow` puts a soft dark ellipse under each figure,
  constrained to the hips, because a high sun hides its own shadow behind the figure.
- `SET_SUN="elev,azim"` — aims the key light at the plate's painted light direction,
  per episode (valley 52/118, winter 45/120, cliff 26/96).
- Tinted, thinner line (above).

---

## 7. Render and assembly

`scripts/ops/render_episode.sh <shots.json> <blend> <tag> <title> <audio_dir> <out.mp4> [parallel]`
renders shots in parallel, **counts only non-empty frames** (a full disk quota writes
0-byte PNGs), retries 3x, assembles, and loudnorms to -14 LUFS.

Cameras are defined in `build_film{,2,3}.py` as **hardcoded coordinate tuples** per shot
(position, target, lens, frame range, move: static/pan/dolly/orbit/crane). Shot lists are
emitted as JSON. There is no bounding-box framing, no headroom rule, no 180-degree line
enforcement.

Output is **PNG beauty frames only** — no depth, no line pass, no cryptomatte — so any
fix requires a full re-render rather than a compositing tweak.

---

## 8. Measured costs

| Thing | Cost |
|---|---|
| Episode master, 1664x960, 3 shots parallel | ~90 min |
| Freestyle | ~15 s/frame on the full set; dominates, CPU-bound |
| Frames without lines | ~0.35 s |
| GPU utilisation during a master render | **~0%** |
| CPU used during a master render | ~13 of ~27 available cores |

The renderer is Freestyle-bound on CPU. The GPU is essentially idle. Parallelism is set
to 3 and could roughly double.

---

## 9. Where we think we are going wrong — open questions for the reviewer

The user's current verdict is: **backgrounds look good, characters look bad and look
superimposed on the scene, faces look deformed.** We agree. Our current analysis:

1. **Detail-density mismatch.** The plate is a dense painting with fine texture, soft
   gradients and dozens of value steps. The character is a smooth, flat object with three
   tone bands and almost no internal shading. The eye reads two different pictures. We
   tried closing this from the background side (posterising the plate) with marginal
   effect.
2. **The character has no form.** In a back-lit shot the whole camera-facing side falls
   in one shadow band and the figure becomes a flat silhouette. We have just implemented
   a per-character light vector for this; it has **not yet visibly landed** and needs
   work on the ramp mapping.
3. **The head geometry is wrong.** Retopology cleaned the silhouette but cannot change
   proportions produced by marching cubes on an AI image. The face is a texture that is
   only ever approximately right.
4. **No internal line work.** Real cel characters carry drawn fold lines, hair strand
   lines, and shadow shapes. Ours carry a silhouette line and nothing else.
5. **Shot language.** We lean on dialogue close-ups, which is exactly where the pipeline
   is weakest, and we use extreme foreground over-shoulder heads that magnify a
   low-resolution painted face.

**Specific questions we would like scrutinised:**
- Is painted-plate projection plus flat cel characters the right pairing at all, or is
  the fidelity gap structural and better solved by rendering the sets as cel-shaded 3D?
- Is there a way to get production-grade anime faces from image-to-3D heads, or is
  clean modelled/VRM head geometry genuinely mandatory?
- What is the cheapest credible route to internal line work and fold shading on a
  character whose albedo texture is a flat AI-painted diffuse map?
- Given a CPU-bound Freestyle renderer on 27 cores, what is the right line-art strategy?

---

## 10. Repository map

```
scripts/blender3d/
  character_kit.py        cast library: load, cel_material, rigging, face variants,
                          integrate_cast, contact_shadow, add_outline_hull
  painter.py              painted-world projection (shared by all sets)
  valley_set.py           Ep1/Ep2 set          cliff_set.py    Ep3 set
  build_film.py/2/3       per-episode scene build -> .blend + shots.json
  film.py                 renders one shot; lines, per-shot plate, integration, grade
  face_project_mv.py      multi-angle face bake      face_paint.py  viseme/blink variants
  retopo_character.py     voxel + quad retopology with texture bake
  reweight_retopo.py      re-skin onto the existing UniRig skeleton
  deform_gate.py          skin acceptance contact sheet
  upscale_plates.py       4x ESRGAN on plates       winter_plate.py  seasonal plate
scripts/ops/
  render_episode.sh       parallel shot render + assemble + loudnorm
  masters_v5.sh / v6.sh   full-episode master runs
  SIXDAY_PLAN.md          every experiment and verdict, in date order
```

Every verdict, including failures, is recorded in `scripts/ops/SIXDAY_PLAN.md`. Review
artifacts (A/B sheets, probe strips, masters) are on the `production-outcomes` branch.
