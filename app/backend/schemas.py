"""Pydantic v2 request / response schemas for Story Builder."""

from __future__ import annotations

import datetime
import re
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit.")
        return v


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime.datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]


class TokenResponse(BaseModel):
    token: str
    user: UserRead


# ── Project ───────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=255)]
    premise: Annotated[str, Field(max_length=4000)] = ""
    tone: Annotated[str, Field(max_length=255)] = ""
    visual_style: Annotated[str, Field(max_length=1000)] = ""
    setting: Annotated[str, Field(max_length=2000)] = ""


class ProjectUpdate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    premise: Annotated[str, Field(max_length=4000)] | None = None
    tone: Annotated[str, Field(max_length=255)] | None = None
    visual_style: Annotated[str, Field(max_length=1000)] | None = None
    setting: Annotated[str, Field(max_length=2000)] | None = None


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
    name: Annotated[str, Field(min_length=1, max_length=255)]
    role: Annotated[str, Field(max_length=255)] = ""
    backstory: Annotated[str, Field(max_length=4000)] = ""
    visual_description: Annotated[str, Field(max_length=2000)] = ""
    voice: Annotated[str, Field(max_length=255)] = "en-GB-SoniaNeural"
    voice_notes: Annotated[str, Field(max_length=2000)] = ""


class CharacterUpdate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    role: Annotated[str, Field(max_length=255)] | None = None
    backstory: Annotated[str, Field(max_length=4000)] | None = None
    visual_description: Annotated[str, Field(max_length=2000)] | None = None
    voice: Annotated[str, Field(max_length=255)] | None = None
    voice_notes: Annotated[str, Field(max_length=2000)] | None = None


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
    name: Annotated[str, Field(min_length=1, max_length=255)]
    description: Annotated[str, Field(max_length=2000)] = ""


class LocationUpdate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    description: Annotated[str, Field(max_length=2000)] | None = None


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
    number: Annotated[int, Field(ge=1, le=9999)]
    title: Annotated[str, Field(min_length=1, max_length=255)]
    summary: Annotated[str, Field(max_length=4000)] = ""


class EpisodeUpdate(BaseModel):
    number: Annotated[int, Field(ge=1, le=9999)] | None = None
    title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    summary: Annotated[str, Field(max_length=4000)] | None = None


class EpisodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    number: int
    title: str
    summary: str
    scenes: list[SceneRead] = []


# ── Scene ─────────────────────────────────────────────────────────────────────

_CLIP_LENGTHS = {"short", "medium", "long"}


class DialogueLine(BaseModel):
    character: Annotated[str, Field(max_length=255)]
    line: Annotated[str, Field(max_length=1000)]


class SceneCreate(BaseModel):
    order_idx: Annotated[int, Field(ge=0)] = 0
    location_id: int | None = None
    clip_length: Annotated[str, Field(pattern=r"^(short|medium|long)$")] = "medium"
    visual: Annotated[str, Field(max_length=2000)] = ""
    narration: Annotated[str, Field(max_length=500)] | None = None
    dialogue: Annotated[list[DialogueLine], Field(max_length=20)] = []
    character_ids: Annotated[list[int], Field(max_length=20)] = []


class SceneUpdate(BaseModel):
    order_idx: Annotated[int, Field(ge=0)] | None = None
    location_id: int | None = None
    clip_length: Annotated[str, Field(pattern=r"^(short|medium|long)$")] | None = None
    visual: Annotated[str, Field(max_length=2000)] | None = None
    narration: Annotated[str, Field(max_length=500)] | None = None
    dialogue: Annotated[list[DialogueLine], Field(max_length=20)] | None = None
    character_ids: Annotated[list[int], Field(max_length=20)] | None = None


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
    reference_image_path: str | None = None
    characters: list[CharacterRead] = []
    preview_url: str | None = None
    reference_url: str | None = None
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


class SelectPortraitRequest(BaseModel):
    portrait_path: Annotated[str, Field(max_length=1024)]


class PortraitGenerateResponse(BaseModel):
    portrait_urls: list[str]
    message: str


class SelectReferenceRequest(BaseModel):
    reference_path: Annotated[str, Field(max_length=1024)]


class ReferenceGenerateResponse(BaseModel):
    reference_urls: list[str]
    message: str


class SceneReferenceGenerateResponse(BaseModel):
    reference_urls: list[str]
    message: str


class ProduceResponse(BaseModel):
    job_id: int
    message: str


# ── Forward-ref resolution ────────────────────────────────────────────────────
# These must come after all classes are defined.

ProjectDetail.model_rebuild()
EpisodeRead.model_rebuild()
