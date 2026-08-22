"""T83 — every direct `.run()` in the repo layer must render its template.

`run_read` / `run_read_any_owner` / `run_write` render for the session's engine, so anything
going through them is safe by construction. A handful of repo functions call `session.run` or
`tx.run` directly and are therefore outside that chokepoint:

    maintenance.invalidate_stale_quarantined_facts   its `user_id` is legitimately None
    enrichment  (4 sites)                            multi-statement anchor/fact upserts
    entities._GLOSSARY_ANCHOR_SYNC_CYPHER
    hierarchy._UPSERT_CYPHER

⚠️ **They were found by a live failure, not by a review.** T83 removed 51 `render(X, "neo4j")`
literals with a regex; the bypass sites lost theirs with the rest and nothing noticed until
`test_t35_identity_rename` hit Neo4j with a literal `{NOW}` — `Invalid input '}': expected ':'`,
because Cypher reads it as a map literal. Four unit suites and 620 integration tests were green
at that moment; only a query that actually reached a database could tell.

Enumerating the exceptions by hand is what failed. This derives them from the AST, the same way
`test_passage_index_fixture_coverage` derives its readers, so a NEW bypass site is covered the
day it is written rather than the day it breaks.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.db.cypher_dialect import _TOKEN

_REPOS = pathlib.Path(__file__).resolve().parents[2] / "app" / "db" / "neo4j_repos"


def _module_templates(tree: ast.Module) -> dict[str, str]:
    """Module-level `NAME = "…"` string constants that carry a dialect token."""
    out: dict[str, str] = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            out[node.targets[0].id] = node.value.value
    return out


def _unrendered_direct_runs(path: pathlib.Path) -> list[str]:
    """`x.run(TEMPLATE, …)` where TEMPLATE carries a token and is not wrapped in `render(…)`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    templates = _module_templates(tree)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "run" or not node.args:
            continue
        # `run_read(session, X, …)` is the CHOKEPOINT, not a bypass — it is a plain Name call.
        #
        # ⚠️ BOTH shapes, and the second one is why this comment exists. The first cut matched
        # only a bare `Name`, so `session.run(_WRITE_SUMMARY_CYPHER.format(label=…))` — an
        # `ast.Call`, not a Name — slipped through, and `hierarchy.write_summary_to_node`
        # handed AGE a literal `{NOW}`: `syntax error at or near "}"`. A guard that only knows
        # the shape it was written from is the defect it exists to catch.
        arg = node.args[0]
        name = None
        if isinstance(arg, ast.Name):
            name = arg.id
        elif (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute)
                and arg.func.attr == "format" and isinstance(arg.func.value, ast.Name)):
            name = arg.func.value.id          # `TEMPLATE.format(...)`
        if name and _TOKEN in templates.get(name, "").replace("{{NOW}}", _TOKEN):
            offenders.append(f"{path.name}:{node.lineno}: .run({name}…) — not rendered")
    return offenders


def test_no_direct_run_hands_the_driver_an_unrendered_template():
    """A raw `{NOW}` reaching Neo4j is `Invalid input '}': expected ':'` — a syntax error about
    a map literal, three layers from the template that forgot to render."""
    offenders: list[str] = []
    for path in sorted(_REPOS.glob("*.py")):
        offenders.extend(_unrendered_direct_runs(path))
    assert not offenders, (
        "these repo call sites bypass `run_read`/`run_write` and hand the driver a template "
        "with its dialect token still in it. Wrap the template in "
        "`render(TEMPLATE, engine_of(session))` — NOT in `render(TEMPLATE, \"neo4j\")`, which "
        "is the 51-site defect T83 removed:\n  " + "\n  ".join(offenders)
    )


def test_the_scanner_SEES_an_unrendered_call(tmp_path):
    """Non-vacuity. If the scanner found nothing anywhere it would pass forever — green because
    it is blind, which is the failure one level down that this file exists to stop."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        'Q = "MATCH (e) SET e.at = {NOW} RETURN e"\n'
        "async def go(session):\n"
        "    await session.run(Q, user_id=1)\n",
        encoding="utf-8",
    )
    found = _unrendered_direct_runs(probe)
    assert len(found) == 1, f"the scanner missed an obvious offender: {found}"


@pytest.mark.parametrize("src,expected", [
    # A `.format()`ed template is the shape that slipped through the first cut (T88).
    ('Q = "SET e.at = {{NOW}}"\nasync def g(s):\n    await s.run(Q.format(x=1))\n', 1),
    ('Q = "SET e.at = {{NOW}}"\nasync def g(s):\n'
     "    await s.run(render(Q.format(x=1), engine_of(s)))\n", 0),
    # Rendered — the fix, and it must not be flagged.
    ('Q = "SET e.at = {NOW}"\nasync def g(s):\n    await s.run(render(Q, engine_of(s)))\n', 0),
    # A template with no token needs no render.
    ('Q = "MATCH (e) RETURN e"\nasync def g(s):\n    await s.run(Q)\n', 0),
    # A different receiver — `tx.run` bypasses the helpers just as `session.run` does.
    ('Q = "SET e.at = {NOW}"\nasync def g(tx):\n    await tx.run(Q)\n', 1),
])
def test_the_scanner_distinguishes_the_cases(tmp_path, src, expected):
    """Validated on cases the scanner was NOT derived from — it was written against
    `session.run`, and `tx.run` is the one the merge/erase paths actually use."""
    probe = tmp_path / "probe2.py"
    probe.write_text(src, encoding="utf-8")
    assert len(_unrendered_direct_runs(probe)) == expected
