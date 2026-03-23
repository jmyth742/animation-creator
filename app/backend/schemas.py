"""Pydantic v2 request / response schemas for Story Builder."""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: str
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime.datetime


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    token: str
    user: UserRead


# ── Project ───────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    title: str
    premise: str = ""
    tone: str = ""
    visual_style: str = ""
    setting: str = ""


class ProjectUpdate(BaseModel):
    title: str | None = None
    premise: str | None = None
    tone: str | None = None
    visual_style: str | None = None
    setting: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    premise: str
    tone: str
    visual_style: str
    setting: str
    series_slug: str
    created_at: datetime.datetime
    character_count: int = 0
    episode_count: int = 0


class ProjectDetail(ProjectRead):
    characters: list[CharacterRead] = []
    episodes: list[EpisodeRead] = []
    locations: list[LocationRead] = []


# ── Character ─────────────────────────────────────────────────────────────────

class CharacterCreate(BaseModel):
    name: str
    role: str = ""
    backstory: str = ""
    visual_description: str = ""
    voice: str = "en-GB-SoniaNeural"
    voice_notes: str = ""


class CharacterUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    backstory: str | None = None
    visual_description: str | None = None
    voice: str | None = None
    voice_notes: str | None = None


class CharacterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    role: str
    backstory: str
    visual_description: str
    voice: str
    voice_notes: str
    reference_image_path: str | None = None
    portrait_url: str | None = None


# ── Location ──────────────────────────────────────────────────────────────────

class LocationCreate(BaseModel):
    name: str
    description: str = ""


class LocationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    slug: str
    description: str
    reference_image_path: str | None = None
    reference_url: str | None = None


# ── Episode ───────────────────────────────────────────────────────────────────

class EpisodeCreate(BaseModel):
    number: int
    title: str
    summary: str = ""


class EpisodeUpdate(BaseModel):
    number: int | None = None
    title: str | None = None
    summary: str | None = None


class EpisodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    number: int
    title: str
    summary: str
    scenes: list[SceneRead] = []


# ── Scene ─────────────────────────────────────────────────────────────────────

class DialogueLine(BaseModel):
    character: str
    line: str


class SceneCreate(BaseModel):
    order_idx: int = 0
    location_id: int | None = None
    clip_length: str = "medium"
    visual: str = ""
    narration: str | None = None
    dialogue: list[DialogueLine] = []
    character_ids: list[int] = []


class SceneUpdate(BaseModel):
    order_idx: int | None = None
    location_id: int | None = None
    clip_length: str | None = None
    visual: str | None = None
    narration: str | None = None
    dialogue: list[DialogueLine] | None = None
    character_ids: list[int] | None = None


class SceneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    episode_id: int
    order_idx: int
    location_id: int | None = None
    clip_length: str
    visual: str
    narration: str | None = None
    dialogue: str  # raw JSON string; callers parse as list[DialogueLine]
    status: str
    output_clip_path: str | None = None
    characters: list[CharacterRead] = []
    preview_url: str | None = None
    location_name: str | None = None


class SceneReorderItem(BaseModel):
    id: int
    order_idx: int


# ── Generation Job ────────────────────────────────────────────────────────────

class GenerationJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    episode_id: int
    status: str
    progress_pct: int
    log_text: str
    created_at: datetime.datetime
    completed_at: datetime.datetime | None = None


class PortraitGenerateResponse(BaseModel):
    portrait_urls: list[str]
    message: str


class ProduceResponse(BaseModel):
    job_id: int
    message: str


# ── Forward-ref resolution ────────────────────────────────────────────────────
# These must come after all classes are defined.

ProjectDetail.model_rebuild()
EpisodeRead.model_rebuild()
