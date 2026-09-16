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

## Day 1 VERDICT (judged 15 Sep, fresh session) — see review/day1b_*, day1c_*, day1d_*
- ROOT CAUSE of every empty verdict render (marathon3 P6, marathon4 P4):
  film.py used the Blender 2.7x name `select_by_group`; 4.2 = `select_by_collection`.
  Fixed + verified (3-frame render). Freestyle also treated FILM_LINES=0 as ON.
- CHAR_SMOOTH=40 is DESTRUCTIVE: 40 Laplacian iterations shred hair/cloth
  into tatters (the "black scribble" columns were shredded meshes, not lines).
  Dropped. Do not revive without a <=5-iteration test first.
- NORMAL EDITING (CHAR_NORMALFIX=1): softer, rounder face terminator; the
  nearest-polygon mapping grains the skin, POLYINTERP_NEAREST (now default)
  does not. ADOPTED.
- LINES: crease edges = scribbles on AI meshes (off by default now);
  silhouette-only + chains <20px dropped is clean; 2.0px reads most "drawn".
  ADOPTED: FILM_LINES=2.0 FILM_LINE_MINLEN=20. Ext-contour-only is too faint.
- LINE WEIGHT IN MOTION (day1_linewidth_ab.mp4, judged 07:25): 1.4 faint,
  2.0 right, 2.6 clumps in hair. Freestyle thickness is ABSOLUTE pixels and
  the film blends are 832x480, so the Day-5 1664x960 masters need ~4.0 to
  match; v2cast masters are 480p verdict renders, not finals.
- COST: Freestyle is CPU-bound, ~15s/frame on the full set (culling on);
  frames without lines are 0.35s. render_episode.sh renders 6 shots in
  parallel (256 cores) so an episode is ~1h wall, not 5h.
- Grids: turntables used the factory default lineset on top of ours — fixed
  in turn_grid.py (clears linesets first). marathon4's own grids are invalid.
- OUTSTANDING from Day 1, running in marathon5 P1: both v2cast masters +
  day1_linewidth_ab.mp4 (1.4/2.0/2.6 in motion). Flat-palette-in-motion sweep
  deferred to Day 5 integration (marathon3's flat variants exist as stills).

## Day 2 AS LAUNCHED (studio_marathon5.sh, go5.sh) — 15 Sep
- P1 Day-1 masters with the adopted stack (parallel shots), P2 three venv
  installs (UniRig / CharacterGen / TRELLIS.2 under /workspace/envs) in
  parallel with P1, P4 UniRig rig+skin+merge on both leads + rig_test.py walk
  render, P5 CharacterGen on the 34 sheets -> A/B turntables vs current cast,
  P6 TRELLIS.2 on leads + hall + benttree vs Hunyuan, P7 prop sweep bank.
  Judge: day2_unirig_walk_*.mp4, day2_charactergen_ab_*.png, day2_trellis_ab_*.png

## Day 2 — New generation models (CharacterGen + UniRig + TRELLIS.2)
- Install CharacterGen (anime-native img->3D) + UniRig (auto skeleton+skin)
- Run our existing sheets through it; UniRig-rig the winners
- TRELLIS.2 install; A/B our leads + hero props (hall, trees) vs Hunyuan
- Turntable A/Bs vs current cast; walk test on a UniRig skeleton
DELIVERABLES: verdict on replacing mesh source and numpy skinning

## Day 2 VERDICT (judged 15 Sep 08:00)
- UniRig WORKS: both leads rigged from the painted glb in ~4 min each —
  real humanoid skeletons (Oisin 28 bones incl. fingers; Niamh 47 incl. hair
  chains), skinned, and they animate in Blender (review/day2_unirig_walk_*.mp4,
  day2_unirig_strip_*.png). Bones are UNNAMED (bone_N): scripts/day2/rig_test.py
  picks limbs by rest geometry; the arm picker must skip head-height chains
  (it grabbed Niamh's hair). VERDICT: replace the 14-bone numpy skinning with
  UniRig rigs — Day 4's motion library retargets onto these skeletons.
- TRELLIS.2: installed, imports, 16 GB weights cached, but its image encoder
  facebook/dinov3-vitl16-pretrain-lvd1689m is GATED (HF 401). USER: accept the
  DINOv3 license on huggingface.co and put HF_TOKEN in /workspace/.env, then
  `bash /workspace/loopwork/p6_redo.sh`. Also: this box's OpenCV has no
  OpenEXR, so the PBR preview is optional (driver handles it).
- CharacterGen (run 16 Sep, review/day2_charactergen_ab_oisin.png, _faces_):
  2D stage gives four clean, consistent turnaround views straight from our
  sheet (review/day2_charactergen_views_oisin.png) — better source material
  than the FLUX left/back views. 3D stage: BETTER BODY than Hunyuan-mv
  (proportions, T-pose, cape/boots intact, faithful hair colour) but a WORSE
  FACE texture (smeared eyes). Meshes face +Y (turn_grid TURN_YAW=180).
  Day-5 candidate: CharacterGen body + our FACE_BASE HD repaint, then UniRig.
- CharacterGen Niamh (review/day2_charactergen_ab_niamh.png, _faces_): WINS
  on body AND face (full dress silhouette, clear eyes + smile) vs the
  current washed face. MESH-SOURCE VERDICT: CharacterGen for both leads;
  Oisin's face via FACE_BASE HD repaint; then UniRig (T-pose helps).
- CharacterGen: NOT run — 19 GB of weights need the disk-space decision
  (see workspace-environment-traps). Installer is fixed (per-package pip,
  huggingface_hub 0.25 for diffusers 0.24, CUDA env for nvdiffrast).
- Day-1 masters: both v2cast episodes verified frame-by-frame (480p verdict
  renders); ep1's closing shot was re-rendered after the quota incident.
- CORRECTION (15 Sep 10:40): the v2cast masters carry the new LINES but NOT
  the normal editing — CHAR_NORMALFIX only acted inside build_film (blend
  build time) and the film blends predate it; film.py never read it. Normal
  editing now happens at RENDER time in film.py (no per-frame cost measured).
  Build-time NORMALFIX also stalls build_film for an hour (the transfer is
  re-evaluated on every keyframed frame) — never export CHAR_NORMALFIX into
  a build. v3cast masters (complete stack) queued: loopwork/masters_v3.sh.
- v3cast masters (complete stack) done 15 Sep 17:41, both frame-verified.
  At 480p a v2cast/v3cast frame is near-identical: normal editing is a
  close-up/hi-res refinement, not a film-scale change. BOTH episodes stage
  Oisin's dialogue close in profile (ep2 CLOSE cam 1.7,7.4 -> -0.75,8.75 too)
  — restage to 3/4 before Day 5 masters or his mouth never reads.
- MASTER RECIPE (judged 15 Sep 08:20, review/day1_lines_480vs960.png): 4.0px
  @1664x960 matches 2.0px @480p. Single instance 19s/frame at 960p; keep
  hi-res parallelism at 2-3 (six instances contend 8x). Day 5 masters:
  FILM_RES=1664x960 FILM_LINES=4.0 FILM_LINE_MINLEN=40.

## Day 3 — Facial acting chain (the exponential unlock)
- NVIDIA Audio2Face-3D samples: install, run on its sample head ->
  prove audio -> ARKit blendshape animation -> Blender import end-to-end
- OmniFaceRig code hunt; if released, auto-blendshape OUR heads
- Fallback bridging: map A2F ARKit curves onto our texture-viseme system
  (better timing/shapes even without mesh blendshapes)
- USER TASK (1 hour, optional but decisive): VRoid both leads -> VRM
  upload; ARP quick-rig gives blendshapes+visemes for free
DELIVERABLES: working audio->face-acting chain on at least one head

## Day 3 VERDICT (15 Sep, complete 19:25)
- CHAIN WORKS: LAM Audio2Expression (Apache-2.0) -> ARKit-52 @30fps for all
  10 lines; scripts/day3/arkit_bridge.py maps them onto the 6-column texture
  visemes. LAM carries mouth opening mostly in mouthLowerDown (~0.8) not
  jawOpen (~0.35): per-line p95 normalisation fixed a mostly-closed first
  pass. Open/closed agreement with Rhubarb 0.83-0.96 per line.
- A/B (review/day3_lipsync_ab_ep1.mp4 + _mouths.png): LAM articulates more
  (open + teeth-wide on stressed syllables); Rhubarb stays small/mid. Timing
  must be judged BY EAR on the mp4 (line audio is muxed). If LAM over-opens,
  raise the column-3/4 thresholds in arkit_bridge.py (0.58 / 0.85).
- ALL FOUR A/Bs DONE: review/day3_lipsync_ab_{ep1,ep1b,ep2,ep2b}.mp4 (+_mouths.png).
  ep1 (Niamh) and ep2b (Niamh) are the judgeable ones: the drivers disagree
  on ~10% of instants (e.g. ep2b Rhubarb opens at 1.7s/4.1s, LAM at
  2.9s/3.5s/4.1s) — DECIDE BY EAR on the mp4s. ep1b/ep2 (Oisin) are profiles.
- Adoption path if LAM wins: build_film*.py already take FILM_VIS_SUFFIX=_lam
  FILM_ENV_SUFFIX=_lam; the bridge also writes l<i>_blink_lam.npy (unused yet:
  apply_talk_tex could take real blink events instead of the fixed cadence).
- OmniFaceRig: no code released (dataset only). NVIDIA A2F-3D SDK: C++ +
  TensorRT 10.13 / CUDA 12.8 — not runnable here without a toolkit upgrade.
- USER TASK still open (decisive for real mouths): VRoid both leads -> VRM
  with ARKit blendshapes; LAM's curves then drive them directly.
- Ops lessons today: python3.10 venvs need get-pip; any non-empty
  CHAR_NORMALFIX stalled build_film (fixed: "0" = off); quota hit 3x.

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

## Day 4 VERDICT (16 Sep 13:00)
- MOTION LIBRARY WORKS: MoMask (MIT, ~1 min for 10 prompts x 2 takes) -> BVH
  -> scripts/day4/retarget.py onto the UniRig rigs. Retarget method that
  held up: hips take the full rest-delta (facing + travel from the first
  animated frame), every other bone is a SWING-ONLY aim onto the source
  bone's world direction (no twist transfer — bone rolls differ). Rest-
  delta alone folded arms across the chest; direction-alignment fixed it.
- 10 motions x 2 leads rendered: review/day4_motion_<name>_<who>.mp4 and
  day4_motion_library_sheet.png (walk, sadwalk, run, idle, turn, sit,
  kneel, point, hug, wave). Oisin reads correctly on all ten.
- GAIT A/B (review/day4_gait_ab_oisin_mv.mp4): procedural numpy gait is a
  stiff slide; the retargeted walk has weight shift, hip rotation, arm
  swing. ADOPTED: retargeted motion replaces apply_walk for Day 5.
- NIAMH'S DRESS: skinned to the leg bones, every stride tents the skirt
  into a blob. Day 5: rig the CharacterGen mesh (better dress) and weight
  the skirt to hips/spine (or cull leg weights below the knee on skirt verts).
- HY-Motion-Lite needs the whole 24 GB card — parked. Animated rigs for
  integration: /workspace/loopwork/day4/r_<motion>_<who>/<motion>_<who>.glb.
- Ops: MoMask needs the numpy-alias .pth shim + umath/plot patches (in the
  installer); hstack needs fps-normalised inputs; clear render dirs per pass.

## Days 5-6 REVISED (written 16 Sep from the Day 1-4 findings)
Principle: every item ends in an A/B or a frame-verified master, exported.
GPU never idle: each day's script ends with a sweep bank.

### Day 5 — Put the wins ON SCREEN (studio_marathon8.sh)
- DONE 16 Sep 13:40: UniRig cast IN THE FILM. kit.load_rigged_character
  renames the mapped bones to the kit names (+ a jaw bone), puts the feet at
  the origin, scales by mesh extent, yaws 180 (UniRig glbs face +Y); the
  existing animators and face variants drive it unchanged. FILM_RIG=unirig
  in build_film*.py. Probes: review/day5_rigged_cast_s0{2,3,4}*.png — same
  blocking, real skinning. ADOPTED for the v4 masters (rendering).
1. RIGGED CAST IN THE FILM (the largest visible upgrade) — on the
   CharacterGen meshes (Day-2 verdict), UniRig-rigged, Oisin face repainted:
   character_kit gains load_rigged_character(glb) + apply_motion(rig, glb/bvh)
   so build_film can stage the UniRig rigs driven by Day-4 retargeted MoMask
   motion (walk-in, idle, turn, point) instead of the 14-bone numpy gait.
   A/B: ep1 s02_walk + s03_meet restaged -> review/day5_rigged_cast_ab.mp4.
- DONE 16 Sep 13:12: Oisin's closes restaged to 3/4 front in both episodes
  (ep1 cam -2.0,7.4 -> tgt 0.0,6.95; ep2 cam 0.97,9.05 -> tgt -0.75,8.75) and
  the jaw drive raised 0.13 -> 0.30 rad. Probe: review/day5_oisin_close_restaged.png.
2. RESTAGE OISIN'S CLOSES to 3/4 front in BOTH episodes (CLOSE_O cams) and
   raise the jaw drive 0.13 -> 0.3 rad: his mouth must read. A/B stills.
- DONE 16 Sep 13:55: Niamh's skirt weights handed to the hips (17.6k verts;
  no more tenting — loopwork probe). FILM_BLINK=lam switch built; A/B
  rendering -> review/day5_blink_ab_ep2b.mp4 (fixed cadence | LAM events).
  CharacterGen leads rigged (loopwork/day5/cg_*_rigged.glb, all roles mapped);
  face variants for their UVs being painted (auto-calibrated from probe_face,
  CHAR_YAW=180) -> review/day5_cg_faces_*.png. v4 masters rendering with the
  UniRig cast + restaged closes + skirt fix (loopwork/day5_prod.log).
- DONE 16 Sep 14:00: CharacterGen cast has FACE VARIANTS (face_paint on
  its own UVs; auto-calibration from probe_face fails on these meshes — the
  hair fringe reads as the nose — so calibration was set from a check render:
  oisin mouth 1.45 / eyes 1.53, niamh 1.46 / 1.525; their own eyes kept).
  review/day5_cg_faces_*.png. FILM_CAST=cg switches the film to the
  CharacterGen rigs (props/cg_*_rigged.glb + cg_*_face_*.png).
- DONE 16 Sep 14:31: CharacterGen cast VALIDATED IN THE FILM (FILM_CAST=cg):
  review/day5_cg_cast_facing.png — pair face each other, Niamh's close reads,
  mouths/blinks work. Facing is now detected from the toe bones and BAKED into
  bone+mesh data (kit facing = toes along -Y; the animators overwrite object
  rotation, so an object yaw never worked). At close range the CG face
  textures are rougher than the current cast's -> keep the mv cast for the v4
  masters; run face_repaint (FACE_BASE) on the CG textures before switching.
- BLINKS (16 Sep 15:40, review/day5_blink_ab_ep2b.mp4): LAM emits real blink
  events (ep2 line 1: 0.06 s, 2.69 s, 5.69 s vs the fixed 0.69/4.09/7.49 s
  cadence); the lam half blinks at a phrase boundary (~2.7 s) where the
  fixed one holds. Subtle, correct, free: ADOPT FILM_BLINK=lam for masters.
3. MOUTHS: adopt the user's LAM/Rhubarb verdict (FILM_VIS_SUFFIX=_lam) and
   use LAM's real blink events (l<i>_blink_lam.npy) instead of the fixed
   3.4 s cadence -> apply_talk_tex(blinks=events).
- LOOSE SHELLS (16 Sep 15:45, review/day5_shellcull_*_oisin.png): after a
  merge-by-distance the "700 shells" collapse to ONE — they were unshared
  marching-cubes seams, not fragments. The weld gives continuous normals
  (the chin/neck terminator loses its step). ADOPTED as the load default
  (CHAR_SHELLCULL=1; =N also culls real shells under N faces; 0 = off).
4. LOOSE SHELLS: merge-by-distance / tiny-shell cull at load (~700 shells per
   lead) -> fewer interior line dashes; grid before/after.
5. v4 MASTERS at 1664x960, FILM_LINES=4.0 MINLEN=40, parallel 3, both
   episodes, frame-verified, exported (~3-4 h each).
6. Sweep bank: CharacterGen + TRELLIS.2 (if DINOv3 unblocked) mesh A/Bs ->
   verdict on the mesh source for Episode 3.

### Day 6 — Episode 3 + release
- TRAP (16 Sep 15:05): glTF armatures import in QUATERNION rotation mode; the
  animators set rotation_euler, so a rigged cast silently ignores every
  heading unless the loader sets rig.rotation_mode='XYZ'. The facing-bake
  rewrite dropped that line; Episode 3's first build had both leads facing
  -Y regardless of blocking. Verified fixed (mesh follows rig z in a probe).
  Also: never kill by a SHARED helper name (render_shot / xargs) — it took
  out the v4 master of ep1 with the ep3 render; both re-queued (ep1 then ep2).
- LAUNCHED 16 Sep 14:45: EPISODE 3 "The Farewell Cliff" — scripts/ops/ep3_produce.sh
  (cliff_set.py stage from the marathon2 headland + boat/seastacks, five lines
  in voice continuing the waterfall motif, build_film3.py with 3/4 closes,
  UniRig cast, 480p verdict master -> review/farewell_cliff_v1.mp4,
  probes -> review/day6_ep3_probes.png). Docs: CLAUDE.md studio section added.
 (studio_marathon9.sh)
1. EPISODE 3 written in-voice (5 lines, word budgets per wan-clip limits) and
   produced in the cliff stage with the full stack: rigged cast, restaged
   closes, chosen visemes, hi-res lines. The proof the pipeline compounds.
2. Regression: selftest green; probe_shot + preflight gates run before the
   episode render; deterministic-seed check on one shot rendered twice.
3. Trailer v2 (with ep3 shots) + pilot v2 (3 episodes) + upload kit refresh.
4. Docs: CLAUDE.md + docs/ refreshed (kit env hooks, ops layer, quota rules,
   export branch) so a new session can run the whole studio unattended.
5. Full export; IMPROVEMENTS.md groomed for the next campaign.
USER INPUTS THAT RAISE THE CEILING: LAM-vs-Rhubarb verdict (Day 5.3);
HF_TOKEN + DINOv3 licence (Day 5.6); VRoid leads -> real blendshape mouths.

## Standing orders (all six days)
- All working state under /workspace; never /tmp
- Every phase: verify an artifact (frame/probe) before checking off
- Export inside every marathon; judgment sheets named review/dayN_*
- GPU gaps auto-filled: each day's script ends with a sweep bank
  (seed variants of props, extra coverage passes, ambience renders)
  so the card is never idle while awaiting judgment
- RECOMMENDED ONCE: install the hourly export cron on the pod:
  crontab: 17 * * * * bash /workspace/export_outcomes.sh >> /workspace/export.log 2>&1
