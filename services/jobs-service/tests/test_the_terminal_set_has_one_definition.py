"""DQ-T86 (c) — the SDK's TERMINAL set is the ONLY definition of 'terminal'.

OWNER RULING 2026-08-31: "the six hard-coded terminal tuples are a latent defect independent of
whether a status is added -- the SDK annotates its own TERMINAL set 'The single source of truth
(no parallel set to drift)' and six places drifted from it anyway, one of them in the file that
decides what the projection calls LIVE."

🔴 WHY THIS IS TESTED AT ALL, GIVEN NOTHING IS BROKEN TODAY. The failure mode is SILENT and
arrives only when someone adds a member to `JobStatus` — the very change DQ-T86 (b) contemplates.
On that day every surviving copy goes on believing the old vocabulary, and in the projection's
upsert a new terminal status reads as NON-TERMINAL, so a later non-terminal event can REGRESS a
finished job. There is no error, no log line, and the wrong value is in the store.

So these assertions are written against a SIMULATED new member. A test that only checked today's
three values would pass forever and catch precisely nothing.
"""
from __future__ import annotations

import ast
import pathlib

import pytest
from loreweave_jobs import TERMINAL, JobStatus

REPO = pathlib.Path(__file__).resolve().parents[3]

#: The values that were copied into six places.
TERMINAL_TRIPLE = {"completed", "failed", "cancelled"}


def _hardcoded_terminal_literals(src: str) -> list[str]:
    """Tuple/list/set literals in CODE that spell the terminal set out.

    🔴 PARSED, NOT GREPPED, AND THE FIRST VERSION OF THIS GUARD IS WHY. A regex over the source
    matched the fix's own EXPLANATION -- the comment that quotes the old literal, and a docstring
    on `_mark_orphans_dead` that reasons about "at least six places carry their own hard-coded
    ('completed','failed','cancelled')". Stripping `#` lines was not enough, because prose lives
    in docstrings too. A guard that fires on the text describing the fix is a guard nobody can
    keep green, and this loop has been caught by source-substring guards before.

    `ast` sees only what executes. A docstring is a bare Expr, never a Tuple of Constants.
    """
    out: list[str] = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            continue
        vals = [e.value for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if len(vals) == len(node.elts) and set(vals) == TERMINAL_TRIPLE:
            out.append(repr(tuple(vals)))
    return out

#: The files the ruling names. Kept as an explicit list rather than a repo-wide sweep: a sweep
#: would also flag the ledger, the docs and this test, and a guard that has to be exempted in
#: five places stops being read.
NAMED_SITES = [
    "services/campaign-service/app/routers/campaigns.py",
    "services/composition-service/app/eval/driver.py",
    "services/jobs-service/app/projection/store.py",
    "services/video-gen-service/app/worker/consumer.py",
]


@pytest.mark.parametrize("rel", NAMED_SITES)
def test_no_site_carries_its_own_terminal_tuple(rel: str):
    """THE FALSIFIER, on the original instances: the exact literal, in the exact files."""
    hits = _hardcoded_terminal_literals((REPO / rel).read_text(encoding="utf-8"))
    assert not hits, (
        f"{rel} carries its own ('completed','failed','cancelled') again. That set has ONE "
        f"definition — loreweave_jobs.TERMINAL — and a copy here goes silently stale the day a "
        f"member is added. Found: {hits}"
    )


def test_the_guard_can_actually_FAIL():
    """A guard that cannot go red is decoration. Feed it the original defect."""
    assert _hardcoded_terminal_literals(
        'if row["status"] in ("completed", "failed", "cancelled"):\n    pass\n')
    # ...and prove it does NOT fire on the prose that describes the fix, which is what the
    # regex version got wrong.
    assert not _hardcoded_terminal_literals(
        '"""at least six places carry their own ("completed", "failed", "cancelled")."""\n')
    assert not _hardcoded_terminal_literals(
        '# This read ("completed", "failed", "cancelled") - a second copy.\n')
    # A DIFFERENT tuple is not this defect.
    assert not _hardcoded_terminal_literals('X = ("pending", "running")\n')


def test_the_upsert_sql_renders_from_the_sdk_set():
    """The four SQL copies were the dangerous ones: the WHERE clause decides whether an incoming
    event may overwrite the row."""
    from app.projection import store

    assert "{_TERMINAL_SQL}" not in store._UPSERT, (
        "the sentinel is still in the SQL — the substitution did not run, and this query would "
        "fail at execution time on a WRITE path")
    for s in TERMINAL:
        assert f"'{s.value}'" in store._TERMINAL_SQL
    assert store._TERMINAL_SQL.startswith("(") and store._TERMINAL_SQL.endswith(")")
    # It must appear in BOTH arms of the WHERE clause — terminal and non-terminal.
    assert store._UPSERT.count(store._TERMINAL_SQL) == 4, (
        "the upsert should reference the rendered set exactly four times; a different count "
        "means an arm was missed and still carries a literal")


def test_a_NEW_terminal_member_would_reach_the_sql(monkeypatch):
    """🔴 THE TEETH, and the reason this file exists.

    Simulate DQ-T86 (b) — the `abandoned` status the question was raised to consider — and assert
    the rendering picks it up. A guard that only ever sees today's three values proves nothing
    about the change it is meant to survive.
    """
    import enum
    import importlib

    import loreweave_jobs
    from app.projection import store as store_mod

    # The CONTROL first: without the patch, 'abandoned' is absent. Asserting this before the
    # seed is what stops the test being one whose control and seed agree.
    assert "'abandoned'" not in store_mod._TERMINAL_SQL

    class _Widened(str, enum.Enum):
        COMPLETED = "completed"
        FAILED = "failed"
        CANCELLED = "cancelled"
        ABANDONED = "abandoned"

    # Patch the SDK ITSELF, then reload the module, so the assertion is about the module's own
    # derivation rather than about a string this test computed. Patching store's local alias
    # would prove nothing: the reload re-imports from the SDK and would discard it.
    monkeypatch.setattr(loreweave_jobs, "TERMINAL", frozenset(_Widened), raising=True)
    try:
        importlib.reload(store_mod)
        assert "'abandoned'" in store_mod._TERMINAL_SQL, (
            "adding a member to the SDK's TERMINAL set did NOT reach the projection's SQL — "
            "the upsert still carries its own copy, which is the exact regression DQ-T86 (c) "
            "was ruled to prevent")
        assert store_mod._UPSERT.count(store_mod._TERMINAL_SQL) == 4
    finally:
        monkeypatch.undo()
        importlib.reload(store_mod)      # leave the module holding the real set

    assert "'abandoned'" not in store_mod._TERMINAL_SQL


def test_the_sdk_is_the_only_place_that_defines_terminality():
    """`is_terminal` is what the five runtime sites now call, so it must actually discriminate."""
    assert JobStatus.is_terminal("completed") is True
    assert JobStatus.is_terminal(JobStatus.CANCELLED) is True
    assert JobStatus.is_terminal("running") is False
    assert JobStatus.is_terminal("paused") is False
    # An unknown value is NOT terminal — the projection must not treat a status it has never
    # heard of as finished, which is the regression this whole ruling is about.
    assert JobStatus.is_terminal("abandoned") is False
