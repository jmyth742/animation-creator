"""FastAPI application entry-point for Story Builder."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import settings
from database import init_db
from routers import auth, characters, episodes, generate, jobs, locations, projects, scenes

limiter = Limiter(key_func=get_remote_address)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    # Ensure static-served directories exist so StaticFiles doesn't raise.
    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    settings.COMFYUI_OUTPUT.mkdir(parents=True, exist_ok=True)
    settings.SERIES_DIR.mkdir(parents=True, exist_ok=True)
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

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(characters.router, tags=["characters"])
app.include_router(locations.router, tags=["locations"])
app.include_router(episodes.router, tags=["episodes"])
app.include_router(scenes.router, tags=["scenes"])
app.include_router(jobs.router, tags=["jobs"])
app.include_router(generate.router, tags=["generate"])


# ── Root ──────────────────────────────────────────────────────────────────────

@app.get("/", tags=["health"])
def root():
    return {"message": "Story Builder API", "docs": "/docs"}
