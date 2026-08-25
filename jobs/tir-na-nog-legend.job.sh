# ─────────────────────────────────────────────────────────────────────
#  Tir na nOg — The Land of Eternal Youth  (16 scenes, ~75s)
#  v2: reference-portrait seeding, chain-breaking, render-only style.
#  Draft pass only — review before spending on the final pass.
# ─────────────────────────────────────────────────────────────────────
SERIES="tir-na-nog-legend"
SR="python scripts/showrunner.py"

step "p1-draft-ep1" \
    "$SR produce $SERIES --episode 1 --quality draft --optimization fast --resume"
