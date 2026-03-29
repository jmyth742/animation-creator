"""
Training Orchestrator for LoRA training on remote RunPod pods.

Manages the full lifecycle: pod creation, environment setup, dataset upload,
training execution, result download, and pod cleanup — all via RunPod GraphQL
API and SSH.

Usage:
    from runpod.training_orchestrator import TrainingOrchestrator

    orch = TrainingOrchestrator()
    pod_id, ssh_host, ssh_port = orch.create_training_pod()
    orch.wait_for_pod_ready(pod_id)
    orch.bootstrap_training_env(ssh_host, ssh_port)
    orch.upload_dataset(ssh_host, ssh_port, "/workspace/datasets/my_char")
    session = orch.start_training(ssh_host, ssh_port, {
        "dataset_path": "/workspace/datasets/my_char",
        "character_name": "my_char",
    })
    status = orch.check_training_status(ssh_host, ssh_port, session)
    orch.download_lora(ssh_host, ssh_port, remote_path, local_dest)
    orch.stop_pod(pod_id)
"""

import json
import logging
import os
import subprocess
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RUNPOD_GRAPHQL_URL = "https://api.runpod.io/graphql"

DEFAULT_DOCKER_IMAGE = "runpod/pytorch:2.1.0-py3.10-cuda12.1.0-devel-ubuntu22.04"

SSH_KEY_PATHS = [
    "/root/.ssh/id_ed25519",
    "/root/.runpod/ssh/RunPod-Key-Go",
]

# HuggingFace model references needed for training
HF_DIT_REPO = "Comfy-Org/HunyuanVideo_1.5_repackaged"
HF_DIT_FILE = "split_files/diffusion_models/hunyuanvideo1.5_480p_t2v_cfg_distilled_fp16.safetensors"
HF_VAE_REPO = "Comfy-Org/HunyuanVideo_1.5_repackaged"
HF_VAE_FILE = "split_files/vae/hunyuanvideo15_vae_fp16.safetensors"
HF_TE_REPO = "Comfy-Org/HunyuanVideo_1.5_repackaged"
HF_TE_FILE = "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"
HF_BYT5_REPO = "Comfy-Org/HunyuanVideo_1.5_repackaged"
HF_BYT5_FILE = "split_files/text_encoders/byt5_small_glyphxl_fp16.safetensors"

# Default training hyperparameters
DEFAULT_TRAINING_CONFIG = {
    "rank": 32,
    "alpha": 32,
    "lr": "1e-4",
    "epochs": 150,
    "save_every": 25,
    "resolution": "480,320",
    "blocks_to_swap": 20,  # 20 for 48GB GPU (A6000), 32 for 24GB
    "optimizer": "adamw8bit",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PodInfo:
    """Tracks a running training pod."""
    pod_id: str
    ssh_host: str
    ssh_port: int
    gpu_type: str
    status: str = "CREATED"


@dataclass
class TrainingStatus:
    """Snapshot of training progress."""
    running: bool
    current_epoch: Optional[int] = None
    total_epochs: Optional[int] = None
    latest_loss: Optional[float] = None
    latest_lr: Optional[float] = None
    log_tail: str = ""
    elapsed_seconds: Optional[float] = None


# Type alias for the status callback
StatusCallback = Callable[[Dict[str, Any]], None]


def _noop_callback(status: Dict[str, Any]) -> None:
    """Default no-op status callback."""
    pass


# ---------------------------------------------------------------------------
# Helper: find a working SSH key
# ---------------------------------------------------------------------------

def _find_ssh_key() -> str:
    """Return the first SSH key path that exists on disk."""
    for path in SSH_KEY_PATHS:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(
        f"No SSH key found. Checked: {SSH_KEY_PATHS}"
    )


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class TrainingOrchestrator:
    """Manages LoRA training lifecycle on a remote RunPod pod."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        ssh_key_path: Optional[str] = None,
        status_callback: Optional[StatusCallback] = None,
    ):
        self.api_key = api_key or os.environ.get("RUNPOD_API_KEY")
        if not self.api_key:
            raise ValueError(
                "RunPod API key required. Set RUNPOD_API_KEY env var or pass api_key=."
            )
        self.ssh_key_path = ssh_key_path or _find_ssh_key()
        self.callback = status_callback or _noop_callback
        self._pods: Dict[str, PodInfo] = {}

    # ------------------------------------------------------------------
    # Status callback helper
    # ------------------------------------------------------------------

    def _notify(self, stage: str, message: str, progress: float = 0.0,
                **extra: Any) -> None:
        """Send a status update via the callback."""
        payload = {
            "stage": stage,
            "message": message,
            "progress": round(progress, 3),
            **extra,
        }
        logger.info("[%s] %s (%.0f%%)", stage, message, progress * 100)
        try:
            self.callback(payload)
        except Exception:
            logger.exception("Status callback raised an exception")

    # ------------------------------------------------------------------
    # RunPod GraphQL helpers
    # ------------------------------------------------------------------

    def _gql(self, query: str, variables: Optional[dict] = None) -> dict:
        """Execute a RunPod GraphQL query and return the JSON response."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        body: Dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables

        resp = requests.post(RUNPOD_GRAPHQL_URL, json=body, headers=headers,
                             timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"RunPod GraphQL errors: {json.dumps(data['errors'])}")
        return data

    # ------------------------------------------------------------------
    # SSH / rsync helpers
    # ------------------------------------------------------------------

    def _ssh_opts(self, ssh_host: str, ssh_port: int) -> List[str]:
        """Build common SSH option flags."""
        return [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=30",
            "-i", self.ssh_key_path,
            "-p", str(ssh_port),
        ]

    def _ssh_run(self, ssh_host: str, ssh_port: int, command: str,
                 timeout: int = 600, check: bool = True) -> subprocess.CompletedProcess:
        """Run a command on the remote pod via SSH."""
        ssh_cmd = self._ssh_opts(ssh_host, ssh_port) + [
            f"root@{ssh_host}",
            command,
        ]
        logger.debug("SSH command: %s", " ".join(ssh_cmd))
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            logger.error("SSH command failed (rc=%d): %s\nstderr: %s",
                         result.returncode, command, result.stderr)
            raise subprocess.CalledProcessError(
                result.returncode, command,
                output=result.stdout, stderr=result.stderr,
            )
        return result

    def _rsync(self, ssh_host: str, ssh_port: int,
               src: str, dest: str, direction: str = "upload",
               timeout: int = 1800) -> subprocess.CompletedProcess:
        """rsync files to/from the remote pod.

        direction: "upload" (local→remote) or "download" (remote→local)
        """
        ssh_cmd_str = (
            f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
            f"-o ConnectTimeout=15 -i {self.ssh_key_path} -p {ssh_port}"
        )
        if direction == "upload":
            rsync_cmd = [
                "rsync", "-avz", "--progress",
                "-e", ssh_cmd_str,
                src,
                f"root@{ssh_host}:{dest}",
            ]
        else:
            rsync_cmd = [
                "rsync", "-avz", "--progress",
                "-e", ssh_cmd_str,
                f"root@{ssh_host}:{src}",
                dest,
            ]

        logger.debug("rsync command: %s", " ".join(rsync_cmd))
        result = subprocess.run(
            rsync_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, " ".join(rsync_cmd),
                output=result.stdout, stderr=result.stderr,
            )
        return result

    # ------------------------------------------------------------------
    # 1. create_training_pod
    # ------------------------------------------------------------------

    # GPUs verified to work with musubi-tuner LoRA training.
    # Requirements: CUDA compute >= 7.0, bf16 support, 24GB+ VRAM.
    # Maps GPU ID → blocks_to_swap (fewer = faster, requires more VRAM).
    TRAINING_COMPATIBLE_GPUS = {
        # 48GB — fast training, fewer blocks to swap
        "NVIDIA RTX A6000": 20,
        "NVIDIA A40": 20,
        "NVIDIA L40": 20,
        "NVIDIA L40S": 20,
        "NVIDIA RTX 6000 Ada Generation": 20,
        # 32GB
        "NVIDIA RTX 5000 Ada Generation": 28,
        "NVIDIA GeForce RTX 5090": 28,
        "NVIDIA RTX PRO 4500 Blackwell": 28,
        # 24GB — need more block swapping
        "NVIDIA GeForce RTX 3090": 32,
        "NVIDIA GeForce RTX 3090 Ti": 32,
        "NVIDIA GeForce RTX 4090": 32,
        "NVIDIA RTX A5000": 32,
    }

    GPU_FALLBACK_ORDER = list(TRAINING_COMPATIBLE_GPUS.keys())

    def _get_available_gpus(self, preferred_gpu: str) -> List[str]:
        """Query RunPod for GPUs with actual stock, ordered by availability.

        Returns the preferred GPU first (if in stock), then High stock, Medium, Low.
        Only includes 24GB+ GPUs under $2/hr.
        """
        query = """query { gpuTypes { id displayName memoryInGb communityPrice lowestPrice(input: {gpuCount: 1}) { stockStatus } } }"""
        try:
            data = self._gql(query)
            gpus = data.get("data", {}).get("gpuTypes", [])
        except Exception:
            logger.warning("Failed to query GPU availability, using static fallback")
            candidates = [preferred_gpu]
            for fb in self.GPU_FALLBACK_ORDER:
                if fb != preferred_gpu:
                    candidates.append(fb)
            return candidates

        # Filter to only training-compatible GPUs with actual stock
        stock_order = {"High": 0, "Medium": 1, "Low": 2}
        available = []
        for g in gpus:
            gpu_id = g.get("id", "")
            if gpu_id not in self.TRAINING_COMPATIBLE_GPUS:
                continue
            price = g.get("communityPrice") or 0
            stock = (g.get("lowestPrice") or {}).get("stockStatus") or "None"
            if stock != "None" and price > 0:
                available.append((gpu_id, stock, price))

        # Sort: preferred first, then by stock level, then price
        def sort_key(item):
            gpu_id, stock, price = item
            is_preferred = 0 if gpu_id == preferred_gpu else 1
            return (is_preferred, stock_order.get(stock, 3), price)

        available.sort(key=sort_key)

        candidates = [gpu_id for gpu_id, _, _ in available]
        if not candidates:
            # Nothing in stock, fall back to static list
            candidates = [preferred_gpu]
            for fb in self.GPU_FALLBACK_ORDER:
                if fb != preferred_gpu:
                    candidates.append(fb)

        for gpu_id, stock, price in available[:5]:
            logger.info("GPU available: %s (stock=%s, $%.2f/hr)", gpu_id, stock, price)

        return candidates

    def create_training_pod(
        self,
        gpu_type: str = "NVIDIA RTX A6000",
        volume_size_gb: int = 50,
        pod_name: str = "lora-training",
        disk_size_gb: int = 20,
        docker_image: str = DEFAULT_DOCKER_IMAGE,
    ) -> Tuple[str, str, int]:
        """Create a new RunPod pod for training.

        If the requested GPU is unavailable, automatically tries fallback GPUs.

        Returns:
            (pod_id, ssh_host, ssh_port)
        """
        # Check live stock and build candidate list ordered by availability
        gpu_candidates = self._get_available_gpus(gpu_type)

        mutation = textwrap.dedent("""\
            mutation createPod($input: PodFindAndDeployOnDemandInput!) {
                podFindAndDeployOnDemand(input: $input) {
                    id
                    desiredStatus
                    runtime {
                        ports {
                            ip
                            isIpPublic
                            privatePort
                            publicPort
                        }
                    }
                }
            }
        """)

        last_error = None
        for candidate_gpu in gpu_candidates:
            self._notify("creating_pod", f"Trying {candidate_gpu}...", 0.0)

            variables = {
                "input": {
                    "name": pod_name,
                    "imageName": docker_image,
                    "gpuTypeId": candidate_gpu,
                    "cloudType": "ALL",
                    "volumeInGb": volume_size_gb,
                    "containerDiskInGb": disk_size_gb,
                    "minVcpuCount": 2,
                    "minMemoryInGb": 16,
                    "ports": "22/tcp",
                    "dockerArgs": "",
                    "startSsh": True,
                    "supportPublicIp": True,
                }
            }

            try:
                data = self._gql(mutation, variables)
                pod_data = data["data"]["podFindAndDeployOnDemand"]
                pod_id = pod_data["id"]
                # Success — update gpu_type to what actually deployed
                gpu_type = candidate_gpu
                break
            except RuntimeError as exc:
                last_error = exc
                if "SUPPLY_CONSTRAINT" in str(exc):
                    logger.warning("GPU %s unavailable, trying next...", candidate_gpu)
                    self._notify("creating_pod",
                                 f"{candidate_gpu} unavailable, trying next...", 0.02)
                    continue
                else:
                    raise
        else:
            raise RuntimeError(
                f"No GPUs available after trying {len(gpu_candidates)} options. "
                f"Last error: {last_error}"
            )

        # SSH connection details come after the pod is actually running,
        # so we return placeholders and resolve them in wait_for_pod_ready
        logger.info("Pod created: %s", pod_id)
        self._notify("creating_pod", f"Pod {pod_id} created, waiting for SSH details...", 0.05)

        # We need to poll for SSH details since they aren't immediately available
        ssh_host, ssh_port = self._resolve_ssh_details(pod_id)

        pod_info = PodInfo(
            pod_id=pod_id,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            gpu_type=gpu_type,
            status="CREATED",
        )
        self._pods[pod_id] = pod_info

        self._notify("creating_pod",
                      f"Pod {pod_id} created. SSH: {ssh_host}:{ssh_port}", 0.1)
        return pod_id, ssh_host, ssh_port

    def _resolve_ssh_details(self, pod_id: str,
                             timeout: int = 120) -> Tuple[str, int]:
        """Poll until SSH connection details are available for the pod."""
        query = textwrap.dedent("""\
            query getPod($podId: String!) {
                pod(input: { podId: $podId }) {
                    id
                    desiredStatus
                    runtime {
                        ports {
                            ip
                            isIpPublic
                            privatePort
                            publicPort
                        }
                    }
                }
            }
        """)

        deadline = time.time() + timeout
        while time.time() < deadline:
            data = self._gql(query, {"podId": pod_id})
            pod = data["data"]["pod"]
            runtime = pod.get("runtime")
            if runtime and runtime.get("ports"):
                for port_info in runtime["ports"]:
                    if port_info.get("privatePort") == 22 and port_info.get("ip"):
                        return port_info["ip"], port_info["publicPort"]
            time.sleep(5)

        raise TimeoutError(
            f"Timed out waiting for SSH details on pod {pod_id} "
            f"after {timeout}s"
        )

    # ------------------------------------------------------------------
    # 2. wait_for_pod_ready
    # ------------------------------------------------------------------

    def wait_for_pod_ready(self, pod_id: str, timeout: int = 300) -> str:
        """Poll pod status until RUNNING. Returns final status string."""
        self._notify("waiting_for_pod", f"Waiting for pod {pod_id} to be ready...", 0.1)

        query = textwrap.dedent("""\
            query getPod($podId: String!) {
                pod(input: { podId: $podId }) {
                    id
                    desiredStatus
                    runtime {
                        uptimeInSeconds
                        ports {
                            ip
                            isIpPublic
                            privatePort
                            publicPort
                        }
                        gpus {
                            id
                            gpuUtilPercent
                            memoryUtilPercent
                        }
                    }
                }
            }
        """)

        deadline = time.time() + timeout
        poll_interval = 5
        last_status = "UNKNOWN"

        while time.time() < deadline:
            data = self._gql(query, {"podId": pod_id})
            pod = data["data"]["pod"]
            if pod is None:
                raise RuntimeError(f"Pod {pod_id} not found — may have been terminated")

            status = pod.get("desiredStatus", "UNKNOWN")
            runtime = pod.get("runtime")
            last_status = status

            if status == "EXITED":
                raise RuntimeError(f"Pod {pod_id} exited unexpectedly")

            if status == "RUNNING" and runtime and runtime.get("uptimeInSeconds", 0) > 0:
                # Verify SSH connectivity
                ssh_host = ssh_port = None
                if runtime.get("ports"):
                    for p in runtime["ports"]:
                        if p.get("privatePort") == 22 and p.get("ip"):
                            ssh_host = p["ip"]
                            ssh_port = p["publicPort"]
                            break

                if ssh_host and ssh_port:
                    # Update cached pod info
                    if pod_id in self._pods:
                        self._pods[pod_id].ssh_host = ssh_host
                        self._pods[pod_id].ssh_port = ssh_port
                        self._pods[pod_id].status = "RUNNING"

                    self._notify("waiting_for_pod",
                                 f"Pod {pod_id} is RUNNING (uptime: {runtime['uptimeInSeconds']}s)",
                                 0.15)

                    # Wait a few more seconds for SSH daemon to be fully ready
                    time.sleep(10)

                    # Test SSH connectivity
                    try:
                        self._ssh_run(ssh_host, ssh_port, "echo ready", timeout=30)
                        self._notify("waiting_for_pod",
                                     f"Pod {pod_id} SSH is accessible", 0.2)
                        return "RUNNING"
                    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                        logger.warning("SSH not yet accessible, retrying...")

            elapsed = time.time() - (deadline - timeout)
            progress = min(0.15 + 0.05 * (elapsed / timeout), 0.19)
            self._notify("waiting_for_pod",
                         f"Pod status: {status} (waiting...)", progress)
            time.sleep(poll_interval)

        raise TimeoutError(
            f"Pod {pod_id} did not become ready within {timeout}s. "
            f"Last status: {last_status}"
        )

    # ------------------------------------------------------------------
    # 3. bootstrap_training_env
    # ------------------------------------------------------------------

    def bootstrap_training_env(self, ssh_host: str, ssh_port: int) -> None:
        """SSH into the training pod and install all dependencies."""
        self._notify("bootstrapping", "Installing system dependencies...", 0.2)

        # Step 1: System packages
        self._ssh_run(ssh_host, ssh_port, textwrap.dedent("""\
            apt-get update -qq && \
            apt-get install -y -qq git git-lfs screen rsync ffmpeg > /dev/null 2>&1
        """).strip(), timeout=120)

        self._notify("bootstrapping", "Installing Python dependencies...", 0.25)

        # Step 2: Python packages for musubi-tuner
        self._ssh_run(ssh_host, ssh_port, textwrap.dedent("""\
            pip install -q --upgrade pip && \
            pip install -q torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 && \
            pip install -q accelerate bitsandbytes prodigyopt huggingface_hub && \
            pip install -q safetensors transformers sentencepiece protobuf && \
            pip install -q einops timm opencv-python-headless pillow pyyaml toml && \
            pip install -q wandb tensorboard
        """).strip(), timeout=300)

        self._notify("bootstrapping", "Cloning musubi-tuner...", 0.35)

        # Step 3: Clone musubi-tuner
        self._ssh_run(ssh_host, ssh_port, textwrap.dedent("""\
            if [ ! -d /workspace/musubi-tuner ]; then
                git clone https://github.com/kohya-ss/musubi-tuner /workspace/musubi-tuner
                cd /workspace/musubi-tuner && pip install -q -r requirements.txt
            else
                echo "musubi-tuner already exists"
            fi
        """).strip(), timeout=120)

        self._notify("bootstrapping", "Installing flash-attn...", 0.4)

        # Step 4: Flash attention (best-effort)
        self._ssh_run(ssh_host, ssh_port,
                      "pip install -q flash-attn --no-build-isolation 2>/dev/null || "
                      "echo 'flash-attn install skipped'",
                      timeout=600, check=False)

        self._notify("bootstrapping",
                     "Downloading full-precision DiT model (~16.7GB)...", 0.45)

        # Step 5: Download full-precision DiT model for training
        self._ssh_run(ssh_host, ssh_port, textwrap.dedent(f"""\
            mkdir -p /workspace/training_models
            python -c "
from huggingface_hub import hf_hub_download
import os
dest_dir = '/workspace/training_models/'
target = os.path.join(dest_dir, '{HF_DIT_FILE}')
if os.path.exists(target):
    print('DiT model already exists')
else:
    print('Downloading DiT model...')
    hf_hub_download('{HF_DIT_REPO}', filename='{HF_DIT_FILE}', local_dir=dest_dir)
    print('DiT model downloaded.')
"
        """).strip(), timeout=3600)

        self._notify("bootstrapping", "Downloading VAE...", 0.7)

        # Step 6: Download VAE
        self._ssh_run(ssh_host, ssh_port, textwrap.dedent(f"""\
            python -c "
from huggingface_hub import hf_hub_download
import os
dest_dir = '/workspace/training_models/'
target = os.path.join(dest_dir, '{HF_VAE_FILE}')
if os.path.exists(target):
    print('VAE already exists')
else:
    print('Downloading VAE...')
    hf_hub_download('{HF_VAE_REPO}', filename='{HF_VAE_FILE}', local_dir=dest_dir)
    print('VAE downloaded.')
"
        """).strip(), timeout=600)

        self._notify("bootstrapping", "Downloading text encoders...", 0.8)

        # Step 7: Download text encoders
        self._ssh_run(ssh_host, ssh_port, textwrap.dedent(f"""\
            python -c "
from huggingface_hub import hf_hub_download
import os
dest_dir = '/workspace/training_models/'
for repo, fname in [
    ('{HF_TE_REPO}', '{HF_TE_FILE}'),
    ('{HF_BYT5_REPO}', '{HF_BYT5_FILE}'),
]:
    target = os.path.join(dest_dir, fname)
    if os.path.exists(target):
        print(f'Already exists: {{fname}}')
    else:
        print(f'Downloading {{fname}}...')
        hf_hub_download(repo, filename=fname, local_dir=dest_dir)
        print(f'Downloaded: {{fname}}')
"
        """).strip(), timeout=600)

        self._notify("bootstrapping",
                     "Training environment ready.", 0.9)

    # ------------------------------------------------------------------
    # 4. upload_dataset
    # ------------------------------------------------------------------

    def upload_dataset(self, ssh_host: str, ssh_port: int,
                       local_dataset_path: str) -> str:
        """Upload dataset to training pod via rsync.

        Returns the remote dataset path.
        """
        dataset_name = Path(local_dataset_path).name
        remote_path = f"/workspace/datasets/{dataset_name}"

        self._notify("uploading_dataset",
                     f"Uploading dataset '{dataset_name}' to training pod...", 0.0)

        # Create remote directory
        self._ssh_run(ssh_host, ssh_port, f"mkdir -p {remote_path}")

        # rsync the dataset (trailing slash on src to copy contents)
        src = local_dataset_path.rstrip("/") + "/"
        self._rsync(ssh_host, ssh_port, src, remote_path + "/",
                    direction="upload", timeout=600)

        # Verify
        result = self._ssh_run(ssh_host, ssh_port,
                               f"ls -la {remote_path}/ | head -20")
        file_count = len(result.stdout.strip().splitlines()) - 1  # minus header
        self._notify("uploading_dataset",
                     f"Dataset uploaded: {file_count} files in {remote_path}",
                     1.0)
        return remote_path

    # ------------------------------------------------------------------
    # 5. start_training
    # ------------------------------------------------------------------

    def start_training(self, ssh_host: str, ssh_port: int,
                       config: Dict[str, Any]) -> str:
        """Start LoRA training on the remote pod inside a screen session.

        Required config keys:
            - dataset_path: remote path to dataset directory
            - character_name: name for the LoRA output

        Optional config keys (with defaults from DEFAULT_TRAINING_CONFIG):
            - rank, alpha, lr, epochs, save_every, resolution,
              blocks_to_swap, optimizer

        Returns:
            screen session name (for checking status later)
        """
        # Merge with defaults
        cfg = {**DEFAULT_TRAINING_CONFIG, **config}
        character_name = cfg["character_name"]
        dataset_path = cfg["dataset_path"]
        rank = cfg["rank"]
        alpha = cfg["alpha"]
        lr = cfg["lr"]
        epochs = cfg["epochs"]
        save_every = cfg["save_every"]
        resolution = cfg["resolution"]
        blocks_to_swap = cfg["blocks_to_swap"]
        optimizer = cfg["optimizer"]

        session_name = f"train_{character_name}"

        # Model paths on remote pod
        dit_path = f"/workspace/training_models/{HF_DIT_FILE}"
        vae_path = f"/workspace/training_models/{HF_VAE_FILE}"
        te_path = f"/workspace/training_models/{HF_TE_FILE}"
        byt5_path = f"/workspace/training_models/{HF_BYT5_FILE}"

        output_dir = f"/workspace/lora_outputs/{character_name}"
        cache_dir = f"/workspace/lora_cache/{character_name}"

        self._notify("starting_training",
                     f"Preparing training for '{character_name}'...", 0.0)

        # Create dataset config TOML on remote
        toml_content = textwrap.dedent(f"""\
            [general]
            resolution = [{resolution}]
            caption_extension = ".txt"
            batch_size = 1
            enable_bucket = true

            [[datasets]]
            image_directory = "{dataset_path}"
            cache_directory = "{cache_dir}/latents"
            num_repeats = 1
        """)

        # Check for video files and add video dataset config
        video_check = self._ssh_run(
            ssh_host, ssh_port,
            f'ls "{dataset_path}"/*.mp4 2>/dev/null | head -1',
            check=False,
        )
        if video_check.returncode == 0 and video_check.stdout.strip():
            toml_content += textwrap.dedent(f"""\

                [[datasets]]
                video_directory = "{dataset_path}"
                cache_directory = "{cache_dir}/latents_video"
                num_repeats = 1
                target_frames = [1, 25, 45]
                frame_extraction = "head"
            """)

        # Write config and create dirs on remote
        escaped_toml = toml_content.replace("'", "'\\''")
        self._ssh_run(ssh_host, ssh_port, textwrap.dedent(f"""\
            mkdir -p "{output_dir}" "{cache_dir}/latents" "{cache_dir}/latents_video"
            cat > "{cache_dir}/config.toml" << 'TOML_EOF'
{toml_content}TOML_EOF
        """).strip())

        self._notify("starting_training",
                     "Starting training in screen session...", 0.1)

        # Build the full training script to run in screen
        training_script = textwrap.dedent(f"""\
            #!/bin/bash
            set -euo pipefail

            cd /workspace/musubi-tuner
            CONFIG="{cache_dir}/config.toml"
            LOG_FILE="{output_dir}/training.log"

            echo "=== Caching latents ===" | tee "$LOG_FILE"
            python hv_1_5_cache_latents.py \\
                --dataset_config "$CONFIG" \\
                --vae "{vae_path}" \\
                --vae_chunk_size 32 \\
                --vae_tiling 2>&1 | tee -a "$LOG_FILE"

            echo "" | tee -a "$LOG_FILE"
            echo "=== Caching text encoder outputs ===" | tee -a "$LOG_FILE"
            python hv_1_5_cache_text_encoder_outputs.py \\
                --dataset_config "$CONFIG" \\
                --text_encoder "{te_path}" \\
                --byt5 "{byt5_path}" \\
                --batch_size 16 2>&1 | tee -a "$LOG_FILE"

            echo "" | tee -a "$LOG_FILE"
            echo "=== Training LoRA ===" | tee -a "$LOG_FILE"
            accelerate launch --num_cpu_threads_per_process 1 --mixed_precision bf16 \\
                hv_1_5_train_network.py \\
                --dit "{dit_path}" \\
                --dataset_config "$CONFIG" \\
                --network_module networks.lora_hv_1_5 \\
                --network_dim {rank} \\
                --network_alpha {alpha} \\
                --learning_rate {lr} \\
                --optimizer_type {optimizer} \\
                --mixed_precision bf16 \\
                --max_train_epochs {epochs} \\
                --save_every_n_epochs {save_every} \\
                --gradient_checkpointing \\
                --fp8_base \\
                --blocks_to_swap {blocks_to_swap} \\
                --timestep_sampling shift \\
                --discrete_flow_shift 2.0 \\
                --weighting_scheme none \\
                --sdpa \\
                --split_attn \\
                --output_dir "{output_dir}" \\
                --output_name "{character_name}" 2>&1 | tee -a "$LOG_FILE"

            echo "" | tee -a "$LOG_FILE"
            echo "=== Converting for ComfyUI ===" | tee -a "$LOG_FILE"
            LATEST=$(ls -t "{output_dir}"/{character_name}*.safetensors 2>/dev/null | head -1)
            if [ -n "$LATEST" ]; then
                python convert_lora.py \\
                    --input "$LATEST" \\
                    --output "{output_dir}/{character_name}-comfyui.safetensors" \\
                    --target other 2>&1 | tee -a "$LOG_FILE"
                echo "TRAINING_COMPLETE" | tee -a "$LOG_FILE"
            else
                echo "TRAINING_FAILED: No checkpoint found" | tee -a "$LOG_FILE"
            fi
        """)

        # Write the script to remote and launch in screen
        escaped_script = training_script.replace("'", "'\\''")
        self._ssh_run(ssh_host, ssh_port, textwrap.dedent(f"""\
            cat > /tmp/train_{character_name}.sh << 'SCRIPT_EOF'
{training_script}SCRIPT_EOF
            chmod +x /tmp/train_{character_name}.sh
            screen -dmS {session_name} bash /tmp/train_{character_name}.sh
        """).strip())

        # Verify screen session started
        verify = self._ssh_run(ssh_host, ssh_port,
                               f"screen -ls | grep {session_name} || true",
                               check=False)
        if session_name in verify.stdout:
            self._notify("starting_training",
                         f"Training started in session '{session_name}'", 0.2)
        else:
            raise RuntimeError(
                f"Failed to start screen session '{session_name}'. "
                f"stdout: {verify.stdout}, stderr: {verify.stderr}"
            )

        return session_name

    # ------------------------------------------------------------------
    # 6. check_training_status
    # ------------------------------------------------------------------

    def check_training_status(self, ssh_host: str, ssh_port: int,
                              session_name: str) -> TrainingStatus:
        """Check if training is still running and parse latest metrics."""
        # Check if screen session is alive
        screen_check = self._ssh_run(
            ssh_host, ssh_port,
            f"screen -ls | grep {session_name} || echo 'NOT_RUNNING'",
            check=False,
        )
        running = session_name in screen_check.stdout and "NOT_RUNNING" not in screen_check.stdout

        # Extract character name from session name
        char_name = session_name.replace("train_", "", 1)
        log_path = f"/workspace/lora_outputs/{char_name}/training.log"

        # Get tail of log file
        log_result = self._ssh_run(
            ssh_host, ssh_port,
            f"tail -50 {log_path} 2>/dev/null || echo 'NO_LOG'",
            check=False,
        )
        log_tail = log_result.stdout.strip()

        status = TrainingStatus(running=running, log_tail=log_tail)

        # Parse epoch and loss from log lines
        # Typical accelerate/musubi-tuner output:
        #   epoch 5/150, step 120, loss=0.0523, lr=1e-4
        #   or: Steps:  50%|###  | 50/100 [00:30<00:30, 1.00it/s, loss=0.052]
        for line in reversed(log_tail.splitlines()):
            line_lower = line.lower()

            # Try to parse epoch info
            if status.current_epoch is None and "epoch" in line_lower:
                try:
                    # Pattern: epoch N/M
                    import re
                    epoch_match = re.search(r'epoch\s+(\d+)\s*/\s*(\d+)', line_lower)
                    if epoch_match:
                        status.current_epoch = int(epoch_match.group(1))
                        status.total_epochs = int(epoch_match.group(2))
                except (ValueError, IndexError):
                    pass

            # Try to parse loss
            if status.latest_loss is None and "loss" in line_lower:
                try:
                    import re
                    loss_match = re.search(r'loss[=:\s]+([0-9]+\.?[0-9]*(?:e[+-]?\d+)?)', line_lower)
                    if loss_match:
                        status.latest_loss = float(loss_match.group(1))
                except (ValueError, IndexError):
                    pass

            # Try to parse lr
            if status.latest_lr is None and "lr" in line_lower:
                try:
                    import re
                    lr_match = re.search(r'lr[=:\s]+([0-9]+\.?[0-9]*(?:e[+-]?\d+)?)', line_lower)
                    if lr_match:
                        status.latest_lr = float(lr_match.group(1))
                except (ValueError, IndexError):
                    pass

            # Check for completion
            if "TRAINING_COMPLETE" in line:
                status.running = False
                break
            if "TRAINING_FAILED" in line:
                status.running = False
                break

        return status

    # ------------------------------------------------------------------
    # 7. download_lora
    # ------------------------------------------------------------------

    def download_lora(self, ssh_host: str, ssh_port: int,
                      remote_lora_path: str,
                      local_dest: Optional[str] = None) -> str:
        """Download trained LoRA .safetensors from training pod.

        If local_dest is not specified, downloads to
        ComfyUI/models/loras/ on this machine.

        Returns the local path of the downloaded file.
        """
        if local_dest is None:
            local_dest = "/workspace/text-to-video/ComfyUI/models/loras/"

        os.makedirs(local_dest, exist_ok=True)

        filename = Path(remote_lora_path).name
        local_path = os.path.join(local_dest, filename)

        self._notify("downloading_lora",
                     f"Downloading LoRA '{filename}'...", 0.0)

        self._rsync(ssh_host, ssh_port, remote_lora_path, local_dest,
                    direction="download", timeout=600)

        if os.path.isfile(local_path):
            size_mb = os.path.getsize(local_path) / (1024 * 1024)
            self._notify("downloading_lora",
                         f"Downloaded {filename} ({size_mb:.1f} MB)", 1.0)
        else:
            # rsync may have put it inside a subdirectory
            self._notify("downloading_lora",
                         f"Download complete to {local_dest}", 1.0)

        return local_path

    # ------------------------------------------------------------------
    # 8. stop_pod / terminate_pod
    # ------------------------------------------------------------------

    def stop_pod(self, pod_id: str) -> None:
        """Stop a pod (preserves disk, stops billing for GPU)."""
        self._notify("stopping_pod", f"Stopping pod {pod_id}...", 0.0)

        mutation = textwrap.dedent("""\
            mutation stopPod($podId: String!) {
                podStop(input: { podId: $podId }) {
                    id
                    desiredStatus
                }
            }
        """)
        self._gql(mutation, {"podId": pod_id})

        if pod_id in self._pods:
            self._pods[pod_id].status = "STOPPED"

        self._notify("stopping_pod", f"Pod {pod_id} stopped.", 1.0)

    def terminate_pod(self, pod_id: str) -> None:
        """Terminate a pod (destroys disk, fully stops billing)."""
        self._notify("terminating_pod", f"Terminating pod {pod_id}...", 0.0)

        mutation = textwrap.dedent("""\
            mutation terminatePod($podId: String!) {
                podTerminate(input: { podId: $podId })
            }
        """)
        self._gql(mutation, {"podId": pod_id})

        if pod_id in self._pods:
            del self._pods[pod_id]

        self._notify("terminating_pod", f"Pod {pod_id} terminated.", 1.0)

    # ------------------------------------------------------------------
    # 9. list_pods
    # ------------------------------------------------------------------

    def list_pods(self) -> List[Dict[str, Any]]:
        """List all pods on the RunPod account."""
        query = textwrap.dedent("""\
            query getPods {
                myself {
                    pods {
                        id
                        name
                        desiredStatus
                        imageName
                        machineId
                        machine {
                            gpuDisplayName
                        }
                        runtime {
                            uptimeInSeconds
                            ports {
                                ip
                                isIpPublic
                                privatePort
                                publicPort
                            }
                            gpus {
                                id
                                gpuUtilPercent
                                memoryUtilPercent
                            }
                        }
                    }
                }
            }
        """)

        data = self._gql(query)
        pods = data["data"]["myself"]["pods"]

        result = []
        for pod in pods:
            ssh_host = None
            ssh_port = None
            runtime = pod.get("runtime")
            if runtime and runtime.get("ports"):
                for port_info in runtime["ports"]:
                    if port_info.get("privatePort") == 22 and port_info.get("ip"):
                        ssh_host = port_info["ip"]
                        ssh_port = port_info["publicPort"]
                        break

            result.append({
                "pod_id": pod["id"],
                "name": pod.get("name", ""),
                "status": pod.get("desiredStatus", "UNKNOWN"),
                "gpu": pod.get("machine", {}).get("gpuDisplayName", ""),
                "image": pod.get("imageName", ""),
                "uptime_seconds": runtime.get("uptimeInSeconds") if runtime else None,
                "ssh_host": ssh_host,
                "ssh_port": ssh_port,
            })

        return result

    # ------------------------------------------------------------------
    # Convenience: full pipeline
    # ------------------------------------------------------------------

    def run_full_training(
        self,
        local_dataset_path: str,
        character_name: str,
        gpu_type: str = "NVIDIA RTX A6000",
        training_config: Optional[Dict[str, Any]] = None,
        poll_interval: int = 60,
        auto_terminate: bool = False,
    ) -> str:
        """Run the entire training pipeline end-to-end.

        This is a blocking call that:
        1. Creates a pod
        2. Waits for it to be ready
        3. Bootstraps the environment
        4. Uploads the dataset
        5. Starts training
        6. Polls until training completes
        7. Downloads the LoRA
        8. Optionally stops/terminates the pod

        Returns the local path of the downloaded LoRA file.
        """
        config = training_config or {}
        config["character_name"] = character_name

        # Step 1-2: Create pod and wait
        pod_id, ssh_host, ssh_port = self.create_training_pod(gpu_type=gpu_type)
        self.wait_for_pod_ready(pod_id)

        try:
            # Step 3: Bootstrap
            self.bootstrap_training_env(ssh_host, ssh_port)

            # Step 4: Upload dataset
            remote_dataset = self.upload_dataset(
                ssh_host, ssh_port, local_dataset_path
            )
            config["dataset_path"] = remote_dataset

            # Step 5: Start training
            session_name = self.start_training(ssh_host, ssh_port, config)

            # Step 6: Poll for completion
            self._notify("training", "Training in progress...", 0.3)
            while True:
                time.sleep(poll_interval)
                status = self.check_training_status(ssh_host, ssh_port,
                                                    session_name)
                if status.current_epoch and status.total_epochs:
                    progress = 0.3 + 0.5 * (status.current_epoch / status.total_epochs)
                    self._notify(
                        "training",
                        f"Epoch {status.current_epoch}/{status.total_epochs}, "
                        f"loss={status.latest_loss}",
                        progress,
                    )

                if not status.running:
                    break

            # Step 7: Download LoRA
            remote_lora = (
                f"/workspace/lora_outputs/{character_name}/"
                f"{character_name}-comfyui.safetensors"
            )
            local_path = self.download_lora(ssh_host, ssh_port, remote_lora)

            self._notify("complete",
                         f"Training complete. LoRA saved to {local_path}", 1.0)
            return local_path

        finally:
            # Step 8: Cleanup
            if auto_terminate:
                self.terminate_pod(pod_id)
            else:
                self.stop_pod(pod_id)
