"""S5 — the stage protocol's declarations are checked AGAINST THE CODE, both directions.

A declaration nobody checks is a comment with a dataclass around it. These tests are what make
`StagePlan` a protocol rather than documentation.
"""
from __future__ import annotations

import ast
import io
import pathlib
import re
import tokenize

import pytest

from app.engine.heal_protocol import PLANS, STAGE_PRIMITIVES, HealStage, StagePlan

_ENGINE = pathlib.Path(__file__).resolve().parents[2] / "app" / "engine"


def _code_only(src: str) -> str:
    """`src` with docstrings and comments blanked.

    Load-bearing, and measured: `error_block_heal` names `_snap_to_sentence` in its docstring —
    inside the sentence explaining why it does NOT call it. A text scan therefore reports SNAP
    as RUN and this module's declaration as a lie. The check would be defeated by the very
    documentation that makes that module the exemplar.
    """
    blank: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                blank.add(tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    try:
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, (ast.Module, ast.FunctionDef,
                                     ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                blank.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    except (SyntaxError, ValueError):
        pass
    return "\n".join("" if i in blank else ln for i, ln in enumerate(src.splitlines(), 1))


def _runs_stage(module: str, stage: HealStage) -> bool:
    src = _code_only((_ENGINE / f"{module}.py").read_text(encoding="utf-8", errors="ignore"))
    return any(re.search(rf"\b{re.escape(p)}\b", src) for p in STAGE_PRIMITIVES[stage])


@pytest.mark.parametrize("plan", PLANS, ids=lambda p: p.module)
def test_every_stage_is_accounted_for(plan: StagePlan):
    """Run it or give a reason — total coverage. Before this, `plan_heal` skipped six stages in
    silence, which is indistinguishable from six nobody noticed."""
    missing = sorted(set(HealStage) - set(plan.runs) - set(plan.skipped))
    assert plan.accounts_for_every_stage(), f"{plan.module} accounts for neither: {missing}"


@pytest.mark.parametrize("plan", PLANS, ids=lambda p: p.module)
def test_no_stage_is_both_run_and_skipped(plan: StagePlan):
    overlap = sorted(set(plan.runs) & set(plan.skipped))
    assert overlap == [], f"{plan.module} declares {overlap} both run and skipped"


@pytest.mark.parametrize("plan", PLANS, ids=lambda p: p.module)
def test_every_skip_carries_a_REASON_not_a_marker(plan: StagePlan):
    """An opt-out with no reason is an omission wearing a decision's clothes.

    A length floor is a PROXY for "is this a reason", and a crude one — it cannot tell a
    complete short answer from a shrug. It earned its keep anyway: it caught
    `error_block_heal`'s REJUDGE skip, which read "there was no judge pass to re-run." That is
    true and complete, and it did not say why the stage's PURPOSE (report the drop in finding
    count) is moot here. Expanding it was the right response; lowering the floor to admit it
    would also have admitted "n/a because".
    """
    thin = {s: r for s, r in plan.skipped.items() if len(r.strip()) < 40}
    assert thin == {}, f"{plan.module} has skip reason(s) too thin to be a reason: {thin}"


@pytest.mark.parametrize("plan", PLANS, ids=lambda p: p.module)
def test_a_declared_RUN_stage_is_actually_referenced_in_the_code(plan: StagePlan):
    """Direction 1: a consumer cannot claim a stage it does not implement."""
    lying = sorted(s for s in plan.runs if not _runs_stage(plan.module, s))
    assert lying == [], (
        f"{plan.module} declares it RUNS {lying} but references none of their primitives"
    )


@pytest.mark.parametrize("plan", PLANS, ids=lambda p: p.module)
def test_a_declared_SKIPPED_stage_is_actually_absent_from_the_code(plan: StagePlan):
    """Direction 2, and the one that catches drift. A consumer that quietly starts calling a
    stage it documented as deliberately skipped — `error_block_heal` snapping an author's
    span — reds here instead of silently widening a deliberate selection."""
    sneaking = sorted(s for s in plan.skipped if _runs_stage(plan.module, s))
    assert sneaking == [], (
        f"{plan.module} declares {sneaking} SKIPPED but the code references their primitives"
    )


def test_the_checker_reads_CODE_and_not_PROSE():
    """The control for `_code_only`, pinned on the real case that motivated it.

    `error_block_heal` mentions `_snap_to_sentence` in its docstring while declaring SNAP
    skipped. Over raw text that is a contradiction; over code it is consistent. If `_code_only`
    ever stops stripping, this fails here rather than turning the SKIPPED direction above into
    a false accusation.
    """
    raw = (_ENGINE / "error_block_heal.py").read_text(encoding="utf-8", errors="ignore")
    assert "_snap_to_sentence" in raw, "the fixture case is gone; re-point this test"
    assert "_snap_to_sentence" not in _code_only(raw), "docstrings are no longer stripped"


def test_self_heal_is_the_one_that_runs_everything():
    """The owner of the pipeline. If it ever stops running a stage, that is a real change and
    it should be declared with a reason like anyone else — not silently absent."""
    plan = next(p for p in PLANS if p.module == "self_heal")
    assert set(plan.runs) == set(HealStage) and plan.skipped == {}


def test_the_stage_detector_can_tell_RUN_from_SKIP():
    """A control for `_runs_stage` itself: every assertion above is satisfied by a detector
    that returns a constant. Pin one known-true and one known-false."""
    assert _runs_stage("self_heal", HealStage.VERIFY) is True
    assert _runs_stage("plan_heal", HealStage.VERIFY) is False
