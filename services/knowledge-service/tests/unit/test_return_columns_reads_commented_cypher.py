"""`return_columns` must read every query the repo layer actually ships.

WHAT THIS EXISTS FOR
--------------------
`POST /internal/projects/{id}/fact-for-check` answered **502 to every caller**, and the cause
was a COMMENT. `_EVENTS_AT_OR_BEFORE_CYPHER` documents its `e.id` tie-break between the
`RETURN` list and the `ORDER BY` that tie-break is about -- which is where a reader wants it.
`return_columns` slices from the last `RETURN` to the first tail keyword and splits on commas,
so the last item arrived as `e.participants AS participants` with eleven lines of prose glued
to it, no longer matched the identifier pattern, and raised `ColumnParseError`.

**AGE was never the problem.** That same query carries a `//` comment inside its `WHERE`
clause and executes fine, as do its siblings -- the engine reads Cypher comments. Only this
parser could not read what the engine could.

WHY A SWEEP AND NOT A CASE FOR THE ONE QUERY
--------------------------------------------
Fixing the single constant that broke would leave the next comment to find the same edge, and
the defect was invisible precisely because nothing ever fed the real constants to the real
parser: `test_repo_layer_runs_on_age.py` is a floor of repo FUNCTIONS proven against a live
graph, and `get_fact_for_check` is not in it. So this sweeps every `RETURN`-bearing constant
in `app/db/graph_repos` through the shipped `return_columns`, and it runs with no database.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import app.db.graph_repos as graph_repos
from app.db.age_session import ColumnParseError, return_columns
from app.db.graph_repos.fact_for_check import _EVENTS_AT_OR_BEFORE_CYPHER

#: FLOORS, not expectations. A discovery bug that imported nothing would sweep nothing and
#: pass, which is the vacuity this repo keeps finding in its own gates. Measured 2026-08-31:
#: 17 CONTRIBUTING modules (20 exist; three ship no RETURN-bearing constant) and 155
#: parseable constants. They may rise; they must not fall silently.
_MIN_MODULES = 15
_MIN_CONSTANTS = 150


def _repo_cypher_constants() -> list[tuple[str, str, str]]:
    """Every module-level `RETURN`-bearing Cypher constant, as (module, name, text).

    `*_TEMPLATE` constants holding `{...}` placeholders are excluded: they are not Cypher
    until `render()` fills them, and `score AS raw_score{vector_projection}` has no column
    name because it has no value yet. Five of them, all named `_TEMPLATE`.
    """
    found: list[tuple[str, str, str]] = []
    for mod_info in pkgutil.iter_modules(graph_repos.__path__):
        module = importlib.import_module(f"app.db.graph_repos.{mod_info.name}")
        for name, value in vars(module).items():
            if not (isinstance(value, str) and name.isupper()):
                continue
            if "RETURN" not in value.upper():
                continue
            if name.endswith("_TEMPLATE") and "{" in value and "}" in value:
                continue
            found.append((mod_info.name, name, value))
    return found


def test_every_shipped_repo_query_names_its_columns():
    """The sweep. One raise here is one route answering 502."""
    constants = _repo_cypher_constants()
    modules = {m for m, _, _ in constants}

    assert len(modules) >= _MIN_MODULES, (
        f"swept only {len(modules)} module(s), floor is {_MIN_MODULES} — discovery is broken, "
        f"and a sweep that finds nothing passes for the wrong reason"
    )
    assert len(constants) >= _MIN_CONSTANTS, (
        f"swept only {len(constants)} constant(s), floor is {_MIN_CONSTANTS} — same reason"
    )

    broken: list[str] = []
    for mod, name, text in constants:
        try:
            return_columns(text)
        except ColumnParseError as exc:
            broken.append(f"  {mod}.{name}: {exc}")
    assert not broken, (
        "return_columns cannot name the columns of query/queries the repo layer ships. "
        "Every one of these is a live route answering 502:\n" + "\n".join(broken)
    )


def test_the_query_that_took_fact_for_check_down_names_its_five_columns():
    """The regression, against the REAL constant so it cannot drift from the shipped query."""
    assert return_columns(_EVENTS_AT_OR_BEFORE_CYPHER) == [
        "id", "title", "summary", "event_order", "participants",
    ]


def test_a_comment_between_RETURN_and_ORDER_BY_is_not_part_of_the_last_column():
    """The shape itself, minimised — a comment is legal Cypher exactly there."""
    cypher = (
        "MATCH (e:Event)\n"
        "RETURN e.id AS id, e.participants AS participants\n"
        "// the tie-break, explained where it happens\n"
        "// and it runs to a second line, as real prose does\n"
        "ORDER BY e.event_order DESC, e.id DESC\n"
        "LIMIT $limit\n"
    )
    assert return_columns(cypher) == ["id", "participants"]


def test_a_block_comment_between_columns_is_not_a_column():
    assert return_columns("RETURN e.a AS a /* why a */, e.b AS b") == ["a", "b"]


# ── NEGATIVE CONTROLS. A comment stripper that ate too much would make every case above
# pass while quietly changing what the query means. ──────────────────────────────────────


def test_a_double_slash_inside_a_string_literal_is_NOT_a_comment():
    """`RETURN "http://x" AS url` is a URL, not a comment, and truncating there loses the AS."""
    assert return_columns('RETURN "http://x/y" AS url') == ["url"]
    assert return_columns("RETURN 'http://x/y' AS url, e.b AS b") == ["url", "b"]


def test_an_unnameable_column_STILL_raises():
    """The fix must not turn a real parse failure into a silent wrong column name."""
    with pytest.raises(ColumnParseError):
        return_columns("RETURN e.participants")


def test_a_CALL_subquery_is_still_refused():
    """Comments are stripped BEFORE this guard, so the guard must still see a real one."""
    with pytest.raises(ColumnParseError, match="CALL"):
        return_columns("CALL { MATCH (x) RETURN x } RETURN x AS x")


def test_a_CALL_mentioned_only_in_a_COMMENT_is_not_a_subquery():
    """And stripping first is what buys this: prose about `CALL {` is not a `CALL {`."""
    assert return_columns(
        "// §10.1 removed the last CALL { } subquery from this module\n"
        "MATCH (e:Event) RETURN e.id AS id"
    ) == ["id"]
