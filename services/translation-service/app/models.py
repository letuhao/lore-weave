from __future__ import annotations
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, field_validator


# ── Settings ──────────────────────────────────────────────────────────────────

class PreferencesPayload(BaseModel):
    target_language: str
    model_source: str
    model_ref: Optional[UUID] = None
    system_prompt: str
    user_prompt_tpl: str

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
    updated_at: datetime


class BookSettingsPayload(PreferencesPayload):
    pass


class BookTranslationSettings(UserTranslationPreferences):
    book_id: UUID
    owner_user_id: UUID
    is_default: bool


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
    chapter_ids: list[UUID]
    total_chapters: int
    completed_chapters: int
    failed_chapters: int
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
    chapter_translations: Optional[list[ChapterTranslation]] = None


class ErrorResponse(BaseModel):
    code: str
    message: str
