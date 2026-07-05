"""POC — Narrative Forge gate-reconciliation for Knowledge extraction (pure units +
fake-judge). Mirrors composition-service's `tests/test_canon_check.py` structure."""

from __future__ import annotations

import pytest
from types import SimpleNamespace

from app.extraction.canon_check import (
    ExtractionCanonCandidate,
    check_extraction_canon,
    gone_entities_asserted_active,
    judge_extraction_contradiction,
)


def _snap(*entities):
    return {"entities": list(entities)}


def _ent(entity_id, name, status, **extra):
    return {"entity_id": entity_id, "name": name, "canonical_name": name.lower(),
            "status": status, **extra}


# ── gone_entities_asserted_active (symbolic pre-filter) ─────────────────────

def test_flags_gone_entity_present_in_new_chapter_text():
    snap = _snap(_ent("e-alice", "Alice", "gone", from_order=3_000_000))
    out = gone_entities_asserted_active("Alice smiled and picked up her sword.", snap)
    assert len(out) == 1
    assert out[0].entity_id == "e-alice"
    assert out[0].status == "gone"
    assert out[0].gone_from_order == 3_000_000
    assert out[0].source == "score_symbolic"
    assert out[0].confirmed is None
    assert "Alice" in out[0].span


def test_active_entity_not_flagged():
    snap = _snap(_ent("e-bob", "Bob", "active"))
    assert gone_entities_asserted_active("Bob walked to town.", snap) == []


def test_gone_entity_absent_from_text_not_flagged():
    snap = _snap(_ent("e-alice", "Alice", "gone"))
    assert gone_entities_asserted_active("Bob walked alone through the empty hall.", snap) == []


def test_ascii_word_boundary_avoids_substring_false_positive():
    snap = _snap(_ent("e-al", "Al", "gone"))
    assert gone_entities_asserted_active("Always the wind blew cold.", snap) == []
    assert len(gone_entities_asserted_active("Al stood in the doorway.", snap)) == 1


def test_cjk_name_substring_match():
    snap = _snap(_ent("e-z", "卡斯托", "gone"))
    out = gone_entities_asserted_active("城门倒下，卡斯托举起了剑。", snap)
    assert len(out) == 1 and out[0].entity_id == "e-z"


def test_dedup_per_entity():
    snap = _snap(_ent("e-alice", "Alice", "gone"))
    out = gone_entities_asserted_active("Alice spoke. Alice laughed. Alice left.", snap)
    assert len(out) == 1  # one candidate per entity, not per occurrence


def test_absent_snapshot_degrades_to_empty():
    assert gone_entities_asserted_active("Alice acted.", None) == []
    assert gone_entities_asserted_active("", _snap(_ent("e", "Alice", "gone"))) == []


def test_canonical_name_match_when_display_name_differs():
    snap = _snap({"entity_id": "e-p", "name": "The Phoenix",
                  "canonical_name": "phoenix", "status": "gone"})
    out = gone_entities_asserted_active("A phoenix rose from the ash.", snap)
    assert len(out) == 1 and out[0].matched == "phoenix"


def test_candidate_model_shape():
    c = ExtractionCanonCandidate(entity_id="e1", span="x")
    assert c.kind == "gone_entity_asserted_active_in_extraction"
    assert c.confirmed is None


# ── judge_extraction_contradiction (fake LLM client) ─────────────────────────

class _FakeLLM:
    def __init__(self, content=None, status="completed", raise_exc=None):
        self._content, self._status, self._exc = content, status, raise_exc
        self.calls = 0

    async def submit_and_wait(self, **kwargs):
        self.calls += 1
        if self._exc:
            raise self._exc
        return SimpleNamespace(status=self._status,
                                result={"messages": [{"content": self._content}]})


def _cand(eid="e-alice", name="Alice"):
    return ExtractionCanonCandidate(entity_id=eid, name=name, span=f"{name} smiled")


@pytest.mark.asyncio
async def test_judge_confirms_contradiction():
    llm = _FakeLLM('{"verdicts":[{"entity_id":"e-alice","violated":true,"why":"acts with no revival"}]}')
    out = await judge_extraction_contradiction(
        llm, user_id="u", model_source="user_model", model_ref="m",
        chapter_text="Alice smiled and picked up her sword.", candidates=[_cand()],
    )
    assert out[0].confirmed is True and out[0].source == "llm_judge"
    assert out[0].why == "acts with no revival"
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_judge_clears_flashback_as_non_contradiction():
    llm = _FakeLLM('{"verdicts":[{"entity_id":"e-alice","violated":false,"why":"a memory of Alice"}]}')
    out = await judge_extraction_contradiction(
        llm, user_id="u", model_source="user_model", model_ref="m",
        chapter_text="He remembered how Alice used to smile.", candidates=[_cand()],
    )
    assert out[0].confirmed is False


@pytest.mark.asyncio
async def test_judge_degrades_to_symbolic_on_error_never_blocks():
    llm = _FakeLLM(raise_exc=RuntimeError("provider down"))
    out = await judge_extraction_contradiction(
        llm, user_id="u", model_source="user_model", model_ref="m",
        chapter_text="Alice acts.", candidates=[_cand()],
    )
    assert out[0].confirmed is None  # CC4-style — never blocks on its own failure


@pytest.mark.asyncio
async def test_judge_noop_on_empty_candidates():
    llm = _FakeLLM("{}")
    out = await judge_extraction_contradiction(
        llm, user_id="u", model_source="user_model", model_ref="m",
        chapter_text="Nothing relevant.", candidates=[],
    )
    assert out == [] and llm.calls == 0


# ── check_extraction_canon (compose) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_extraction_canon_symbolic_only_without_llm():
    snap = _snap(_ent("e-alice", "Alice", "gone"))
    out = await check_extraction_canon("Alice charged forward.", snap, llm=None)
    assert len(out) == 1 and out[0].confirmed is None  # advisory (no judge configured)


@pytest.mark.asyncio
async def test_check_extraction_canon_no_candidates_never_calls_llm():
    llm = _FakeLLM("{}")
    out = await check_extraction_canon(
        "Bob walked home.", _snap(_ent("e-alice", "Alice", "gone")),
        llm=llm, user_id="u", model_source="user_model", model_ref="m",
    )
    assert out == [] and llm.calls == 0  # no gone-entity text match → judge never invoked


@pytest.mark.asyncio
async def test_check_extraction_canon_full_path_with_llm():
    llm = _FakeLLM('{"verdicts":[{"entity_id":"e-alice","violated":true,"why":"acts"}]}')
    snap = _snap(_ent("e-alice", "Alice", "gone", from_order=3_000_000))
    out = await check_extraction_canon(
        "Alice smiled and drew her sword.", snap,
        llm=llm, user_id="u", model_source="user_model", model_ref="m",
    )
    assert len(out) == 1
    assert out[0].confirmed is True
    assert out[0].source == "llm_judge"
    assert llm.calls == 1
