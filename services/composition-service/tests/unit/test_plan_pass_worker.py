"""27 V2-C2 — the `plan_pass` worker op, its dispatch, and its finalize hook.

The registry (C1) and the adapters (C5) are each covered. This file covers the WIRING between them
and the job system, which is where the interesting failures live: an op the dispatch doesn't know, a
gate that redelivers forever, a pointer recorded before the artifact it points at exists.
"""

from __future__ import annotations

import inspect

import pytest

from app.services.plan_pass_service import PASS_REGISTRY, UpstreamStale, default_decision
from app.worker import job_consumer
from app.worker.constants import SUPPORTED_OPERATIONS

CONSUMER_SRC = inspect.getsource(job_consumer)


def test_plan_pass_is_a_supported_operation():
    """A worker op the dispatch doesn't recognize raises `UnsupportedOperationError` — so the job
    fails instantly and the user's pass silently never runs."""
    assert "plan_pass" in SUPPORTED_OPERATIONS


def test_ONE_op_runs_ALL_seven_passes():
    """Seven ops would have meant seven dispatch branches drifting apart from one registry. The pass
    is data (`input['pass_id']`), not a new code path."""
    assert CONSUMER_SRC.count('if op == "plan_pass"') == 1
    for pid in PASS_REGISTRY:
        assert f'op == "{pid}"' not in CONSUMER_SRC


def test_UpstreamStale_is_a_BUSINESS_error_so_a_blocked_pass_ACKS():
    """THE bug this test exists for: `UpstreamStale` subclasses `Exception`, not `ValueError`.

    Left out of `_BUSINESS_ERRORS` it propagates as an INFRA error — the AMQP message is un-ACKed
    and the broker redelivers a pass that is *correctly refusing to run*. Forever. "Your upstream is
    stale" is the most ordinary condition in the compiler: it is the PF-5 gate doing its job, and it
    must fail the job cleanly and ACK.
    """
    assert UpstreamStale in job_consumer._BUSINESS_ERRORS
    # and it really isn't caught incidentally by one of the others
    assert not issubclass(UpstreamStale, (ValueError, KeyError))


def test_the_finalize_hook_saves_the_ARTIFACT_before_recording_the_POINTER():
    """Ordering is the whole correctness argument.

    artifact-then-pointer: a crash between the two leaves an orphan artifact nothing references. The
    pass reads as "not done", a re-run redoes it, and we lose tokens — not correctness.

    pointer-then-artifact: `pass_state` names an artifact that does not exist. Every downstream pass
    resolves its input to nothing while the ledger insists the pass completed. That is the
    `surrogate-partition-write-strands` shape — a dangling pointer that reads as success.
    """
    src = inspect.getsource(job_consumer._finalize_plan_pass_job)
    save_at = src.index("save_artifact(")
    record_at = src.index("record_pass(\n        run, pass_id, status=\"completed\"")
    assert save_at < record_at, "the artifact must exist before anything points at it"


def test_a_FAILED_pass_records_the_failure_and_does_NOT_wipe_the_last_good_pointer():
    """`record_pass` leaves untouched fields alone. A failed re-run must not clear the artifact
    pointer a previous SUCCESS recorded — the last good artifact stays resolvable, and freshness
    (derived, never stored) reports the truth on its own."""
    src = inspect.getsource(job_consumer._finalize_plan_pass_job)
    fail_branch = src[src.index('if terminal_status != "completed":'):src.index("artifact = await")]
    assert 'status="failed"' in fail_branch
    assert "artifact_id" not in fail_branch  # not passed ⇒ not touched ⇒ not wiped


def test_a_BLOCKING_pass_lands_PENDING_and_an_advisory_one_lands_AUTO():
    """PF-6. The compiler stops at exactly the two questions only the author can answer: who the
    characters ARE (`cast`) and what SHAPE the story takes (`beats`)."""
    assert default_decision("cast") == "pending"
    assert default_decision("beats") == "pending"
    for pid, spec in PASS_REGISTRY.items():
        expected = "pending" if spec.checkpoint == "blocking" else "auto"
        assert default_decision(pid) == expected, pid
    # …and the hook actually uses it, rather than hardcoding one of the two
    src = inspect.getsource(job_consumer._finalize_plan_pass_job)
    assert "decision=default_decision(pass_id)" in src


def test_the_finalize_hook_only_fires_for_plan_pass_jobs():
    """It runs on EVERY job's terminal path. A missing op check would make it try to read a
    `pass_id` off a `generate` job and write garbage into some other run's ledger."""
    src = inspect.getsource(job_consumer._finalize_plan_pass_job)
    assert 'if _worker_op(job) != "plan_pass":' in src
    assert "return" in src.split('if _worker_op(job) != "plan_pass":')[1][:40]


@pytest.mark.parametrize("terminal", ["completed", "failed"])
def test_both_terminal_paths_call_the_finalize_hook(terminal):
    """A pass that fails must still be RECORDED as failed. If only the success path finalized, a
    failed pass would sit in `pass_state` looking like it had never been attempted — and the run
    would report a cursor it has not actually reached."""
    run_src = inspect.getsource(job_consumer.run_job)
    assert run_src.count("_finalize_plan_pass_job(") == 2
    assert '_finalize_plan_pass_job(pool, job, {"error": str(exc)}, "failed")' in run_src
    assert '_finalize_plan_pass_job(pool, job, result, "completed")' in run_src


# ── the input resolver ───────────────────────────────────────────────────────────────────────────

def test_inputs_resolve_BY_POINTER_and_are_keyed_by_PASS_not_by_KIND():
    """PF-3. Pass 7 re-emits `scene_plan`, so KIND is not a unique key — a latest-by-kind read would
    hand pass 7 its own output as its input and it would stale itself against itself, forever."""
    from app.worker.operations import run_plan_pass

    src = inspect.getsource(run_plan_pass)
    assert "artifacts_by_ids(" in src
    # There is exactly ONE by-kind read, and it is the PACKAGE — which is not a pass at all.
    assert "latest_artifact(book_id, run_id, PACKAGE_KIND)" in src
    assert src.count("latest_artifact(") == 1
    assert "for dep in spec.depends_on:" in src


def test_an_UNRESOLVABLE_input_pointer_RAISES_rather_than_running_the_pass_on_nothing():
    """Absent ≠ empty. A pointer that names a missing (or another book's) artifact means we cannot
    build this pass's inputs — running anyway would produce a plan that looks complete and is built
    on nothing."""
    from app.worker.operations import run_plan_pass

    src = inspect.getsource(run_plan_pass)
    assert "missing.append(dep)" in src
    assert "cannot resolve its input artifact(s)" in src


def test_the_fingerprint_is_over_the_SAME_pointers_that_were_resolved():
    """If we resolved inputs one way and fingerprinted another, the fingerprint we record could never
    equal the one a later freshness check recomputes — and every pass would read as permanently
    stale, blocking everything downstream of it."""
    from app.worker.operations import run_plan_pass

    src = inspect.getsource(run_plan_pass)
    assert "pointers = input_pointers(" in src
    assert "loaded = await runs.artifacts_by_ids(book_id, run_id, pointers)" in src
    assert "fp = fingerprint(input_artifact_ids=pointers, params=params)" in src


def test_the_package_is_required_when_the_pass_reads_it():
    """`motifs`/`cast` have no pass dependencies. Without the package in their input set their
    fingerprint would be a constant — fresh forever, including after a re-compile against a
    different arc left them pointing at a plan that no longer exists."""
    from app.worker.operations import run_plan_pass

    src = inspect.getsource(run_plan_pass)
    # NOTE the shape: the package is loaded UNCONDITIONALLY (see the test below — the gate has to
    # recompute the upstreams' fingerprints, and they may read it); it is only an ERROR when a pass
    # that genuinely reads it has none.
    assert "if spec.reads_package and package_art is None:" in src
    assert "compile first" in src


# ── the package artifact: kind + nesting ─────────────────────────────────────────────────────────

def test_the_package_kind_is_a_MEMBER_of_the_closed_set():
    """I first wrote `"planning_package"` — which is not a member of `PlanArtifactKind` at all. The
    lookup could never match, so every package-reading pass was unrunnable behind a message that
    blamed the USER ("compile first") for something they had already done.

    The type is a `Literal`, but at runtime it is just a string, and no unit test ran the worker
    against a real row — so only the LIVE SMOKE could see it. Second closed-set drift of this run
    (DR-06 was the first). This test is the gate that makes a third impossible."""
    from typing import get_args

    from app.db.models import PlanArtifactKind
    from app.services.plan_pass_service import PACKAGE_KIND

    assert PACKAGE_KIND in get_args(PlanArtifactKind)
    assert PACKAGE_KIND == "package"


def test_the_package_is_read_out_of_its_WRAPPER_not_used_as_the_wrapper():
    """`compile()` saves `{"planning_package": {...}, <other compiled keys>}` under kind `package`.
    So the artifact's content is NOT the package — the package is one key INSIDE it.

    An adapter handed the wrapper reads every field as absent, and then, being degrade-safe, plans a
    book with no premise, no arc and no chapters — and reports that as a perfectly successful empty
    plan. A silent success is a bug, not a no-op."""
    from app.services.plan_pass_service import package_body

    assert package_body({"planning_package": {"premise": "p"}, "spec": {}}) == {"premise": "p"}
    assert package_body({"premise": "p"}) == {}       # the wrapper is required, not optional
    assert package_body({}) == {}
    assert package_body({"planning_package": None}) == {}


def test_the_pass_runner_reads_the_package_through_the_ONE_constant_and_the_ONE_reader():
    """One name, one home. A second literal here is how the first bug happened."""
    from app.worker import operations

    src = inspect.getsource(operations.run_plan_pass)
    assert "latest_artifact(book_id, run_id, PACKAGE_KIND)" in src
    assert "package_body(package_art.content)" in src
    assert '"planning_package"' not in src


def test_the_worker_ALWAYS_loads_the_package_even_for_a_pass_that_does_not_read_it():
    """THE bug the full seven-pass live smoke found — and nothing else could have.

    `character_arcs` has `reads_package=False`, so the worker skipped loading the package. But it
    DEPENDS on `cast` and `beats`, which both DO read it. The PF-5 gate then recomputed those
    upstreams' fingerprints with `package_artifact_id=None`, so they could not possibly match what
    they had recorded, and they read as STALE.

    Result: the SERVICE said the pass was runnable (HTTP 200, job enqueued) and the WORKER then
    refused it — "upstream ['cast', 'beats'] is stale or not accepted" — about two passes the ledger
    showed as fresh and accepted. Two components answering the same question with different inputs.

    The package is a property of the RUN, not of the pass being run.
    """
    from app.worker.operations import run_plan_pass

    src = inspect.getsource(run_plan_pass)
    load = src.index("package_art = await runs.latest_artifact(book_id, run_id, PACKAGE_KIND)")
    gate = src.index("assert_runnable(")
    assert load < gate, "the package must be loaded BEFORE the gate that recomputes upstreams"
    # …unconditionally: not nested under `if spec.reads_package`
    assert "if spec.reads_package:\n        package_art = await" not in src
    # …and it is still an ERROR when a pass that DOES read it has none
    assert "if spec.reads_package and package_art is None:" in src


def test_input_pointers_still_omits_the_package_for_a_pass_that_does_not_read_it():
    """The other half. Always LOADING the package must not mean always FINGERPRINTING it — a pass
    that does not read the package must not go stale when the package changes."""
    from uuid import uuid4

    from app.db.models import PlanRun
    from app.services.plan_pass_service import input_pointers

    run = PlanRun(
        id=uuid4(), created_by=uuid4(), book_id=uuid4(), status="compiled", mode="rules",
        pass_state={
            "cast": {"status": "completed", "artifact_id": str(uuid4())},
            "beats": {"status": "completed", "artifact_id": str(uuid4())},
        },
    )
    pkg = uuid4()
    # character_arcs reads_package=False ⇒ only its two deps
    assert len(input_pointers(run, "character_arcs", package_artifact_id=pkg)) == 2
    assert str(pkg) not in input_pointers(run, "character_arcs", package_artifact_id=pkg)
    # cast reads_package=True ⇒ the package IS its only input
    assert input_pointers(run, "cast", package_artifact_id=pkg) == [str(pkg)]


# ── the roster join (PF-8b / H3) ─────────────────────────────────────────────────────────────────

def test_the_CAST_IS_JOINED_TO_ITS_GLOSSARY_IDS_before_any_pass_reads_it():
    """The `cast` artifact holds NAMES. The glossary `entity_id`s do not exist until the human has
    applied the seed proposal (PF-7). So somebody has to join them, and it has to happen before pass
    6 runs.

    Without it, `grounded_decompose`'s `cast_index` — which keys on `entity_id` — is EMPTY, every
    scene comes back with `present_entity_ids: []`, and the linker writes scene nodes with no cast
    on them. The 7-pass live smoke showed exactly that (`present=0` on every scene) while the plan
    looked complete in every other respect: the characters were in the glossary, the roster was bound
    to the arc, and the scenes simply had nobody in them."""
    from app.worker.operations import run_plan_pass

    src = inspect.getsource(run_plan_pass)
    join = src.index("_resolve_cast_entity_ids(")
    adapter = src.index("PASS_ADAPTERS[pass_id](ctx)")
    assert join < adapter, "the cast must be resolved BEFORE the adapter reads it"


def test_an_UNRESOLVABLE_cast_member_keeps_its_name_and_gets_NO_invented_id():
    """Degrade-safe and honest. A member we cannot resolve is absent from `cast_index`, so pass 6
    falls back to `present_entity_names_unresolved` — the field that exists precisely to say "this
    character is in the scene and I cannot tell you which glossary entity they are".

    Inventing an id would be worse: the scene would point at an entity that is not that person."""
    from app.worker.operations import _resolve_cast_entity_ids

    src = inspect.getsource(_resolve_cast_entity_ids)
    assert "out.append(dict(m))" in src            # kept, un-enriched
    assert "present_entity_names_unresolved" in src  # …and the reason why is written down


def test_the_join_reads_the_APPLIED_proposal_not_glossary_directly():
    """INV-KAL. The apply step is what MINTED the ids and recorded them; composition reads the cast
    through the roster, never glossary."""
    from app.worker.operations import _resolve_cast_entity_ids

    src = inspect.getsource(_resolve_cast_entity_ids)
    assert "applied_results" in src
    assert 'proposal.status != "applied"' in src


def test_the_worker_ASSEMBLES_the_known_cast_and_puts_it_ON_the_context():
    """E6, outermost link. Mutation-checked: deleting `known_cast=known_cast` from the PassContext
    construction left the entire suite green — the adapter tests build their own context, so
    nothing watched the one place the real value is supplied. This file already inspects source for
    exactly that reason (the op's dependencies make a live call impractical), so it does here too."""
    from app.worker.operations import run_plan_pass

    src = inspect.getsource(run_plan_pass)
    assert "known = await _known_entities(pool, book_id)" in src
    assert "known_cast = _cast_of_known(known)" in src
    assert "known_cast=known_cast" in src


def test_the_worker_ASSEMBLES_the_known_world_and_puts_it_ON_the_context():
    """E6b, outermost link — and it needs its own assertion, not a shared one with the cast: the
    two slices come off the same read, so a forward that carries only `known_cast=` looks entirely
    healthy from the cast's side while pass 3 stays blind."""
    from app.worker.operations import run_plan_pass

    src = inspect.getsource(run_plan_pass)
    assert "known_world = _world_of_known(known)" in src
    assert "known_world=known_world" in src


def test_the_seed_proposals_are_read_ONCE_for_both_slices():
    """Two loaders would mean two queries over the same rows and two kind-filters free to drift
    apart — which is how the cast pass and the world pass would end up disagreeing about what is
    already in the book."""
    from app.worker.operations import run_plan_pass

    src = inspect.getsource(run_plan_pass)
    assert src.count("_known_entities(") == 1


@pytest.mark.asyncio
async def test_known_cast_counts_only_APPLIED_proposals_and_only_CHARACTERS(monkeypatch):
    """A pending proposal is a request, not a fact: feeding one back as "already exists" would
    teach the planner to skip introducing someone who is not in the book. And a seeded location
    listed under EXISTING CAST would invite the model to write it as a person."""
    from types import SimpleNamespace

    from uuid import uuid4

    import app.db.repositories.plan_bootstrap_proposals as mod
    from app.worker.operations import _cast_of_known, _known_entities, _world_of_known

    proposals = [
        SimpleNamespace(status="applied", applied_results={
            "a": {"name": "Lâm Uyển", "entity_id": "e1", "kind_code": "character"},
            "b": {"name": "Hoa Sơn", "entity_id": "e2", "kind_code": "location"},
            "c": {"name": "lâm uyển", "entity_id": "e3", "kind_code": "character"},  # dup, folded
        }),
        SimpleNamespace(status="pending", applied_results={
            "d": {"name": "Not Yet Real", "entity_id": "e4", "kind_code": "character"},
        }),
    ]

    class _Repo:
        def __init__(self, pool): pass
        async def list_active_for_book(self, book_id): return proposals

    monkeypatch.setattr(mod, "PlanBootstrapProposalsRepo", _Repo)
    known = await _known_entities(None, uuid4())
    assert _cast_of_known(known) == ["Lâm Uyển"]
    # E6b — the same read now keeps the rows the cast slice drops, instead of discarding them.
    assert _world_of_known(known) == {"location": ["Hoa Sơn"]}


@pytest.mark.asyncio
async def test_a_row_with_no_kind_stays_on_the_CAST_side(monkeypatch):
    """E6b preserved E6's behaviour deliberately: an unkinded seed row counted as cast before, and
    quietly moving it to the world side would change which pass sees it — a silent re-routing is
    exactly the class of change that should never ride along with a refactor."""
    from types import SimpleNamespace
    from uuid import uuid4

    import app.db.repositories.plan_bootstrap_proposals as mod
    from app.worker.operations import _cast_of_known, _known_entities, _world_of_known

    class _Repo:
        def __init__(self, pool): pass
        async def list_active_for_book(self, book_id):
            return [SimpleNamespace(status="applied", applied_results={
                "a": {"name": "Unkinded", "entity_id": "e1"},
            })]

    monkeypatch.setattr(mod, "PlanBootstrapProposalsRepo", _Repo)
    known = await _known_entities(None, uuid4())
    assert _cast_of_known(known) == ["Unkinded"]
    assert _world_of_known(known) == {}


@pytest.mark.asyncio
async def test_the_world_slice_carries_only_kinds_pass_3_MAY_PROPOSE(monkeypatch):
    """WORLD_KINDS is a closed set. A seeded `item` or `event` listed under EXISTING WORLD would
    be an instruction the model cannot obey — it is forbidden to return those kinds."""
    from types import SimpleNamespace
    from uuid import uuid4

    import app.db.repositories.plan_bootstrap_proposals as mod
    from app.engine.world_plan import WORLD_KINDS
    from app.worker.operations import _known_entities, _world_of_known

    class _Repo:
        def __init__(self, pool): pass
        async def list_active_for_book(self, book_id):
            return [SimpleNamespace(status="applied", applied_results={
                "a": {"name": "Hoa Sơn", "kind_code": "location"},
                "b": {"name": "Thanh Vân Môn", "kind_code": "faction"},
                "c": {"name": "Kiếm Đạo", "kind_code": "concept"},
                "d": {"name": "Huyền Thiết Kiếm", "kind_code": "item"},
                "e": {"name": "Lâm Uyển", "kind_code": "character"},
            })]

    monkeypatch.setattr(mod, "PlanBootstrapProposalsRepo", _Repo)
    world = _world_of_known(await _known_entities(None, uuid4()))
    assert set(world) == set(WORLD_KINDS)
    assert world["location"] == ["Hoa Sơn"]
    assert "Huyền Thiết Kiếm" not in str(world) and "Lâm Uyển" not in str(world)


@pytest.mark.asyncio
async def test_known_cast_DEGRADES_to_empty_rather_than_failing_the_plan(monkeypatch):
    """Advisory context. A read failure must not kill a planning run — the pass then behaves
    exactly as it did before E6, which is a worse plan, not a broken one."""
    from uuid import uuid4

    import app.db.repositories.plan_bootstrap_proposals as mod
    from app.worker.operations import _cast_of_known, _known_entities, _world_of_known

    class _Boom:
        def __init__(self, pool): pass
        async def list_active_for_book(self, book_id): raise RuntimeError("db down")

    monkeypatch.setattr(mod, "PlanBootstrapProposalsRepo", _Boom)
    known = await _known_entities(None, uuid4())
    assert known == {}
    # Both slices degrade, and each to the shape its consumer expects (a list / a dict) — a
    # `None` leaking into either would crash the pass it was meant to protect.
    assert _cast_of_known(known) == []
    assert _world_of_known(known) == {}
