"""S6 — one place decides who judges, and it says WHY when nobody does.

The rule under test is small. What earns a test file is that it used to live in SEVEN places
in `routers/engine.py` and that the one thing it never did — tell the author the blocking tier
was off — is the reason S6 exists.
"""
from __future__ import annotations

import ast
import pathlib
import re
import uuid

import pytest

from app.engine.critic_policy import (
    CriticResolution, CriticStatus, resolve_critic, resolve_critic_verified,
)

_APP = pathlib.Path(__file__).resolve().parents[2] / "app"
#: The whole app tree, not a named file.
#:
#: This started as `app/routers/engine.py` — the file the seven copies happened to live in —
#: and an AUDIT then found an EIGHTH in `app/engine/canon_reflect.py` that the guard could not
#: see. That is NV-2 verbatim: an enumerated scope is DEFAULT-UNCOVERED, and the question it
#: fails to answer is "what about a file created tomorrow?". The scope is now the tree.
_SCANNED = sorted(
    p for p in _APP.rglob("*.py")
    if "__pycache__" not in p.as_posix() and not p.name.startswith("test_")
)


# ── the four states, and why each is its own state ────────────────────────────────────────

def test_a_distinct_critic_resolves_and_carries_both_halves():
    r = resolve_critic({"critic_model_source": "user_model", "critic_model_ref": "judge-1"},
                       "drafter-1")
    assert r.status is CriticStatus.CONFIGURED
    assert r.distinct is True
    assert (r.source, r.ref) == ("user_model", "judge-1")


def test_no_critic_at_all_is_NOT_CONFIGURED():
    """The blocking tier is off and the author has not been told. Not an error — but not
    the same thing as a critic that was refused."""
    r = resolve_critic({}, "drafter-1")
    assert r.status is CriticStatus.NOT_CONFIGURED
    assert r.distinct is False


def test_the_drafters_own_model_is_REFUSED_and_says_so():
    """The anti-self-reinforcement rule. A model grading its own prose is a self-witness, and
    this must be distinguishable from 'nothing configured' because the FIX is different."""
    r = resolve_critic({"critic_model_source": "user_model", "critic_model_ref": "same"}, "same")
    assert r.status is CriticStatus.SAME_AS_DRAFTER
    assert r.distinct is False


def test_a_half_written_setting_is_INCOMPLETE_not_absent():
    for s in ({"critic_model_ref": "judge-1"}, {"critic_model_source": "user_model"}):
        assert resolve_critic(s, "drafter-1").status is CriticStatus.INCOMPLETE


def test_a_refused_critic_BLANKS_its_fields_rather_than_flagging_them():
    """The refusal is expressed by removing the model, not by a boolean a caller must
    remember to consult. A caller that ignores `.distinct` still cannot send the refused
    model anywhere, because there is nothing to send."""
    for s, drafter in (({"critic_model_source": "user_model", "critic_model_ref": "same"}, "same"),
                       ({}, "drafter-1"),
                       ({"critic_model_ref": "judge-1"}, "drafter-1")):
        r = resolve_critic(s, drafter)
        assert (r.source, r.ref) == (None, None), f"{r.status} leaked a model"


# ── the type trap that would let a model judge itself ─────────────────────────────────────

def test_a_UUID_setting_and_a_str_drafter_are_the_SAME_model():
    """The setting comes out of JSONB and the drafter ref off a request body or a job input,
    so the two sides arrive differently typed. `UUID(x) == str(x)` is False in Python, so an
    identity check on the raw values would call a model distinct from ITSELF and let it grade
    its own prose — with every test that used matching types staying green.
    """
    same = uuid.uuid4()
    r = resolve_critic({"critic_model_source": "user_model", "critic_model_ref": same}, str(same))
    assert r.status is CriticStatus.SAME_AS_DRAFTER, "a UUID/str pair escaped the self-judge rule"

    # …and the CONTROL: two genuinely different ids must still resolve, or the assertion above
    # would also pass for an implementation that called everything SAME_AS_DRAFTER.
    other = resolve_critic(
        {"critic_model_source": "user_model", "critic_model_ref": uuid.uuid4()}, str(same))
    assert other.status is CriticStatus.CONFIGURED


def test_an_unknown_drafter_does_not_silently_refuse_the_critic():
    """`drafter_ref=None` means 'the caller does not know', not 'it matches'. Treating None as
    a match would disable the judge on exactly the paths that forgot to pass it — a guard
    switching itself off in silence, which is the shape this run keeps finding."""
    r = resolve_critic({"critic_model_source": "user_model", "critic_model_ref": "judge-1"}, None)
    assert r.status is CriticStatus.CONFIGURED


# ── the reason this module exists: no EIGHTH hand-built copy ──────────────────────────────

#: The detector, named so that the scan and its control are THE SAME CODE. Written as a
#: literal pattern in source rather than emitted by a helper: the corrupted version of this
#: guard was produced by a generator script, and `\b` did not survive the trip.
_RULE_RE = re.compile(r"(critic|judge)[A-Za-z0-9_]*(ref|source)")


def _reinlines_rule(node: ast.Compare) -> bool:
    """True when `node` is the distinct-critic rule, hand-rolled instead of delegated."""
    if not any(isinstance(o, (ast.Eq, ast.NotEq)) for o in node.ops):
        return False
    src = ast.unparse(node)
    # a critic/judge ref compared against the DRAFTER's — the rule, re-inlined
    if _RULE_RE.search(src) and "drafter" in src:
        return True
    return "critic" in src and "model_ref" in src

def test_no_module_re_inlines_the_distinct_critic_rule():
    """`ast`, over the WHOLE app tree, because the first version of this guard scanned one file.

    A regex was rejected for a reason this run's drift log records: a regex over call bodies
    passed its own injection because one match ran 19,993 characters and swallowed the next
    call. The structure is a comparison inside a BoolOp — that is a parse tree.

    And the scope matters as much as the tool. Pointed at `routers/engine.py` this passed while
    `engine/canon_reflect.py` carried an eighth copy; an audit found it, not the guard.
    """
    offenders: list[str] = []
    for path in _SCANNED:
        if path.name == "critic_policy.py":
            continue  # the policy IS the comparison
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        offenders += [f"{path.relative_to(_APP).as_posix()}:{n.lineno}"
                      for n in ast.walk(tree)
                      if isinstance(n, ast.Compare) and _reinlines_rule(n)]
    assert offenders == [], (
        f"the distinct-critic rule is re-inlined at {offenders} — call resolve_critic() or "
        f"resolve_critic_refs(); that rule had EIGHT copies once"
    )


def test_the_ast_guard_can_actually_see_such_a_comparison():
    """A control for the guard above — and it must call `_reinlines_rule`, not describe it.

    The first version of this control re-stated the pattern by hand (`"critic" in
    ast.unparse(n)`) instead of invoking the detector. That is precisely how this file once
    reported PASS with an eighth copy in front of it: the real scan's regex had been written
    by a generator that turned `\\b` into a literal 0x08 byte, so it required a control
    character no source contains and matched nothing — while this control, matching its own
    restatement, stayed green and certified the silence.

    A control that re-implements the thing it is controlling tests the author's intent. Only
    a control that calls the same code tests the code.
    """
    seen = ast.parse("x = str(critic_ref) != str(drafter_ref)\n")
    assert [n for n in ast.walk(seen) if isinstance(n, ast.Compare) and _reinlines_rule(n)], \
        "the detector would not have seen the very pattern it forbids"

    # …and the negative half, or a detector hardwired to True would satisfy the line above.
    clean = ast.parse("x = resolve_critic_refs(src, ref, drafter_ref).distinct\n")
    assert [n for n in ast.walk(clean)
            if isinstance(n, ast.Compare) and _reinlines_rule(n)] == [], \
        "the detector fires on a call that DELEGATES the rule — it would flag the fix"


# ── every status has author-facing words, and they differ ─────────────────────────────────

def test_every_non_configured_status_has_its_OWN_message():
    """The defect S6 fixes: one sentence covered all of them, so 'you never set a critic' and
    'the critic you set is the drafter' read identically. A new status with no message must
    fail here rather than fall through to a plausible default."""
    from app.routers.engine import _CRITIC_SKIP_WARNING

    expected = set(CriticStatus) - {CriticStatus.CONFIGURED}
    assert set(_CRITIC_SKIP_WARNING) == expected, "a status has no author-facing message"
    msgs = list(_CRITIC_SKIP_WARNING.values())
    assert len(set(msgs)) == len(msgs), "two statuses share a message — the conflation is back"
    for status, m in _CRITIC_SKIP_WARNING.items():
        assert "Settings" in m, f"{status} does not tell the author WHERE to fix it"


@pytest.mark.parametrize("status", [s for s in CriticStatus if s is not CriticStatus.CONFIGURED])
def test_the_message_lookup_is_closed(status):
    """Keyed on the enum, so an unhandled member raises instead of resolving to something
    that reads fine and means nothing."""
    from app.routers.engine import _CRITIC_SKIP_WARNING

    assert isinstance(_CRITIC_SKIP_WARNING[status], str)


# ── two ROWS, one MODEL — the level below where the rule was looking ──────────────────────

def _identity_map(mapping: dict[tuple[str, str], str | None]):
    """A resolver that answers from a table, and records what it was asked."""
    asked: list[tuple[str, str]] = []

    async def resolve(source: str, ref: str) -> str | None:
        asked.append((source, ref))
        return mapping.get((source, ref))

    return resolve, asked


_GEMMA = "lm_studio::google/gemma-4-26b-a4b-qat"
_QWEN = "lm_studio::qwen/qwen3.6-35b-a3b"


async def test_two_DIFFERENT_rows_pointing_at_ONE_model_is_still_self_judging():
    """The defect, with the numbers that make it not-hypothetical.

    Measured on the dev stack 2026-08-02:
        lm_studio::google/gemma-4-26b-a4b-qat   5 active user_models rows
        ollama::gemma3:12b                      5
    and the first is the model `scripts/dev-model.py` resolves for chat — the default drafter.
    Any two of its five rows have different `user_model_id`s, so the ref comparison answers
    CONFIGURED and the model grades its own prose.
    """
    resolve, asked = _identity_map({
        ("user_model", "row-A"): _GEMMA,
        ("user_model", "row-B"): _GEMMA,   # a second credential for the SAME weights
    })
    r = await resolve_critic_verified(
        {"critic_model_source": "user_model", "critic_model_ref": "row-B"},
        "user_model", "row-A", resolve,
    )
    assert r.status is CriticStatus.SAME_AS_DRAFTER
    assert r.distinct is False
    assert r.identity_verified is True
    assert (r.source, r.ref) == (None, None), "a refused critic must not leak its model"
    assert len(asked) == 2, "both sides must be resolved — one is not a comparison"


async def test_a_genuinely_different_model_still_resolves_and_is_marked_verified():
    """The control. Without it every assertion above is satisfied by an implementation that
    calls everything SAME_AS_DRAFTER, which would silently disable the blocking tier."""
    resolve, _ = _identity_map({
        ("user_model", "row-A"): _GEMMA,
        ("user_model", "row-C"): _QWEN,
    })
    r = await resolve_critic_verified(
        {"critic_model_source": "user_model", "critic_model_ref": "row-C"},
        "user_model", "row-A", resolve,
    )
    assert r.status is CriticStatus.CONFIGURED
    assert r.identity_verified is True
    assert (r.source, r.ref) == ("user_model", "row-C")


async def test_an_UNRESOLVABLE_identity_is_unverified_and_does_NOT_switch_the_tier_off():
    """Deliberate, and the harder half.

    Failing closed here would mean the critic stops running whenever provider-registry is
    briefly unreachable — a new outage mode, strictly worse than the state before this check
    existed. Same decision, same reason, as `PanelSafety.exclusion_unverified` keeping `safe`
    True: a flag that is false on every ordinary run stops being read.
    """
    resolve, _ = _identity_map({})   # nothing resolves — an outage
    r = await resolve_critic_verified(
        {"critic_model_source": "user_model", "critic_model_ref": "row-C"},
        "user_model", "row-A", resolve,
    )
    assert r.status is CriticStatus.CONFIGURED
    assert r.distinct is True, "an outage must not disable the blocking tier"
    assert r.identity_verified is False, "…but it must not read as verified either"


async def test_a_HALF_resolved_pair_is_unknown_and_never_upgraded_to_verified():
    """`None` from one side means unknown, not different. Treating it as different is how a
    degraded check reports the reassuring answer — the shape this whole audit keeps finding."""
    resolve, _ = _identity_map({("user_model", "row-A"): _GEMMA})   # the critic is unknown
    r = await resolve_critic_verified(
        {"critic_model_source": "user_model", "critic_model_ref": "row-C"},
        "user_model", "row-A", resolve,
    )
    assert r.identity_verified is False


async def test_the_SAME_ROW_case_is_caught_WITHOUT_asking_the_resolver():
    """The cheap check runs first and needs no network, so the most obvious misconfiguration
    is still refused when provider-registry is down."""
    resolve, asked = _identity_map({})
    r = await resolve_critic_verified(
        {"critic_model_source": "user_model", "critic_model_ref": "same"},
        "user_model", "same", resolve,
    )
    assert r.status is CriticStatus.SAME_AS_DRAFTER
    assert asked == [], "the resolver was called for a decision already made"


async def test_no_critic_at_all_does_not_call_the_resolver_either():
    resolve, asked = _identity_map({})
    r = await resolve_critic_verified({}, "user_model", "row-A", resolve)
    assert r.status is CriticStatus.NOT_CONFIGURED
    assert r.identity_verified is None, "nothing was attempted, which is not the same as False"
    assert asked == []


def test_resolution_is_frozen():
    r = CriticResolution(CriticStatus.NOT_CONFIGURED)
    with pytest.raises(Exception):
        r.status = CriticStatus.CONFIGURED  # type: ignore[misc]


# ══ the MAP form reaches the policy, not only the legacy scalar ══════════════════════════
#
# `work.settings` stores a per-role model two ways and the platform declares it prefers
# `settings["model_roles"]`. Measured 2026-08-03: that key had ZERO writers, so the branch
# reading it was dead in production and `resolve_critic` read `critic_model_ref` directly.
# The moment the settings UI started writing the map — which it now does, because two scalars
# cannot express a six-role vocabulary — a critic set through the UI would have resolved to
# NOT_CONFIGURED here, with the blocking tier silently off, while the internal endpoint
# reported the critic correctly. Two readers of one concept, one of them out of date.

def test_a_critic_written_in_the_MAP_is_seen():
    s = {"model_roles": {"critic": {"model_ref": "judge-1", "model_source": "user_model"}}}
    r = resolve_critic(s, "drafter-1")
    assert r.status is CriticStatus.CONFIGURED
    assert (r.source, r.ref) == ("user_model", "judge-1")


def test_the_MAP_wins_over_a_stale_legacy_scalar():
    """Per-role precedence, in the direction the endpoint already documented."""
    s = {
        "critic_model_ref": "old-judge", "critic_model_source": "user_model",
        "model_roles": {"critic": {"model_ref": "new-judge", "model_source": "user_model"}},
    }
    assert resolve_critic(s, "drafter-1").ref == "new-judge"


def test_CONTROL_the_legacy_scalar_still_works_for_a_book_saved_before_the_map():
    """The fallback is the whole reason the migration needs no data change."""
    s = {"critic_model_ref": "judge-1", "critic_model_source": "user_model"}
    assert resolve_critic(s, "drafter-1").ref == "judge-1"


def test_a_HALF_WRITTEN_map_entry_is_INCOMPLETE_not_configured():
    """The raw pair reaches the policy, un-normalised — and this is why.

    `model_roles_from_settings` defaults a missing `model_source` to `user_model`, which is
    right for the wire shape its consumers read. Routing the POLICY through that normaliser
    turned a ref-without-source into CONFIGURED — a provider nobody selected — and two
    pre-existing tests refused it. `role_ref` returns the raw pair for exactly this state.
    """
    s = {"model_roles": {"critic": {"model_ref": "judge-1"}}}
    assert resolve_critic(s, "drafter-1").status is CriticStatus.INCOMPLETE


def test_a_map_critic_that_IS_the_drafter_is_still_refused():
    """Invariant 2 does not care which key the setting was stored under."""
    s = {"model_roles": {"critic": {"model_ref": "same", "model_source": "user_model"}}}
    r = resolve_critic(s, "same")
    assert r.status is CriticStatus.SAME_AS_DRAFTER
    assert (r.source, r.ref) == (None, None), "a refused critic must not leak its model"
