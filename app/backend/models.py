"""SQLAlchemy ORM models for Story Builder."""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from database import Base

# ── Default voice options (for reference) ─────────────────────────────────────
# "en-GB-SoniaNeural"     – British female, clear
# "en-GB-RyanNeural"      – British male, neutral
# "en-IE-EmilyNeural"     – Irish female, warm
# "en-IE-ConnorNeural"    – Irish male, gruff
# "en-US-AriaNeural"      – American female
# "en-AU-NatashaNeural"   – Australian female


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# ── User ──────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, index=True)
    email: str = Column(String(255), unique=True, index=True, nullable=False)
    password_hash: str = Column(String(255), nullable=False)
    created_at: datetime.datetime = Column(DateTime, default=_now, nullable=False)

    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")


# ── Project ───────────────────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id: int = Column(Integer, primary_key=True, index=True)
    user_id: int = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title: str = Column(String(255), nullable=False)
    premise: str = Column(Text, default="", nullable=False)
    tone: str = Column(String(255), default="", nullable=False)
    visual_style: str = Column(Text, default="", nullable=False)
    setting: str = Column(Text, default="", nullable=False)
    series_slug: str = Column(String(255), unique=True, nullable=False, index=True)
    created_at: datetime.datetime = Column(DateTime, default=_now, nullable=False)

    owner = relationship("User", back_populates="projects")
    characters = relationship("Character", back_populates="project", cascade="all, delete-orphan")
    locations = relationship("Location", back_populates="project", cascade="all, delete-orphan")
    episodes = relationship("Episode", back_populates="project", cascade="all, delete-orphan", order_by="Episode.number")


# ── Character ─────────────────────────────────────────────────────────────────

class Character(Base):
    __tablename__ = "characters"

    id: int = Column(Integer, primary_key=True, index=True)
    project_id: int = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name: str = Column(String(255), nullable=False)
    role: str = Column(String(255), default="", nullable=False)
    backstory: str = Column(Text, default="", nullable=False)
    visual_description: str = Column(Text, default="", nullable=False)
    voice: str = Column(String(255), default="en-GB-SoniaNeural", nullable=False)
    voice_notes: str = Column(Text, default="", nullable=False)
    reference_image_path: str | None = Column(String(1024), nullable=True)

    project = relationship("Project", back_populates="characters")
    scene_characters = relationship("SceneCharacter", back_populates="character", cascade="all, delete-orphan")


# ── Location ──────────────────────────────────────────────────────────────────

class Location(Base):
    __tablename__ = "locations"

    id: int = Column(Integer, primary_key=True, index=True)
    project_id: int = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name: str = Column(String(255), nullable=False)
    slug: str = Column(String(255), nullable=False)
    description: str = Column(Text, default="", nullable=False)
    reference_image_path: str | None = Column(String(1024), nullable=True)

    project = relationship("Project", back_populates="locations")
    scenes = relationship("Scene", back_populates="location")


# ── Episode ───────────────────────────────────────────────────────────────────

class Episode(Base):
    __tablename__ = "episodes"

    id: int = Column(Integer, primary_key=True, index=True)
    project_id: int = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    number: int = Column(Integer, nullable=False)
    title: str = Column(String(255), nullable=False)
    summary: str = Column(Text, default="", nullable=False)

    project = relationship("Project", back_populates="episodes")
    scenes = relationship(
        "Scene",
        back_populates="episode",
        cascade="all, delete-orphan",
        order_by="Scene.order_idx",
    )
    generation_jobs = relationship(
        "GenerationJob",
        back_populates="episode",
        cascade="all, delete-orphan",
    )


# ── Scene ─────────────────────────────────────────────────────────────────────

class Scene(Base):
    __tablename__ = "scenes"

    id: int = Column(Integer, primary_key=True, index=True)
    episode_id: int = Column(Integer, ForeignKey("episodes.id"), nullable=False, index=True)
    order_idx: int = Column(Integer, nullable=False, default=0)
    location_id: int | None = Column(Integer, ForeignKey("locations.id"), nullable=True)

    # "short" | "medium" | "long"
    clip_length: str = Column(String(32), nullable=False, default="medium")

    visual: str = Column(Text, default="", nullable=False)
    narration: str | None = Column(Text, nullable=True)

    # JSON-encoded list of {"character": str, "line": str}
    dialogue: str = Column(Text, nullable=False, default="[]")

    # "pending" | "generating" | "done" | "error"
    status: str = Column(String(32), nullable=False, default="pending")

    output_clip_path: str | None = Column(String(1024), nullable=True)
    reference_image_path: str | None = Column(String(1024), nullable=True)

    episode = relationship("Episode", back_populates="scenes")
    location = relationship("Location", back_populates="scenes")
    scene_characters = relationship(
        "SceneCharacter",
        back_populates="scene",
        cascade="all, delete-orphan",
    )
    clip_versions = relationship(
        "SceneClipVersion",
        back_populates="scene",
        cascade="all, delete-orphan",
        order_by="SceneClipVersion.created_at.desc()",
    )


# ── SceneCharacter (join table) ───────────────────────────────────────────────

class SceneCharacter(Base):
    __tablename__ = "scene_characters"

    scene_id: int = Column(Integer, ForeignKey("scenes.id"), primary_key=True)
    character_id: int = Column(Integer, ForeignKey("characters.id"), primary_key=True)

    scene = relationship("Scene", back_populates="scene_characters")
    character = relationship("Character", back_populates="scene_characters")


# ── GenerationJob ─────────────────────────────────────────────────────────────

class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: int = Column(Integer, primary_key=True, index=True)
    episode_id: int = Column(Integer, ForeignKey("episodes.id"), nullable=False, index=True)

    # "pending" | "running" | "complete" | "error"
    status: str = Column(String(32), nullable=False, default="pending")
    progress_pct: int = Column(Integer, nullable=False, default=0)
    log_text: str = Column(Text, nullable=False, default="")

    created_at: datetime.datetime = Column(DateTime, default=_now, nullable=False)
    completed_at: datetime.datetime | None = Column(DateTime, nullable=True)

    episode = relationship("Episode", back_populates="generation_jobs")


# ── SceneClipVersion ──────────────────────────────────────────────────────────

class SceneClipVersion(Base):
    """
    Archives a previous generation of a scene clip before it is overwritten.

    Captures enough context to understand *what settings produced this clip*
    so versions can be meaningfully compared.
    """
    __tablename__ = "scene_clip_versions"

    id: int = Column(Integer, primary_key=True, index=True)
    scene_id: int = Column(Integer, ForeignKey("scenes.id"), nullable=False, index=True)

    # Path relative to COMFYUI_OUTPUT — same format as scene.output_clip_path
    clip_path: str = Column(String(1024), nullable=False)

    # Generation settings snapshot
    quality: str | None = Column(String(32), nullable=True)       # draft | quality | final
    visual_style: str | None = Column(Text, nullable=True)        # project.visual_style at gen time
    tone: str | None = Column(Text, nullable=True)                # project.tone at gen time
    prompt: str | None = Column(Text, nullable=True)              # full prompt sent to model
    seed_image: str | None = Column(String(1024), nullable=True)  # reference image used

    created_at: datetime.datetime = Column(DateTime, default=_now, nullable=False)

    scene = relationship("Scene", back_populates="clip_versions")
