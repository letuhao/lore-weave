"""Unit coverage for the LLM-as-judge harness (tests/quality/llm_judge.py).

Deterministic — the judge LLM client is mocked, so these assert the
prompt/parse/score logic without any provider call.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from loreweave_llm.errors import LLMError

from tests.quality.llm_judge import (
    CategoryJudgement,
    GoldVerdict,
    ItemVerdict,
    _extract_json_object,
    _index_verdicts,
    format_items_for_judge,
    judge_category,
    judge_chapter,
    judge_precision,
    judge_recall,
)


def _job(content: str, status: str = "completed") -> SimpleNamespace:
    """Fake terminal Job carrying a chat-style result payload."""
    return SimpleNamespace(
        status=status,
        result={"messages": [{"role": "assistant", "content": content}]},
    )


class _FakeClient:
    """Returns queued responses in submit order; records each call.

    A queued entry that is an Exception instance is raised instead of
    returned — lets a test simulate a gateway/LLM failure mid-run.
    """

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def submit_and_wait(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("submit_and_wait called more often than queued")
        nxt = self._responses.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


# ── format_items_for_judge ──────────────────────────────────────────


def test_format_entities():
    out = format_items_for_judge("entity", [{"name": "Kai", "kind": "person"}])
    assert out == ["Kai (kind: person)"]


def test_format_relations_negated():
    out = format_items_for_judge(
        "relation",
        [{"subject": "A", "predicate": "trusts", "object": "B", "polarity": "negate"}],
    )
    assert out == ["A --trusts--> B [NEGATED]"]


def test_format_events():
    out = format_items_for_judge(
        "event", [{"summary": "Alice falls", "participants": ["Alice"]}]
    )
    assert out == ["Alice falls (participants: Alice)"]


# ── _extract_json_object ────────────────────────────────────────────


def test_extract_plain_json():
    assert _extract_json_object('{"verdicts": []}') == {"verdicts": []}


def test_extract_fenced_json():
    raw = '```json\n{"verdicts": [{"idx": 0}]}\n```'
    assert _extract_json_object(raw) == {"verdicts": [{"idx": 0}]}


def test_extract_prose_wrapped_json():
    raw = 'Sure! Here you go: {"verdicts": []} hope that helps'
    assert _extract_json_object(raw) == {"verdicts": []}


def test_extract_empty_raises():
    with pytest.raises(ValueError):
        _extract_json_object("   ")


def test_extract_no_object_raises():
    with pytest.raises(ValueError):
        _extract_json_object("no json here")


# ── _index_verdicts ─────────────────────────────────────────────────


def test_index_verdicts_skips_malformed():
    verdicts = [
        {"idx": 0, "verdict": "supported"},
        "not a dict",
        {"idx": True, "verdict": "x"},   # bool rejected
        {"verdict": "no idx"},            # missing key
        {"idx": 2, "verdict": "partial"},
    ]
    out = _index_verdicts(verdicts, key="idx")
    assert set(out) == {0, 2}


# ── CategoryJudgement math ──────────────────────────────────────────


def test_category_precision_excludes_unjudged_from_denominator():
    cat = CategoryJudgement(
        category="entity", n_extracted=4, n_gold=0,
        precision_verdicts=[
            ItemVerdict(0, "supported", ""),
            ItemVerdict(1, "partial", ""),
            ItemVerdict(2, "unsupported", ""),
            ItemVerdict(3, "unjudged", ""),
        ],
    )
    # (1.0 + 0.5 + 0) / 3 judged — unjudged item excluded from denominator
    assert cat.precision == pytest.approx(0.5)
    assert cat.n_unjudged == 1
    assert cat.n_precision_judged == 3
    assert cat.precision_coverage == pytest.approx(0.75)


def test_category_precision_none_when_all_unjudged():
    cat = CategoryJudgement(
        category="entity", n_extracted=2, n_gold=0,
        precision_verdicts=[
            ItemVerdict(0, "unjudged", ""), ItemVerdict(1, "unjudged", ""),
        ],
    )
    assert cat.precision is None  # extracted but none judged → meaningless
    assert cat.precision_coverage == 0.0


def test_category_recall_excludes_unjudged_gold():
    cat = CategoryJudgement(
        category="entity", n_extracted=0, n_gold=3,
        recall_verdicts=[
            GoldVerdict(0, True, 1, "", judged=True),
            GoldVerdict(1, False, None, "", judged=False),  # omitted
            GoldVerdict(2, True, 0, "", judged=True),
        ],
    )
    # found 2 / judged 2 (gold_idx 1 omitted) = 1.0
    assert cat.recall == pytest.approx(1.0)
    assert cat.recall_coverage == pytest.approx(2 / 3)


def test_category_recall_fraction():
    cat = CategoryJudgement(
        category="entity", n_extracted=0, n_gold=3,
        recall_verdicts=[
            GoldVerdict(0, True, 1, ""),
            GoldVerdict(1, False, None, ""),
            GoldVerdict(2, True, 0, ""),
        ],
    )
    assert cat.recall == pytest.approx(2 / 3)


def test_category_empty_is_vacuously_perfect():
    cat = CategoryJudgement(category="event", n_extracted=0, n_gold=0)
    assert cat.precision == 1.0
    assert cat.recall == 1.0


# ── judge_precision ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_judge_precision_maps_and_fills_missing():
    # 3 items; judge returns verdicts for 0 and 2 only, plus a bad value.
    content = (
        '{"verdicts": ['
        '{"idx": 0, "verdict": "supported", "reason": "named in text"},'
        '{"idx": 2, "verdict": "BOGUS", "reason": "x"}'
        ']}'
    )
    client = _FakeClient([_job(content)])
    verdicts = await judge_precision(
        client, judge_model="m", user_id="u", model_source="user_model",
        source_text="...", category="entity",
        extracted=[{"name": "A", "kind": "person"},
                   {"name": "B", "kind": "person"},
                   {"name": "C", "kind": "place"}],
    )
    assert [v.verdict for v in verdicts] == ["supported", "unjudged", "unjudged"]
    # idx 1 omitted by judge → unjudged; idx 2 invalid value → unjudged
    assert verdicts[0].reason == "named in text"


@pytest.mark.asyncio
async def test_judge_precision_batches_and_maps_global_idx():
    # 5 items, batch_size=2 → 3 calls; verify global idx preserved and
    # each batch uses LOCAL idx in its prompt/response.
    r1 = _job('{"verdicts": [{"idx": 0, "verdict": "supported", "reason": ""},'
              '{"idx": 1, "verdict": "unsupported", "reason": ""}]}')
    r2 = _job('{"verdicts": [{"idx": 0, "verdict": "partial", "reason": ""},'
              '{"idx": 1, "verdict": "supported", "reason": ""}]}')
    r3 = _job('{"verdicts": [{"idx": 0, "verdict": "supported", "reason": ""}]}')
    client = _FakeClient([r1, r2, r3])
    items = [{"name": f"E{i}", "kind": "person"} for i in range(5)]
    verdicts = await judge_precision(
        client, judge_model="m", user_id="u", model_source="user_model",
        source_text="...", category="entity", extracted=items, batch_size=2,
    )
    assert len(client.calls) == 3
    assert [v.idx for v in verdicts] == [0, 1, 2, 3, 4]
    assert [v.verdict for v in verdicts] == [
        "supported", "unsupported", "partial", "supported", "supported",
    ]


@pytest.mark.asyncio
async def test_judge_precision_llm_error_marks_batch_unjudged():
    # MED#1: a gateway/LLM error must NOT abort the run — the batch is
    # marked unjudged and excluded from the denominator.
    client = _FakeClient([LLMError("gateway down")])
    verdicts = await judge_precision(
        client, judge_model="m", user_id="u", model_source="user_model",
        source_text="...", category="entity",
        extracted=[{"name": "A", "kind": "person"}, {"name": "B", "kind": "person"}],
    )
    assert [v.verdict for v in verdicts] == ["unjudged", "unjudged"]


@pytest.mark.asyncio
async def test_judge_recall_batches_and_maps_global_gold_idx():
    # LOW#1: 5 gold, batch_size=2 → 3 calls; global gold_idx preserved,
    # found flags mapped correctly across batches.
    r1 = _job('{"verdicts": [{"gold_idx": 0, "found": true, "matched": 0, "reason": ""},'
              '{"gold_idx": 1, "found": false, "matched": null, "reason": ""}]}')
    r2 = _job('{"verdicts": [{"gold_idx": 0, "found": true, "matched": 1, "reason": ""},'
              '{"gold_idx": 1, "found": false, "matched": null, "reason": ""}]}')
    r3 = _job('{"verdicts": [{"gold_idx": 0, "found": true, "matched": 2, "reason": ""}]}')
    client = _FakeClient([r1, r2, r3])
    gold = [{"name": f"G{i}", "kind": "person"} for i in range(5)]
    verdicts = await judge_recall(
        client, judge_model="m", user_id="u", model_source="user_model",
        source_text="...", category="entity", gold=gold,
        extracted=[{"name": "X", "kind": "person"}], batch_size=2,
    )
    assert len(client.calls) == 3
    assert [v.gold_idx for v in verdicts] == [0, 1, 2, 3, 4]
    assert [v.found for v in verdicts] == [True, False, True, False, True]
    assert all(v.judged for v in verdicts)


@pytest.mark.asyncio
async def test_judge_precision_empty_returns_empty_no_call():
    client = _FakeClient([])  # no responses queued — must not be called
    verdicts = await judge_precision(
        client, judge_model="m", user_id="u", model_source="user_model",
        source_text="...", category="entity", extracted=[],
    )
    assert verdicts == []
    assert client.calls == []


@pytest.mark.asyncio
async def test_judge_precision_parse_failure_all_unjudged():
    client = _FakeClient([_job("the model rambled with no json")])
    verdicts = await judge_precision(
        client, judge_model="m", user_id="u", model_source="user_model",
        source_text="...", category="entity",
        extracted=[{"name": "A", "kind": "person"}],
    )
    assert [v.verdict for v in verdicts] == ["unjudged"]


@pytest.mark.asyncio
async def test_judge_precision_non_completed_job_all_unjudged():
    client = _FakeClient([_job("", status="failed")])
    verdicts = await judge_precision(
        client, judge_model="m", user_id="u", model_source="user_model",
        source_text="...", category="entity",
        extracted=[{"name": "A", "kind": "person"}],
    )
    assert [v.verdict for v in verdicts] == ["unjudged"]


# ── judge_recall ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_judge_recall_maps_found():
    content = (
        '{"verdicts": ['
        '{"gold_idx": 0, "found": true, "matched": 1, "reason": "same fact"},'
        '{"gold_idx": 1, "found": false, "matched": null, "reason": "absent"}'
        ']}'
    )
    client = _FakeClient([_job(content)])
    verdicts = await judge_recall(
        client, judge_model="m", user_id="u", model_source="user_model",
        source_text="...", category="relation",
        gold=[{"subject": "A", "predicate": "knows", "object": "B"},
              {"subject": "C", "predicate": "owns", "object": "D"}],
        extracted=[{"subject": "x", "predicate": "y", "object": "z"}],
    )
    assert verdicts[0].found is True and verdicts[0].matched_actual_idx == 1
    assert verdicts[1].found is False and verdicts[1].matched_actual_idx is None


@pytest.mark.asyncio
async def test_judge_recall_empty_gold_no_call():
    client = _FakeClient([])
    verdicts = await judge_recall(
        client, judge_model="m", user_id="u", model_source="user_model",
        source_text="...", category="entity", gold=[], extracted=[{"name": "A", "kind": "p"}],
    )
    assert verdicts == []
    assert client.calls == []


# ── judge_category / judge_chapter ──────────────────────────────────


@pytest.mark.asyncio
async def test_judge_category_runs_precision_then_recall():
    prec = _job('{"verdicts": [{"idx": 0, "verdict": "supported", "reason": "ok"}]}')
    rec = _job('{"verdicts": [{"gold_idx": 0, "found": true, "matched": 0, "reason": "ok"}]}')
    client = _FakeClient([prec, rec])
    cat = await judge_category(
        client, judge_model="m", user_id="u", model_source="user_model",
        source_text="...", category="entity",
        extracted=[{"name": "A", "kind": "person"}],
        gold=[{"name": "A", "kind": "person"}],
    )
    assert cat.precision == 1.0
    assert cat.recall == 1.0
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_judge_chapter_aggregates_three_categories():
    # entity: 1 extracted supported, 1 gold found
    # relation: 0 extracted, 0 gold  → vacuous
    # event: 1 extracted unsupported, 1 gold not-found
    responses = [
        _job('{"verdicts": [{"idx": 0, "verdict": "supported", "reason": ""}]}'),  # ent prec
        _job('{"verdicts": [{"gold_idx": 0, "found": true, "matched": 0, "reason": ""}]}'),  # ent rec
        # relation has no items/gold → no calls
        _job('{"verdicts": [{"idx": 0, "verdict": "unsupported", "reason": ""}]}'),  # evt prec
        _job('{"verdicts": [{"gold_idx": 0, "found": false, "matched": null, "reason": ""}]}'),  # evt rec
    ]
    client = _FakeClient(responses)
    j = await judge_chapter(
        client, judge_model="m", user_id="u", model_source="user_model",
        chapter="ch", source_text="...",
        actual={"entities": [{"name": "A", "kind": "person"}], "relations": [],
                "events": [{"summary": "S", "participants": []}]},
        expected={"entities": [{"name": "A", "kind": "person"}], "relations": [],
                  "events": [{"summary": "T", "participants": []}]},
    )
    # item-weighted precision: ent supported(1.0) + evt unsupported(0) over 2 extracted = 0.5
    assert j.precision == pytest.approx(0.5)
    # recall: ent found(1) + evt not-found(0) over 2 gold = 0.5
    assert j.recall == pytest.approx(0.5)
    # relation category contributed no calls
    assert len(client.calls) == 4
