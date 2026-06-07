"""M7a — _emit_translation_quality: emit the V3 rollup as translation.quality
(aggregate_type='translation' → loreweave:events:translation), skip on no signal."""
import json
from uuid import uuid4

import pytest

from app.workers.chapter_worker import _emit_translation_quality

CT = uuid4()
_MSG = {
    "user_id": str(uuid4()), "book_id": str(uuid4()),
    "chapter_id": str(uuid4()), "target_language": "vi",
}


class FakeDB:
    """Mocks the asyncpg txn connection: fetchrow (rollup), fetch (issue counts),
    execute (captures the outbox INSERT)."""
    def __init__(self, quality_row, issue_rows):
        self._row = quality_row
        self._issues = issue_rows
        self.execs: list = []

    async def fetchrow(self, sql, *args):
        return self._row

    async def fetch(self, sql, *args):
        return self._issues

    async def execute(self, sql, *args):
        self.execs.append((sql, args))


def _outbox_inserts(db):
    return [e for e in db.execs if "INSERT INTO outbox_events" in e[0]]


@pytest.mark.asyncio
async def test_emits_quality_with_translation_aggregate_type():
    # quality_score is the verifier's 0-100 int (as stored in chapter_translations);
    # the emit must NORMALISE it to [0,1] for learning's score_config (review-impl HIGH).
    db = FakeDB(
        {"quality_score": 91, "unresolved_high_count": 1, "qa_rounds_used": 2},
        [{"issue_type": "wrong_name", "n": 1}, {"issue_type": "omission", "n": 2}],
    )
    await _emit_translation_quality(db, CT, _MSG, "v3")
    ins = _outbox_inserts(db)
    assert len(ins) == 1
    sql, args = ins[0]
    # args: event_type, aggregate_type, aggregate_id, payload_json
    assert args[0] == "translation.quality"
    assert args[1] == "translation"          # routes to loreweave:events:translation
    assert str(args[2]) == str(CT)
    payload = json.loads(args[3])
    assert payload["quality_score"] == 0.91   # 91/100 — IN [0,1], so learning accepts it
    assert 0.0 <= payload["quality_score"] <= 1.0
    assert payload["unresolved_high_count"] == 1
    assert payload["qa_rounds_used"] == 2
    assert payload["issue_counts"] == {"wrong_name": 1, "omission": 2}
    assert payload["chapter_translation_id"] == str(CT)
    assert payload["target_language"] == "vi"
    assert payload["pipeline_version"] == "v3"


@pytest.mark.asyncio
async def test_perfect_score_normalises_to_one():
    """A clean chapter scores 100 → must emit 1.0 (NOT 100, which learning rejects)."""
    db = FakeDB({"quality_score": 100, "unresolved_high_count": 0, "qa_rounds_used": 0}, [])
    await _emit_translation_quality(db, CT, _MSG, "v3")
    payload = json.loads(_outbox_inserts(db)[0][1][3])
    assert payload["quality_score"] == 1.0
    assert payload["issue_counts"] == {}


@pytest.mark.asyncio
async def test_skips_when_no_quality_signal():
    """V2 / no V3 verifier run → quality_score NULL → no event (no empty rows)."""
    db = FakeDB({"quality_score": None, "unresolved_high_count": 0, "qa_rounds_used": 0}, [])
    await _emit_translation_quality(db, CT, _MSG, "v2")
    assert _outbox_inserts(db) == []


@pytest.mark.asyncio
async def test_skips_when_row_missing():
    db = FakeDB(None, [])
    await _emit_translation_quality(db, CT, _MSG, "v3")
    assert _outbox_inserts(db) == []
