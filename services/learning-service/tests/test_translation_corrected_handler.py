"""M7c — translation.corrected handler (human-fix gold → corrections).

A human edit of an LLM translation becomes a corrections row carrying the RAW
before (LLM) / after (human) body (PO raw-text choice) + structural + hash.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.events.dispatcher import EventData
from app.events.handlers import handle_translation_corrected


class FakePool:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *params):
        self.calls.append((sql, params))


# corrections INSERT param order (after sql), target_type/op/actor_type/origin_service are literals:
# user_id, book_id, target_id, before_structural, after_structural, before_hash, after_hash,
# before_content, after_content, diff_class, source_chapter, origin_event_id, origin_event_type
P_USER, P_TARGET, P_BEFORE_STRUCT, P_BEFORE_HASH, P_AFTER_HASH, P_BEFORE_CONTENT, P_AFTER_CONTENT, P_ORIGIN_ID = 0, 2, 3, 5, 6, 7, 8, 11


def _corrected_event(*, outbox_id="tc-1", user_id=None, ct_id=None,
                     before_body="LLM draft", after_body="human fix", lang="vi"):
    ct = ct_id or str(uuid.uuid4())
    return EventData(
        stream="loreweave:events:translation",
        message_id="1-0",
        event_type="translation.corrected",
        aggregate_id=ct,
        payload={
            "user_id": user_id if user_id is not None else str(uuid.uuid4()),
            "book_id": str(uuid.uuid4()),
            "chapter_id": str(uuid.uuid4()),
            "chapter_translation_id": ct,
            "edited_from_version_id": str(uuid.uuid4()),
            "target_language": lang,
            "before": {"target_language": lang, "version_num": 1, "body": before_body},
            "after": {"target_language": lang, "version_num": 2, "body": after_body},
        },
        source="translation",
        raw={},
        outbox_id=outbox_id,
    )


async def test_persists_correction_with_raw_before_after():
    pool = FakePool()
    ct = str(uuid.uuid4())
    await handle_translation_corrected(
        _corrected_event(ct_id=ct, before_body="他来了", after_body="Anh ấy đã đến", outbox_id="tc-1"),
        pool=pool,
    )
    ins = [c for c in pool.calls if "INSERT INTO corrections" in c[0]]
    assert len(ins) == 1
    p = ins[0][1]
    assert p[P_TARGET] == ct
    assert p[P_ORIGIN_ID] == "tc-1"
    # RAW before/after body stored (PO raw-text), as {"body": ...} jsonb
    assert json.loads(p[P_BEFORE_CONTENT])["body"] == "他来了"
    assert json.loads(p[P_AFTER_CONTENT])["body"] == "Anh ấy đã đến"
    # structural carries language/version; content hash differs (a real edit)
    assert json.loads(p[P_BEFORE_STRUCT])["target_language"] == "vi"
    assert p[P_BEFORE_HASH] != p[P_AFTER_HASH]


async def test_identical_body_same_hash():
    """No-op edit (before==after) → equal content hashes (a real edit differs)."""
    pool = FakePool()
    await handle_translation_corrected(
        _corrected_event(before_body="same", after_body="same"), pool=pool)
    p = [c for c in pool.calls if "INSERT INTO corrections" in c[0]][0][1]
    assert p[P_BEFORE_HASH] == p[P_AFTER_HASH]


async def test_empty_outbox_id_raises_no_write():
    pool = FakePool()
    with pytest.raises(ValueError):
        await handle_translation_corrected(_corrected_event(outbox_id=""), pool=pool)
    assert pool.calls == []


async def test_missing_user_raises():
    pool = FakePool()
    with pytest.raises(ValueError):
        await handle_translation_corrected(_corrected_event(user_id=""), pool=pool)
