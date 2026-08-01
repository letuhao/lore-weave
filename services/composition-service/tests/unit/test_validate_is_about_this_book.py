"""The Validate button was useless, and the reason was architectural rather than a wrong rule.

`run_rules` began as the POC's OWN golden-fixture acceptance test and was wired straight in as the
live per-user gate — its own docstring says so. Four of its rules are about ONE novel's specifics:
the PA/HA/CD/THR variable framework, an arc literally called `arc_2`. They were demoted to
`advisory`, which stopped them BLOCKING — and then the transport dropped `tier`, so the panel
received eleven flat pass/fail rows and drew a rule about another book's PA variable exactly like
"your plan has no events". Five ✗ of equal weight, and no way to tell which one was the author's to
fix.

Two things are wrong with a verdict on a rule that does not apply, and only one of them is the ✗:
`pa_not_realm` PASSES VACUOUSLY for every book with no PA. A tick for a check that never ran is as
dishonest as a cross for a check that could never pass.
"""

from __future__ import annotations

from app.engine.plan_forge.validate import run_rules

_POC_SCOPED = {"vars_four", "pa_not_realm", "thr_no_early_explain", "arc2_discovery"}


def _spec(**over):
    base = {
        "meta": {"open_questions": []},
        "charter": {"consistency_anchors": [], "style_constraints": [], "forbids": []},
        "layers": {"characters": [], "mechanics": [], "variables": []},
        "arcs": [], "events": [], "links": [],
    }
    base.update(over)
    return base


def _by_id(spec):
    return {r["rule"]: r for r in run_rules(spec)}


def test_a_book_without_the_POC_entities_gets_NO_verdict_on_them():
    """Not a ✗ (it never had those variables) and not a ✓ (nothing was checked)."""
    rules = _by_id(_spec())
    for rid in _POC_SCOPED:
        assert rules[rid]["applicable"] is False, f"{rid} still judges a book it is not about"


def test_a_book_that_DOES_declare_them_is_still_judged():
    """The rules are not deleted — for the novel they are about, they still say something."""
    spec = _spec(
        layers={"characters": [], "mechanics": [],
                "variables": [{"code": c, "name": c} for c in ("PA", "HA", "CD", "THR")]},
        arcs=[{"id": "arc_2", "title": "x", "arc_kind": "power"}],
    )
    rules = _by_id(spec)
    for rid in _POC_SCOPED:
        assert rules[rid]["applicable"] is True, f"{rid} went silent on the book it IS about"
    assert rules["vars_four"]["pass"] is True
    assert rules["arc2_discovery"]["pass"] is False, "arc_2 is `power`, the rule wants `discovery`"


def test_a_PARTIAL_overlap_still_counts_as_applicable():
    """A book that declares PA but not the other three is a book this rule has something to say
    about — silence there would hide a real finding."""
    spec = _spec(layers={"characters": [], "mechanics": [],
                         "variables": [{"code": "PA", "name": "PA"}]})
    rules = _by_id(spec)
    assert rules["vars_four"]["applicable"] is True and rules["vars_four"]["pass"] is False
    assert rules["pa_not_realm"]["applicable"] is True
    assert rules["thr_no_early_explain"]["applicable"] is False, "no THR, no verdict about THR"


def test_a_NON_APPLICABLE_rule_can_never_block_a_compile():
    """`_hard_rules_pass` honoured `tier` but not applicability — a hard rule scoped to an entity
    the book does not have would have blocked over another novel's variable."""
    from app.services.plan_forge_service import _hard_rules_pass

    assert _hard_rules_pass([
        {"rule": "x", "pass": False, "tier": "hard", "applicable": False},
        {"rule": "y", "pass": True, "tier": "hard", "applicable": True},
    ]) is True
    assert _hard_rules_pass([{"rule": "z", "pass": False, "tier": "hard"}]) is False, \
        "a rule with no `applicable` key must still gate — absent means applicable"


def test_the_POC_THRESHOLDS_say_whose_numbers_they_are():
    """`>=6 open questions` and `>=4 anchors` are one novel's counts. An author with one open
    question is not doing it wrong, and the message must not imply they are."""
    rules = _by_id(_spec(meta={"open_questions": ["only one"]}))
    for rid in ("open_questions_preserved", "anchors_min"):
        assert "POC fixture" in rules[rid]["detail"], f"{rid} presents its threshold as a standard"
        assert rules[rid]["tier"] == "advisory"


def test_the_GENERAL_gates_are_still_hard_and_still_apply():
    """The fix must not disarm the checks that ARE about any novel.

    `every_arc_has_events` is deliberately advisory and stays that way — compile has its own guard
    at the link step ("a compile that materialises nothing is a failure"), so gating twice would
    refuse a mid-authoring plan the author is still filling in. I assumed it was hard when writing
    this test; the code was right and the assumption was not.
    """
    rules = _by_id(_spec())
    for rid in ("spec_has_arc", "spec_has_events", "notes_linked"):
        assert rules[rid].get("tier", "hard") == "hard", f"{rid} stopped gating"
        assert rules[rid].get("applicable", True) is True

    # …and EVERY hard rule must be a general one. A hard rule scoped to one novel is the bug.
    hard = {rid for rid, r in rules.items() if r.get("tier", "hard") == "hard"}
    assert hard & _POC_SCOPED == set(), f"a fixture rule is gating compile: {hard & _POC_SCOPED}"


def test_the_transport_carries_tier_and_applicability():
    """The actual architecture bug: the service honoured `tier` and then threw it away on the way
    out, so the panel could not tell a blocker from a fixture rule."""
    import inspect

    from app.services.plan_forge_service import PlanForgeService

    src = inspect.getsource(PlanForgeService.validate)
    assert '"tier": r.get("tier"' in src, "tier is dropped before it reaches the client"
    assert '"applicable": r.get("applicable"' in src
