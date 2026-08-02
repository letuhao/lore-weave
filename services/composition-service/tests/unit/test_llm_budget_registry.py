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
    for code, was in (("plan_forge_chat", 12000),   # the callers' number, not the dead default
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

def test_truncation_fatality_is_the_KIND_or_an_explicit_escalation():
    """A clipped array is unparseable, not short — `cast_plan` records that biting for real.

    STRUCTURED is fatal by kind. A row of another kind may ESCALATE, and exactly one does:
    `cross_scene_check` emits a cast ROSTER while sizing like a verdict, and at a small cap it
    returns zero rows that `compare_people` reports as a CHECKED, clean seam. The assertion is
    written as `== (kind is STRUCTURED or row.truncation_fatal)` rather than being relaxed to
    `>=`, so a row that escalates without saying so still fails.
    """
    for code, p in PROFILES.items():
        fatal = budget_for(code).truncation_is_fatal
        expected = (p.kind is OutputKind.STRUCTURED) or p.truncation_fatal
        assert fatal is expected, f"{code} ({p.kind}) reported {fatal}, expected {expected}"


def test_an_escalation_can_only_ESCALATE():
    """`truncation_fatal=False` must never turn a STRUCTURED row's fatality off.

    The direction matters: a caller-supplied value that can DEFEAT a capability default is a
    shape this repo has already paid for. `or`, not a replacement.
    """
    from loreweave_llm.budget import call_budget
    assert call_budget(OutputKind.STRUCTURED, truncation_is_fatal=False).truncation_is_fatal
    assert call_budget(OutputKind.VERDICT, truncation_is_fatal=True).truncation_is_fatal
    assert not call_budget(OutputKind.VERDICT).truncation_is_fatal


def test_exactly_the_rows_that_declare_it_escalate():
    """Pins the SET, so a second escalation is a decision someone makes on purpose."""
    escalated = sorted(c for c, p in PROFILES.items()
                       if p.truncation_fatal and p.kind is not OutputKind.STRUCTURED)
    assert escalated == ["cross_scene_check"], escalated


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

    # Language signal is a PROSE property, and `compress` — the only PROSE row — is
    # deliberately ceiling-bounded because its SIZE is the feature. So the mechanism is
    # asserted directly rather than through a row that is supposed to ignore it.
    from loreweave_llm.budget import call_budget
    en = call_budget(OutputKind.PROSE, target=2000, language="en").max_output_tokens
    zh = call_budget(OutputKind.PROSE, target=2000, language="zh").max_output_tokens
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


# ── `was` must be the budget IN USE, not the signature default ────────────────────────────

def test_plan_forge_records_the_budget_its_callers_actually_used():
    """The signature default was 8000 and every one of the five live callers overrode it with
    12000, so 8000 was dead code. `was` reads into the no-downgrade test, so recording the
    default would have proved the guarantee against a number nothing used."""
    p = PROFILES["plan_forge_chat"]
    assert p.was == 12000 and max_tokens_for("plan_forge_chat") >= 12000


def test_no_caller_re_introduces_a_budget_literal_the_registry_owns():
    """A caller-supplied value silently defeats the row — the whole reason `was` was wrong.
    Scans for a budget kwarg with an INT literal anywhere in app/, at any call depth, which
    is the class the SSOT gate cannot see (it only reads submit/stream payloads)."""
    offenders = []
    for f in _APP.rglob("*.py"):
        if "__pycache__" in f.as_posix() or f.name == "llm_budget.py":
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            for kw in n.keywords:
                if kw.arg in ("max_tokens", "max_output_tokens") \
                        and isinstance(kw.value, ast.Constant) \
                        and isinstance(kw.value.value, int) and kw.value.value > 0:
                    offenders.append(f"{f.relative_to(_APP).as_posix()}:{n.lineno} ={kw.value.value}")
    assert sorted(offenders) == sorted(_KNOWN_HELPER_LITERALS), (
        f"budget literals changed.\n  now: {offenders}\n  known: {_KNOWN_HELPER_LITERALS}"
    )


#: The remaining helper-hop literals, held as a ratchet. Each is a budget passed to a helper
#: that forwards to submit, so it never reaches the SSOT gate's payload scan — the same
#: unscanned-surface class the gate names in its PASS line. Shrink this list, never grow it.
#: EMPTY as of 2026-08-02 (DoD-3). All three drained onto registry rows
#: (`chapter_beat_map`, `material_search`, `self_heal_rerank`). An empty ratchet is the
#: point of a ratchet; the test still runs, and the next literal anyone adds reds it.
_KNOWN_HELPER_LITERALS: list[str] = []


# ── a ceiling row bounds a call whose SIZE is the feature ─────────────────────────────────

def test_compress_is_bounded_because_its_prompt_states_no_length():
    """`compress` output is injected IN PLACE OF raw prose to shrink the prompt, and its
    prompt carries no length directive — so `max_tokens` IS the size control. The PROSE floor
    would have doubled 512 -> 1024, letting the summary grow past the thing it replaces."""
    assert max_tokens_for("compress") == 512
    for kw in ({"target": 5000}, {"language": "zh"}, {"target": 9999, "language": "zh"}):
        assert max_tokens_for("compress", **kw) == 512, f"{kw} escaped the ceiling"


def test_only_rows_that_declare_a_ceiling_are_bounded_by_one():
    bounded = {c for c, p in PROFILES.items() if p.ceiling is not None}
    assert bounded == {"compress"}, f"unexpected ceiling rows: {bounded - {'compress'}}"


# ── `signal_inert` must agree with the MECHANISM, not with a comment ──────────────────────

#: Signal values chosen to be absurdly large in every direction a row could respond to. If a
#: row does not move under ALL of these, nothing a real call site could pass will move it.
#: `reasoning=None` is deliberate: the reasoning multiplier scales `need`, which is already 0
#: for a row that ignores `target`, so it cannot rescue an otherwise-inert row on its own.
_PROBE_SIGNALS = (
    {"target": 100_000},
    {"language": "zh"},
    {"target": 100_000, "language": "zh"},
    {"context_length": 8},          # the window clamp, pushing DOWN rather than up
    {"target": 100_000, "context_length": 4_000_000},
)


def _row_responds_to_any_signal(code: str) -> bool:
    """Does ANY signal change this row's resolved budget? Probed, never assumed."""
    base = max_tokens_for(code)
    return any(max_tokens_for(code, **kw) != base for kw in _PROBE_SIGNALS)


@pytest.mark.parametrize("code", sorted(PROFILES))
def test_signal_inert_matches_what_the_mechanism_actually_does(code):
    """The flag is a CLAIM about `call_budget`; this is the claim being checked.

    It fails in BOTH directions on purpose. A row wrongly marked inert would let its call
    sites stop passing signal they really do have — the rot this slice exists to pay down,
    re-introduced through its own exemption. A row wrongly NOT marked inert forces its call
    sites to pass arguments the kind never reads, which is the theatre the flag exists to
    stop. Only one of those is caught by a one-directional assert, and it is the less likely
    one.
    """
    declared_inert = PROFILES[code].signal_inert
    responds = _row_responds_to_any_signal(code)
    if declared_inert:
        assert not responds, (
            f"{code!r} declares signal_inert=True but its budget DOES move under a real "
            f"signal — the call sites are entitled to pass one, and this flag is excusing "
            f"them from it"
        )
    else:
        assert responds, (
            f"{code!r} does not declare signal_inert, but NO signal changes its budget. "
            f"Its call sites can only satisfy the no-signal gate with arguments the kind "
            f"never reads. Either mark the row signal_inert=True with the reason, or fix "
            f"the sizing model so the signal is actually consumed."
        )


def test_a_ceiling_bounds_ONE_direction_and_the_window_clamp_is_the_other():
    """The near-miss this test exists to pin, because I shipped the wrong claim first.

    `compress` has `ceiling == floor == 512`, and the ceiling is applied last — from which I
    concluded nothing could move it and marked the row `signal_inert`. The probe reddened:
    the window clamp also runs after the floor and pushes DOWN, so a tiny `context_length`
    resolves the row to 4. A ceiling bounds ABOVE; it says nothing about below.

    The consequence is not cosmetic. Marking the row inert would have excused its call site
    from a signal it is genuinely entitled to pass, inside the slice whose whole purpose is
    removing that excuse.
    """
    assert max_tokens_for("compress") == 512
    for kw in ({"target": 100_000}, {"language": "zh"}):
        assert max_tokens_for("compress", **kw) == 512, f"{kw} escaped the ceiling"
    assert max_tokens_for("compress", context_length=8) == 4, "the window clamp stopped biting"


def test_the_probe_can_tell_the_two_classes_apart():
    """A control, and it has to reach OUTSIDE this registry to be one.

    Every non-MIRROR row responds to `context_length`, because the window clamp applies to
    all of them. So composition-service currently has NO inert row, the `declared_inert`
    branch of the test above never executes here, and `_row_responds_to_any_signal` returning
    a hardcoded True would leave every assertion in this file green. That is precisely the
    check-that-cannot-fail shape, so the negative case is exercised against the mechanism
    directly rather than waiting for a row that may never exist.
    """
    from loreweave_llm.budget import call_budget

    assert _row_responds_to_any_signal("propose_cast") is True    # STRUCTURED sizes on items
    assert _row_responds_to_any_signal("compress") is True        # via the window clamp only

    # MIRROR is the genuinely inert construction — it returns the omit sentinel BEFORE the
    # sizing model and before every clamp, so no signal reaches anything. translation-service
    # owns three such rows; this asserts the probe would report False if one landed here.
    base = call_budget(OutputKind.MIRROR).max_output_tokens
    assert base == 0
    for kw in _PROBE_SIGNALS:
        assert call_budget(OutputKind.MIRROR, **kw).max_output_tokens == base


def test_composition_declares_no_inert_row_and_that_is_a_measurement():
    """Pinned so that ADDING one is a deliberate act with a failing test to read first.

    If this ever needs updating, the question to answer is not "does the flag look right" but
    "what does the probe say" — the probe is the authority, and it has already overruled one
    confident argument in this file's history."""
    assert {c for c, p in PROFILES.items() if p.signal_inert} == set()


def test_language_is_unread_by_the_structured_and_edit_branches():
    """The specific asymmetry that makes a kwarg-counting gate satisfiable with theatre.

    `call_budget` computes `per_word` from `language` and then consults it ONLY on the PROSE
    and VERDICT branches. So `budget_for("propose_cast", language="zh")` is a no-op, while
    `budget_for("judge_canon", language="zh")` is not — and a gate that greps for the kwarg
    cannot tell those apart. Pinning it here means a future change to the sizing model that
    makes `language` load-bearing for STRUCTURED shows up as a failing test rather than as a
    silent shift in what the call sites ought to be passing.
    """
    for code in ("propose_cast", "plan_character_arcs", "plan_forge_chat"):
        assert profile_for(code).kind is OutputKind.STRUCTURED
        assert (max_tokens_for(code, target=20, language="zh")
                == max_tokens_for(code, target=20)), f"{code}: language became load-bearing"
    for code in ("propose_edits_direct", "propose_self_heal"):
        assert profile_for(code).kind is OutputKind.EDIT
        assert (max_tokens_for(code, target=50_000, language="zh")
                == max_tokens_for(code, target=50_000)), f"{code}: language became load-bearing"
    # …and the CONTROL: on VERDICT it really is read, so the pattern above is a statement
    # about the branch and not about `max_tokens_for` ignoring its kwargs generally.
    assert (max_tokens_for("judge_canon", target=40, language="zh")
            != max_tokens_for("judge_canon", target=40))


# ── the request may NARROW a budget, never raise it ───────────────────────────────────────

def test_a_request_can_only_narrow_a_computed_budget():
    from app.llm_budget import narrowed_by_request
    assert narrowed_by_request(8000, 2000) == 2000      # narrows
    assert narrowed_by_request(8000, 32768) == 8000     # cannot raise
    assert narrowed_by_request(8000, None) == 8000      # absent = no narrowing
    assert narrowed_by_request(8000, 0) == 8000         # 0/negative is not a budget


def test_a_request_cannot_walk_past_the_deploy_ceiling():
    """The defect this rule exists to close, expressed as the deployment that exposes it.

    The router computed `min(scene_count * per_scene, settings.<deploy ceiling>)` and then let
    `body.max_output_tokens` win OUTRIGHT. Nothing bad happened only because
    SCENE_OUTPUT_CEILING (the request field's `le=` bound) and both deploy ceilings are all
    32768 today. Lower a deploy ceiling for a small-context deployment — which is exactly what
    a deploy ceiling is FOR — and the request walks straight past it.
    """
    from app.llm_budget import narrowed_by_request

    deploy_ceiling = 8192          # an operator narrowing the platform
    computed = min(4 * 3000, deploy_ceiling)
    request_asks_for_the_field_maximum = 32768

    assert narrowed_by_request(computed, request_asks_for_the_field_maximum) == deploy_ceiling
    # …and the old idiom, written out, is what it would have produced instead:
    assert (request_asks_for_the_field_maximum or computed) == 32768
