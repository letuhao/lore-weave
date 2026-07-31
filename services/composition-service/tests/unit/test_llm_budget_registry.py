"""composition-service's call-profile registry — adoption must never be a downgrade.

The SDK seam's docstring promised that adopting it "can never truncate something that
previously fit". Measured against the full 18-site inventory, that was false: `plan_forge`'s
chat uses 8000 against a STRUCTURED floor of 4096 (it would have been HALVED), and both
self-heal proposers use 3000 against an EDIT floor of 2200. A halved plan JSON does not come
back short, it comes back unparseable.

So the promise stops being a sentence here. Every row records the literal it replaced (`was`),
and the first test below fails if any row resolves under it. That is the whole reason the row
carries a number at all.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app.llm_budget import PROFILES, budget_for, max_tokens_for, profile_for

from loreweave_llm.budget import OutputKind

_APP = pathlib.Path(__file__).resolve().parents[2] / "app"


# ── the invariant the whole registry exists to make checkable ─────────────────────────────

@pytest.mark.parametrize("code", sorted(PROFILES))
def test_no_row_resolves_below_the_literal_it_replaced(code):
    got = max_tokens_for(code)
    was = PROFILES[code].was
    assert got >= was, (
        f"{code} would DOWNGRADE {was} -> {got}. Raise its `floor`; the seam's guarantee is "
        f"that adoption never truncates something that previously fit."
    )


def test_the_three_sites_that_would_have_been_downgraded_are_covered():
    """Named explicitly, because a parametrized sweep passes just as loudly when a future
    edit drops the rows entirely."""
    for code, was in (("plan_forge_chat", 8000),
                      ("propose_edits_direct", 3000),
                      ("propose_self_heal", 3000)):
        assert PROFILES[code].was == was
        assert max_tokens_for(code) >= was


def test_a_row_floor_can_raise_but_never_lower_the_kinds_safety_net():
    """`floor` is a service-measured MINIMUM, not a replacement — otherwise a registry row
    could quietly drop a call under its kind's net."""
    from loreweave_llm.budget import call_budget
    assert call_budget(OutputKind.STRUCTURED, floor=10).max_output_tokens >= 4096
    assert call_budget(OutputKind.STRUCTURED, floor=8000).max_output_tokens >= 8000


# ── the kind is the load-bearing half ─────────────────────────────────────────────────────

def test_structured_rows_report_truncation_as_fatal():
    """A clipped array is unparseable, not short — `cast_plan` records that biting for real.
    A caller must be able to branch on this, which one flat integer could never express."""
    for code, p in PROFILES.items():
        fatal = budget_for(code).truncation_is_fatal
        assert fatal is (p.kind is OutputKind.STRUCTURED), f"{code} ({p.kind}) reported {fatal}"


def test_every_row_carries_a_reason():
    missing = sorted(c for c, p in PROFILES.items() if not p.why.strip())
    assert missing == [], f"rows with no rationale: {missing}"


def test_profile_for_raises_on_an_unknown_code():
    with pytest.raises(KeyError, match="unknown composition call profile"):
        profile_for("no_such_call")


# ── the seam must carry SIGNAL, or it is a renamed constant ───────────────────────────────

def test_the_budget_moves_with_the_facts_the_caller_knows():
    """"A seam that carries no signal is a renamed constant." If passing a real target/language
    changed nothing, a future scored policy would have nothing to adapt on."""
    small = max_tokens_for("propose_cast", target=3)
    large = max_tokens_for("propose_cast", target=200)
    assert large > small, "item count does not move a STRUCTURED budget"

    en = max_tokens_for("compress", target=2000, language="en")
    zh = max_tokens_for("compress", target=2000, language="zh")
    assert zh > en, "CJK tokenizes ~2x denser per word; the budget must reflect it"


# ── call sites and rows must stay in correspondence ───────────────────────────────────────

def _used_codes() -> set[str]:
    codes: set[str] = set()
    for p in _APP.rglob("*.py"):
        if "__pycache__" in p.as_posix() or p.name == "llm_budget.py":
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            if fn not in ("budget_for", "max_tokens_for", "profile_for"):
                continue
            for arg in n.args:
                codes |= _literal_codes(arg)
    return codes


def _literal_codes(node: ast.AST) -> set[str]:
    """Literals that can REACH the accessor — an `x if c else y` contributes both branches,
    but never the condition (walking the whole node would collect the test's literals too)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _literal_codes(node.body) | _literal_codes(node.orelse)
    return set()


def test_every_call_site_code_exists_in_the_registry():
    missing = sorted(_used_codes() - set(PROFILES))
    assert missing == [], f"call sites pass codes with no PROFILES row: {missing}"
