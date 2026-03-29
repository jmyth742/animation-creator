"""Training job routes — LoRA training via RunPod."""

from __future__ import annotations

import datetime
import os
import shutil
import tarfile
import tempfile
import threading
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from database import get_db
from models import Character, Location, Project, TrainingJob, User
from schemas import (
    DatasetGenerateRequest,
    DatasetGenerateResponse,
    DatasetJobStatus,
    LoraInfo,
    SetLoraRequest,
    TrainingJobCreate,
    TrainingJobRead,
    TrainingStartResponse,
)

router = APIRouter()


# ── GET /training/gpu-availability ────────────────────────────────────────────
# Defined FIRST so it doesn't get swallowed by /training/{job_id}

@router.get("/training/gpu-availability")
def get_gpu_availability(
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Check which GPUs are available on RunPod right now."""
    import requests as _requests

    api_key = os.environ.get("RUNPOD_API_KEY", "")
    if not api_key:
        return []

    query = """query { gpuTypes { id displayName memoryInGb communityPrice securePrice lowestPrice(input: {gpuCount: 1}) { stockStatus } } }"""
    try:
        resp = _requests.post(
            "https://api.runpod.io/graphql",
            json={"query": query},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=10,
        )
        data = resp.json().get("data", {}).get("gpuTypes", [])
    except Exception:
        return []

    # Only GPUs verified to work with musubi-tuner LoRA training
    compatible_gpus = {
        "NVIDIA RTX A6000", "NVIDIA A40", "NVIDIA L40", "NVIDIA L40S",
        "NVIDIA RTX 6000 Ada Generation",
        "NVIDIA RTX 5000 Ada Generation", "NVIDIA GeForce RTX 5090",
        "NVIDIA RTX PRO 4500 Blackwell",
        "NVIDIA GeForce RTX 3090", "NVIDIA GeForce RTX 3090 Ti",
        "NVIDIA GeForce RTX 4090", "NVIDIA RTX A5000",
    }

    results = []
    for g in data:
        gpu_id = g.get("id", "")
        if gpu_id not in compatible_gpus:
            continue
        mem = g.get("memoryInGb", 0)
        price = g.get("communityPrice") or g.get("securePrice") or 0
        stock = (g.get("lowestPrice") or {}).get("stockStatus") or "None"
        if stock != "None" and price > 0:
            results.append({
                "id": gpu_id,
                "name": g["displayName"],
                "vram_gb": mem,
                "price": price,
                "stock": stock,
            })
    results.sort(key=lambda x: ({"High": 0, "Medium": 1, "Low": 2}.get(x["stock"], 3), x["price"]))
    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_project_or_404(project_id: int, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def _get_training_job_or_404(job_id: int, user: User, db: Session) -> TrainingJob:
    job = db.get(TrainingJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training job not found.")
    if job.project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    return job


def _get_character_or_404(character_id: int, user: User, db: Session) -> Character:
    char = db.get(Character, character_id)
    if char is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found.")
    if char.project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    return char


def _get_location_or_404(location_id: int, user: User, db: Session) -> Location:
    loc = db.get(Location, location_id)
    if loc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found.")
    if loc.project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    return loc


# ── POST /projects/{project_id}/training ─────────────────────────────────────

@router.post("/projects/{project_id}/training", response_model=TrainingStartResponse, status_code=status.HTTP_201_CREATED)
def create_training_job(
    project_id: int,
    payload: TrainingJobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrainingStartResponse:
    """Create a new training job and optionally start it in the background.

    When ``defer_training`` is True the job is created but training is NOT
    started yet.  The frontend uses this when it will generate a dataset
    first — after the dataset is ready it calls the ``start-training``
    endpoint to kick things off.
    """
    _get_project_or_404(project_id, current_user, db)

    # Validate character_id belongs to this project if provided
    if payload.character_id is not None:
        char = db.get(Character, payload.character_id)
        if char is None or char.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Character not found in this project.",
            )

    # Validate location_id belongs to this project if provided
    if payload.location_id is not None:
        loc = db.get(Location, payload.location_id)
        if loc is None or loc.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Location not found in this project.",
            )

    job = TrainingJob(
        project_id=project_id,
        character_id=payload.character_id,
        location_id=payload.location_id,
        character_name=payload.subject_name,
        trigger_word=payload.trigger_word,
        gpu_type=payload.gpu_type,
        rank=payload.rank,
        epochs=payload.epochs,
        learning_rate=payload.learning_rate,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if not payload.defer_training:
        if payload.gpu_type == "local":
            from pipeline import run_local_training_job
            target_fn = run_local_training_job
        else:
            from pipeline import run_training_job
            target_fn = run_training_job

        thread = threading.Thread(
            target=target_fn,
            args=(job.id,),
            daemon=True,
        )
        thread.start()

    return TrainingStartResponse(
        job_id=job.id,
        message=f"Training job {job.id} created for '{payload.subject_name}'.",
    )


# ── GET /projects/{project_id}/training ──────────────────────────────────────

@router.get("/projects/{project_id}/training")
def list_training_jobs(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List training jobs grouped by root job. Each entry shows the latest attempt."""
    _get_project_or_404(project_id, current_user, db)
    all_jobs = (
        db.query(TrainingJob)
        .filter(TrainingJob.project_id == project_id)
        .order_by(TrainingJob.created_at.desc())
        .all()
    )

    # Group: root jobs (parent_id is None) collect their retries
    roots: dict[int, list] = {}
    for j in all_jobs:
        root_id = j.parent_id if j.parent_id is not None else j.id
        roots.setdefault(root_id, []).append(j)

    results = []
    for root_id, group in roots.items():
        # Sort by attempt desc — latest first
        group.sort(key=lambda j: (j.attempt or 1), reverse=True)
        latest = group[0]
        data = TrainingJobRead.model_validate(latest).model_dump()
        data["total_attempts"] = len(group)
        data["root_id"] = root_id
        data["attempts"] = [
            {
                "id": j.id,
                "attempt": j.attempt or 1,
                "status": j.status,
                "gpu_type": j.gpu_type,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "training_loss": j.training_loss,
            }
            for j in group
        ]
        results.append(data)

    # Sort by latest created_at desc
    results.sort(key=lambda r: r["created_at"], reverse=True)
    return results


# ── GET /training/{job_id} ───────────────────────────────────────────────────

@router.get("/training/{job_id}", response_model=TrainingJobRead)
def get_training_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrainingJobRead:
    """Get a single training job status."""
    job = _get_training_job_or_404(job_id, current_user, db)
    return TrainingJobRead.model_validate(job)


# ── POST /training/{job_id}/cancel ───────────────────────────────────────────

@router.post("/training/{job_id}/cancel")
def cancel_training_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Cancel a running training job."""
    job = _get_training_job_or_404(job_id, current_user, db)

    if job.status in ("complete", "error", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Training job is already {job.status}.",
        )

    job.cancelled_at = datetime.datetime.now(datetime.timezone.utc)
    job.status = "cancelled"
    job.log_text = (job.log_text or "") + "\n\n[CANCELLED] Training job cancelled by user."
    db.commit()

    # Try to stop the RunPod pod if one is running
    if job.pod_id:
        try:
            from runpod.training_orchestrator import TrainingOrchestrator
            orchestrator = TrainingOrchestrator()
            orchestrator.stop_pod(job.pod_id)
        except Exception:
            pass  # Best-effort cleanup

    return {"ok": True, "status": "cancelled"}


# ── GET /projects/{project_id}/loras ─────────────────────────────────────────

@router.get("/projects/{project_id}/loras", response_model=list[LoraInfo])
def list_loras(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LoraInfo]:
    """List available LoRA files in ComfyUI/models/loras/."""
    project = _get_project_or_404(project_id, current_user, db)

    loras_dir = settings.COMFYUI_DIR / "models" / "loras"
    if not loras_dir.exists():
        return []

    # Build lookup: lora filename -> character/location
    char_by_lora = {}
    for c in project.characters:
        if c.lora_path:
            char_by_lora[c.lora_path] = c
    loc_by_lora = {}
    for loc in project.locations:
        if loc.lora_path:
            loc_by_lora[loc.lora_path] = loc

    results: list[LoraInfo] = []
    for f in sorted(loras_dir.iterdir()):
        if f.is_file() and f.suffix in (".safetensors", ".pt", ".ckpt"):
            stat = f.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            created_at = datetime.datetime.fromtimestamp(
                stat.st_mtime, tz=datetime.timezone.utc
            ).isoformat()

            char = char_by_lora.get(f.name)
            loc = loc_by_lora.get(f.name)
            # Fallback: try to extract name from filename
            char_name = char.name if char else (f.stem.replace("_lora", "").replace("_", " ").title() if "_" in f.stem and not loc else None)

            results.append(LoraInfo(
                filename=f.name,
                character_name=char_name,
                character_id=char.id if char else None,
                location_name=loc.name if loc else None,
                location_id=loc.id if loc else None,
                size_mb=size_mb,
                created_at=created_at,
            ))

    return results


# ── POST /characters/{character_id}/set-lora ─────────────────────────────────

@router.post("/characters/{character_id}/set-lora")
def set_character_lora(
    character_id: int,
    payload: SetLoraRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Set the active LoRA for a character."""
    char = _get_character_or_404(character_id, current_user, db)

    # Verify the LoRA file exists
    lora_file = settings.COMFYUI_DIR / "models" / "loras" / payload.lora_path
    if not lora_file.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LoRA file not found.",
        )

    char.lora_path = payload.lora_path
    char.lora_strength = payload.strength
    db.commit()
    db.refresh(char)

    return {"ok": True, "lora_path": char.lora_path, "lora_strength": char.lora_strength}


# ── POST /locations/{location_id}/set-lora ───────────────────────────────────

@router.post("/locations/{location_id}/set-lora")
def set_location_lora(
    location_id: int,
    payload: SetLoraRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Set the active LoRA for a location."""
    loc = _get_location_or_404(location_id, current_user, db)

    # Verify the LoRA file exists
    lora_file = settings.COMFYUI_DIR / "models" / "loras" / payload.lora_path
    if not lora_file.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LoRA file not found.",
        )

    loc.lora_path = payload.lora_path
    loc.lora_strength = payload.strength
    db.commit()
    db.refresh(loc)

    return {"ok": True, "lora_path": loc.lora_path, "lora_strength": loc.lora_strength}


# ── PUT /projects/{project_id}/loras/assign ──────────────────────────────────

class LoraAssignRequest(BaseModel):
    filename: str
    character_id: int | None = None
    location_id: int | None = None


@router.put("/projects/{project_id}/loras/assign")
def assign_lora(
    project_id: int,
    payload: LoraAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Assign a LoRA file to a character or location (or unassign from both)."""
    project = _get_project_or_404(project_id, current_user, db)

    # Verify the LoRA file exists
    lora_file = settings.COMFYUI_DIR / "models" / "loras" / payload.filename
    if not lora_file.exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="LoRA file not found.")

    # Clear this LoRA from any existing character/location assignment in this project
    for c in project.characters:
        if c.lora_path == payload.filename:
            c.lora_path = None
    for loc in project.locations:
        if loc.lora_path == payload.filename:
            loc.lora_path = None

    # Assign to character
    if payload.character_id:
        char = db.get(Character, payload.character_id)
        if char and char.project_id == project_id:
            char.lora_path = payload.filename
            char.lora_strength = 0.7

    # Assign to location
    if payload.location_id:
        loc = db.get(Location, payload.location_id)
        if loc and loc.project_id == project_id:
            loc.lora_path = payload.filename
            loc.lora_strength = 0.5

    db.commit()
    return {"ok": True}


# ── POST /training/{job_id}/upload-dataset ───────────────────────────────────

@router.post("/training/{job_id}/upload-dataset")
async def upload_dataset(
    job_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Accept a zip or tar.gz file containing dataset images and captions.
    Extracts to /workspace/datasets/{character_name}/.
    """
    job = _get_training_job_or_404(job_id, current_user, db)

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided.",
        )

    is_zip = file.filename.endswith(".zip")
    is_tar = file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")

    if not (is_zip or is_tar):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a .zip or .tar.gz archive.",
        )

    # Determine extraction path — works for both character and location jobs
    subject_name = (job.character_name or "unknown").lower().replace(" ", "_")
    dataset_dir = Path("/workspace/datasets") / subject_name
    dataset_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded file to a temp location, then extract
    with tempfile.NamedTemporaryFile(delete=False, suffix=file.filename) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if is_zip:
            with zipfile.ZipFile(tmp_path, "r") as zf:
                zf.extractall(dataset_dir)
        elif is_tar:
            with tarfile.open(tmp_path, "r:gz") as tf:
                tf.extractall(dataset_dir)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to extract archive: {exc}",
        )
    finally:
        os.unlink(tmp_path)

    # Update the job with the dataset path
    job.dataset_path = str(dataset_dir)
    db.commit()

    # Count extracted files
    file_count = sum(1 for _ in dataset_dir.rglob("*") if _.is_file())

    return {
        "ok": True,
        "dataset_path": str(dataset_dir),
        "file_count": file_count,
        "message": f"Dataset extracted to {dataset_dir} ({file_count} files).",
    }


# ── POST /training/{job_id}/retry ──────────────────────────────────────────────


class RetryOverrides(BaseModel):
    gpu_type: str | None = None


@router.post("/training/{job_id}/retry", response_model=TrainingStartResponse)
def retry_training_job(
    job_id: int,
    payload: RetryOverrides | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrainingStartResponse:
    """Retry a failed or cancelled training job by cloning it. Optionally override GPU type."""
    old_job = _get_training_job_or_404(job_id, current_user, db)

    if old_job.status not in ("error", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Can only retry failed or cancelled jobs (current: {old_job.status}).",
        )

    # Find the root job (follow parent chain)
    root_job = old_job
    while root_job.parent_id is not None:
        root_job = db.get(TrainingJob, root_job.parent_id) or root_job
        if root_job.parent_id is None:
            break

    # Count existing attempts under this root
    attempt_count = (
        db.query(TrainingJob)
        .filter((TrainingJob.parent_id == root_job.id) | (TrainingJob.id == root_job.id))
        .count()
    )

    new_job = TrainingJob(
        project_id=old_job.project_id,
        character_id=old_job.character_id,
        location_id=old_job.location_id,
        character_name=old_job.character_name,
        trigger_word=old_job.trigger_word,
        gpu_type=(payload.gpu_type if payload and payload.gpu_type else old_job.gpu_type),
        dataset_path=old_job.dataset_path,
        rank=old_job.rank,
        epochs=old_job.epochs,
        learning_rate=old_job.learning_rate,
        lora_strength=old_job.lora_strength,
        parent_id=root_job.id,
        attempt=attempt_count + 1,
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    if new_job.gpu_type == "local":
        from pipeline import run_local_training_job
        target_fn = run_local_training_job
    else:
        from pipeline import run_training_job
        target_fn = run_training_job

    thread = threading.Thread(target=target_fn, args=(new_job.id,), daemon=True)
    thread.start()

    return TrainingStartResponse(
        job_id=new_job.id,
        message=f"Retrying training job (new ID: {new_job.id}).",
    )


# ── POST /training/{job_id}/start-training ────────────────────────────────────

@router.post("/training/{job_id}/start-training")
def start_training(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Start training for a deferred job (dataset was generated first)."""
    job = _get_training_job_or_404(job_id, current_user, db)

    if job.status not in ("pending",):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is already {job.status}, cannot start.",
        )

    if job.gpu_type == "local":
        from pipeline import run_local_training_job
        target_fn = run_local_training_job
    else:
        from pipeline import run_training_job
        target_fn = run_training_job

    thread = threading.Thread(
        target=target_fn,
        args=(job.id,),
        daemon=True,
    )
    thread.start()

    return {"message": f"Training started for job {job.id}."}


# ── POST /training/{job_id}/generate-dataset ─────────────────────────────────

@router.post("/training/{job_id}/generate-dataset", response_model=DatasetGenerateResponse)
def generate_dataset(
    job_id: int,
    payload: DatasetGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DatasetGenerateResponse:
    """
    Generate a training dataset using FLUX T2I.

    Creates varied images of a character or location with auto-captions,
    ready for LoRA training. Runs in the background — poll status via
    GET /training/dataset-job/{dataset_job_id}.
    """
    job = _get_training_job_or_404(job_id, current_user, db)

    if not payload.character_id and not payload.location_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either character_id or location_id.",
        )

    from pipeline import start_generate_dataset

    dataset_job_id = start_generate_dataset(
        project_id=job.project_id,
        training_job_id=job.id,
        character_id=payload.character_id,
        location_id=payload.location_id,
        trigger_word=payload.trigger_word,
        num_images=payload.num_images,
    )

    return DatasetGenerateResponse(
        dataset_job_id=dataset_job_id,
        message=f"Generating {payload.num_images} training images via FLUX T2I...",
    )


# ── GET /training/dataset-job/{dataset_job_id} ──────────────────────────────

@router.get("/training/dataset-job/{dataset_job_id}", response_model=DatasetJobStatus)
def get_dataset_job_status(
    dataset_job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DatasetJobStatus:
    """Poll the status of a dataset generation job."""
    from pipeline import get_dataset_gen_job

    job = get_dataset_gen_job(dataset_job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset generation job not found.",
        )

    return DatasetJobStatus(
        status=job["status"],
        progress=job["progress"],
        total=job["total"],
        generated=job.get("generated", 0),
        dataset_path=job.get("dataset_path"),
        error=job.get("error"),
    )


# ── GET /training/{job_id}/dataset-preview ──────────────────────────────────

@router.get("/training/{job_id}/dataset-preview")
def get_dataset_preview(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List generated dataset images with preview URLs."""
    job = _get_training_job_or_404(job_id, current_user, db)

    if not job.dataset_path:
        return {"images": [], "count": 0}

    dataset_dir = Path(job.dataset_path)
    if not dataset_dir.exists():
        return {"images": [], "count": 0}

    # Get the folder name relative to /workspace/datasets/
    try:
        rel_dir = dataset_dir.relative_to("/workspace/datasets")
    except ValueError:
        return {"images": [], "count": 0}

    images = []
    for img in sorted(dataset_dir.glob("*.png")):
        caption_file = img.with_suffix(".txt")
        caption = caption_file.read_text().strip() if caption_file.exists() else ""
        images.append({
            "filename": img.name,
            "url": f"/static/datasets/{rel_dir}/{img.name}",
            "caption": caption,
        })

    return {"images": images, "count": len(images)}
