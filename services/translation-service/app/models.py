from __future__ import annotations
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


# ── Settings ──────────────────────────────────────────────────────────────────

class PreferencesPayload(BaseModel):
    target_language: str
    model_source: str
    model_ref: Optional[UUID] = None
    system_prompt: str
    user_prompt_tpl: str
    compact_model_source: Optional[str] = None
    compact_model_ref: Optional[UUID] = None
    compact_system_prompt: str = ''
    compact_user_prompt_tpl: str = ''
    chunk_size_tokens: int = 2000
    invoke_timeout_secs: int = 300

    @field_validator("user_prompt_tpl")
    @classmethod
    def must_contain_chapter_text(cls, v: str) -> str:
        if "{chapter_text}" not in v:
            raise ValueError("user_prompt_tpl must contain {chapter_text}")
        return v


class UserTranslationPreferences(BaseModel):
    user_id: UUID
    target_language: str
    model_source: str
    model_ref: Optional[UUID]
    system_prompt: str
    user_prompt_tpl: str
    compact_model_source: Optional[str] = None
    compact_model_ref: Optional[UUID] = None
    compact_system_prompt: str = ''
    compact_user_prompt_tpl: str = ''
    chunk_size_tokens: int = 2000
    invoke_timeout_secs: int = 300
    updated_at: datetime


class BookSettingsPayload(PreferencesPayload):
    pass


class BookTranslationSettings(UserTranslationPreferences):
    book_id: UUID
    owner_user_id: UUID
    is_default: bool


# ── Chunk ──────────────────────────────────────────────────────────────────────

class ChapterTranslationChunk(BaseModel):
    id: UUID
    chapter_translation_id: UUID
    chunk_index: int
    chunk_text: str
    translated_text: Optional[str]
    compact_memo_applied: Optional[str]
    status: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    created_at: datetime


# ── Jobs ──────────────────────────────────────────────────────────────────────

class CreateJobPayload(BaseModel):
    chapter_ids: list[UUID]

    @field_validator("chapter_ids")
    @classmethod
    def must_not_be_empty(cls, v: list[UUID]) -> list[UUID]:
        if not v:
            raise ValueError("chapter_ids must not be empty")
        return v


class ChapterTranslation(BaseModel):
    id: UUID
    job_id: UUID
    chapter_id: UUID
    book_id: UUID
    owner_user_id: UUID
    status: str
    translated_body: Optional[str]
    source_language: Optional[str]
    target_language: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    usage_log_id: Optional[UUID]
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime


class TranslationJob(BaseModel):
    job_id: UUID
    book_id: UUID
    owner_user_id: UUID
    status: str
    target_language: str
    model_source: str
    model_ref: UUID
    system_prompt: str
    user_prompt_tpl: str
    compact_model_source: Optional[str] = None
    compact_model_ref: Optional[UUID] = None
    compact_system_prompt: str = ''
    compact_user_prompt_tpl: str = ''
    chunk_size_tokens: int = 2000
    invoke_timeout_secs: int = 300
    chapter_ids: list[UUID]
    total_chapters: int
    completed_chapters: int
    failed_chapters: int
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
    chapter_translations: Optional[list[ChapterTranslation]] = None


class TranslateTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=30_000)
    source_language: str = "auto"
    target_language: str | None = None  # None = use user's preference


class TranslateTextResponse(BaseModel):
    translated_text: str
    source_language: str
    target_language: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class ErrorResponse(BaseModel):
    code: str
    message: str


# ── Version / Coverage (LW-72) ─────────────────────────────────────────────────

class VersionSummary(BaseModel):
    id: UUID
    version_num: int
    job_id: UUID
    status: str
    is_active: bool
    model_source: str
    model_ref: Optional[UUID]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    created_at: datetime


class LanguageVersionGroup(BaseModel):
    target_language: str
    active_id: Optional[UUID]
    versions: list[VersionSummary]


class ChapterVersionsResponse(BaseModel):
    chapter_id: UUID
    languages: list[LanguageVersionGroup]


class ActiveVersionResponse(BaseModel):
    chapter_id: UUID
    target_language: str
    active_id: UUID


class CoverageCell(BaseModel):
    has_active: bool
    active_version_num: Optional[int]
    latest_version_num: Optional[int]
    latest_status: Optional[str]
    version_count: int


class ChapterCoverage(BaseModel):
    chapter_id: UUID
    languages: dict[str, CoverageCell]


class BookCoverageResponse(BaseModel):
    book_id: UUID
    coverage: list[ChapterCoverage]
    known_languages: list[str]
