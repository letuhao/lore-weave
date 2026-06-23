"""KG-ML M2 — `translation.published` outbox emit.

Single source of truth for the event payload so the 3 active-version-set
chokepoints (manual publish, human-block-edit activate, auto-promote on
completion — DD5) emit an identical envelope. Routed by `aggregate_type=
'translation'` → `loreweave:events:translation` via the worker-infra relay;
consumed by knowledge-service to dual-index the chapter's translated passages.
"""
from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import UUID


class _Execable(Protocol):
    async def execute(self, query: str, *args: Any) -> Any: ...


async def emit_translation_published(
    conn: _Execable,
    *,
    user_id: str | UUID,
    book_id: str | UUID,
    chapter_id: str | UUID,
    chapter_translation_id: str | UUID,
    target_language: str,
    source: str,
) -> None:
    """Insert a `translation.published` row into `outbox_events`.

    Call inside the SAME transaction/connection as the active-version write so
    the event is durable iff the activation committed (transactional outbox).
    `source` ∈ {"manual", "human_edit", "auto_promote"} — provenance only.
    """
    await conn.execute(
        """INSERT INTO outbox_events (event_type, aggregate_type, aggregate_id, payload)
           VALUES ('translation.published', 'translation', $1, $2::jsonb)""",
        UUID(str(chapter_translation_id)),
        json.dumps(
            {
                "user_id": str(user_id),
                "book_id": str(book_id),
                "chapter_id": str(chapter_id),
                "chapter_translation_id": str(chapter_translation_id),
                "target_language": target_language,
                "source": source,
            }
        ),
    )
