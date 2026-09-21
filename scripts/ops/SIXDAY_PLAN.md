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
  ADOPTED: FILM_LINES=4.0 FILM_LINE_MINLEN=20. Ext-contour-only is too faint.
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
  FILM_RES=1664x960 FILM_LINES=8.0 FILM_LINE_MINLEN=40.

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
- FLAT PALETTE IN MOTION (16 Sep 16:30, review/day5_flat_ab_ep2b.mp4 + _strip):
  the 14-colour textures dull the eyes (green-grey) and muddy the skin; the
  current textures keep their contrast. NOT adopted. The Day-1 deferral is
  closed; palette discipline, if wanted, should be a cel ramp change, not a
  texture quantisation.
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
- 17 Sep 01:30: the hi-res masters exceed GitHub's 100 MB file limit and live
  on the media branch as split .part files (reassemble: cat name.mp4.part* >
  name.mp4). Browser-playable copies are exported alongside: *_v4_web.mp4
  (1664x960, ~7.5 Mbps, < 95 MB). The quota filled again during ep1's
  re-render: envs/trellis2 + the TRELLIS.2 checkout were deleted (blocked on
  the DINOv3 gate; `bash scripts/day2/install_trellis2.sh` rebuilds them) and
  superseded large videos already on the branch were removed from review/.
- DONE 16 Sep 23:56: review/farewell_cliff_v4.mp4 — ep3 at 1664x960, 8 px lines,
  79.6 s, 12 shots frame-verified; full-res check clean (loopwork/v4e3_check.png).
  ep1's rebuild (weld + LAM blinks) + 8 px re-render is the last job in the chain.
- DONE 16 Sep 21:54: review/first_snow_v4.mp4 — ep2 at 1664x960, 8 px lines,
  80.1 s, 12 shots frame-verified; full-res check clean (loopwork/v4e2_check.png).
  ep3 v4 rendering next, then ep1's re-render replaces its 16 px v4.
- LINE THICKNESS CORRECTED (16 Sep 19:30, review/day6_line_thickness_check.png):
  Freestyle's scene unit thickness MULTIPLIES the linestyle thickness; film.py
  set both to FILM_LINES, so 2.0 at 480p was 4 px (fine) but 4.0 at 960p was
  16 px — the ep1 v4 master rendered with lines twice too heavy. film.py now
  keeps the unit at 1.0 and FILM_LINES is the effective width in pixels:
  480p = 4.0, 1664x960 = 8.0 (verified against the 480p reference). All ops
  scripts, docs and the plan were rewritten to the new numbers. ep1's v4 is
  re-rendered at the end of the chain; ep2/ep3 restarted with 8.0.
  Verified 19:35 on ep2's first hi-res shot: an even ~8 px outline that reads
  as drawn (loopwork/v4_ep2_check.png).
- 16 Sep 17:15: ep2 + ep3 blends rebuilt with the seam weld (now applied in
  the rigged loader too — it had only run on the numpy path) and LAM blinks
  before their v4 renders (loopwork/v4_rebuild.log: weld=2 each); ep1's v4 (already
  rendering on the pre-weld blend) is re-rendered at the end of the chain
  (masters_v4_ep1b.sh) so all three v4 masters share one stack.
- DONE 16 Sep 16:55: RELEASE PACKAGE v2 — review/pilot_v2_ep1_ep2_ep3.mp4
  (239.5 s), trailer_v2.mp4 (14 moments from all three masters), farewell_cliff.srt,
  metadata_farewell_cliff.md. Contact sheet review/day6_trailer_v2_contact.png.
- DONE 16 Sep 16:44: EPISODE 3 MASTER review/farewell_cliff_v1.mp4 (79.6 s, 12
  shots frame-verified; contact sheet review/day6_ep3_master_contact.png).
  Three episodes now exist on one stack: UniRig cast, restaged closes, LAM
  blinks available, seam weld, 2.0 px lines. Release package running
  (release_v2.sh); v4 hi-res masters for all three in the queue.
- QUEUED 16 Sep 16:10 (all detached, in dependency order): ep3 480p master
  (scripts/ops/ep3_v2master.sh -> review/farewell_cliff_v1.mp4) -> release_v2.sh
  (ep3 .srt + metadata, pilot_v2_ep1_ep2_ep3.mp4, trailer_v2.mp4); v4 1664x960
  masters ep1 -> ep2 -> ep3 (loopwork/masters_v4_ep{1,2,3}.sh ->
  review/*_v4.mp4). Logs: loopwork/{ep3_v2master,release_v2,masters_v4_ep*}.log.
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

## CAMPAIGN COMPLETE (17 Sep 04:05)
Three episodes on one stack, delivered at 480p (verdict masters) and
1664x960 (v4, 8 px lines; browser copies *_v4_web.mp4): The Nine Waterfalls
(79.8 s), The First Snow (80.1 s), The Farewell Cliff (79.6 s); pilot v2,
trailer v2, subtitles + metadata; every verdict in this file; docs in
CLAUDE.md; backlog groomed in IMPROVEMENTS.md; production assets committed.
Open user gates: lip-sync verdict (LAM vs Rhubarb by ear), DINOv3 licence +
HF_TOKEN for TRELLIS.2 (env deleted for quota, installer rebuilds it), VRoid
leads for real blendshape mouths, repo visibility.

## Anime-style pass (21 Sep) — replicating the researched cel look
- kit.cel_material now carries CEL_STYLE=anime next to the classic two-tone:
  the albedo's SHADOW is hue-shifted toward violet (+29 deg, value 0.62,
  saturation 1.15) instead of a grey multiply, a narrow mid-band sits at the
  terminator, and optional stepped Fresnel rim + specular pip.
- Grid verdict (review/anime_style_faces_*.png, anime_style_*.png; columns:
  classic | anime no rim/spec | anime + rim/spec | anime hue +50 deg):
  the hue-shifted three-tone is a clear gain on both leads (cleaner bands,
  warmer skin, the dress and tunic keep their colour in shadow); rim + spec
  wash the faces toward white and lay flat patches on cloth — OFF by default.
  The stronger hue shift is not better than +29 deg.
- Film A/B (dialogue closes, classic | anime): review/anime_style_ab_ep2b.mp4,
  anime_style_ab_ep1b.mp4 — decides whether it becomes the master default.

## Quality pass 2 (21 Sep) — characters and environment
- CEL SHADER: anime three-tone (violet-shifted shadow, mid-band) is now the
  DEFAULT (CEL_STYLE=classic restores the v4 look). Film A/B: review/
  anime_style_ab_ep1b.mp4 (summer key: cleaner, warmer terminator — the gain),
  anime_style_ab_ep2b.mp4 (winter fill: near-identical). Rim + spec rejected.
- FACE RESOLUTION, measured: the face spans ~312 texels on the mv leads (~100
  on CharacterGen) but a 4K atlas (face_repaint FACE_HD_SCALE=2) and a higher
  FLUX denoise changed nothing at a 900 px close-up (review/face_res_ab_niamh.png):
  the blur is the marching-cubes FACETING of the head, not the texture. Lever:
  a denser relaxed hero head (subsurf + normal transfer) — A/B in progress
  (review/face_mesh_ab_niamh.png). VRoid heads remain the real fix (user).
- ENVIRONMENT: the primitive sets never matched the painted concept plates
  the cast was designed against. Tested: depth-projected plate as a set
  (env_plate_stage_test.png: right look, but blocking floats off-plate);
  plate as a backdrop behind primitives (worse by contrast). ADOPTED: the
  HYBRID in cliff_set.py — a painter's camera frames the stage as the plate
  does; near geometry (shelf, cliff, sea) samples the plate at its screen
  position through the cel ramp, a far dome carries the plate's sky/sea band,
  props stay real for parallax. review/env_backdrop_probes.png. Env:
  SET_PLATE=<plate.png>, SET_BACKDROP=0 to disable.
- HERO HEAD (judged 07:00): subsurf level 1 softens hair/cheek silhouettes a
  little, level 2 adds nothing, the eyes stay soft in all three
  (review/face_mesh_ab_{niamh,oisin}.png). Hook: CHAR_HERO_SUBSURF=1 (both
  loaders, before the normal transfer), off by default. Modest; close-ups only.
- FACE REPAINT WAS NEVER A REPAINT (found 07:00): the "face patch" cut from the
  atlas is NOT a face — the auto-UV atlas scatters the face over small islands
  (review/face_flux_patch_oisin.png: FLUX draws stray eyes/profiles into the
  fragments). At denoise 0.3 x 8 distilled steps it was a no-op (atlas differs
  by 0.5/255 mean), which is why "4K changed nothing". REPLACED by camera
  projection (face_project.py): front-on unlit ortho render -> FLUX img2img on
  the coherent face -> UV Project back from the same camera -> Cycles EMIT bake
  into a 2x atlas masked to front-facing surface near the face. Same technique
  as the painted sets. Verdict: review/face_proj_<name>.png (front | FLUX |
  close-up base | close-up HD).
- PROJECTION IS EXACT NOW: cliff_set uses a UV Project modifier from the
  painter camera (review/env_painter_proj_check.png). Shared module
  painter.py; valley_set wears the tir_na_nog plate (pose vd, review/
  env_painter_calib_valley2.png -> env_painter_proj_check_valley.png). Cliff
  foot slab + painted shore stop the plate's cliff base streaking over the sea.
- BUG that stalled three renders for an hour: `while ob.modifiers[-1] is not md`
  never ends — every RNA access returns a fresh Python wrapper, so `is` is
  always False-equal. Compare names, never identity, on bpy objects.
- FACE HD ADOPTED (07:20): review/face_proj_{oisin,niamh}_mv.png — crisp anime
  eyes/brows/lips on the same meshes; Niamh's collar embroidery even survives.
  Variants painted with face_paint.py --keep-eyes on the HD bases as
  <who>_hd_face_*.png; in film via FILM_FACE_SUFFIX=_hd
  (review/face_hd_film_ab_ep1.png: plain | HD).
- ONE PAINTER CAMERA IS NOT ENOUGH (07:15): review/env_painted_{ep1p,ep3p}_
  probes.png — shots near the painter pose are paintings, everything else
  streaks; ep3 filmed from the sea is unusable. FIX = PER-SHOT projection in
  film.py: the projector becomes the shot camera at the middle frame and the
  plate is picked by heading vs the master (master/side/reverse, closer for
  long lenses; FILM_PLATE overrides). review/env_painted_{ep1q,ep3q}_probes.png:
  every shot is now the painting with the cast in it. Plates upscaled 4x
  (upscale_plates.py, 4x-AnimeSharp) so they out-resolve 1664x960; painter.py
  prefers <setup>_4x.png. The tir_na_nog setups are five copies of the master
  (the WAN derivation converged) — the valley has one angle; the cliff has
  real reverse/side/wider plates.
- Follow-ups applied: GLB dressing off on painted sets (SET_DRESS=1 restores;
  the plate paints the hall/trees/cross), the cliff's bent-tree prop dropped
  (doubled the painted tree), ep3 s01_est restaged to the painter's side with
  a slow push (a plate exists there; over the sea none does), FILM_STEP for
  move probes, winter plate derived from the summer master by FLUX img2img
  (winter_plate.py) so Episode 2 shares the calibration.
- PROBE ROUNDS 2-7 (07:30-08:15, review/env_painted_ep{1,2,3}{r,t,u,v}_probes.png,
  *_moves.png, q6/q7): camera moves hold (plate glued to geometry, mild
  parallax). Fixed in turn: big faces showed the plate offset (projected UVs
  interpolate per vertex -> painter.py subdivides to ~1.5 m faces first);
  GLB dressing and primitives the plate already paints (hall, trees, cross,
  door, flowers, falls plane, relief) dropped in painted mode; the hall is a
  camera-facing BILLBOARD (painter.billboard) so its steps never stretch
  across the floor; the cliff shelf is the painted headland only, its top
  tiles the plate's own grass (painter.tiled) so the cast stands on grass
  from every camera; sea/shore/foot fade to a flat plate colour at grazing
  angles; a closed sky dome shadowed the whole stage (visible_shadow off);
  season-aware setup pick (master_winter -> never the summer master).
- WINTER: FLUX img2img on the summer master at 0.65 (seed 6100, birds cloned
  out) = master_winter.png; 0.5 gave no snow + hallucinated people, other
  seeds/graded inputs drift the layout. Episode 2's closing walk redirected
  up the path (the winter plate's lake lies where they walked).
  review/env_painted_ep2x_probes.png.
- LAKE (q8-q10): a per-shot projected lake shows the hall's steps from a
  sideways camera (idpass_s07b found it); a tiled water crop was too dark;
  ADOPTED: the lake projects from a FIXED master camera (painter_master,
  ob['painter_fixed']) when the shot is >50 deg off the master heading and
  per-shot otherwise (review/env_painted_q10_probes.png).
- V5 MASTERS launched 08:25 (scripts/ops/masters_v5.sh, log
  loopwork/masters_v5.log): painted sets + _hd faces + anime shader, UniRig,
  LAM blinks, 1664x960 / 8 px lines -> review/{nine_waterfalls,first_snow,
  farewell_cliff}_v5.mp4 (+ _web.mp4), exported after each episode.
  WATCH: those three against the *_v4.mp4 masters; the face A/B is
  review/face_hd_film_ab_ep1.png, the environment before/after is
  env_painted_ep1p_probes.png (one painter camera) vs env_painted_ep1v/
  q10 (per shot).

## V5 verdict + research findings (21 Sep, 14:20)
V5 MASTERS DONE and exported: review/{nine_waterfalls,first_snow,farewell_cliff}_v5.mp4
(+ _web copies). Judged from frames (review/v5_ep1_frames.png, v5_ep2_ep3_frames.png):
- EP1 (summer valley) and EP2 (winter valley): the painted world WORKS. Shots read as
  the concept painting with the cast standing in it; HD faces hold at close range.
- EP3 (cliff): WEAKEST. The shelf top tiles the plate's grass and reads as flat green
  plastic against the painted cliff; the sea band is plain. The cliff needs either a
  painted top-down grass plate of its own or the shelf reduced so the plate's own
  cliff-top does the work.

DEEP RESEARCH (verified 3-0, sources: ASW Guilty Gear Xrd GDC/Docswell, psoft):
1. LINES: studios do NOT use post-process/Freestyle-style lines. Guilty Gear uses an
   INVERTED HULL (duplicated, flipped, expanded mesh), with:
   - per-vertex line width from vertex-color ALPHA (0.5 = neutral, 1.0 = double, 0 = erased)
   - width compensated for camera DISTANCE and FOV so on-screen width is constant
   - a SECOND set of smoothed normals for the hull, separate from the shading normals
   (we already keep edited shading normals — this is exactly the conflict the hull solves)
   Inner/surface lines are drawn into the texture as axis-aligned beams with UVs aligned,
   so thickness is set by UV overlap and never aliases at close-up.
   => Freestyle is our biggest render cost (~15 s/frame CPU). An inverted hull is nearly
   free on GPU AND gives per-vertex width control. HIGH VALUE, days-scale.
2. SHADING: single step threshold on N.L, with a vertex-color channel as a per-region
   OFFSET on that threshold (painted occlusion; 0 = always shaded). No normal maps.
   No scene lighting on characters: each character carries its OWN light vector, fixed
   per pose and animated per shot in cutscenes.
3. MOTION: keyframe interpolation DISABLED entirely (every frame a posed key), no physics
   sim for hair/cloth, ~500 bones, and deliberate per-key mesh deformation to break the
   perfect-perspective read. This is the "limited animation" 2D feel.
4. Pencil+ 4 for Blender: addon is free but REQUIRES a proprietary Windows/macOS render
   app — INFEASIBLE on this Linux pod. Ruled out.

NEXT (priority order, all days-scale):
a. Inverted-hull outlines replacing Freestyle (speed + quality + per-vertex width).
b. Per-character light vector instead of scene lighting for the cast.
c. Step the animation on twos/threes (interpolation off) for the 2D read.
d. Fix EP3's cliff shelf.

### Inverted-hull outlines: TESTED, REJECTED for now (21 Sep 15:00)
Implemented per the research (character_kit.add_outline_hull + FILM_HULL=<px> in film.py):
a separate shell object whose custom split normals are CLEARED and shading smoothed (the
"second set of normals" the ASW talk describes), faces flipped, displaced along those
normals, black backface-culled material, armature modifier kept so it deforms; width
compensated for camera distance and FOV so `px` is on-screen pixels in any shot.
RESULT (review/lines_freestyle_vs_hull.png, Freestyle | hull): the hull is BLOTCHY on our
cast -- the shell pokes through the surface in patches across faces, hair and cloth.
ROOT CAUSE: the technique assumes clean, hand-modelled topology with artist-painted
vertex-color widths. Our cast are marching-cubes AI meshes (Hunyuan-mv/CharacterGen) with
dense irregular triangles, coincident shells and sharp creases, so a uniform normal
displacement crosses the surface wherever local curvature exceeds the offset.
VERDICT: Freestyle STAYS as the shipping line renderer. The hull code is kept behind
FILM_HULL=0 (off) and becomes viable the moment the cast have clean topology.
CONSEQUENCE: this is the SECOND studio technique blocked by AI-mesh topology (the first
was face sharpness). Clean-topology heads/bodies -- VRoid/VRM export, which also brings
MToon cel materials and its own outline system, and proper shape-key face rigs -- is now
the single highest-value unlock in the whole pipeline, not a nice-to-have. It needs the
user to supply VRoid/VRM character exports.
STILL ACTIONABLE without new meshes, in priority order:
 b. per-character light vector instead of scene lighting for the cast (ASW: each character
    carries its own light, animated per shot) -- pure shader/rig work, no mesh dependency;
 c. stepped animation on twos/threes (interpolation off, every frame a key) -- pure
    animation-curve work on the existing MoMask/retarget output;
 d. EP3 cliff shelf (reads flat green against the painted plate).
