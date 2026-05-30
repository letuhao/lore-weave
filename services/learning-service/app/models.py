"""Pydantic models for the corrections read API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Correction(BaseModel):
    """A single persisted correction (redacted projection — no raw content)."""

    id: str
    user_id: str
    project_id: str | None = None
    book_id: str | None = None
    target_type: str
    target_id: str
    op: str
    before_structural: dict[str, Any] | None = None
    after_structural: dict[str, Any] | None = None
    before_content_hash: str | None = None
    after_content_hash: str | None = None
    diff_class: str | None = None
    source_extraction_run_id: str | None = None
    source_chapter: str | None = None
    actor_type: str
    actor_id: str | None = None
    origin_service: str
    origin_event_type: str
    emitted_at: datetime | None = None
    created_at: datetime


class CorrectionPage(BaseModel):
    """Cursor-paginated page of corrections."""

    items: list[Correction]
    next_cursor: str | None = None


class CorrectionStats(BaseModel):
    """Aggregate counts feeding the future eval-gold / few-shot tiers."""

    total: int
    by_diff_class: dict[str, int]
    by_target_type: dict[str, int]
