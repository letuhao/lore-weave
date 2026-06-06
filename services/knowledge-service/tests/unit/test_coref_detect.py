"""mui #1c K-detect — unit tests for the coref detector.

Covers the PURE scorer (name + structural signals, blocking, clustering) and
the async orchestrator (build_candidates / detect_from_records) with a fake LLM
+ fake glossary client. The Neo4j loader is deferred to the phase-6 live-smoke.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.extraction.coref_detect import (
    CorefEntity,
    block_and_score,
    build_candidates,
    cluster_pairs,
    detect_from_records,
    score_pair,
)

CFG = dict(
    score_floor=0.5, name_weight=0.6, struct_weight=0.4,
    max_pairs=200, max_bucket=50, min_mentions=2,
)


def _e(gid, name, aliases=(), mentions=10, neighbors=()):
    return CorefEntity(
        entity_id=gid, name=name, aliases=tuple(aliases),
        mention_count=mentions, neighbor_ids=frozenset(neighbors),
    )


# ── pure signals ───────────────────────────────────────────────────────────


def test_name_signal_exact_alias_overlap():
    a = _e("g1", "姜子牙", ["子牙"])
    b = _e("g2", "太公望", ["子牙"])
    p = score_pair(a, b, name_weight=0.6, struct_weight=0.4)
    assert p.name_score == 1.0  # shared alias 子牙
    assert "子牙" in p.shared_aliases


def test_name_signal_substring_containment():
    a = _e("g1", "姜子牙")
    b = _e("g2", "子牙")  # 子牙 is in a's name set via containment
    p = score_pair(a, b, name_weight=0.6, struct_weight=0.4)
    assert p.name_score >= 0.85


def test_structural_signal_jaccard():
    # No name overlap, but they co-occur with the same neighbours (太公望↔姜子牙).
    a = _e("g1", "太公望", neighbors={"n1", "n2", "n3"})
    b = _e("g2", "姜子牙", neighbors={"n1", "n2", "n4"})
    p = score_pair(a, b, name_weight=0.6, struct_weight=0.4)
    assert p.struct_score == pytest.approx(2 / 4)  # |∩|=2 (n1,n2), |∪|=4
    assert p.shared_neighbors == 2


def test_distinct_names_no_structure_below_floor():
    # Different names, no shared neighbours → should not clear the floor.
    a = _e("g1", "妲己")
    b = _e("g2", "黄飞虎")
    p = score_pair(a, b, name_weight=0.6, struct_weight=0.4)
    assert p.score < 0.5


# ── blocking + clustering ──────────────────────────────────────────────────


def test_block_and_score_finds_alias_cluster():
    ents = [
        _e("g-jiang", "姜子牙", ["子牙"], mentions=50),
        _e("g-taigong", "太公望", ["子牙"], mentions=20),
        _e("g-ziya", "子牙", mentions=5),
        _e("g-unrel", "雷震子", mentions=8),  # unrelated
    ]
    pairs = block_and_score(ents, **{k: v for k, v in CFG.items() if k != "min_mentions"})
    ids = {frozenset((p.a_id, p.b_id)) for p in pairs}
    # the three 子牙-family entities pair up; 雷震子 does not join
    assert frozenset(("g-jiang", "g-taigong")) in ids
    assert all("g-unrel" not in pair for pair in ids)


def test_block_and_score_drops_oversized_bucket():
    # 30 entities all sharing the bigram "aa" but otherwise unrelated; with
    # max_bucket=5 the common-bigram bucket is dropped → no spurious pairs.
    ents = [_e(f"g{i}", f"aa{i:03d}", mentions=5) for i in range(30)]
    pairs = block_and_score(
        ents, score_floor=0.5, name_weight=0.6, struct_weight=0.4,
        max_pairs=200, max_bucket=5,
    )
    # distinct numeric suffixes → low edit similarity; oversized bucket dropped.
    assert pairs == []


def test_cluster_pairs_transitive():
    from app.extraction.coref_detect import CandidatePair

    pairs = [
        CandidatePair("A", "B", 0.9, 0.9, 0.0),
        CandidatePair("B", "C", 0.8, 0.8, 0.0),
        CandidatePair("X", "Y", 0.7, 0.7, 0.0),
    ]
    clusters = {frozenset(c) for c in cluster_pairs(pairs)}
    assert frozenset(("A", "B", "C")) in clusters
    assert frozenset(("X", "Y")) in clusters


# ── orchestrator (fakes) ────────────────────────────────────────────────────


class _FakeJob:
    def __init__(self, content: str, status: str = "completed"):
        self.status = status
        self.result = {"messages": [{"content": content}]} if content is not None else {}


class _FakeLLM:
    """Records calls; returns a scripted verdict (or raises). `raw_content`
    overrides the JSON body to exercise the verdict-coercion path."""

    def __init__(self, *, verdict: bool | None = True, raise_exc=False, bad_status=False, raw_content=None):
        self.calls = 0
        self._verdict = verdict
        self._raise = raise_exc
        self._bad_status = bad_status
        self._raw = raw_content

    async def submit_and_wait(self, **kwargs):
        self.calls += 1
        if self._raise:
            raise RuntimeError("provider down")
        if self._bad_status:
            return _FakeJob("", status="failed")
        if self._raw is not None:
            return _FakeJob(self._raw)
        return _FakeJob(f'{{"same": {str(self._verdict).lower()}}}')


class _FakeGlossary:
    def __init__(self):
        self.proposed_with = None

    async def propose_merge_candidates(self, book_id, *, candidates):
        self.proposed_with = (book_id, candidates)
        return {"results": [{"candidate_id": f"c{i}", "status": "proposed"} for i in range(len(candidates))]}


def _family():
    return [
        _e("g-jiang", "姜子牙", ["子牙"], mentions=50),
        _e("g-taigong", "太公望", ["子牙"], mentions=20),
    ]


@pytest.mark.asyncio
async def test_build_candidates_score_only_no_judge():
    # No judge model → score-only; the alias-sharing pair becomes one cluster.
    cands = await build_candidates(
        _family(), llm=None, user_id="u1", **CFG,
        llm_verify=True, judge_model="", judge_user="", judge_model_source="platform_model",
    )
    assert len(cands) == 1
    c = cands[0]
    assert set(c["member_entity_ids"]) == {"g-jiang", "g-taigong"}
    assert c["suggested_winner_entity_id"] == "g-jiang"  # higher mention_count
    assert "score-only" in c["rationale"]
    assert c["evidence"]  # carries per-pair evidence


@pytest.mark.asyncio
async def test_build_candidates_llm_verify_rejects():
    # Judge says "not same" (homonym guard) → no cluster proposed.
    llm = _FakeLLM(verdict=False)
    cands = await build_candidates(
        _family(), llm=llm, user_id="u1", **CFG,
        llm_verify=True, judge_model="judge-x", judge_user="", judge_model_source="platform_model",
    )
    assert llm.calls >= 1
    assert cands == []


@pytest.mark.asyncio
async def test_build_candidates_llm_failure_degrades_to_keep():
    # LLM raises → verdict None → pair is KEPT (degrade to score-only).
    llm = _FakeLLM(raise_exc=True)
    cands = await build_candidates(
        _family(), llm=llm, user_id="u1", **CFG,
        llm_verify=True, judge_model="judge-x", judge_user="", judge_model_source="platform_model",
    )
    assert len(cands) == 1


@pytest.mark.asyncio
async def test_build_candidates_bad_status_degrades_to_keep():
    llm = _FakeLLM(bad_status=True)
    cands = await build_candidates(
        _family(), llm=llm, user_id="u1", **CFG,
        llm_verify=True, judge_model="judge-x", judge_user="", judge_model_source="platform_model",
    )
    assert len(cands) == 1


@pytest.mark.asyncio
async def test_min_mentions_filters_long_tail():
    ents = [
        _e("g-jiang", "姜子牙", ["子牙"], mentions=1),
        _e("g-taigong", "太公望", ["子牙"], mentions=1),
    ]
    cands = await build_candidates(
        ents, llm=None, user_id="u1", **CFG,
        llm_verify=False, judge_model="", judge_user="", judge_model_source="platform_model",
    )
    assert cands == []  # both below min_mentions=2


@pytest.mark.asyncio
async def test_detect_from_records_proposes_to_glossary():
    glossary = _FakeGlossary()
    result = await detect_from_records(
        _family(), glossary=glossary, llm=None, book_id="book-1", user_id="u1",
        **CFG, llm_verify=False, judge_model="", judge_user="", judge_model_source="platform_model",
    )
    assert result.clusters_found == 1
    assert result.proposed == 1
    book_id, candidates = glossary.proposed_with
    assert book_id == "book-1"
    assert set(candidates[0]["member_entity_ids"]) == {"g-jiang", "g-taigong"}


@pytest.mark.asyncio
async def test_verify_string_no_rejects_pair():
    # review-impl MED: a judge emitting the STRING "no" must reject, not keep
    # (bool("no") is True — the bug). Coercion maps "no" → False → dropped.
    llm = _FakeLLM(raw_content='{"same": "no"}')
    cands = await build_candidates(
        _family(), llm=llm, user_id="u1", **CFG,
        llm_verify=True, judge_model="judge-x", judge_user="", judge_model_source="platform_model",
    )
    assert cands == []


@pytest.mark.asyncio
async def test_verify_string_yes_keeps_pair():
    llm = _FakeLLM(raw_content='{"same": "yes"}')
    cands = await build_candidates(
        _family(), llm=llm, user_id="u1", **CFG,
        llm_verify=True, judge_model="judge-x", judge_user="", judge_model_source="platform_model",
    )
    assert len(cands) == 1


@pytest.mark.asyncio
async def test_detect_and_propose_does_not_cross_cluster_kinds(monkeypatch):
    # review-impl HIGH-1: scoring must be PER KIND. A character and a location
    # that share a neighbour must NOT end up in one cluster (glossary would
    # reject the whole mixed cluster, losing the valid same-kind pairs).
    from app.extraction import coref_detect as cd

    shared = {"shared-neighbor"}
    by_kind = {
        "character": [
            _e("g-jiang", "姜子牙", ["子牙"], mentions=50, neighbors=shared),
            _e("g-taigong", "太公望", ["子牙"], mentions=20, neighbors=shared),
        ],
        # different kind, shares the SAME neighbour as the characters above —
        # a combined-set scorer would wrongly cluster across kinds.
        "location": [
            _e("g-kunlun", "昆仑山", ["昆仑"], mentions=30, neighbors=shared),
            _e("g-kunlunshan", "昆仑", mentions=10, neighbors=shared),
        ],
    }

    async def fake_load(session, *, user_id, project_id, kind, limit):
        return by_kind[kind]

    monkeypatch.setattr(cd, "_load_coref_entities", fake_load)
    glossary = _FakeGlossary()
    result = await cd.detect_and_propose(
        session=None, glossary=glossary, llm=None,
        user_id="u1", project_id="p1", book_id="book-1",
        kinds=["character", "location"],
        score_floor=0.5, name_weight=0.6, struct_weight=0.4,
        max_pairs=200, max_bucket=50, max_candidates_per_kind=500, min_mentions=2,
        llm_verify=False, judge_model="", judge_user="", judge_model_source="platform_model",
    )
    _, candidates = glossary.proposed_with
    assert len(candidates) == 2  # one per kind, NOT one merged cross-kind blob
    char_ids = {"g-jiang", "g-taigong"}
    loc_ids = {"g-kunlun", "g-kunlunshan"}
    for c in candidates:
        members = set(c["member_entity_ids"])
        assert members <= char_ids or members <= loc_ids  # never mixed
    assert result.clusters_found == 2


@pytest.mark.asyncio
async def test_detect_from_records_no_clusters_skips_propose():
    glossary = _FakeGlossary()
    # single entity → nothing to pair
    result = await detect_from_records(
        [_e("g1", "姜子牙", mentions=10)], glossary=glossary, llm=None,
        book_id="book-1", user_id="u1", **CFG,
        llm_verify=False, judge_model="", judge_user="", judge_model_source="platform_model",
    )
    assert result.clusters_found == 0
    assert glossary.proposed_with is None  # no call when nothing to propose
