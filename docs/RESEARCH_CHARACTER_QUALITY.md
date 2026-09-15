# Research: paths to studio-grade characters & facial animation
Compiled 2026-09-15 from live web research. Confidence marked per item.
Context: our stack = FLUX sheets -> Hunyuan3D-2mv -> texture visemes ->
procedural gait, on one RTX 3090, everything headless Blender.

## 1. Character generation — what beats our current chain

- **CharacterGen (SIGGRAPH'24, open)** — anime-NATIVE image-to-3D with
  multi-view pose canonicalization; outputs canonical A-pose characters and
  pairs with **UniRig** for auto-rigging. The closest thing to
  "our chain but built for anime characters specifically." HIGH priority
  test. https://github.com/zjp-shadow/CharacterGen
- **TRELLIS.2 (Microsoft, MIT, 4B params)** — up to 1536^3 PBR assets,
  connected-surface meshes. Strongest general-purpose open model right now;
  worth an A/B against Hunyuan for our leads and hero props.
  https://trellis2.netlify.app/
- **Auto-rigging**: **UniRig** ("One Model to Rig Them All", 2025) rigs
  diverse skeletons on arbitrary meshes — would replace our 14-bone numpy
  skinning with real skeletons incl. hands. https://arxiv.org/pdf/2504.12451
- Consensus caveat (multiple sources): AI topology still lacks animation
  edge loops — auto-rig is fine for our shot distances; hero close-up
  deformation still favours purpose-built meshes.

## 2. Facial animation — the real unlock exists and is open

- **NVIDIA Audio2Face-3D — open samples on GitHub**: audio in ->
  **ARKit blendshape animation out**, with emotion control. This is the
  bridge from our WAV files to true face acting — IF our heads have ARKit
  blendshapes. https://github.com/NVIDIA/Audio2Face-3D-Samples
- **OmniFaceRig (2026)** — fully automatic face rigging (inner-mouth aware)
  across diverse topologies via deformation transfer + dense registration:
  the missing piece that puts blendshapes ON generated heads unattended.
  Check for code release. https://arxiv.org/pdf/2606.08043
- Model families for audio->3D face: UniTalker (unified, ECCV'24),
  FaceDiffuser (works on blendshape data), StreamingTalker (2025 SOTA,
  autoregressive diffusion). https://arxiv.org/html/2408.00762v1
- **The strategy this implies**: heads with ARKit blendshapes (VRoid gives
  them for free; OmniFaceRig may add them to generated heads) + Audio2Face
  -class audio->blendshape = real acting, replacing texture visemes.

## 3. Body motion

- **HY-Motion 1.0 (Tencent, Dec 2025)** — large text-to-motion, flow
  matching; the current strong open line. https://arxiv.org/html/2512.23464v1
- **Motion Gen** Blender addon: text->motion inside Blender, needs only
  ~8GB VRAM — fits alongside our stack. https://haseebahmed295.github.io/motion_gen/
- CMU BVH remains free and Blender-native for locomotion libraries;
  MoMask/MDM are MIT-code but non-commercial training data (fine for R&D,
  check before monetised episodes).

## 4. Cel rendering craft (what makes 3D read hand-drawn)

- **Goo Engine** (DillonGoo Studios' Blender fork, open) — purpose-built
  anime NPR: curvature-based shading nodes, per-part shader groups. Study
  or adopt its techniques; binaries via Patreon, source open.
- Stock-Blender path (our current): Shader-to-RGB + Line Art modifier is
  the accepted baseline; the missing industry tricks we should add:
  **normal editing** (smoothed/transferred normals so face shading bands
  are clean, not lumpy — directly attacks our terminator noise) and
  **face-shadow gradient maps** (hand-authored shadow ramps for faces).
  https://www.strayspark.studio/blog/how-to-get-anime-toon-look-blender

## 5. Product angle — what creators actually adopt

- Evidence point: a solo creator shipped a **12-episode donghua series**
  with ComfyUI+SDXL+LoRAs+Blender NPR+TTS — the market for "one person,
  whole series" pipelines is real and active.
  https://github.com/Comfy-Org/ComfyUI/discussions/16004
- ComfyUI's portable JSON workflows are cited as the reason studios keep
  series style locked across episodes — our episode-JSON + deterministic
  renders is the same virtue, stronger. Position SHOWRUNNER as
  "the series-consistency machine."
- VRoid->Blender pipelines are mature (Auto-Rig Pro quick-rig gives
  one-click rigs WITH visemes/blendshapes) — the VRoid road is paved.
  https://blenderartists.org/t/vroid-avatars-to-blender-via-arp-quick-rig/1598623

## Ranked plan for OUR pipeline

1. **Normal-editing + face gradient pass** (craft, no new models): transfer
   smoothed normals onto character faces so cel bands run clean. Cheap,
   big, immediate.
2. **CharacterGen + UniRig test-drive**: anime-native generation and real
   auto-rigging — could replace both our mesh source AND numpy skinning.
3. **Blendshape strategy**: try OmniFaceRig (if code released) on our
   heads; else VRoid heads (blendshapes included) grafted or full VRoid
   cast; then **Audio2Face-3D samples** for audio->ARKit acting. This is
   the "real mouths and eyebrows" endgame.
4. **TRELLIS.2** for hero props + set pieces (MIT, PBR, high res).
5. **Motion Gen / HY-Motion** for the gait+gesture library upgrade.
6. Keep positioning: deterministic series-consistency + one-command
   episodes is the differentiator no hosted tool offers.
