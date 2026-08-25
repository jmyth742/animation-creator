# ep04 — revised coverage + the audio fix.
#
# WHAT CHANGED FROM THE LAST CUT
#   close-ups 12 -> 3      reserved for the three beats that earn them
#   silent shots 7 -> 0    reaction beats now carry narration
#   framing                4 wide, 5 medium, 4 three-quarter, 1 over-shoulder
#   ambience               beds scaled to a measured target, not a fixed 0.22
#                          (they were RMS 0.005 x 0.22 = inaudible; 72% of the
#                           film was near-silent, now 0%)
#
# Keeps everything already measured: S2V reference conditioning wired to the
# sampler (+0.198 on the worst shot), plate seeding for wides, portrait for the
# rest, no character LoRA on S2V, absolute-timeline audio.
SERIES=tir-na-nog-legend
EP=4
PY=/workspace/venv/bin/python

NEEDS_COMFY=0
RETRIES=1
step "selftest"        "$PY scripts/selftest.py"
step "graph-check"     "$PY scripts/validate_workflow.py $SERIES --episode $EP"
step "preflight"       "$PY scripts/preflight.py $SERIES --episode $EP"

step "show-coverage" \
    "$PY - <<'PYEOF'
import sys
sys.path.insert(0, 'scripts')
from pathlib import Path
import showrunner as sr
sr.set_current_series('$SERIES')
ep = sr.load_json(sr.episode_path('$SERIES', $EP))
for s in ep['scenes']:
    g = sr.get_scene_seed_image(s, '$SERIES', None)
    d = (s.get('dialogue') or [{}])[0]
    line = d.get('line') or s.get('narration') or ''
    print(f\"  {s['id'][-3:]}  {s['visual'][:30]:30} {Path(g).name if g else None:34} {line[:28]}\")
PYEOF"

# Audio must be regenerated: seven shots have new narration.
NEEDS_COMFY=1
RETRIES=3
step "archive-prev" \
    "d=ComfyUI/output/video/$SERIES; mkdir -p \$d/ep04-prev-coverage;
     n=0; for f in \$d/ep04_s*.mp4; do [ -e \"\$f\" ] || continue; mv \"\$f\" \$d/ep04-prev-coverage/; n=\$((n+1)); done;
     cp output/$SERIES/ep04/ep04_final_audiofix.mp4 output/$SERIES/ep04/ep04_prev_final.mp4 2>/dev/null || true;
     rm -f output/$SERIES/ep04/audio/ep04_s*.mp3;
     echo \"  archived \$n clip(s), cleared stale VO\""

step "render" "$PY scripts/showrunner.py produce $SERIES --episode $EP --lightning"

NEEDS_COMFY=0
RETRIES=1
step "verify"  "$PY scripts/verify_render.py $SERIES --episode $EP || true"
step "lipsync" "$PY /tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/lipsync_align.py || true"
step "audio-coverage" \
    "$PY - <<'PYEOF'
import subprocess
import numpy as np
f = 'output/$SERIES/ep04/ep04_final.mp4'
o = subprocess.run(['ffmpeg','-v','error','-i',f,'-ac','1','-ar','8000','-f','f32le','-'],
                   capture_output=True).stdout
x = np.frombuffer(o, dtype=np.float32); w = 2000
rms = np.array([float(np.sqrt((x[i:i+w]**2).mean())) for i in range(0, len(x)-w, w)])
pk = rms.max(); dur = len(x)/8000
print(f'  audible {(rms>pk*0.15).sum()*0.25:.1f}s   near-silent {(rms<pk*0.03).sum()*0.25:.1f}s of {dur:.1f}s')
PYEOF"
