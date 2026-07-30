"""D-COMPOSITION-ID-TRAP — an AST gate: every `_book_or_deny` caller must re-bind its
project id from the gate's result.

`scope_meta` accepts a **work_id** in the `project_id` slot, because a book carries three
uuids and the agent mixes them up. That makes `_book_or_deny` the CANONICALIZATION point:
the id handed in may not be the project's, so the value used afterwards must come from
`meta.project_id`.

A gate that resolves while the query after it keeps comparing the RAW argument passes the
grant and then fails the scope check — which is exactly what shipped in the first cut of
this fix. `composition_get_outline_node` gated fine and still answered *"not found or not
accessible"* for the node it had just been granted, and it was caught only by calling the
live MCP endpoint. 34 call sites were repaired; nothing stops the 35th from forgetting.

So this is a rule with a gate, not a rule in a comment.
"""
from __future__ import annotations

import ast
from pathlib import Path

SERVER = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"


def _is_gate_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_book_or_deny"
    )


def _gate_calls(tree: ast.AST) -> list[ast.stmt]:
    """The INNERMOST statement wrapping each `_book_or_deny(...)` call.

    Deliberately not "every statement containing the call": `ast.walk` also yields the
    enclosing `if`/`try`/`FunctionDef`, and judging those would flag a perfectly
    canonicalized `pid = (await …).project_id` merely because it sits inside an `if`.
    Walk a parent map instead and take the nearest statement ancestor.
    """
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    out: list[ast.stmt] = []
    for node in ast.walk(tree):
        if not _is_gate_call(node):
            continue
        cur: ast.AST | None = node
        while cur is not None and not isinstance(cur, ast.stmt):
            cur = parent.get(cur)
        if cur is not None:
            out.append(cur)
    return out


def _binds_the_result(stmt: ast.stmt) -> bool:
    """True when the statement keeps the gate's answer — either
    `x = (await _book_or_deny(...)).project_id` or `meta = await _book_or_deny(...)`.
    A bare `await _book_or_deny(...)` throws the canonical ids away."""
    return isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.Return))


def test_no_caller_discards_the_gates_canonical_ids():
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    calls = _gate_calls(tree)
    # Sanity: the gate is widely used, so a passing test means something. If this number
    # collapses, the walk is broken rather than the code being clean.
    assert len(calls) >= 30, f"expected the gate to be used widely, found {len(calls)}"

    offenders = [
        (stmt.lineno, ast.unparse(stmt)[:100])
        for stmt in calls
        if not _binds_the_result(stmt) and not isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    assert not offenders, (
        "these call sites discard _book_or_deny's result, so they keep using the RAW "
        "project_id the caller passed. If that was actually a work_id the grant will "
        "pass and the very next scoped read will 404 — the D-COMPOSITION-ID-TRAP bug, "
        "re-introduced:\n"
        + "\n".join(f"  server.py:{ln}: {src}" for ln, src in offenders)
    )


def test_the_gate_detector_actually_fires_on_the_shape_it_bans():
    """A gate nobody has seen go red is a decoration. Prove it catches the bare form."""
    offending = ast.parse(
        "async def f():\n"
        "    await _book_or_deny(works, tc, pid, GrantLevel.EDIT)\n"
        "    return await outline.get_node(pid)\n"
    )
    calls = _gate_calls(offending)
    bare = [s for s in calls if not _binds_the_result(s)
            and not isinstance(s, ast.FunctionDef | ast.AsyncFunctionDef)]
    assert bare, "the detector must flag a bare `await _book_or_deny(...)`"


def test_the_detector_accepts_both_repaired_shapes():
    for good in (
        "async def f():\n    pid = (await _book_or_deny(w, tc, pid, L)).project_id\n",
        "async def f():\n    meta = await _book_or_deny(w, tc, pid, L)\n    pid = meta.project_id\n",
    ):
        calls = _gate_calls(ast.parse(good))
        bare = [s for s in calls if not _binds_the_result(s)
                and not isinstance(s, ast.FunctionDef | ast.AsyncFunctionDef)]
        assert not bare, f"a repaired shape must pass:\n{good}"
