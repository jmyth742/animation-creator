#!/usr/bin/env python3
"""
Download FLUX.1-schnell model files for T2I reference image generation.

Files downloaded:
  ~5.8 GB  flux1-schnell-Q4_K_S.gguf       → ComfyUI/models/unet/
  ~4.9 GB  t5xxl_fp8_e4m3fn.safetensors    → ComfyUI/models/text_encoders/
  ~246 MB  clip_l.safetensors              → ComfyUI/models/text_encoders/
  ~335 MB  ae.safetensors (FLUX VAE)       → ComfyUI/models/vae/

The first 3 files are public. The FLUX VAE requires a free HuggingFace account
and accepting the FLUX.1-schnell license:
  https://huggingface.co/black-forest-labs/FLUX.1-schnell

Set HF_TOKEN in your environment before running if you haven't already:
  export HF_TOKEN=hf_your_token_here

Usage:
  conda activate hunyuan-comfy
  python scripts/download_flux.py
"""

import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("Installing requests...")
    os.system(f"{sys.executable} -m pip install -q requests")
    import requests

# ── Paths ──────────────────────────────────────────────────────────────────────

WORKSPACE = Path(__file__).resolve().parent.parent
COMFYUI = WORKSPACE / "ComfyUI" / "models"

DEST = {
    "unet":          COMFYUI / "unet",
    "text_encoders": COMFYUI / "text_encoders",
    "vae":           COMFYUI / "vae",
}

# ── File manifest ──────────────────────────────────────────────────────────────

FILES = [
    {
        "filename": "flux1-schnell-Q4_K_S.gguf",
        "dest_dir": "unet",
        "url": "https://huggingface.co/city96/FLUX.1-schnell-gguf/resolve/main/flux1-schnell-Q4_K_S.gguf",
        "size_gb": 5.8,
        "gated": False,
    },
    {
        "filename": "t5xxl_fp8_e4m3fn.safetensors",
        "dest_dir": "text_encoders",
        "url": "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors",
        "size_gb": 4.9,
        "gated": False,
    },
    {
        "filename": "clip_l.safetensors",
        "dest_dir": "text_encoders",
        "url": "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors",
        "size_gb": 0.25,
        "gated": False,
    },
    {
        "filename": "ae.safetensors",
        "dest_dir": "vae",
        "url": "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors",
        "size_gb": 0.33,
        "gated": True,
    },
]

# ── Helpers ────────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RED    = "\033[31m"
BOLD   = "\033[1m"


def fmt_size(n_bytes: int) -> str:
    if n_bytes >= 1_073_741_824:
        return f"{n_bytes / 1_073_741_824:.1f} GB"
    if n_bytes >= 1_048_576:
        return f"{n_bytes / 1_048_576:.0f} MB"
    return f"{n_bytes / 1024:.0f} KB"


def progress_bar(done: int, total: int, width: int = 40) -> str:
    if total == 0:
        return "[" + "?" * width + "]"
    pct = done / total
    filled = int(pct * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct * 100:.1f}%"


def download(url: str, dest: Path, token: str | None) -> bool:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        r = requests.get(url, headers=headers, stream=True, timeout=30)
    except requests.ConnectionError as e:
        print(f"  {RED}Connection error: {e}{RESET}")
        return False

    if r.status_code == 401:
        print(f"  {RED}Authentication required. Set HF_TOKEN and re-run.{RESET}")
        return False
    if r.status_code == 403:
        print(f"  {RED}Access denied — accept the model license at the HuggingFace URL above.{RESET}")
        return False
    if r.status_code != 200:
        print(f"  {RED}HTTP {r.status_code}{RESET}")
        return False

    total = int(r.headers.get("Content-Length", 0))
    done = 0
    t0 = time.time()

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    try:
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):  # 1 MB chunks
                f.write(chunk)
                done += len(chunk)
                elapsed = time.time() - t0
                speed = done / elapsed if elapsed > 0 else 0
                bar = progress_bar(done, total)
                print(
                    f"  {CYAN}{bar}  {fmt_size(done)}/{fmt_size(total)}  "
                    f"{fmt_size(int(speed))}/s{RESET}",
                    end="\r",
                )
        tmp.rename(dest)
        print()  # newline after progress
        return True
    except Exception as e:
        tmp.unlink(missing_ok=True)
        print(f"\n  {RED}Download failed: {e}{RESET}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("HF_TOKEN", "").strip() or None

    print(f"\n{BOLD}FLUX.1-schnell model downloader{RESET}")
    print(f"Destination: {COMFYUI}\n")

    if not token:
        print(
            f"{YELLOW}⚠  HF_TOKEN not set. Public files will download fine.\n"
            f"   For ae.safetensors (FLUX VAE) you need a token:\n"
            f"   1. Create a free account at https://huggingface.co\n"
            f"   2. Accept the license at https://huggingface.co/black-forest-labs/FLUX.1-schnell\n"
            f"   3. Generate a token at https://huggingface.co/settings/tokens\n"
            f"   4. Re-run:  HF_TOKEN=hf_xxx python scripts/download_flux.py{RESET}\n"
        )

    results = {}
    for f in FILES:
        dest = DEST[f["dest_dir"]] / f["filename"]
        label = f"{f['filename']} (~{f['size_gb']} GB)"

        if dest.exists():
            size = dest.stat().st_size
            print(f"{GREEN}✓  {label}  [{fmt_size(size)}]  already exists — skipping{RESET}")
            results[f["filename"]] = "exists"
            continue

        if f["gated"] and not token:
            print(f"{YELLOW}⚠  {label}  — skipped (needs HF_TOKEN, see above){RESET}")
            results[f["filename"]] = "skipped"
            continue

        print(f"\n{BOLD}↓  {label}{RESET}")
        print(f"   {f['url']}")
        ok = download(f["url"], dest, token if f["gated"] else None)
        results[f["filename"]] = "ok" if ok else "failed"
        if ok:
            print(f"   {GREEN}Saved → {dest}{RESET}")

    # ── Summary ────────────────────────────────────────────────────────────────

    print(f"\n{BOLD}{'─' * 60}{RESET}")
    all_present = all(
        (DEST[f["dest_dir"]] / f["filename"]).exists() for f in FILES
    )

    if all_present:
        print(f"{GREEN}{BOLD}✓  All files present. FLUX T2I is ready.{RESET}")
        print(
            "\nTo verify in ComfyUI, open http://localhost:8188 and check that\n"
            "UnetLoaderGGUF can see  flux1-schnell-Q4_K_S.gguf  in its dropdown."
        )
    else:
        missing = [f["filename"] for f in FILES if not (DEST[f["dest_dir"]] / f["filename"]).exists()]
        print(f"{YELLOW}Missing: {', '.join(missing)}{RESET}")
        if any(f["filename"] == "ae.safetensors" for f in FILES if f["filename"] in missing):
            print(
                f"\n{YELLOW}The VAE (ae.safetensors) is still missing.\n"
                f"Set HF_TOKEN and re-run — everything else will be skipped.{RESET}"
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
