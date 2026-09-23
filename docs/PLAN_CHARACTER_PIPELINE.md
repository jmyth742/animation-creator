# Character pipeline plan (23 Sep 2026)

The reference the user judges against is `the_nine_waterfalls.mp4` (3 Sep). It used a
worse rig than we have now and looked better because of proportions and staging. The
order below is the research doc's order, which we skipped, restored.

## Gates (a change ships only if it passes these, measured, with a control render)
- Deformation gate at 45 and 60 degrees: no tearing at shoulder, elbow, knee, head.
- Foot slide under 5 mm/frame on the walk (measured on DEF-foot, lowest foot).
- Knee between 15 and 80 degrees through the cycle; hip-to-ankle reach under 1.05 of leg length.
- Forearm folds toward -Y after arm_pose (measured fold vector).
- Every rig or motion change judged INSIDE a build_film shot, never in the arena alone.

## Order
1. Lock the source: A-pose, mitten hands, retopo at 18k, one deform gate. The retopo mesh is the asset.
2. Rigify is the only rig (`rigify_fit.py`); UniRig and the kit rig are retired for characters.
3. Faces: heads with real blendshapes (VRoid/template wrap) driven by the LAM curves. Painted faces are a stopgap only.
4. Craft pass: smoothed normals + AO shadow map on close-ups (CHAR_NORMALFIX, CHAR_AO), chosen by A/B sheet.
5. Motion library on the Rigify rig, last.

## Overnight queue (23 Sep) and what to look at in the morning
- `hand_scores.txt`, `RIGIFY_gate_oisin4_45.png`, `RIGIFY_xray_oisin4.png`: the mitten-hand cast, chosen by geometry.
- `nine_waterfalls_rigify_chibi_web.mp4` and `..._chibi3_web.mp4`: the benchmark at master quality, both Oisin candidates, staging held constant.
- `CRAFT_PASS_AB.png`: NORMALFIX x AO on the close-up. Pick one, it becomes the master default.
- `RIGIFY_face_<cast>.png` and `TALK_<cast>_l<i>.mp4`: face rig and every line, per cast.
- `RIG_GATES.txt`: the numbers above for every cast.
- `MOTION_<cast>_rigify.mp4`: three-shot reels with Niamh's stride scaled to her legs.
