"""DQ-T45 — a Tier-R read must not be able to authorise a cost-bearing run.

THE DEFECT. `plan_validate` is declared `require_meta("R", "book", ...)` — a read. It lints a
plan against the golden rules and returns a verdict. It ALSO used to write
`update_run(status="validated")` when every hard rule passed, and `validated` is one of the two
statuses the authoring start-gate accepts as approval:

    authoring_run_service._APPROVED_PLAN_STATUSES = ("validated", "compiled")

so a passing lint put the plan into the state that authorises a drafting run that spends money.
Nothing human had to happen in between.

🔴 THE GATE WAS NEVER THE THING THAT WAS WRONG, AND THIS FILE EXISTS TO KEEP IT THAT WAY.
`validated` has a SECOND writer — `review_checkpoint(approved=True)`, a person approving the
plan — and the gate's own comment names only that one ("`validated` is what
review_checkpoint(approved=True) stamps"). Narrowing the gate to `compiled`, which is how this
defect was first framed, would have de-authorised every plan a human actually approved in order
to close a hole one line inside the linter. Measured before the change: of the 37 live plan runs
at `validated`, only 3 carry a `validation_report` artifact at all, and `validate()` saves that
artifact BEFORE it ever stamped the status — so 34 of 37 provably came from the human path.

THE INVARIANT: the linter records its verdict and advances nothing. The human approval path and
the start-gate are untouched, and this file asserts all three together, because a fix that
closed the hole by breaking approval would pass a test that only looked at the hole.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.services.plan_forge_service import PlanForgeService

OWNER = uuid4()
BOOK = uuid4()
RUN = uuid4()

#: A spec shaped to PASS every HARD rule, so the branch under test is the one that used to
#: advance the run. A spec that fails proves nothing here — the old code only stamped on pass.
#:
#: The hard tier is small and deliberately general: `spec_has_arc` and `spec_has_events` (plus
#: `notes_linked`, which passes vacuously with no arc_2 planner notes, and `premise_max`, which
#: only appears when a package artifact exists). Everything else in `run_rules` is advisory and
#: `_hard_rules_pass` filters it out. My first fixture was a plausible-looking spec of `title`
#: and `sections` and it failed both hard rules — caught by this file's own assertion rather
#: than passing silently as a test of the wrong branch.
PASSING_SPEC: dict[str, Any] = {
    "title": "The Ember Codex",
    "logline": "A scribe outruns her own footnotes.",
    "arcs": [{"id": "arc_1", "arc_kind": "descent", "theme": "the ledger burns"}],
    "events": [{"id": "arc_1_e1", "arc_id": "arc_1", "synopsis": "Wen burns the ledger."}],
    "links": [],
}


class _Artifact:
    def __init__(self, content: dict[str, Any]) -> None:
        self.id = uuid4()
        self.content = content


class _Run:
    def __init__(self, status: str = "proposed") -> None:
        self.id = RUN
        self.book_id = BOOK
        self.created_by = OWNER
        self.status = status
        self.mode = "rules"


class FakePlanRunsRepo:
    """Records what `validate()` does rather than what it says it does. `update_run` is the
    whole point: if it is ever called from the lint path this defect is back."""

    def __init__(self, spec: dict[str, Any] | None = None, status: str = "proposed") -> None:
        self.run = _Run(status)
        self.spec = spec if spec is not None else PASSING_SPEC
        self.saved: list[tuple[str, dict[str, Any]]] = []
        self.status_writes: list[dict[str, Any]] = []

    async def get_for_book(self, book_id, run_id):
        return self.run

    async def latest_artifact(self, book_id, run_id, kind):
        if kind == "spec":
            return _Artifact(self.spec)
        if kind == "validation_report":
            # `_run_fidelity_config` reads this; {} means "no per-run rubric", the normal case.
            return None
        return None

    async def save_artifact(self, created_by, run_id, kind, content):
        self.saved.append((kind, content))
        return _Artifact(content)

    async def update_run(self, book_id, run_id, **kw):
        self.status_writes.append(kw)
        if "status" in kw:
            self.run.status = kw["status"]
        return self.run


def _svc(repo: FakePlanRunsRepo) -> PlanForgeService:
    return PlanForgeService(repo, jobs=None, works=None, llm=None)


# ── the hole ───────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_passing_lint_does_not_advance_the_run():
    """🔴 THE ORIGINAL INSTANCE. Before the fix this run came out of `validate()` at
    `validated` — a status the start-gate accepts — with no human in the loop."""
    repo = FakePlanRunsRepo()
    report = await _svc(repo).validate(OWNER, BOOK, RUN)

    assert report["passed"] is True, (
        "the fixture no longer passes the hard rules, so this test is exercising the FAILING "
        "branch and proves nothing — repair PASSING_SPEC, do not relax the assertion"
    )
    assert repo.status_writes == [], (
        f"the linter advanced the run: {repo.status_writes}"
    )
    assert repo.run.status == "proposed"


@pytest.mark.asyncio
async def test_the_linter_never_produces_a_gate_approved_status():
    """Stated as the invariant rather than as one status, so a future edit that advances the
    run to `compiled` instead is caught by the same guard."""
    from app.services.authoring_run_service import _APPROVED_PLAN_STATUSES

    repo = FakePlanRunsRepo()
    await _svc(repo).validate(OWNER, BOOK, RUN)
    assert repo.run.status not in _APPROVED_PLAN_STATUSES


# ── the verdict is RECORDED, not lost ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_verdict_is_still_persisted_and_still_returned():
    """The decision was 'validate RECORDS, it does not authorise' — not 'validate goes quiet'.
    A fix that dropped the verdict would satisfy the test above and destroy the tool."""
    repo = FakePlanRunsRepo()
    report = await _svc(repo).validate(OWNER, BOOK, RUN)

    kinds = [k for k, _ in repo.saved]
    assert "validation_report" in kinds, "the linter stopped persisting its own report"
    persisted = next(c for k, c in repo.saved if k == "validation_report")
    assert persisted["passed"] is True
    assert persisted["rules"], "the per-rule detail is what an author acts on"
    assert report["fidelity_report_id"] is not None, (
        "the caller can no longer find the persisted report"
    )


@pytest.mark.asyncio
async def test_a_failing_lint_is_still_reported_as_failing():
    """The control that could refute the change: if `validate` now returned `passed: True`
    unconditionally, every test above would still be green."""
    repo = FakePlanRunsRepo(spec={"title": "", "sections": []})
    report = await _svc(repo).validate(OWNER, BOOK, RUN)
    assert report["passed"] is False
    assert repo.status_writes == []


# ── what must NOT have changed ─────────────────────────────────────────────────────────────

def test_the_human_approval_path_still_stamps_validated():
    """`review_checkpoint(approved=True)` is the OTHER writer of `validated`, and it is a
    person approving a plan. If this goes red the fix moved the hole instead of closing it."""
    import inspect

    from app.services import plan_forge_service as mod

    src = inspect.getsource(mod.PlanForgeService.review_checkpoint)
    assert 'status="validated" if approved else "checkpoint"' in src, (
        "the human approval path no longer stamps `validated` — DQ-T45 closed the linter's "
        "hole, it did not touch how a person approves a plan"
    )


def test_the_start_gate_still_accepts_a_human_approved_plan():
    """🔴 THE 34 RUNS. This is the assertion that says no existing plan was de-authorised.
    Narrowing this tuple to `("compiled",)` was the first-drafted fix and is the wrong one."""
    from app.services.authoring_run_service import _APPROVED_PLAN_STATUSES

    assert "validated" in _APPROVED_PLAN_STATUSES, (
        "the start-gate no longer accepts `validated`, which is the status "
        "review_checkpoint(approved=True) stamps — every plan a human approved is now blocked"
    )
    assert "compiled" in _APPROVED_PLAN_STATUSES


def test_plan_validate_is_still_declared_a_read():
    """The declaration is half the invariant: the tool says Tier R, and this run proves the
    code now agrees with it. If someone re-tiers the tool to W the defect is 'fixed' by
    relabelling, which is not a fix."""
    import inspect

    from app.mcp import server as mod

    src = inspect.getsource(mod)
    idx = src.index('name="plan_validate"')
    window = src[idx: idx + 700]
    assert 'require_meta("R"' in window, (
        "plan_validate is no longer declared Tier R — the point of DQ-T45 was to make the "
        "CODE match that declaration, not to change the declaration to match the code"
    )
