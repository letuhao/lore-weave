"""S3 — `skip_reason` is a CLOSED vocabulary, and the check is mechanical.

The enum on its own is a suggestion: `Finding.skip_reason` is typed `str | None`, so
`f.skip_reason = "not_locatd"` still assigns cleanly and the finding becomes silently
un-countable. `worker/operations.py` reports how many findings the verifier refuted by
comparing against the literal `"refuted"` — a typo there or at any producer yields
`refuted: 0` on a run where every finding was refuted, and nothing raises.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app.engine.finding import SkipReason

_APP = pathlib.Path(__file__).resolve().parents[2] / "app"
#: The modules whose findings use the closed vocabulary. `glossary_build` is DELIBERATELY
#: absent: its `skip_reason` is a free-text sentence shown to a human and persisted in a TEXT
#: column — the same spelling for a different concept, and merging them would be the
#: one-name-two-concepts drift this vocabulary exists to end.
_HEAL_MODULES = ("engine/self_heal.py", "engine/plan_heal.py")


def _assigned_in_source(src: str) -> list[tuple[int, str]]:
    """Every string LITERAL assigned to a `.skip_reason` attribute in `src`.

    Takes SOURCE, not a path, so the control below can drive the same function the scan uses.
    A control that re-states the detector inline is how a sibling guard in this suite once
    certified its own silence — it matched its own restatement while the real scan, whose
    regex had been corrupted, matched nothing.
    """
    tree = ast.parse(src)
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t for t in node.targets
                   if isinstance(t, ast.Attribute) and t.attr == "skip_reason"]
        if targets and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            out.append((node.lineno, node.value.value))
    return out


def _assigned_skip_reasons(rel: str) -> list[tuple[int, str]]:
    return _assigned_in_source((_APP / rel).read_text(encoding="utf-8"))


@pytest.mark.parametrize("rel", _HEAL_MODULES)
def test_no_heal_module_assigns_a_RAW_skip_reason_string(rel):
    """Reds on `f.skip_reason = "whatever"`. The producers must go through the enum, because
    `str | None` accepts a typo and the downstream comparison then silently never matches."""
    raw = _assigned_skip_reasons(rel)
    assert raw == [], (
        f"{rel} assigns raw skip_reason string(s) {raw} — use SkipReason.<MEMBER>; a free "
        f"string here is un-countable downstream and nothing raises"
    )


def test_the_scanner_can_actually_SEE_a_raw_assignment():
    """The control, driving `_assigned_in_source` — the same function the scan calls.

    The assertion above expects an EMPTY list, which is exactly what a broken scanner returns.
    Both halves are pinned: one source that must be flagged, and one that must not, because a
    detector hardwired to report a hit satisfies the first on its own.
    """
    assert _assigned_in_source('f.skip_reason = "not_located"\n') == [(1, "not_located")]
    assert _assigned_in_source("f.skip_reason = SkipReason.NOT_LOCATED\n") == [], \
        "the scanner flags the enum form — it would red on the fix it is asking for"


def test_the_undocumented_members_are_the_load_bearing_ones():
    """`refuted` and `noop` were written by the code and ABSENT from the trailing-comment
    vocabulary that documented it — and `refuted` is the one member a consumer reads."""
    assert SkipReason.REFUTED.value == "refuted"
    assert SkipReason.NOOP.value == "noop"


def test_the_consumer_literal_still_matches_the_enum():
    """`worker/operations.py` counts `f.skip_reason == "refuted"`. `SkipReason` is `str`-valued
    precisely so that comparison keeps working; this fails if someone makes it a plain Enum,
    which would break the count silently rather than loudly."""
    assert SkipReason.REFUTED == "refuted"
    src = (_APP / "worker" / "operations.py").read_text(encoding="utf-8")
    assert '== "refuted"' in src, (
        "the consumer stopped comparing against the literal — re-point this test at whatever "
        "it compares now, and check the value still matches SkipReason.REFUTED"
    )


def test_not_found_is_gone_as_a_second_name_for_not_located():
    """The duplicate this slice removed. Both meant 'the quoted text could not be located'.

    Scanned over the AST's string CONSTANTS, not the file text. A raw-text scan reds on the
    comment that documents the removal — which is the prose-versus-mechanism confusion the
    deferral registry already has a rule about, arrived at from the other side: a comment
    mentioning a retired name is not the name being in use.
    """
    assert "not_found" not in {m.value for m in SkipReason}
    for rel in _HEAL_MODULES:
        tree = ast.parse((_APP / rel).read_text(encoding="utf-8"))
        live = [n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and n.value == "not_found"]
        assert live == [], f"{rel} still USES 'not_found' at line(s) {live}"


# ── the member must survive FORMATTING, not only comparison ──────────────────────────────

def test_a_skip_reason_formats_as_its_VALUE_not_its_member_path():
    """The regression a live run caught and every unit test here missed.

    The first version was `class SkipReason(str, Enum)`. That satisfies `== "refuted"` (it is
    a `str` subclass) and JSON-serialises to `"noop"` — so comparison-based tests all passed.
    But `str()` and f-string interpolation return `"SkipReason.NOOP"`, so any consumer that
    FORMATS a skip_reason into a log line, a message or a report starts emitting the member
    path instead of the value. A live self-heal printed `skip_reasons seen:
    ['SkipReason.NOOP']`, which is what exposed it.

    Asserted across all three shapes a value can leave this process by, because the bug was
    invisible in two of them.
    """
    import json

    for m in SkipReason:
        assert str(m) == m.value, f"str({m!r}) is {str(m)!r}, expected {m.value!r}"
        assert f"{m}" == m.value, f"f-string of {m!r} is {f'{m}'!r}"
        assert json.loads(json.dumps({"r": m}))["r"] == m.value
        assert m == m.value, "comparison broke — a consumer using == would stop matching"


def test_a_finding_carrying_a_member_formats_cleanly_end_to_end():
    """The same property through the dataclass a producer actually writes, rather than through
    the enum alone — the gap between the two is where the live run found it."""
    from app.engine.self_heal import Finding

    f = Finding(type="t", span="s", issue="i", fix="x")
    f.skip_reason = SkipReason.NOOP
    assert f"{f.skip_reason}" == "noop"
    assert str(f.skip_reason) == "noop"
