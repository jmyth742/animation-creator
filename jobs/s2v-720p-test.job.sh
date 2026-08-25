# ─────────────────────────────────────────────────────────────────────
#  Lip sync at 480p vs 720p — one shot, so the decision has evidence
#
#  A face in a 480p medium shot is ~150px tall, which leaves a handful of
#  pixels for a mouth. If lip sync reads as mush, resolution is the first
#  thing to try. 720p latents are 2.3x larger and the S2V checkpoint is
#  14GB, so whether it even fits in 24GB is genuinely unknown -- the test
#  reports FAILED and carries on rather than taking the job down.
# ─────────────────────────────────────────────────────────────────────
SERIES="tir-na-nog-legend"

NEEDS_COMFY=0
step "wait-ep02" '
    J=.jobs/dialogue-s2v
    [ -d "$J" ] || { echo "no ep02 job"; exit 0; }
    while true; do
        s=$(cat "$J/state" 2>/dev/null || echo unknown)
        p=$(cat "$J/pid" 2>/dev/null)
        if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then sleep 120; continue; fi
        [ "$s" = "running" ] && { sleep 120; continue; }
        echo "ep02: $s"; break
    done'

NEEDS_COMFY=1
# ep02_s05 is Niamh's two-line warning: the longest speech, best lip-sync read
step "s2v-res-test" "python scripts/shot_test.py $SERIES --episode 2 --scene ep02_s05 --test resolution"
step "report" "cat /workspace/review/shot_tests/ep02_s05_resolution.json 2>/dev/null; ls -lh /workspace/review/shot_tests/ | grep ep02"
