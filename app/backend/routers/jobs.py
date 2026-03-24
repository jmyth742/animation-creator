"""Generation job routes and WebSocket progress feed."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from auth import decode_token, get_current_user
from database import SessionLocal, get_db
from models import GenerationJob, User
from schemas import GenerationJobRead

router = APIRouter()

_POLL_INTERVAL = 1.5  # seconds between DB polls on the WebSocket


# ── GET /jobs/{id} ────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}", response_model=GenerationJobRead)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GenerationJobRead:
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    # Ownership check via episode → project
    if job.episode.project.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    return GenerationJobRead.model_validate(job)


# ── WebSocket /ws/{job_id} ────────────────────────────────────────────────────

@router.websocket("/ws/{job_id}")
async def job_websocket(websocket: WebSocket, job_id: int, token: str | None = None) -> None:
    """
    Stream job progress to the client.

    Authentication
    --------------
    Pass the bearer token as a query parameter:
        ws://host/ws/123?token=<jwt>

    Protocol
    --------
    Client connects; server polls the DB every 1.5 s and sends JSON frames:

      {"progress": 42, "log": "...", "status": "running"}

    When the job reaches a terminal state:

      {"done": true, "status": "complete", "final_path": "/static/output/..."}
    """
    # Authenticate before accepting the connection
    if not token:
        await websocket.close(code=4001)
        return

    user_id = decode_token(token)
    if user_id is None:
        await websocket.close(code=4001)
        return

    # Verify job ownership
    auth_db: Session = SessionLocal()
    try:
        job_check: GenerationJob | None = auth_db.get(GenerationJob, job_id)
        if job_check is None or job_check.episode.project.user_id != user_id:
            await websocket.close(code=4003)
            return
    finally:
        auth_db.close()

    await websocket.accept()

    try:
        while True:
            await asyncio.sleep(_POLL_INTERVAL)

            # Use a fresh session each iteration to avoid stale reads.
            db: Session = SessionLocal()
            try:
                job: GenerationJob | None = db.get(GenerationJob, job_id)
                if job is None:
                    await websocket.send_text(
                        json.dumps({"done": True, "status": "error", "detail": "Job not found."})
                    )
                    break

                is_terminal = job.status in ("complete", "error")

                # Build a compact log excerpt (last 40 lines) to avoid huge payloads.
                log_lines = job.log_text.splitlines() if job.log_text else []
                recent_log = "\n".join(log_lines[-40:])

                if is_terminal:
                    final_path = _resolve_final_path(job)
                    payload = {
                        "done": True,
                        "status": job.status,
                        "progress": job.progress_pct,
                        "log": recent_log,
                        "final_path": final_path,
                    }
                    await websocket.send_text(json.dumps(payload))
                    break
                else:
                    payload = {
                        "progress": job.progress_pct,
                        "log": recent_log,
                        "status": job.status,
                    }
                    await websocket.send_text(json.dumps(payload))
            finally:
                db.close()

    except WebSocketDisconnect:
        # Client disconnected — nothing to do.
        pass
    except Exception:
        try:
            await websocket.send_text(
                json.dumps({"done": True, "status": "error", "detail": "An internal error occurred."})
            )
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── Internal helper ───────────────────────────────────────────────────────────

def _resolve_final_path(job: GenerationJob) -> str | None:
    """
    Return a URL-path for the stitched episode output, if it exists.

    showrunner writes the final episode to:
        output/<series_slug>/ep<NN>/ep<NN>_final.mp4
    or
        output/<series_slug>/ep<NN>/ep<NN>_final_graded.mp4
    """
    from config import settings

    try:
        project = job.episode.project
        ep_num = job.episode.number
        series_slug = project.series_slug
        ep_dir = settings.OUTPUT_DIR / series_slug / f"ep{ep_num:02d}"

        # Prefer graded, then plain final
        for candidate in [
            ep_dir / f"ep{ep_num:02d}_final_graded.mp4",
            ep_dir / f"ep{ep_num:02d}_final.mp4",
        ]:
            if candidate.exists():
                rel = candidate.relative_to(settings.OUTPUT_DIR)
                return f"/static/output/{rel}"
    except Exception:
        pass
    return None
