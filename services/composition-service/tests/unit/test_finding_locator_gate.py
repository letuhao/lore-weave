"""A sixth finding type may not invent a sixth locator.

Why a test and not a `scripts/*-gate.py`
----------------------------------------
The other gates written this cycle are repo-wide and cross-language, so they live in
`scripts/` and run in the `lints` job with no service deps. This one's denominator is *Python
classes inside one service*, and the cheapest honest way to enumerate them is to import the
package — which the `lints` job cannot do. It runs with composition's own suite, which is where
the thing it guards lives.

The denominator comes from the CODE, not from a list. `_finding_classes()` walks `app/engine`
for classes whose name says they are a finding, so a new one is in the set on the day it is
written — the same shape as `test_injection_persist`'s reading of `chapter_worker`'s dispatch,
which found two chapter paths I had not noticed.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[2] / "app" / "engine"

#: Names that say "this is a finding". Deliberately broad — a false candidate costs one
#: EXEMPT row with a reason, a missed one costs a producer that silently has no locator.
_NAME = ("Finding", "Violation")

#: Finding-shaped classes that legitimately have no locator, each with the reason. A row for a
#: class that no longer exists FAILS: a stale exemption is a live one.
#:
#: EMPTY today, and it was not always going to be — the first draft exempted
#: `ReferenceViolationError`, which turned out to be filtered already (it is an Exception, and
#: it lives outside `app/engine`). The staleness check caught my own unnecessary row, which is
#: the one thing an empty registry cannot demonstrate; `test_the_staleness_check_can_FAIL`
#: below exercises it against a fabricated row so the rule stays proven at zero.
EXEMPT: dict[str, str] = {}


def _finding_classes() -> dict[str, pathlib.Path]:
    out: dict[str, pathlib.Path] = {}
    for p in sorted(ENGINE.rglob("*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.ClassDef):
                continue
            if not any(w in n.name for w in _NAME):
                continue
            # An exception is not a finding: it is raised and caught, never carried in a list
            # that a report renders. Judged by its BASE, not by its name ending in "Error" —
            # a class called `SomethingViolation(Exception)` would slip a name check.
            bases = {getattr(b, "id", getattr(b, "attr", "")) for b in n.bases}
            if bases & {"Exception", "ValueError", "RuntimeError"}:
                continue
            out[n.name] = p
    return out


def _has_locator(path: pathlib.Path, cls: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == cls:
            for st in n.body:
                if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and st.name == "locator":
                    return True
                if isinstance(st, ast.AnnAssign) and getattr(st.target, "id", "") == "locator":
                    return True
    return False


def test_the_set_of_finding_classes_is_not_empty():
    """Without this the parametrised test below passes by having nothing to check."""
    assert _finding_classes(), "no finding classes found — this gate would be vacuous"


@pytest.mark.parametrize("cls", sorted(_finding_classes()))
def test_every_finding_class_projects_a_locator(cls):
    path = _finding_classes()[cls]
    if cls in EXEMPT:
        pytest.skip(f"exempt: {EXEMPT[cls]}")
    assert _has_locator(path, cls), (
        f"{cls} ({path.name}) carries a finding and cannot say WHERE it is. Add a `locator` "
        f"property returning a `Locator` — including `Locator.nowhere(...)` when the answer is "
        f"that nothing could place it, which is an answer and not an absence."
    )


def _stale(exempt: dict[str, str]) -> list[str]:
    return sorted(set(exempt) - set(_finding_classes()))


def test_no_EXEMPT_row_is_stale():
    assert _stale(EXEMPT) == [], (
        f"EXEMPT rows for classes that no longer exist: {_stale(EXEMPT)}. A registry that only "
        f"grows stops describing the repo, and the row is a standing exemption for nothing."
    )


def test_the_staleness_check_can_FAIL():
    """At an empty EXEMPT the test above cannot fail, so the RULE is proved separately.

    Not ceremony: the first draft of this file carried a row that was already unnecessary, and
    the staleness check is what said so. An empty registry must not quietly turn that check
    into decoration.
    """
    assert _stale({"AClassThatDoesNotExist": "why"}) == ["AClassThatDoesNotExist"]
