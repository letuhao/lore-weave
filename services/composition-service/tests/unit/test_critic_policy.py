"""S6 — one place decides who judges, and it says WHY when nobody does.

The rule under test is small. What earns a test file is that it used to live in SEVEN places
in `routers/engine.py` and that the one thing it never did — tell the author the blocking tier
was off — is the reason S6 exists.
"""
from __future__ import annotations

import ast
import pathlib
import uuid

import pytest

from app.engine.critic_policy import CriticResolution, CriticStatus, resolve_critic

_ENGINE = pathlib.Path(__file__).resolve().parents[2] / "app" / "routers" / "engine.py"


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

def test_there_is_no_eighth_hand_rolled_distinct_check():
    """`ast`, not a regex, and the reason is recorded in this run's drift log: a regex over
    call bodies passed its own injection because one match ran 19,993 characters and swallowed
    the next call whole. Here the structure is a comparison inside a BoolOp, which is a parse
    tree.

    Reds when someone re-inlines `str(critic_ref) != str(drafter_ref)` instead of calling the
    policy — the drift that produced seven copies, six of which stayed in lockstep while the
    seventh, written inverted, grew the defect S6 fixes.
    """
    tree = ast.parse(_ENGINE.read_text(encoding="utf-8"))
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        src = ast.unparse(node)
        if "critic" in src and any(isinstance(o, (ast.Eq, ast.NotEq)) for o in node.ops):
            offenders.append(node.lineno)
    assert offenders == [], (
        f"engine.py re-inlines a critic identity comparison at line(s) {offenders} — "
        f"call resolve_critic() instead; that rule had seven copies once"
    )


def test_the_ast_guard_can_actually_see_such_a_comparison():
    """A control for the guard above. It asserts an EMPTY list, which is exactly the shape
    that passes when the detector is broken — so prove the detector fires on the pattern it
    claims to catch, rather than trusting a green from a scan that found nothing."""
    tree = ast.parse("x = str(critic_ref) != str(drafter_ref)\n")
    hits = [n for n in ast.walk(tree)
            if isinstance(n, ast.Compare) and "critic" in ast.unparse(n)
            and any(isinstance(o, (ast.Eq, ast.NotEq)) for o in n.ops)]
    assert len(hits) == 1, "the guard would not have seen the very pattern it forbids"


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


def test_resolution_is_frozen():
    r = CriticResolution(CriticStatus.NOT_CONFIGURED)
    with pytest.raises(Exception):
        r.status = CriticStatus.CONFIGURED  # type: ignore[misc]
