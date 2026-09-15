# Ops layer — the campaign scripts that run the studio unattended

These scripts live on the pod at `/workspace/` and are mirrored here so a
fresh pod (or a fresh session) can rebuild the whole production loop.
Restore with `cp scripts/ops/*.sh scripts/ops/*.md /workspace/`.

| file | role |
|---|---|
| `SIXDAY_PLAN.md` | the six-day quality campaign, one marathon per day |
| `IMPROVEMENTS.md` | rolling backlog; `export_outcomes.sh` copies it into `docs/` |
| `studio_marathon*.sh` | day-long GPU marathons (marathon4 = Day 1) |
| `go*.sh` | detached launchers with pid files (`bash /workspace/go4.sh`) |
| `export_outcomes.sh` | incremental exporter: code -> working branch, media -> `production-outcomes` |
| `deadline_guardian.sh`, `gpu_queue.sh` | watchdogs / queueing helpers |
| `night*.sh`, `overnight_3d*.sh`, `ep1*_overnight.sh`, `winter*.sh` | earlier overnight runs, kept as reference |

Conventions every marathon follows: all state under `/workspace`, never
`/tmp`; every phase verifies a frame or probe before it is checked off;
judgment sheets go to `/workspace/review/dayN_*`; the exporter runs inside
every marathon; each day ends with a sweep bank so the GPU is never idle.
