# Deploying SHOWRUNNER without an always-on GPU

The cost problem: an RTX 3090 pod bills ~$0.44/h whether it renders or idles.
The console, the queue, the bible, every JSON blob — all of that is CPU work
worth pennies. Only `showrunner.py` render jobs and `forge_assets.py` need CUDA.

The seam already exists: **everything GPU-bound goes through the serial render
queue** (`workbench_data/render_queue.txt` + the bash runner). The console
never renders inline; it appends a line. That line is the deployment boundary.

## Tier 0 — today, one pod (implemented)

`scripts/idle_hibernate.sh`, armed from the Home tab (admin only):
when queue empty + no jobs + ComfyUI queue empty + GPU <15% for 30 straight
minutes → `runpodctl stop pod`. Storage persists on the network volume;
restart from the RunPod app and `scripts/ensure_all.sh` boots the studio.

- Requires a working RunPod API key (`runpodctl config --apiKey …`).
  Until then the watcher logs "would stop now" instead of firing —
  check `workbench_data/hibernate.log`.
- Rough saving: a pod used 6h/day stops billing the other 18h → ~70% off.
- Cold start cost: ~3–4 min for pod boot + model load on first render.

## Tier 1 — split console from GPU (the real product shape)

- **Console**: this Flask app on a $5/mo CPU box (or RunPod CPU pod).
  It owns users.json, quotas, shows, uploads, the queue. No CUDA anywhere.
- **Worker**: the current GPU pod image, booted *by the console* when the
  queue goes non-empty (`runpodctl start pod` / RunPod REST), self-stopping
  via the same hibernate watcher when drained.
- **Shared state**: the network volume mounted on both (RunPod network
  volumes attach to pods in the same datacenter), or S3-compatible bucket
  sync of `series/`, `output/`, `workbench_data/`.
- The runner loop needs one change: today it `bash`-execs render commands
  locally; split, the *worker* runs the runner and the console only appends.
  That is already true — the runner is a separate process reading a file.

## Tier 2 — serverless (scale past one user)

RunPod Serverless with a ComfyUI worker image: each queue line becomes a job
POST; billing is per-second of actual GPU time, zero when idle. Needs the
models baked into the image or on a network volume, and the S2V chain's
3×81-frame stitching moved inside the handler. This is the shape where many
users rendering concurrently stops being one serial queue.

## Multi-user pieces (implemented)

- **Accounts**: `/login` — first login registers (username + password,
  salted SHA-256, `workbench_data/users.json`); sessions in `sessions.json`;
  the operator key still maps to `admin`.
- **Quotas**: new users start with 240 GPU-minutes. `/api/render` estimates
  the burn (28 min/dialogue shot, 16/silent), refuses with a 402 when the
  tank is short, debits up front. Admin is unmetered; top up by editing
  `users.json`.
- **Ownership**: `owners.json` maps show → creator; admin owns everything.
- **Bring-your-own art**: `/api/upload` accepts portrait / location-master /
  plate images (≤15MB, PIL-validated, resized ≤1664×960) straight into the
  show's `reference_images/` and `sets/`, so a new user can seed a show from
  their own drawings instead of forging everything with FLUX.
- **Share links**: `/api/sharelink/<ep>` → HMAC-signed `/share/…` URL that
  streams the final with no login. Revoke-all by rotating `key.txt`.
- **Script breakdown**: `/api/breakdown` turns pasted prose into gated shots
  via the Claude API *when a funded key exists* in `workbench_data/llm_key.txt`
  (or `ANTHROPIC_API_KEY`). Without one it returns an honest 501. The
  current project key has no credit, so today the button explains itself.
- **PWA**: `manifest.json` → "Add to Home Screen" installs the console.

## What is deliberately NOT here

Payments (per instruction), email verification, rate limiting beyond quotas,
and per-user storage isolation — all users share one filesystem tree, scoped
by show ownership only. Fine for invited testers; not for hostile strangers.
