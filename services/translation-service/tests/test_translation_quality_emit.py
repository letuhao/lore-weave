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


# ── M7d-3 — opt-in fidelity feed (source_text + translated_text) ──────────────
# The M7d-2 online judge reads payload["source_text"]/["translated_text"]. They
# ride the SAME translation.quality event, gated on translation_judge_feed_enabled
# (off by default) — when off the payload is byte-identical to M7a.

import app.config as _cfg

_GOOD_ROW = {"quality_score": 88, "unresolved_high_count": 0, "qa_rounds_used": 1}


def _payload_of(db):
    return json.loads(_outbox_inserts(db)[0][1][3])


@pytest.mark.asyncio
async def test_feed_off_by_default_no_text_keys(monkeypatch):
    """Default (flag off): even when the worker passes the texts, the payload must
    NOT carry source_text/translated_text — byte-parity with M7a."""
    monkeypatch.setattr(_cfg.settings, "translation_judge_feed_enabled", False)
    db = FakeDB(_GOOD_ROW, [])
    await _emit_translation_quality(
        db, CT, _MSG, "v3", source_text="原文", translated_text="bản dịch")
    p = _payload_of(db)
    assert "source_text" not in p
    assert "translated_text" not in p


@pytest.mark.asyncio
async def test_feed_on_attaches_both_texts(monkeypatch):
    monkeypatch.setattr(_cfg.settings, "translation_judge_feed_enabled", True)
    db = FakeDB(_GOOD_ROW, [])
    await _emit_translation_quality(
        db, CT, _MSG, "v3", source_text="他来了。", translated_text="Anh ấy đã đến.")
    p = _payload_of(db)
    assert p["source_text"] == "他来了。"
    assert p["translated_text"] == "Anh ấy đã đến."


@pytest.mark.asyncio
async def test_feed_on_truncates_to_max_chars(monkeypatch):
    monkeypatch.setattr(_cfg.settings, "translation_judge_feed_enabled", True)
    monkeypatch.setattr(_cfg.settings, "translation_judge_feed_max_chars", 5)
    db = FakeDB(_GOOD_ROW, [])
    await _emit_translation_quality(
        db, CT, _MSG, "v3", source_text="abcdefghij", translated_text="0123456789")
    p = _payload_of(db)
    # equal-length inputs → same fraction → both capped at 5
    assert p["source_text"] == "abcde"
    assert p["translated_text"] == "01234"
    assert len(p["source_text"]) == 5


@pytest.mark.asyncio
async def test_feed_samples_same_fraction_not_same_char_count(monkeypatch):
    """review-impl MED: a char is not language-invariant. A verbose target (vi)
    has more chars than a dense source (zh) for the same story span. Truncating
    each to the same CHAR count would feed the judge misaligned spans. Assert both
    sides are sampled by the SAME FRACTION of their own length, each bounded by cap."""
    monkeypatch.setattr(_cfg.settings, "translation_judge_feed_enabled", True)
    monkeypatch.setattr(_cfg.settings, "translation_judge_feed_max_chars", 6)
    db = FakeDB(_GOOD_ROW, [])
    src = "abcdefghijkl"               # len 12 (dense source)
    tr = "ABCDEFGHIJKLMNOPQRSTUVWX"    # len 24 (verbose translation, 2× chars)
    await _emit_translation_quality(db, CT, _MSG, "v3", source_text=src, translated_text=tr)
    p = _payload_of(db)
    # frac = min(1, 6/12, 6/24) = 0.25 → src[:3], tr[:6] — SAME 25% span of each.
    # A naive same-CHAR-count cap of 6 would have taken src[:6] (50%!) vs tr[:6]
    # (25%) — misaligned. The fraction sampling keeps the spans equal.
    assert p["source_text"] == "abc"
    assert p["translated_text"] == "ABCDEF"
    assert len(p["source_text"]) / len(src) == pytest.approx(len(p["translated_text"]) / len(tr))
    # both stay within the cap
    assert len(p["source_text"]) <= 6 and len(p["translated_text"]) <= 6


@pytest.mark.asyncio
async def test_feed_skips_when_cap_non_positive(monkeypatch):
    """A misconfigured cap<=0 must SKIP the feed (no empty-string keys), not emit
    inert blanks that look like a feed."""
    monkeypatch.setattr(_cfg.settings, "translation_judge_feed_enabled", True)
    monkeypatch.setattr(_cfg.settings, "translation_judge_feed_max_chars", 0)
    db = FakeDB(_GOOD_ROW, [])
    await _emit_translation_quality(
        db, CT, _MSG, "v3", source_text="abc", translated_text="xyz")
    p = _payload_of(db)
    assert "source_text" not in p and "translated_text" not in p


@pytest.mark.asyncio
async def test_feed_on_but_empty_source_skips_keys(monkeypatch):
    """Block chapters with empty text_content → no source to judge → keys absent
    (the consumer hook stays inert, no crash)."""
    monkeypatch.setattr(_cfg.settings, "translation_judge_feed_enabled", True)
    db = FakeDB(_GOOD_ROW, [])
    await _emit_translation_quality(
        db, CT, _MSG, "v3", source_text="", translated_text="có bản dịch")
    p = _payload_of(db)
    assert "source_text" not in p
    assert "translated_text" not in p
