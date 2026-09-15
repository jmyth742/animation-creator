# Improvement loop backlog — top unchecked item first, check off when verified
# Rules: one item per iteration; render/produce a verifiable artifact into
# /workspace/review/; keep working state under /workspace (never /tmp);
# run /workspace/export_outcomes.sh after every iteration.

- [x] FACE QUALITY (user priority): run `bash /workspace/upgrade_hy3d21.sh` —  <- done by marathon
      fetches Hunyuan3D-2.1 (open PBR pipeline; verify import paths against
      its demo.py, modules moved to hy3dshape/hy3dpaint), re-meshes both
      characters from the existing MV view sets, QA turntables to
      review/qa_*_v21.png. Also records whether 2.5's 4K-texture weights
      are public (loopwork/hy3d25_probe.json) — if yes, test-drive them.
- [x] FACE QUALITY part 2: face-region HD repaint via  <- done by marathon
      scripts/blender3d/face_repaint.py (see its header for the 3-line
      FACE_BASE wire-up in face_paint.py). Run on the winning mesh from the
      2.1 A/B, QA a close-up render before adopting; then rebuild both
      film blends and re-render the dialogue shots.
- [x] Regenerate the tmp-wipe losses: rebuild film_shots.json + film2_shots.json  <- done by marathon
      (run build_film.py / build_film2.py with audio dirs re-made by
      film_lines.py + rhubarb), then re-render + assemble the DOF cut of ep1
      (dialogue shots FILM_DOF=2.4) -> review/nine_waterfalls_dof.mp4
- [x] ep2 hi-res master 1664x960 -> review/first_snow_1080.mp4  <- done by marathon
- [x] C-cam passes for both episodes -> review/*_ccam.mp4  <- done by marathon
- [x] Backlot ambiences for storm/cliff/ruin (depth builds are re-runnable  <- done by marathon
      from sets/*/master.png) -> review/ambience_<loc>_30min.mp4
- [x] Poster stills: one composed beauty frame per episode at 1664x960 ->  <- done by marathon
      review/poster_ep1.png, poster_ep2.png (thumbnail material)
- [x] Subtitles: generate SRT per episode from lines.json timings ->  <- done by marathon
      review/*.srt
- [x] YouTube metadata: title/description/tags per finished video ->  <- done by marathon
      review/metadata_<video>.md
- [x] Proper 45-60s trailer cut with title cards + mixed lines audio ->  <- done by marathon
      review/trailer_60s.mp4
- [ ] Episode 3 script + full production in the cliff backlot or 3D cliff set
      (write 5 lines in-voice; reuse build_film machinery; new location)
- [ ] Full 3D cliff stage: benttree + seastack + rocks + sea plane module,
      beauty stills + a flythrough -> review/cliff_stage.png/.mp4
- [ ] Winter wardrobe cast: winter outfit sheets (front/left/back) -> MV
      meshes -> paint -> QA turntables (do NOT swap into episodes unreviewed)
- [ ] Gesture library v2: add point, shrug, bow, wave; A/B render one line
      with richer acting -> review/acting_ab.mp4
- [ ] Ambience audio upgrade: layered wind + birdsong synth + water for the
      loops (ffmpeg filters only) — remaster both 30-min loops
- [ ] 4K-class master of ep1 (3328x1920) if render time <2h -> review/
- [x] Episode 1+2 combined "pilot" cut with recap card between -> review/  <- done by marathon
