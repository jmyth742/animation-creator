"""FastAPI application entry-point for Story Builder."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config import settings
from database import init_db
from limiter import limiter
from routers import auth, characters, episodes, generate, jobs, locations, projects, scenes, training


# ── Lifespan ──────────────────────────────────────────────────────────────────

def _recover_interrupted_training_jobs() -> None:
    """Mark any training jobs left in an active status as error.

    When the server restarts (e.g. uvicorn --reload), background threads
    driving training jobs are killed but the DB rows keep their in-progress
    status forever.  This finds them and marks them as failed so the UI
    shows the correct state and the user can retry.
    """
    import logging

    from database import SessionLocal
    from models import TrainingJob

    logger = logging.getLogger("uvicorn.error")
    active_statuses = {"pending", "provisioning", "bootstrapping", "uploading", "training", "downloading"}

    db = SessionLocal()
    try:
        stuck = db.query(TrainingJob).filter(TrainingJob.status.in_(active_statuses)).all()
        if stuck:
            logger.warning("Recovering %d training job(s) interrupted by server restart", len(stuck))
        for job in stuck:
            logger.warning("  → TrainingJob #%d (%s → error)", job.id, job.status)
            job.status = "error"
            job.log_text = (job.log_text or "") + "\n[ERROR] Job interrupted by server restart. Retry to continue."
        db.commit()
    finally:
        db.close()


def _recover_interrupted_scenes() -> None:
    """Recover scenes stuck in 'generating' after a server restart.

    When uvicorn --reload kills background threads, ComfyUI may have already
    finished but the DB never got updated.  This checks for matching clips
    on disk and marks those scenes as done, or falls back to error.
    """
    import logging
    import os

    from database import SessionLocal
    from models import Scene, Episode
    from pathlib import Path

    logger = logging.getLogger("uvicorn.error")

    db = SessionLocal()
    try:
        stuck = db.query(Scene).filter(Scene.status == "generating").all()
        if not stuck:
            return
        logger.warning("Recovering %d scene(s) interrupted by server restart", len(stuck))
        for scene in stuck:
            episode = scene.episode
            ep_id = f"ep{episode.number:02d}"
            clip_prefix = f"{ep_id}_s{scene.order_idx + 1:02d}"

            # Look for the latest matching clip in ComfyUI output
            clip_dir = settings.COMFYUI_OUTPUT
            if clip_dir.is_dir():
                candidates = [f for f in os.listdir(clip_dir)
                              if f.startswith(clip_prefix) and f.endswith(".mp4")]
                candidates.sort(key=lambda f: os.path.getmtime(clip_dir / f), reverse=True)
            else:
                candidates = []

            if candidates:
                scene.output_clip_path = candidates[0]
                scene.status = "done"
                logger.warning("  → Scene #%d (%s) recovered → done (%s)", scene.id, clip_prefix, candidates[0])
            else:
                scene.status = "error"
                logger.warning("  → Scene #%d (%s) no clip found → error", scene.id, clip_prefix)
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    _recover_interrupted_training_jobs()
    _recover_interrupted_scenes()
    # Ensure static-served directories exist so StaticFiles doesn't raise.
    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    settings.COMFYUI_OUTPUT.mkdir(parents=True, exist_ok=True)
    settings.SERIES_DIR.mkdir(parents=True, exist_ok=True)
    from pathlib import Path
    Path("/workspace/datasets").mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown (nothing to tear down)


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Story Builder API",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Static file mounts ────────────────────────────────────────────────────────

app.mount(
    "/static/output",
    StaticFiles(directory=str(settings.OUTPUT_DIR)),
    name="output",
)
app.mount(
    "/static/clips",
    StaticFiles(directory=str(settings.COMFYUI_OUTPUT)),
    name="clips",
)
app.mount(
    "/static/series",
    StaticFiles(directory=str(settings.SERIES_DIR)),
    name="series",
)
app.mount(
    "/static/datasets",
    StaticFiles(directory="/workspace/datasets"),
    name="datasets",
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(characters.router, tags=["characters"])
app.include_router(locations.router, tags=["locations"])
app.include_router(episodes.router, tags=["episodes"])
app.include_router(scenes.router, tags=["scenes"])
app.include_router(jobs.router, tags=["jobs"])
app.include_router(generate.router, tags=["generate"])
app.include_router(training.router, tags=["training"])


# ── Root ──────────────────────────────────────────────────────────────────────

@app.get("/", tags=["health"])
def root():
    return {"message": "Story Builder API", "docs": "/docs"}
