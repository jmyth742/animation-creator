#!/usr/bin/env bash
# Overnight GPU work. Three things the card can do that post-production cannot.
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }

P=$(cat .jobs/pids/prelude2.pid 2>/dev/null || echo "")
if [ -n "$P" ]; then
  say "waiting for the prelude to finish (pid $P)"
  while kill -0 "$P" 2>/dev/null; do sleep 30; done
fi

say "1  CAN WAN MOVE THE CAMERA?  (open question, zero research claims)"
# One close-up and one wide, each rendered static / dolly / pan / handheld /
# crane. If a move is real, motion rises without identity falling. If the model
# just warps, identity drops and the question is closed.
$PY scripts/shot_variants.py $S --scene ep05_s03 --camera
$PY scripts/shot_variants.py $S --scene ep05_s01 --camera

say "1b  IS THERE A LORA STRENGTH THAT HELPS S2V?"
# Character LoRAs are dropped on ~80% of shots on the strength of ONE
# measurement taken at strength 0.9. Nobody tried 0.2 or 0.35. Training against
# the S2V checkpoint is not available -- musubi has no S2V task and our weights
# are GGUF -- so this is the question that actually matters.
$PY scripts/lora_strength_sweep.py $S --scene ep05_s03
$PY scripts/lora_strength_sweep.py $S --scene ep07_s05

say "2  COVERAGE — alternate takes on the shots that carry the films"
# Every shot in both films is a first take. Three takes each on the ten that
# matter most, chosen on measured identity.
for SC in ep05_s03 ep07_s05 ep08_s06 ep07_s06 ep09_s03 \
          ep06_s05 ep06_s06 ep08_s05 ep05_s06 ep10_s09; do
  $PY scripts/shot_variants.py $S --scene $SC --seeds 2
done

say "2b  CAN WE PUT BOTH CHARACTERS IN ONE FRAME?"
# 55 shots across six pieces and not one contains two characters. Every
# conversation is two people never seen together, which is why the cutting
# still reads as alternating monologues. Real series use two-shots constantly.
$PY scripts/two_shot_test.py $S --location tir_na_nog --setup master
$PY scripts/two_shot_test.py $S --location farewell_cliff --setup master
$PY scripts/two_shot_test.py $S --location storm_cliffs --setup master

say "3  MORE COVERAGE PER LOCATION — angles we do not have"
# 3-5 camera positions per place means the same framings keep recurring.
$PY scripts/build_sets.py setups $S --all
$PY scripts/build_sets.py check $S --threshold 0.55

say "4  ANOTHER EPISODE — whatever the night has proven"
# Written from tonight's findings rather than in advance: if two-shots hold,
# ep11 is built around them; if a LoRA strength works, dialogue shots use it;
# if the camera moves natively, shots are written with moves in the prompt.
# The script decides from the verdict files rather than guessing now.
$PY scripts/plan_next_episode.py $S || echo "  nothing to plan yet"

say "done"
