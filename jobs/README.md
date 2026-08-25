# Disconnect-proof production runs

Losing the SSH connection used to kill production, because the pipeline ran as a
child of your shell. It no longer does.

## The two pieces

**`scripts/ensure_comfyui.sh`** — runs ComfyUI as a detached daemon (`setsid`,
parent PID 1). It is not attached to your SSH session or to the job, so it keeps
rendering whatever clip is in flight even if everything else dies. Because
`showrunner`'s `find_latest_clip()` scans ComfyUI's own output directory, that
in-flight clip is *found and reused* on the next run — a disconnect mid-clip
costs nothing.

**`scripts/jobctl`** — runs a pipeline as a detached, checkpointed job. Every
`step` that completes is recorded; restarting the job skips them. Failed steps
are retried (ComfyUI gets bounced between attempts, since a wedged ComfyUI is
the usual cause).

## Everyday use

```bash
cd /workspace/text-to-video

scripts/jobctl start jobs/palestine-v2-quality.job.sh   # start, detached
scripts/jobctl status palestine-v2-quality              # where is it up to
scripts/jobctl log    palestine-v2-quality -f           # follow the log
scripts/jobctl list                                     # all jobs at a glance
scripts/jobctl stop   palestine-v2-quality              # stop, keep checkpoint
scripts/jobctl start  palestine-v2-quality              # resume where it left off
```

**After any disconnect, crash, or pod restart, the recovery is one command:**

```bash
scripts/jobctl start <job-name>
```

Completed steps are skipped, the interrupted step restarts from its own
`--resume` point, and already-generated clips are not regenerated.

`jobctl status` reports `interrupted` when a job was killed without a chance to
clean up (SIGKILL, OOM-killer, pod restart) — that is the signal to re-run
`start`.

## Writing a job

A job file is plain bash made of `step "<id>" <command>` lines. The id is the
checkpoint key, so **keep ids stable** — renaming one makes that step run again.

```bash
SERIES="my-series"
SR="python scripts/showrunner.py"

for ep in 1 2 3; do
    step "p1-draft-ep$ep" "$SR produce $SERIES --episode $ep --quality draft --resume"
done
step "compile-season" "$SR compile $SERIES"
```

Two rules:

- Put all real work inside `step` commands. `jobctl status` counts steps by
  sourcing the job file with `step` stubbed out, so side effects at the top
  level would run during a plain status check.
- Always pass `--resume` to `showrunner produce`, so a retried step skips the
  clips it already made.

Set `NEEDS_COMFY=0` at the top of a job that does not need ComfyUI (audio-only,
compile-only) to skip the health check.

## Knobs

| Variable | Default | Meaning |
|---|---|---|
| `JOB_RETRIES` | 3 | attempts per step before giving up |
| `JOB_STOP_ON_FAIL` | 1 | `1` abort the job on a failed step, `0` carry on |
| `COMFY_PORT` | 8188 | ComfyUI port |
| `COMFY_BOOT_TIMEOUT` | 420 | seconds to wait for ComfyUI to answer |

```bash
JOB_STOP_ON_FAIL=0 scripts/jobctl start jobs/palestine-v2-quality.job.sh
```

## Where state lives

`.jobs/<job-name>/` — `job.sh` (snapshot taken at start, so editing the original
mid-run is safe), `completed` (checkpoint), `job.log`, `pid`, `state`.

To force a step to run again: `scripts/jobctl reset <job> <step-id>`.
To start the whole job over: `scripts/jobctl reset <job>`.

## Notes

- ComfyUI keeps running after `jobctl stop`. Stop it with
  `bash scripts/ensure_comfyui.sh stop`.
- `resume_production.sh` in the project root predates this and targets the v1
  Palestine flow; `jobctl` supersedes it.
- `tmux` was installed for `jobctl attach`, but nothing depends on it — it lives
  in the container filesystem, not on `/workspace`, so it disappears when the pod
  is recreated. `jobctl` itself only uses `setsid`/`nohup`.
