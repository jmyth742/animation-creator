# ─────────────────────────────────────────────────────────────────────
#  What actually improves lip sync?
#
#  Resolution is ruled out: 720p cost 2.75x (1461s vs 531s) and came back
#  smoother and waxier, not sharper. The two remaining levers are how much
#  of the frame the mouth occupies, and how much sampling S2V gets.
#
#    A  25 steps, normal close-up      (current setting)
#    B  40 steps, normal close-up
#    C  25 steps, extreme close-up
#    D  40 steps, extreme close-up
#
#  Each produces a 6-frame mouth strip so articulation can be compared
#  directly rather than by impression.
# ─────────────────────────────────────────────────────────────────────
SERIES="tir-na-nog-legend"

NEEDS_COMFY=0
step "wait-ep03" '
    J=.jobs/drama-ep03
    while true; do
        s=$(cat "$J/state" 2>/dev/null || echo unknown)
        p=$(cat "$J/pid" 2>/dev/null)
        if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then sleep 180; continue; fi
        [ "$s" = "running" ] && { sleep 180; continue; }
        echo "ep03: $s"; break
    done'

NEEDS_COMFY=1
step "lipsync" "python scripts/lipsync_test.py $SERIES --episode 2 --scene ep02_s03"
step "report" "cat /workspace/review/lipsync/*_lipsync.json; ls -1 /workspace/review/lipsync/ | grep MOUTH"
