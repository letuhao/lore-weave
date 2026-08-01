"""The intent FSM driven against REAL Postgres (spec 2026-07-28).

WHY DB-GATED AND NOT MOCKED. The whole value of this machine is in its rails, and every rail is a
SQL fact: the optimistic `transition` (a duplicate click 409s), the partial unique index (one live
run per node), the `intent_slots` jsonb MERGE (two settled slots both survive), the record UPSERT
(cost accumulates across visits), and the runtime-chosen column in `settle_intent_slot`. A fake repo
that stores dicts would pass every one of these while the real statements were wrong — the exact
shape of the glossary-build bug that only appeared against Postgres.

Every assertion reads PERSISTED rows, never a return value.

Gated on TEST_COMPOSITION_DB_URL; drops + rebuilds the schema. xdist_group('pg') per the shared-DB
rule.
"""
from __future__ import annotations

import json
import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.works import WorksRepo
from app.services.intent_fsm.repo import IntentRepo
from app.services.intent_fsm.service import IntentFSMError, IntentFSMService

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.asyncio,
    pytest.mark.xdist_group("pg"),
]

_TABLES = [
    "intent_slot_record", "intent_run",
    "structure_node", "motif_application", "motif_link", "motif", "arc_template",
    "plan_bootstrap_proposal", "plan_artifact", "plan_run",
    "composition_daily_progress", "composition_progress_baseline",
    "style_profile", "voice_profile", "scene_grounding_pins", "reference_source",
    "decompose_commit", "outbox_events", "generation_correction", "generation_job",
    "narrative_thread", "canon_rule", "scene_link", "outline_node",
    "structure_template", "entity_override", "divergence_spec", "composition_work",
]

_BEATS = [{"key": "hook", "order": 1}, {"key": "midpoint", "order": 2}, {"key": "climax", "order": 3}]


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await run_migrations(p)
        yield p
    finally:
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await p.close()


class _FakeLLM:
    """Scripted replies keyed by nothing — the FSM asks one slot per call, in order.

    `calls` is the ledger the "one call, one retry, no loop" bound is asserted against; a docstring
    bound is not a bound.
    """

    def __init__(self, replies: list[str]) -> None:
        self.replies, self.calls = list(replies), []

    async def submit_and_wait(self, **kw):
        self.calls.append(kw)
        text = self.replies.pop(0) if self.replies else ""

        class _Job:
            status = "completed"
            # The GATEWAY frame — `messages[0].content`, not the provider's `choices[0].message`.
            # Getting this wrong made every propose land in `proposal_failed`, which is exactly what
            # a real gateway shape change would look like.
            result = {"messages": [{"content": text}]}
        return _Job()


class _FakeTemplates:
    """`resolve_structure`'s repo protocol — a single built-in with the three beats."""

    class _T:
        id = uuid.uuid4()
        owner_user_id = None
        name = "Web Novel Arc"
        kind = "web_novel"
        beats = _BEATS

    async def get(self, user_id, template_id):
        return self._T()

    async def list_for_user(self, user_id, *, include_archived=False):
        return [self._T()]


def _cands(*values):
    return json.dumps({"candidates": [{"value": v, "why": "because"} for v in values]})


async def _seed(pool, *, slots=None):
    """A work + one chapter node, and the service wired to fakes for the two external seams."""
    actor, book_id = uuid.uuid4(), uuid.uuid4()
    work = await WorksRepo(pool).create_pending(actor, book_id)
    outline = OutlineRepo(pool)
    node = await outline.create_node(
        work.id, created_by=actor, kind="chapter", chapter_id=uuid.uuid4(),
        title="Chương 1 — Mực còn ướt", synopsis="Lâm Uyên nhận thư triệu.",
    )
    return actor, book_id, work.id, node, outline


def _svc(pool, outline, llm):
    return IntentFSMService(IntentRepo(pool), outline, llm,
                            plan_runs=None, structure_templates=_FakeTemplates(), kal=None)


async def _run_row(pool, run_id):
    async with pool.acquire() as c:
        return await c.fetchrow("SELECT * FROM intent_run WHERE run_id=$1", run_id)


async def _node_row(pool, node_id):
    async with pool.acquire() as c:
        return await c.fetchrow(
            "SELECT goal, beat_role, tension, intent_slots FROM outline_node WHERE id=$1", node_id)


async def _records(pool, run_id):
    async with pool.acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM intent_slot_record WHERE run_id=$1 ORDER BY position", run_id)
    return [dict(r) for r in rows]


_PARAMS = {"model_source": "user_model", "model_ref": str(uuid.uuid4()), "lang": "en"}


# ── the happy path, proven on the NODE ───────────────────────────────────────────────────────────

async def test_an_accepted_candidate_LANDS_on_the_outline_node(pool):
    """The one thing the whole machine exists to do. Measured 2026-07-28: 0 of 95 chapter nodes
    carried a single intent slot, because nothing had ever written one."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    llm = _FakeLLM([_cands("hook", "midpoint")])
    svc = _svc(pool, outline, llm)

    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["beat_role", "goal"]})
    await svc.propose(run["run_id"], actor)
    await svc.answer(run["run_id"], actor, action="accept", value="midpoint")

    row = await _node_row(pool, node.id)
    assert row["beat_role"] == "midpoint"
    assert json.loads(row["intent_slots"]) == {"beat_role": "settled"}


async def test_two_settled_slots_BOTH_survive(pool):
    """`intent_slots` is merged with `||`, never replaced. A whole-map write would drop the first
    slot the moment the second was settled — and the loss would be invisible until a re-plan."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    llm = _FakeLLM([_cands("hook"), _cands("she refuses the summons")])
    svc = _svc(pool, outline, llm)

    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["beat_role", "goal"]})
    rid = run["run_id"]
    await svc.propose(rid, actor)
    await svc.answer(rid, actor, action="accept")
    await svc.propose(rid, actor)
    await svc.answer(rid, actor, action="revise", value="Lâm Uyên refuses the summons")

    row = await _node_row(pool, node.id)
    assert row["beat_role"] == "hook"
    assert row["goal"] == "Lâm Uyên refuses the summons"
    assert json.loads(row["intent_slots"]) == {"beat_role": "settled", "goal": "settled"}
    assert (await _run_row(pool, rid))["status"] == "done"


async def test_DECLINE_writes_absent_it_is_not_a_no_op(pool):
    """`absent` is an AUTHORED STATEMENT — "the story has not decided this". Treating decline as a
    skip is what lets a fill loop re-ask what the story has no answer to, and the model then
    obliges by inventing."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands("she wants the sword")]))
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["goal"]})
    await svc.propose(run["run_id"], actor)
    await svc.answer(run["run_id"], actor, action="decline")

    row = await _node_row(pool, node.id)
    assert row["goal"] == ""
    assert json.loads(row["intent_slots"]) == {"goal": "absent"}
    assert [r["outcome"] for r in await _records(pool, run["run_id"])] == ["absent"]


async def test_a_declined_slot_is_NEVER_re_asked_by_a_later_run(pool):
    """The terminal property of `absent` (spec §6), across runs — not just within one."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands("x"), _cands("y")]))
    r1 = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                            params={**_PARAMS, "slots": ["goal", "conflict"]})
    await svc.propose(r1["run_id"], actor)
    await svc.answer(r1["run_id"], actor, action="decline")
    await svc.cancel(r1["run_id"], actor)

    r2 = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                            params={**_PARAMS, "slots": ["goal", "conflict"]})
    assert json.loads((await _run_row(pool, r2["run_id"]))["slot_plan"]) == ["conflict"]


async def test_a_settled_slot_is_not_re_asked_either(pool):
    """Re-opening a settled slot needs an explicit act (spec §10 Q3 — deliberately unanswerable
    until prose exists). Silently re-asking would spend the author's attention on a decision they
    already made."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands("hook")]))
    r1 = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                            params={**_PARAMS, "slots": ["beat_role", "goal"]})
    await svc.propose(r1["run_id"], actor)
    await svc.answer(r1["run_id"], actor, action="accept")   # advances to `goal`
    await svc.cancel(r1["run_id"], actor)

    r2 = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id, params=_PARAMS)
    assert "beat_role" not in json.loads((await _run_row(pool, r2["run_id"]))["slot_plan"])


# ── the rails ────────────────────────────────────────────────────────────────────────────────────

async def test_a_double_click_on_answer_409s_instead_of_double_applying(pool):
    """The optimistic transition. Two devices, a double-delivered event, or an impatient click must
    not advance the same run twice — the second answer would land on the NEXT slot's column."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands("hook")]))
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["beat_role", "goal"]})
    await svc.propose(run["run_id"], actor)
    await svc.answer(run["run_id"], actor, action="accept", value="hook")

    with pytest.raises(IntentFSMError) as exc:
        await svc.answer(run["run_id"], actor, action="accept", value="climax")
    assert exc.value.status == 409
    assert (await _node_row(pool, node.id))["beat_role"] == "hook", "the second answer applied"


async def test_propose_while_awaiting_an_answer_409s_and_spends_NOTHING(pool):
    """Every author-facing state BLOCKS. A propose that ran here would both spend money and let the
    machine move while the author was still deciding."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    llm = _FakeLLM([_cands("hook"), _cands("SHOULD NOT BE CALLED")])
    svc = _svc(pool, outline, llm)
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["beat_role"]})
    await svc.propose(run["run_id"], actor)
    with pytest.raises(IntentFSMError) as exc:
        await svc.propose(run["run_id"], actor)
    assert exc.value.status == 409
    assert len(llm.calls) == 1


async def test_a_second_live_run_on_the_same_node_409s(pool):
    """Two runs writing the same columns would interleave their answers with no error anywhere."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([]))
    await svc.open_run(owner=actor, book_id=book_id, node_id=node.id, params=_PARAMS)
    with pytest.raises(IntentFSMError) as exc:
        await svc.open_run(owner=actor, book_id=book_id, node_id=node.id, params=_PARAMS)
    assert exc.value.status == 409 and exc.value.code == "ACTIVE_RUN"


async def test_a_cancelled_run_frees_the_node(pool):
    """…and the partial index must let the author start again, or one abandoned run locks the
    chapter out of intent collection forever."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([]))
    r1 = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id, params=_PARAMS)
    await svc.cancel(r1["run_id"], actor)
    r2 = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id, params=_PARAMS)
    assert r2["run_id"] != r1["run_id"]


async def test_a_value_the_column_rejects_422s_and_LEAVES_the_author_being_asked(pool):
    """Rewound, not failed. Leaving the run in `applying` would strand it with no route out — the
    author would have to cancel and lose the run over a typo."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands(3)]))
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["tension"]})
    await svc.propose(run["run_id"], actor)
    with pytest.raises(IntentFSMError) as exc:
        await svc.answer(run["run_id"], actor, action="revise", value=99)
    assert exc.value.status == 422
    assert (await _run_row(pool, run["run_id"]))["status"] == "awaiting_author"
    # …and the author can still answer properly.
    await svc.answer(run["run_id"], actor, action="revise", value=4)
    assert (await _node_row(pool, node.id))["tension"] == 4


async def test_REVISE_with_no_value_422s_instead_of_settling_the_word_None(pool):
    """Found in review, not by a failing test. `_text(None)` stringifies to "None", so the slot
    would be settled to that literal word — a write that looks entirely successful, is marked
    `settled`, and is therefore never re-asked. Declining is what the author meant, and they have a
    route for it."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands("a guess")]))
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["goal"]})
    await svc.propose(run["run_id"], actor)
    with pytest.raises(IntentFSMError) as exc:
        await svc.answer(run["run_id"], actor, action="revise", value=None)
    assert exc.value.status == 422 and exc.value.code == "NO_VALUE"
    row = await _node_row(pool, node.id)
    assert row["goal"] == "" and json.loads(row["intent_slots"]) == {}
    assert (await _run_row(pool, run["run_id"]))["status"] == "awaiting_author"


async def test_an_over_long_value_is_refused_at_the_boundary(pool):
    """`goal` is unbounded TEXT in Postgres but `_Short` (2000) on the model. Writing past it makes
    every later read of the node raise — so the node must be UNCHANGED and still readable here."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands("a guess")]))
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["goal"]})
    await svc.propose(run["run_id"], actor)
    with pytest.raises(IntentFSMError) as exc:
        await svc.answer(run["run_id"], actor, action="revise", value="x" * 2001)
    assert exc.value.status == 422
    assert (await outline.get_node(node.id)).goal == "", "the node must still READ"


# ── the instrument ───────────────────────────────────────────────────────────────────────────────

async def test_a_FAILED_proposal_is_recorded_never_silently_dropped(pool):
    """I-3. A run that omits its failures reports an acceptance rate it did not earn — the same
    shape as the empty-counted-as-degrade bug. The slot is left unasked AND says so."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    llm = _FakeLLM(["not json", "still not json"])
    svc = _svc(pool, outline, llm)
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["goal"]})
    await svc.propose(run["run_id"], actor)

    assert (await _run_row(pool, run["run_id"]))["status"] == "proposal_failed"
    rec = (await _records(pool, run["run_id"]))[0]
    assert rec["outcome"] == "proposal_failed"
    assert (rec["llm_calls"], rec["retried"]) == (2, True)
    assert len(llm.calls) == 2, "the step looped"
    assert (await _node_row(pool, node.id))["goal"] == "", "a failed proposal wrote to the node"


async def test_the_applied_value_is_read_BACK_off_the_node(pool):
    """Metric B asks whether the artifact ends up saying exactly what the author said. Echoing the
    request would make it measure nothing — the one failure it exists to catch is a write that did
    not land as given."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands("a guess")]))
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["goal"]})
    await svc.propose(run["run_id"], actor)
    await svc.answer(run["run_id"], actor, action="revise", value="  her own words  ")

    rec = (await _records(pool, run["run_id"]))[0]
    assert rec["applied_value"] == "her own words" == (await _node_row(pool, node.id))["goal"]
    assert rec["author_value"] == rec["applied_value"], "metric B: exact"


async def test_the_record_keeps_the_class_the_slot_was_ACTUALLY_asked_under(pool):
    """`beat_role` is only `closed` if the book HAS a structure, and the class is resolved from the
    run's FROZEN vocabulary. Re-deriving it at answer time (without the beats) silently downgraded
    it to `blank_open` — and the POC's constraint-vs-fatigue question is read off this column."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands("hook")]))
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["beat_role"]})
    await svc.propose(run["run_id"], actor)
    await svc.answer(run["run_id"], actor, action="accept")
    rec = (await _records(pool, run["run_id"]))[0]
    assert rec["constraint_class"] == "closed"
    assert rec["outcome"] == "applied"


async def test_an_abandoned_proposal_reads_as_OFFERED_not_skipped(pool):
    """The author never answered. Calling that `skipped` would report an abandoned run as one they
    actively passed on — and the acceptance rate is built entirely on that difference."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands("hook", "midpoint")]))
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["beat_role"]})
    await svc.propose(run["run_id"], actor)
    rec = (await _records(pool, run["run_id"]))[0]
    assert rec["outcome"] == "offered"
    assert len(json.loads(rec["candidates"])) == 2, "what it offered must survive abandonment"


async def test_llm_cost_ACCUMULATES_across_a_retried_slot(pool):
    """A slot proposed twice cost twice. Reporting only the last attempt would under-count exactly
    the runs that cost the most."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    llm = _FakeLLM(["junk", "junk", _cands("she wants out")])
    svc = _svc(pool, outline, llm)
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["goal"]})
    await svc.propose(run["run_id"], actor)                 # 2 calls → proposal_failed
    await svc.propose(run["run_id"], actor)                 # 1 more  → awaiting_author
    rec = (await _records(pool, run["run_id"]))[0]
    assert rec["llm_calls"] == 3
    assert rec["outcome"] == "offered"


async def test_the_position_recorded_is_the_slots_place_in_THIS_run(pool):
    """Q1 plots acceptance against position, so the number has to mean the run's order — not the
    registry's."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands(4), _cands("hook")]))
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "arm": "reversed", "slots": ["beat_role", "tension"]})
    rid = run["run_id"]
    await svc.propose(rid, actor)
    await svc.answer(rid, actor, action="accept")
    await svc.propose(rid, actor)
    await svc.answer(rid, actor, action="accept")
    recs = await _records(pool, rid)
    assert [(r["slot"], r["position"], r["arm"]) for r in recs] == [
        ("tension", 1, "reversed"), ("beat_role", 2, "reversed")]


# ── failure handling ─────────────────────────────────────────────────────────────────────────────

async def test_a_TRANSPORT_failure_is_not_reported_as_a_bad_model(pool):
    """`proposal_failed` means "the model answered and the answer was unusable" — a fact about the
    MODEL. Conflating a provider outage with it would make the POC's failure rate measure the
    network, and the response would be to change models over a broken socket."""
    from loreweave_llm.errors import LLMError

    class _Dead:
        async def submit_and_wait(self, **kw):
            raise LLMError("connection refused")

    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _Dead())
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["goal"]})
    with pytest.raises(IntentFSMError) as exc:
        await svc.propose(run["run_id"], actor)
    assert exc.value.status == 502
    row = await _run_row(pool, run["run_id"])
    assert row["status"] == "opened", "a dead provider must leave the run retryable"
    assert await _records(pool, run["run_id"]) == [], "a transport failure is not a slot outcome"


async def test_skip_moves_past_a_failed_proposal_and_the_slot_stays_unasked(pool):
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM(["junk", "junk"]))
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["goal", "conflict"]})
    rid = run["run_id"]
    await svc.propose(rid, actor)
    await svc.skip(rid, actor)
    row = await _run_row(pool, rid)
    assert (row["status"], row["slot_cursor"]) == ("advanced", "conflict")
    assert json.loads((await _node_row(pool, node.id))["intent_slots"]) == {}


async def test_a_stranded_run_resumes_WITHOUT_skipping_the_author(pool):
    """A restart mid-`applying` must rewind to `awaiting_author`, not advance: the write may or may
    not have landed, and re-applying the same value is idempotent while advancing past it would
    drop the slot in silence."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    repo = IntentRepo(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands("hook")]))
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["beat_role"]})
    rid = run["run_id"]
    await svc.propose(rid, actor)
    await repo.transition(rid, actor, ["awaiting_author"], "applying")   # simulate the crash

    await svc.resume(rid, actor)
    assert (await _run_row(pool, rid))["status"] == "awaiting_author"
    await svc.answer(rid, actor, action="accept")
    assert (await _node_row(pool, node.id))["beat_role"] == "hook"


async def test_resume_refuses_a_run_that_is_not_stranded(pool):
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands("hook")]))
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["beat_role"]})
    await svc.propose(run["run_id"], actor)
    with pytest.raises(IntentFSMError) as exc:
        await svc.resume(run["run_id"], actor)
    assert exc.value.status == 409 and exc.value.code == "NOT_STRANDED"


# ── scope + tenancy ──────────────────────────────────────────────────────────────────────────────

async def test_another_user_cannot_see_or_drive_the_run(pool):
    """Owner-scoped at the repo, so a non-owner 404s rather than 403ing — the route is not an
    existence oracle."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands("hook")]))
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id, params=_PARAMS)
    other = uuid.uuid4()
    for call in (svc.get(run["run_id"], other), svc.propose(run["run_id"], other)):
        with pytest.raises(IntentFSMError) as exc:
            await call
        assert exc.value.status in (404, 409)


async def test_a_run_is_refused_on_a_node_that_cannot_hold_intent(pool):
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([]))
    with pytest.raises(IntentFSMError) as exc:
        await svc.open_run(owner=actor, book_id=book_id, node_id=uuid.uuid4(), params=_PARAMS)
    assert exc.value.status == 404


async def test_a_node_with_nothing_left_to_ask_409s_rather_than_opening_an_empty_run(pool):
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands("hook")]))
    r1 = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                            params={**_PARAMS, "slots": ["beat_role"]})
    await svc.propose(r1["run_id"], actor)
    await svc.answer(r1["run_id"], actor, action="accept")   # only slot → done

    with pytest.raises(IntentFSMError) as exc:
        await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                           params={**_PARAMS, "slots": ["beat_role"]})
    assert exc.value.status == 409 and exc.value.code == "NOTHING_TO_ASK"


async def test_the_author_scores_the_candidates_and_it_persists(pool):
    """Metric A. No route accepts a model-produced verdict — the thing being measured is authorial
    taste, so a model grading it would be the thing under test grading itself."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    svc = _svc(pool, outline, _FakeLLM([_cands("hook", "midpoint")]))
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["beat_role"]})
    await svc.propose(run["run_id"], actor)
    await svc.score(run["run_id"], actor, slot="beat_role",
                    verdicts=[{"index": 0, "verdict": "accept"},
                              {"index": 1, "verdict": "discard"}])
    rec = (await _records(pool, run["run_id"]))[0]
    assert [v["verdict"] for v in json.loads(rec["verdicts"])] == ["accept", "discard"]

    with pytest.raises(IntentFSMError) as exc:
        await svc.score(run["run_id"], actor, slot="beat_role",
                        verdicts=[{"index": 0, "verdict": "brilliant"}])
    assert exc.value.status == 422


async def test_the_prompt_never_presents_a_PLANNER_value_as_settled_author_intent(pool):
    """A column holding the planner's guess is a SUGGESTION. Rendering it as "already settled by the
    author — do not contradict" would launder a machine guess into a constraint the next answer must
    obey, and the author would never see it happen."""
    actor, book_id, project_id, node, outline = await _seed(pool)
    async with pool.acquire() as c:
        await c.execute("UPDATE outline_node SET goal=$2 WHERE id=$1",
                        node.id, "a value the PLANNER wrote")
    llm = _FakeLLM([_cands("her real want")])
    svc = _svc(pool, outline, llm)
    run = await svc.open_run(owner=actor, book_id=book_id, node_id=node.id,
                             params={**_PARAMS, "slots": ["conflict"]})
    await svc.propose(run["run_id"], actor)
    sent = llm.calls[0]["input"]["messages"][-1]["content"]
    assert "a value the PLANNER wrote" not in sent
