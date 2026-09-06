"""T33 — every writer of a world-order edge must pass through the cycle guard.

`drop_cycles` refuses any edge whose target can already reach its source, and it is wired:
`infer_causal_edges` applies it before returning, and the one route that writes edges writes
only what that returns. Measured on the real stack, the live Event DAG is acyclic (0 nodes on
a cycle across 4 edges), and the detector was validated against a planted 3-node cycle so the
0 is a measurement rather than a blind spot.

What none of that protects is the SHAPE. `causal_edges.drop_cycles` says so itself:

    "Today every edge runs strictly forward in reading order, so the graph is a DAG by
     construction and this refuses nothing... The day that filter is relaxed the guarantee
     disappears SILENTLY — a cyclic world order answers 'did A happen before B' with yes in
     both directions, and nothing errors."

A second caller of `merge_causal_edges` that skipped `infer_causal_edges` would do exactly
that. This derives the callers instead of trusting that there is still one.
"""

from __future__ import annotations

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

#: The writer, and the guarded producer whose output it must be given.
_WRITER = "merge_causal_edges"
_GUARDED_PRODUCER = "infer_causal_edges"


def _callers_of(name: str, root: pathlib.Path) -> list[tuple[str, str]]:
    """`(module, enclosing function)` for every call to `name`, by AST."""
    out: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:  # pragma: no cover - a broken file is not this test's business
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == name):
                    out.append((str(path.relative_to(root)), fn.name))
    return out


def _calls_within(module: str, func: str, name: str, root: pathlib.Path) -> bool:
    tree = ast.parse((root / module).read_text(encoding="utf-8", errors="replace"))
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == func:
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == name):
                    return True
    return False


def test_every_world_order_writer_goes_through_the_cycle_guard():
    callers = _callers_of(_WRITER, APP)
    assert callers, (
        f"no caller of `{_WRITER}` was found at all — either the writer was renamed and this "
        f"test now guards nothing, or the write path was deleted. Both need a human."
    )
    unguarded = [
        (m, f) for m, f in callers
        if not _calls_within(m, f, _GUARDED_PRODUCER, APP)
    ]
    assert not unguarded, (
        f"{unguarded} write world-order edges without producing them through "
        f"`{_GUARDED_PRODUCER}`, which is the only thing that applies `drop_cycles`. A cyclic "
        f"world order answers 'did A happen before B' with yes in BOTH directions and nothing "
        f"errors — the guard's own docstring calls this out as the way the guarantee is lost."
    )


def test_the_guard_is_not_merely_PRESENT_but_applied_by_the_producer():
    """The control the caller-scan cannot supply.

    Every caller could route through `infer_causal_edges` while that function had quietly
    stopped calling `drop_cycles` — the scan above would still pass. This asserts the second
    link of the same chain.
    """
    assert _calls_within("extraction/causal_edges.py", _GUARDED_PRODUCER, "drop_cycles", APP), (
        f"`{_GUARDED_PRODUCER}` no longer applies `drop_cycles`; every caller routing through "
        f"it is now routing through nothing"
    )


def test_the_scan_would_FIND_an_unguarded_writer():
    """Rule 3 — validated on a case it was NOT derived from.

    Both assertions above are satisfied by a codebase with ONE correct caller, which is what
    this repo has; a scan that could not see a bad one would pass identically. This builds the
    bad case and requires the scan to fail on it.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "rogue.py").write_text(
            "async def writes_directly(session, pairs):\n"
            f"    return await {_WRITER}(session, pairs)\n",
            encoding="utf-8",
        )
        callers = _callers_of(_WRITER, root)
        assert callers == [("rogue.py", "writes_directly")], callers
        assert not _calls_within("rogue.py", "writes_directly", _GUARDED_PRODUCER, root), (
            "the scan reported a rogue writer as guarded — it cannot tell the two apart"
        )
