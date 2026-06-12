"""DbSink — the learning-service EvalSink (track phase Q1).

Implements the ``loreweave_eval.EvalSink`` Protocol structurally (the SDK must
NOT import this — the SDK can't know the learning-service schema). Holds the
pool + the run metadata the scorer cannot know (it only sees the dump): the
corpus owner, project/book, the run/config provenance, and the idempotency key.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import asyncpg

from loreweave_eval.scorer import EvalResult

from app.db.eval_repo import persist_eval_result


@dataclass
class DbSink:
    """A configured persistence target for one scored run."""

    pool: asyncpg.Pool
    user_id: UUID
    project_id: UUID | None = None
    book_id: UUID | None = None
    source: str = "offline"
    source_extraction_run_id: UUID | None = None
    config_hash: str | None = None
    judge_panel_id: UUID | None = None
    dataset_version: str | None = None
    idempotency_key: str | None = None
    origin_service: str | None = None
    origin_event_id: str | None = None

    async def write_eval_result(self, result: EvalResult) -> UUID:
        return await persist_eval_result(
            self.pool,
            result,
            user_id=self.user_id,
            project_id=self.project_id,
            book_id=self.book_id,
            source=self.source,
            source_extraction_run_id=self.source_extraction_run_id,
            config_hash=self.config_hash,
            judge_panel_id=self.judge_panel_id,
            dataset_version=self.dataset_version,
            idempotency_key=self.idempotency_key,
            origin_service=self.origin_service,
            origin_event_id=self.origin_event_id,
        )
