"""A store probe that could not RUN must not become a value the diff can compare.

FOUND 2026-08-22. The stack was idling at 96 of 100 Postgres connections, a probe was refused, and
`store_snapshot._psql` returned the STRING `"__error__:<stderr>"`. `_counts` filed it under
`out["__error__"]`, that key reached the run's `store` as though it were a table, and `diff`
reported:

    {"loreweave_composition.__error__": {"before": null,
                                         "after": "__error__:... sorry, too many clients"}}

**which is a diff** — and the gate reads a diff as the owning store having MOVED. The affected
entry's `wrote_count` was 1 entirely because of it.

`_scoped_tables` was the same defect wearing quieter clothes: it filtered the sentinel out and
returned `[]`, so a failed `information_schema` probe produced an EMPTY snapshot indistinguishable
from "no tables matched".

WHY IT MATTERS IN BOTH DIRECTIONS. A phantom diff is a false *"this READ wrote to the store"*.
An empty snapshot is a false *"the write landed nothing"*. Either way the DATA bar — the one
assertion a stochastic model cannot talk its way past — is decided on a measurement that never
happened.

BLAST RADIUS, SWEPT: 1,581 runs across every evidence file on disk carry exactly ONE instance
(`batch19-v4`, `composition_motif_link_edit`, run 1) and ZERO empty `store.before`. That tool's
ledger row cites `batch19-v5`, a later arm, so the damaged run drove no conclusion.

THE FIX IS ONE CHOKEPOINT: `_psql` raises `SnapshotUnavailable`. Both exits close together because
both were only callers guessing at what a failure means. The caller records the run as errored and
the gate's EXISTING "LIVE clean" bar refuses the batch — a transport failure is not a model result,
it is a re-run condition. No new bar and no new sentinel.

WHAT THIS DOES NOT COVER: the neo4j path keeps its own `neo4j.__error__` marker, deliberately — a
graph that is down must not silently read as "clean", and it carries `rows: -1` rather than a
string, so `diff` cannot mistake it for a table count. It is a different shape and is left alone.
"""
from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MOD = ROOT / "scripts" / "toolloop" / "store_snapshot.py"

_SPEC = importlib.util.spec_from_file_location("store_snapshot_under_test", MOD)
ss = importlib.util.module_from_spec(_SPEC)
sys.modules["store_snapshot_under_test"] = ss
_SPEC.loader.exec_module(ss)


class _Failed:
    """What subprocess.run returns when the probe could not connect."""
    returncode = 2
    stdout = ""
    stderr = ('psql: error: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" '
              'failed: FATAL:  sorry, too many clients already')


def test_a_refused_probe_raises_instead_of_returning_a_value(monkeypatch):
    """The original instance, verbatim, as the falsifier."""
    monkeypatch.setattr(ss.subprocess, "run", lambda *a, **k: _Failed())
    with pytest.raises(Exception) as e:
        ss._psql("loreweave_composition", "select 1;")
    assert "too many clients" in str(e.value), "the cause must survive into the error"


def test_the_sentinel_string_is_gone_from_the_postgres_path():
    """🔴 A SOURCE CHECK, KEPT DELIBERATELY NARROW AND EXPLAINED.

    This repo already had a test assert over source TEXT and go red for a RENAME while the
    behaviour was intact. So it asserts one narrow thing: that the sentinel is never CONSTRUCTED.

    🔴 AND THE FIRST VERSION OF THIS TEST WAS ITSELF TOO NAIVE. It looked for the literal
    `"__error__:` anywhere above `_neo4j`, and went red on the DOCSTRING that explains the old
    behaviour — prose describing the bug read as the bug. A source check has to name the shape it
    forbids (a value being built), not a substring that documentation legitimately contains.

    The neo4j marker below is a different shape — it carries `rows: -1`, not a string, so `diff`
    cannot mistake it for a table count — and is deliberately out of scope.
    """
    import ast

    tree = ast.parse(MOD.read_text(encoding="utf-8"))
    built = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_neo4j":
            continue
        if isinstance(node, ast.JoinedStr):           # an f-string
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str) \
                        and v.value.startswith("__error__"):
                    built.append(ast.unparse(node))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.value.startswith("__error__:"):
            built.append(node.value)
    assert not built, (
        f"the sentinel is still CONSTRUCTED at {built} — a returned '__error__:...' flows into "
        "the snapshot and `diff` reads it as a table whose value changed"
    )


def test_an_empty_result_now_means_empty_and_not_broken(monkeypatch):
    """_scoped_tables used to swallow a failure into []. An empty list must mean the query really
    returned nothing — that distinction is the whole point of the fix."""
    class _Ok:
        returncode = 0
        stdout = ""
        stderr = ""
    monkeypatch.setattr(ss.subprocess, "run", lambda *a, **k: _Ok())
    assert ss._scoped_tables("loreweave_book", "book_id") == []

    monkeypatch.setattr(ss.subprocess, "run", lambda *a, **k: _Failed())
    with pytest.raises(Exception):
        ss._scoped_tables("loreweave_book", "book_id")


def test_diff_would_have_reported_the_sentinel_as_a_change():
    """Why the sentinel was dangerous rather than merely untidy — asserted on `diff` itself, which
    is unchanged by the fix. A read-intent turn producing THIS diff fails the DATA bar."""
    before = {"loreweave_composition.composition_work": {"rows": 1, "latest": "-"}}
    after = dict(before)
    after["loreweave_composition.__error__"] = "__error__:psql: ... too many clients"
    d = ss.diff(before, after)
    assert d, "a snapshot carrying the old sentinel produced a non-empty diff — a phantom write"
