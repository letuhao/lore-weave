"""The four `raw-sql-lint` baseline rows for `package_rekey.py` rest on a claim.
This is the claim, checked.

`scripts/raw-sql-lint.py` flags four sites in `app/db/package_rekey.py` where a
value is interpolated into SQL text rather than bound as `$1`. They are exempted
in that lint's BASELINE, and the exemption is sound **only because**:

  * every interpolated value is a module-level string literal, and
  * the table names come from module-level tuples of string literals.

Both are true today. Neither is enforced by anything in the module — and a
baseline row that outlives the fact it was granted for is worse than no row,
because it converts a real injection into a documented non-finding. That is
non-vacuity `NV-4`: two individually reasonable decisions (an exemption here, a
refactor there) combining to disable a check.

So this file parses the module with `ast` — deliberately WITHOUT importing it, so
it needs no database, no asyncpg and no settings — and reds the moment one of
those names stops being a literal. If someone later reads the table list from
`information_schema`, from config, or from a request, the four baseline rows stop
being justified and this test says so at that commit rather than at the incident.

Rewriting the four sites to use bind parameters is NOT the alternative: they emit
`DO $$ … $$` blocks, and PL/pgSQL blocks cannot take bind parameters at all.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[2] / "app" / "db" / "package_rekey.py"

# The names the baseline rows depend on. Each is interpolated into SQL text.
LITERAL_TUPLES = ("_USER_ID_RENAMES", "_OWNER_USER_ID_RENAMES", "_BOOK_ID_TABLES")
LITERAL_STRINGS = ("_MARKER",)


@pytest.fixture(scope="module")
def tree() -> ast.Module:
    assert MODULE.is_file(), f"{MODULE} is gone — the baseline rows point at nothing"
    return ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))


def _assignments(tree: ast.Module) -> dict[str, ast.expr]:
    """Module-level `NAME = <expr>` only. A name assigned inside a function or a
    conditional is exactly the dynamic case this test exists to catch, so it is
    NOT collected — an absent name fails below rather than passing quietly."""
    out: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                out[node.target.id] = node.value
    return out


@pytest.mark.parametrize("name", LITERAL_TUPLES)
def test_interpolated_table_lists_are_literal_tuples_of_strings(tree, name):
    """A table name reaching SQL text must be one this file spells out."""
    assigned = _assignments(tree)
    assert name in assigned, (
        f"{name} is not a module-level assignment. If it moved into a function or "
        f"became conditional, the raw-sql-lint BASELINE rows for package_rekey.py "
        f"are no longer justified — the values they exempt may now be dynamic."
    )
    node = assigned[name]
    assert isinstance(node, (ast.Tuple, ast.List)), (
        f"{name} is a {type(node).__name__}, not a literal tuple/list. A computed "
        f"table list can carry a value from config, the database or a request "
        f"straight into interpolated SQL."
    )
    for i, el in enumerate(node.elts):
        assert isinstance(el, ast.Constant) and isinstance(el.value, str), (
            f"{name}[{i}] is not a string literal (got {ast.dump(el)[:80]}). Every "
            f"element is interpolated into `ALTER TABLE {{table}}` and into a "
            f"`WHERE table_name = '{{table}}'` inside a DO block, where no bind "
            f"parameter is available."
        )


@pytest.mark.parametrize("name", LITERAL_STRINGS)
def test_interpolated_scalars_are_string_literals(tree, name):
    assigned = _assignments(tree)
    assert name in assigned, f"{name} is not a module-level assignment"
    node = assigned[name]
    assert isinstance(node, ast.Constant) and isinstance(node.value, str), (
        f"{name} must be a string literal — it is interpolated into "
        f"`DELETE FROM package_migration WHERE marker = '{{marker}}'`."
    )


def test_the_public_entry_points_take_no_table_name():
    """The other half of the argument: nothing crosses a request boundary.

    `run_package_rekey` / `revert_package_rekey` are the module's public surface.
    They take a connection (and, for the former, a schema callable) — no table,
    no column, no marker. A new parameter here is the shape that would let a
    caller choose what gets interpolated, so it must be a deliberate change and
    not a quiet one.
    """
    src = ast.parse(MODULE.read_text(encoding="utf-8"))
    sigs = {
        n.name: [a.arg for a in n.args.args]
        for n in ast.walk(src)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name in {"run_package_rekey", "revert_package_rekey"}
    }
    assert sigs, "neither public entry point was found — did they get renamed?"
    for fn, args in sigs.items():
        unexpected = set(args) - {"conn", "apply_schema"}
        assert not unexpected, (
            f"{fn}() gained parameter(s) {sorted(unexpected)}. If any of them can "
            f"reach a table/column/marker name, the raw-sql-lint BASELINE rows for "
            f"this module are void — an interpolated identifier would then be "
            f"caller-controlled."
        )
