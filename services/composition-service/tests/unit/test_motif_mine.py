"""W8 — motif mining: PrefixSpan miner + the abstraction→judge→draft-write
orchestration (fakes only — no DB, no real gateway, no knowledge-service).

Proves:
  - ``prefixspan`` finds the frequent ordered beat-subsequences ≥ min_support and
    excludes singletons / sub-threshold patterns;
  - the orchestration fetches sequences → mines → abstracts → judges → persists
    gate-passing drafts as ``source='mined', status='draft'`` with judge_score +
    mining_support stamped;
  - §11 NO SILENT DROP: a below-gate candidate is SHOWN in ``candidates`` with its
    score + ``passed_gate: False`` and is NOT persisted;
  - the deferred ``motif_beat`` extractor (client returns []) DEGRADES to
    ``mined: 0, reason: 'beat_extractor_unavailable'`` (job completes, never crashes);
  - the provider-gateway invariant: fail closed on an empty model_ref.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.db.models import Motif
from app.engine import motif_mine as mm

USER = str(uuid.uuid4())


# ── fakes ─────────────────────────────────────────────────────────────────────────────
class _FakeJob:
    def __init__(self, content):
        self.status = "completed"
        self.result = {"messages": [{"content": content}]}


class _FakeLLM:
    """Returns the abstraction frame, then the judge frame, alternating per candidate.
    `abstraction` and `judge_score` drive what each canned response says. Records the
    (model_source, model_ref) it saw so the provider-gateway path is assertable."""

    def __init__(self, *, abstraction: dict, judge_score: float):
        self._abstraction = abstraction
        self._judge_score = judge_score
        self.calls: list[dict] = []
        self._toggle = 0

    async def submit_and_wait(self, *, user_id, operation, model_source, model_ref,
                              input, job_meta=None, **kw):
        self.calls.append({"model_source": model_source, "model_ref": model_ref,
                           "extractor": (job_meta or {}).get("extractor")})
        kind = (job_meta or {}).get("extractor")
        if kind == "motif_mine_judge":
            return _FakeJob(json.dumps({"score": self._judge_score, "verdict": "pass"}))
        # abstraction frame
        return _FakeJob(json.dumps(self._abstraction))


class _FakeMotifRepo:
    def __init__(self, catalog=None):
        self.created: list[dict] = []
        # the user's visible motif catalog the tag-beats pre-pass classifies against
        self._catalog = catalog if catalog is not None else [
            Motif(id=uuid.uuid4(), owner_user_id=None, code="cultivation.face_slap",
                  name="Face-Slap Reversal", summary="a humiliation repaid"),
            Motif(id=uuid.uuid4(), owner_user_id=None, code="revenge.betrayal_to_exile",
                  name="Betrayal to Exile", summary="cast out by an ally"),
        ]

    async def create(self, user_id, args, *, source="authored",
                     imported_derived=False, status="active",
                     judge_score=None, mining_support=None,
                     book_id=None, book_shared=False):
        self.created.append({
            "args": args, "source": source, "status": status,
            "judge_score": judge_score, "mining_support": mining_support,
            "book_id": book_id, "book_shared": book_shared,
        })
        return Motif(id=uuid.uuid4(), owner_user_id=user_id, code=args.code,
                     name=args.name, source=source, status=status,
                     judge_score=judge_score, mining_support=mining_support,
                     book_id=book_id, book_shared=book_shared)

    async def list_for_caller(self, caller_id, *, scope="all", status="active",
                              limit=100, **kw):
        return list(self._catalog)


class _FakeKnowledge:
    """Returns canned raw beat sequences (or [] for the cold/empty-corpus degrade) and
    records the tag-beats pre-pass (D-W8-MOTIF-BEAT-LLM-EXTRACTOR)."""

    def __init__(self, sequences):
        self._sequences = sequences
        self.calls: list[dict] = []
        self.tag_calls: list[dict] = []

    async def get_motif_beat_sequences(self, user_id, *, book_id=None, corpus=False,
                                       language=None):
        self.calls.append({"user_id": str(user_id), "book_id": book_id,
                           "corpus": corpus, "language": language,
                           # capture ordering: how many tag calls preceded this fetch
                           "tagged_before": len(self.tag_calls)})
        return list(self._sequences)

    async def tag_beats(self, user_id, *, book_id=None, corpus=False, motifs,
                        model_source, model_ref):
        self.tag_calls.append({"user_id": str(user_id), "book_id": book_id,
                               "corpus": corpus, "motifs": motifs,
                               "model_source": model_source, "model_ref": model_ref})
        return {"tagged": len(motifs), "events_seen": 1,
                "motifs_assigned": {motifs[0]["code"]: 1} if motifs else {}}


def _seq(*beats):
    """A raw beat sequence: each beat → {beat, thread, tension, role_mentions}."""
    return [{"beat": b, "thread": "main", "tension": 3, "role_mentions": ["x"]}
            for b in beats]


def _abstraction(code="mined.motif-a", name="Abstract Motif"):
    return {
        "code": code, "name": name, "kind": "sequence",
        "summary": "a recurring abstract shape",
        "roles": [{"key": "protagonist", "actant": "subject", "label": "the hero"}],
        "beats": [{"key": "b1", "label": "isolation", "intent": "set up", "order": 0},
                  {"key": "b2", "label": "reversal", "intent": "turn", "order": 1}],
        "preconditions": ["the hero is alone"], "effects": ["the hero is changed"],
    }


# ════════════════════════════════════════════════════════════════════════════════════
# PrefixSpan miner (pure)
# ════════════════════════════════════════════════════════════════════════════════════
def test_prefixspan_finds_frequent_ordered_subsequence():
    # "a → b" recurs in 3 of 3 sequences (each also has noise); "a → b → c" in 2.
    sequences = [
        ["a", "x", "b", "c"],
        ["a", "b", "y", "c"],
        ["z", "a", "b"],
    ]
    patterns = dict(mm.prefixspan(sequences, min_support=3))
    assert ("a", "b") in patterns and patterns[("a", "b")] == 3
    # ("a","b","c") is in only 2 → excluded at min_support=3.
    assert ("a", "b", "c") not in patterns


def test_prefixspan_respects_min_support_threshold():
    sequences = [["a", "b"], ["a", "b"], ["a", "c"]]
    p3 = dict(mm.prefixspan(sequences, min_support=3))
    assert ("a", "b") not in p3      # support 2 < 3
    p2 = dict(mm.prefixspan(sequences, min_support=2))
    assert p2[("a", "b")] == 2


def test_prefixspan_excludes_singletons():
    # a single frequent item is NOT a motif (a motif is a multi-beat shape).
    sequences = [["a"], ["a"], ["a"]]
    assert mm.prefixspan(sequences, min_support=2) == []


def test_prefixspan_subsequence_is_order_sensitive():
    # "b → a" must NOT match "a → b" (order matters for a sequential pattern).
    sequences = [["a", "b"], ["a", "b"], ["a", "b"]]
    patterns = dict(mm.prefixspan(sequences, min_support=3))
    assert ("a", "b") in patterns
    assert ("b", "a") not in patterns


def test_encode_sequences_uses_thread_and_beat_excludes_role_mentions():
    raw = [[{"beat": "Isolation", "thread": "Main", "role_mentions": ["alice"]},
            {"beat": "Reversal", "thread": "Main", "role_mentions": ["bob"]}]]
    encoded = mm._encode_sequences(raw)
    # symbol is thread:beat lower-cased; role mentions (the concrete cast) are excluded.
    assert encoded == [["main:isolation", "main:reversal"]]


# ════════════════════════════════════════════════════════════════════════════════════
# orchestration with fakes
# ════════════════════════════════════════════════════════════════════════════════════
async def test_mine_persists_gate_passing_drafts():
    # "a → b" recurs across 3 sequences (support 3 ≥ min_support 2); judge passes.
    knowledge = _FakeKnowledge([_seq("a", "b"), _seq("a", "b"), _seq("a", "b")])
    llm = _FakeLLM(abstraction=_abstraction(), judge_score=0.9)
    repo = _FakeMotifRepo()
    result = await mm.mine_motifs(
        knowledge=knowledge, llm=llm, motif_repo=repo, user_id=USER,
        scope="book", book_id=uuid.uuid4(), language="en",
        min_support=2, min_judge=0.6,
        model_source="platform_model", model_ref="m-ref",
    )
    assert result["mined"] >= 1
    # a draft was persisted as source='mined', status='draft' with provenance stamped.
    assert repo.created
    rec = repo.created[0]
    assert rec["source"] == "mined"
    assert rec["status"] == "draft"
    assert rec["mining_support"] == 3
    assert rec["judge_score"] is not None
    # the candidate is surfaced with its score + a passing gate.
    passed = [c for c in result["candidates"] if c["passed_gate"]]
    assert passed and passed[0]["judge_score"] >= 0.6
    # the abstraction LLM call carried the resolved (source, ref) — provider-gateway.
    assert any(c["model_ref"] == "m-ref" for c in llm.calls)


async def test_below_gate_candidate_shown_not_dropped():
    # §11 no-silent-drop: judge below the gate → SHOWN in candidates, NOT persisted.
    knowledge = _FakeKnowledge([_seq("a", "b"), _seq("a", "b"), _seq("a", "b")])
    llm = _FakeLLM(abstraction=_abstraction(), judge_score=0.2)  # below 0.6
    repo = _FakeMotifRepo()
    result = await mm.mine_motifs(
        knowledge=knowledge, llm=llm, motif_repo=repo, user_id=USER,
        scope="book", book_id=uuid.uuid4(), language="en",
        min_support=2, min_judge=0.6,
        model_source="platform_model", model_ref="m-ref",
    )
    assert result["mined"] == 0
    assert repo.created == []                      # nothing persisted
    assert result["candidates"]                    # but the candidate is SHOWN
    c0 = result["candidates"][0]
    assert c0["passed_gate"] is False
    assert c0["judge_score"] == pytest.approx(0.2)
    assert result["below_gate"] >= 1


async def test_code_collision_does_not_sink_the_whole_candidate_list():
    """MED-6 (/review-impl): a (owner, code, language) UniqueViolation on ONE persist must
    NOT crash mine_motifs and lose every other candidate (the §11 no-silent-drop guarantee).
    The colliding candidate is surfaced persisted=False/status='code_collision'; the job
    completes instead of raising."""
    import asyncpg

    class _CollidingRepo(_FakeMotifRepo):
        async def create(self, *a, **k):
            raise asyncpg.UniqueViolationError("duplicate key (owner, code, language)")

    knowledge = _FakeKnowledge([_seq("a", "b"), _seq("a", "b"), _seq("a", "b")])
    llm = _FakeLLM(abstraction=_abstraction(), judge_score=0.9)  # passes the gate
    result = await mm.mine_motifs(
        knowledge=knowledge, llm=llm, motif_repo=_CollidingRepo(), user_id=USER,
        scope="book", book_id=uuid.uuid4(), language="en",
        min_support=2, min_judge=0.6,
        model_source="platform_model", model_ref="m-ref",
    )
    assert result["mined"] == 0          # nothing persisted (the collision)
    assert result["candidates"]          # but the candidate is SHOWN, not lost to a crash
    c0 = result["candidates"][0]
    assert c0["passed_gate"] is True
    assert c0.get("persisted") is False
    assert c0.get("status") == "code_collision"


async def test_beat_extractor_unavailable_degrades_cleanly():
    # the deferred motif_beat extractor → client returns [] → job COMPLETES degraded.
    knowledge = _FakeKnowledge([])                 # extractor not available yet
    llm = _FakeLLM(abstraction=_abstraction(), judge_score=0.9)
    repo = _FakeMotifRepo()
    result = await mm.mine_motifs(
        knowledge=knowledge, llm=llm, motif_repo=repo, user_id=USER,
        scope="corpus", book_id=None, language="en",
        min_support=2, min_judge=0.6,
        model_source="platform_model", model_ref="m-ref",
    )
    assert result["mined"] == 0
    assert result["reason"] == "beat_extractor_unavailable"
    assert llm.calls == []                          # no LLM spend on the degrade path
    assert repo.created == []


async def test_no_frequent_patterns_completes_empty():
    # sequences exist but nothing recurs ≥ min_support → completes, no candidates.
    knowledge = _FakeKnowledge([_seq("a", "b"), _seq("c", "d")])
    llm = _FakeLLM(abstraction=_abstraction(), judge_score=0.9)
    repo = _FakeMotifRepo()
    result = await mm.mine_motifs(
        knowledge=knowledge, llm=llm, motif_repo=repo, user_id=USER,
        scope="corpus", book_id=None, language="en",
        min_support=2, min_judge=0.6,
        model_source="platform_model", model_ref="m-ref",
    )
    assert result["mined"] == 0
    assert result["reason"] == "no_frequent_patterns"
    assert result["candidates"] == []


async def test_mine_fails_closed_on_empty_model_ref():
    knowledge = _FakeKnowledge([_seq("a", "b"), _seq("a", "b")])
    with pytest.raises(ValueError, match="model_ref"):
        await mm.mine_motifs(
            knowledge=knowledge, llm=_FakeLLM(abstraction=_abstraction(), judge_score=0.9),
            motif_repo=_FakeMotifRepo(), user_id=USER,
            scope="corpus", book_id=None, language="en",
            min_support=2, min_judge=0.6,
            model_source="platform_model", model_ref="",
        )


async def test_run_mine_motifs_requires_book_id_for_book_scope():
    import asyncpg  # noqa: F401 — run_mine_motifs takes a pool but never touches it here

    with pytest.raises(ValueError, match="book_id"):
        await mm.run_mine_motifs(
            pool=None, llm=_FakeLLM(abstraction=_abstraction(), judge_score=0.9),
            knowledge=_FakeKnowledge([]),
            user_id=USER, input={"worker_op": "mine_motifs", "scope": "book"},
        )


# ── D-W8-MOTIF-BEAT-LLM-EXTRACTOR — the tag-beats pre-pass in run_mine_motifs ──────────


async def test_run_mine_motifs_triggers_tag_beats_with_visible_catalog_first():
    """The worker tags the :Event corpus into the user's VISIBLE motif catalog (BYOK model)
    BEFORE fetching beat sequences — so motif-beats emits generic axes for PrefixSpan."""
    from unittest.mock import patch
    book = uuid.uuid4()
    knowledge = _FakeKnowledge([_seq("a", "b"), _seq("a", "b")])
    fake_repo = _FakeMotifRepo()
    with patch("app.db.repositories.motif_repo.MotifRepo", return_value=fake_repo):
        await mm.run_mine_motifs(
            pool=None, llm=_FakeLLM(abstraction=_abstraction(), judge_score=0.9),
            knowledge=knowledge, user_id=USER,
            input={"worker_op": "mine_motifs", "scope": "book", "book_id": str(book),
                   "model_ref": "m-ref", "model_source": "user_model", "min_support": 2},
        )
    # tag-beats ran exactly once, with the visible catalog + the BYOK model, scoped to the book
    assert len(knowledge.tag_calls) == 1
    tc = knowledge.tag_calls[0]
    assert tc["model_ref"] == "m-ref" and tc["corpus"] is False and tc["book_id"] == book
    codes = {m["code"] for m in tc["motifs"]}
    assert "cultivation.face_slap" in codes and "revenge.betrayal_to_exile" in codes
    # ORDERING: the sequence fetch saw the tag pre-pass already done (tagged_before == 1)
    assert knowledge.calls and knowledge.calls[0]["tagged_before"] == 1


async def test_run_mine_corpus_tags_whole_corpus():
    """scope='corpus' tags the whole corpus (corpus=True), not a single book."""
    from unittest.mock import patch
    knowledge = _FakeKnowledge([])
    with patch("app.db.repositories.motif_repo.MotifRepo", return_value=_FakeMotifRepo()):
        await mm.run_mine_motifs(
            pool=None, llm=_FakeLLM(abstraction=_abstraction(), judge_score=0.9),
            knowledge=knowledge, user_id=USER,
            input={"worker_op": "mine_motifs", "scope": "corpus",
                   "model_ref": "m-ref", "model_source": "user_model"},
        )
    assert knowledge.tag_calls and knowledge.tag_calls[0]["corpus"] is True
    assert knowledge.tag_calls[0]["book_id"] is None


async def test_run_mine_skips_tag_beats_without_a_model(monkeypatch):
    """No resolvable model → NO tagging (don't spend on a no-op), and mine_motifs then fails
    closed on the same empty model_ref (provider-gateway invariant)."""
    from unittest.mock import patch
    monkeypatch.setattr(mm.settings, "motif_deconstruct_model_ref", "", raising=False)
    knowledge = _FakeKnowledge([])
    with patch("app.db.repositories.motif_repo.MotifRepo", return_value=_FakeMotifRepo()):
        with pytest.raises(ValueError, match="model_ref"):
            await mm.run_mine_motifs(
                pool=None, llm=_FakeLLM(abstraction=_abstraction(), judge_score=0.9),
                knowledge=knowledge, user_id=USER,
                input={"worker_op": "mine_motifs", "scope": "book",
                       "book_id": str(uuid.uuid4())},  # no model_ref in input
            )
    assert knowledge.tag_calls == []  # never tagged without a model


async def test_run_mine_tag_beats_failure_degrades_to_mining(monkeypatch):
    """A tag-beats outage must NOT fail the mine — it falls back to the Option-A axes."""
    from unittest.mock import patch
    book = uuid.uuid4()
    knowledge = _FakeKnowledge([_seq("a", "b"), _seq("a", "b")])

    async def _boom(*a, **k):
        raise RuntimeError("knowledge down")
    knowledge.tag_beats = _boom  # type: ignore[assignment]

    with patch("app.db.repositories.motif_repo.MotifRepo", return_value=_FakeMotifRepo()):
        result = await mm.run_mine_motifs(
            pool=None, llm=_FakeLLM(abstraction=_abstraction(), judge_score=0.9),
            knowledge=knowledge, user_id=USER,
            input={"worker_op": "mine_motifs", "scope": "book", "book_id": str(book),
                   "model_ref": "m-ref", "model_source": "user_model", "min_support": 2},
        )
    # mining still completed (the sequences were fetched + mined despite the tagging error)
    assert result["mined"] >= 1 and knowledge.calls
