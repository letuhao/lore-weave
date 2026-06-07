from __future__ import annotations
import json as _json
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator


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


class BookSettingsPayload(BaseModel):
    """PATCH-semantics payload: every field optional. Omitted (None) fields keep
    the existing stored value; only provided fields are written. This lets callers
    (e.g. the inline TranslateModal) persist a partial selection — language + model —
    without resetting custom prompts. See LW-PLAN-MVP-RELEASE T1."""
    target_language: Optional[str] = None
    model_source: Optional[str] = None
    model_ref: Optional[UUID] = None
    system_prompt: Optional[str] = None
    user_prompt_tpl: Optional[str] = None
    compact_model_source: Optional[str] = None
    compact_model_ref: Optional[UUID] = None
    compact_system_prompt: Optional[str] = None
    compact_user_prompt_tpl: Optional[str] = None
    chunk_size_tokens: Optional[int] = None
    invoke_timeout_secs: Optional[int] = None

    @field_validator("user_prompt_tpl")
    @classmethod
    def must_contain_chapter_text(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and "{chapter_text}" not in v:
            raise ValueError("user_prompt_tpl must contain {chapter_text}")
        return v


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
    # Per-job overrides (LW-PLAN-MVP-RELEASE T1 Fix-C): when provided, these win over
    # the book's persisted translation settings, so a one-off translation does not
    # depend on a prior settings write succeeding. Omitted → fall back to settings.
    target_language: Optional[str] = None
    model_source: Optional[str] = None
    model_ref: Optional[UUID] = None
    pipeline_version: Optional[str] = None  # 'v2' (default) | 'v3' — per-job override
    # V3 QA config (per-job overrides; otherwise inherit book/prefs defaults).
    qa_depth: Optional[str] = None           # 'rule_only' | 'standard' | 'thorough'
    max_qa_rounds: Optional[int] = None      # 1..5 (orchestrator caps at 5)
    verifier_model_source: Optional[str] = None
    verifier_model_ref: Optional[UUID] = None
    cold_start_mode: Optional[str] = None    # 'single_pass' (default) | 'two_pass' (M4d-2c)

    @field_validator("pipeline_version")
    @classmethod
    def _valid_pipeline_version(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("v2", "v3"):
            raise ValueError("pipeline_version must be 'v2' or 'v3'")
        return v

    @field_validator("qa_depth")
    @classmethod
    def _valid_qa_depth(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("rule_only", "standard", "thorough"):
            raise ValueError("qa_depth must be 'rule_only', 'standard', or 'thorough'")
        return v

    @field_validator("cold_start_mode")
    @classmethod
    def _valid_cold_start_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("single_pass", "two_pass"):
            raise ValueError("cold_start_mode must be 'single_pass' or 'two_pass'")
        return v

    @field_validator("max_qa_rounds")
    @classmethod
    def _valid_max_qa_rounds(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 5):
            raise ValueError("max_qa_rounds must be between 1 and 5")
        return v

    @field_validator("chapter_ids")
    @classmethod
    def must_not_be_empty(cls, v: list[UUID]) -> list[UUID]:
        if not v:
            raise ValueError("chapter_ids must not be empty")
        return v

    @model_validator(mode="after")
    def _model_source_requires_ref(self):
        # Overriding model_source without a model_ref would leave a mismatched pair
        # (e.g. source=platform_model but the inherited ref points at a user model).
        # model_ref alone is fine — it inherits the resolved model_source.
        if self.model_source is not None and self.model_ref is None:
            raise ValueError("model_ref is required when model_source is overridden")
        # Same pairing rule for the verifier model (else source/ref would mismatch).
        if self.verifier_model_source is not None and self.verifier_model_ref is None:
            raise ValueError("verifier_model_ref is required when verifier_model_source is overridden")
        return self


class ChapterTranslation(BaseModel):
    id: UUID
    job_id: UUID
    chapter_id: UUID
    book_id: UUID
    owner_user_id: UUID
    status: str
    translated_body: Optional[str] = None
    translated_body_json: Optional[list] = None
    translated_body_format: str = "text"

    @field_validator("translated_body_json", mode="before")
    @classmethod
    def _parse_json_string(cls, v):
        if isinstance(v, str):
            return _json.loads(v)
        return v
    source_language: Optional[str] = None
    target_language: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    usage_log_id: Optional[UUID] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    # V3 quality rollup (M5a "needs review" surfacing). Written by the V3
    # orchestrator's _update_rollup; absent/zero for V2 chapters.
    quality_score: Optional[int] = None
    unresolved_high_count: int = 0
    qa_rounds_used: int = 0
    # M5c living-book: true when a glossary change post-dates this translation.
    is_glossary_stale: bool = False


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
    pipeline_version: str = "v2"
    qa_depth: str = "standard"
    max_qa_rounds: int = 2
    verifier_model_source: Optional[str] = None
    verifier_model_ref: Optional[UUID] = None
    cold_start_mode: str = "single_pass"
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
    text: str = Field(default="", max_length=30_000)
    blocks: list[dict] | None = None  # Tiptap block array (Phase 8F block mode)
    source_language: str = "auto"
    target_language: str | None = None  # None = use user's preference


class TranslateTextResponse(BaseModel):
    translated_text: str | None = None  # text mode result
    translated_blocks: list[dict] | None = None  # block mode result (Tiptap JSON)
    translated_body_format: str = "text"  # "text" or "json"
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
