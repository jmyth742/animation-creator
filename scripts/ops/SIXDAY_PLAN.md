# The 6-day campaign — GPU never idle, quality compounding daily
# Goal: incrementally reach studio-grade characters/setup. Each day ends
# with judgment artifacts; each morning a session judges + writes the next
# day's marathon informed by results. Exporter runs inside every marathon.

## Day 1 — Craft & repairs (shift 4, script ready: go4.sh)
- Diagnose + fix marathon3 P6 (verdict renders produced no frames)
- NORMAL EDITING: transfer smoothed normals onto both characters (Data
  Transfer from smooth proxy) -> clean cel shading bands on faces/bodies
- Judge-and-adopt harness: stack turntables incl. normal-edit variant
- Re-render BOTH episodes with the adopted clean stack -> v2cast masters
- Overnight sweeps: line thickness (1.0/1.4/2.0), flat palette (10/14/20)
  in motion, denoise winner into the viseme chain
DELIVERABLES: char stacks judged, 2 episodes re-mastered, grids exported

## Day 2 — New generation models (CharacterGen + UniRig + TRELLIS.2)
- Install CharacterGen (anime-native img->3D) + UniRig (auto skeleton+skin)
- Run our existing sheets through it; UniRig-rig the winners
- TRELLIS.2 install; A/B our leads + hero props (hall, trees) vs Hunyuan
- Turntable A/Bs vs current cast; walk test on a UniRig skeleton
DELIVERABLES: verdict on replacing mesh source and numpy skinning

## Day 3 — Facial acting chain (the exponential unlock)
- NVIDIA Audio2Face-3D samples: install, run on its sample head ->
  prove audio -> ARKit blendshape animation -> Blender import end-to-end
- OmniFaceRig code hunt; if released, auto-blendshape OUR heads
- Fallback bridging: map A2F ARKit curves onto our texture-viseme system
  (better timing/shapes even without mesh blendshapes)
- USER TASK (1 hour, optional but decisive): VRoid both leads -> VRM
  upload; ARP quick-rig gives blendshapes+visemes for free
DELIVERABLES: working audio->face-acting chain on at least one head

## Day 4 — Motion library
- Motion Gen addon (8GB VRAM) or HY-Motion weights: text->motion
- Build the action library: walk styles, idle, turn, sit, kneel, point,
  embrace; retarget to our rig (or Day-2's UniRig skeletons)
- Acting A/B: one dialogue scene re-staged with library motion
DELIVERABLES: gait/gesture upgrade judged in motion

## Day 5 — Integration + Episode 3
- Adopt everything judged from days 1-4 into character_kit/build_film
- EPISODE 3 written + produced in the (recomposed) cliff stage with the
  full new stack — the proof the pipeline compounds
- Re-render eps 1+2 final masters with the same stack
DELIVERABLES: three episodes, one coherent new-quality bar

## Day 6 — Polish, regression, release
- Selftest suite fixed + green; determinism seed applied if found
- 4K masters x3, trailer v2 (with ep3 shots), pilot v2, upload kit refresh
- Docs: pipeline documentation refresh (CLAUDE.md + docs/) so any future
  session or contributor can run the whole studio
- Full final export; IMPROVEMENTS.md groomed for the next campaign
DELIVERABLES: releasable 3-episode season package on GitHub

## Standing orders (all six days)
- All working state under /workspace; never /tmp
- Every phase: verify an artifact (frame/probe) before checking off
- Export inside every marathon; judgment sheets named review/dayN_*
- GPU gaps auto-filled: each day's script ends with a sweep bank
  (seed variants of props, extra coverage passes, ambience renders)
  so the card is never idle while awaiting judgment
- RECOMMENDED ONCE: install the hourly export cron on the pod:
  crontab: 17 * * * * bash /workspace/export_outcomes.sh >> /workspace/export.log 2>&1
