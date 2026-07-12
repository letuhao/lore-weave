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
    assert "if spec.reads_package:" in src
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
