"""Every keyword a CALLER passes to a GraphStore method must exist on the port.

🔴 THE BUG THIS EXISTS FOR, found by a browser e2e and not by any test.

`POST /v1/knowledge/events` called `store.merge_event(..., provenance="human_authored")`.
No adapter accepted `provenance`, so authoring an event from the Studio raised
`TypeError: AgeGraphStore.merge_event() got an unexpected keyword argument 'provenance'`
— a 500 on every backend, not just AGE.

WHY THE CONFORMANCE SUITE DID NOT CATCH IT, which is the part worth keeping.
`test_graph_store_port.py` asserts, for a checklist of methods including `merge_event`,
that `inspect.signature(adapter.m).parameters == inspect.signature(GraphStore.m).parameters`.
It passed. It was RIGHT to pass: every adapter matched the port exactly. **The port was
the thing that was wrong** — `merge_entity` and `merge_fact` had carried `provenance`
since T68, and `graph_repos.events.merge_event` had too, but the port's `merge_event` and
therefore every adapter omitted it. A suite that only compares implementations to a
contract cannot see a contract that is missing something its callers need; everyone
agreed, on the wrong shape.

So this test looks the OTHER way down the seam: from the call sites INTO the port.
"""

from __future__ import annotations

import ast
import inspect
import os

from app.ports.graph_store import GraphStore

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.normpath(os.path.join(_HERE, "..", "..", "app"))

#: Directories whose `.merge_event(...)` calls are NOT port calls.
#:
#: `app/adapters/**` implements the port and legitimately calls the layer beneath it —
#: `Neo4jGraphStore.merge_event` forwards to `graph_repos.events.merge_event`, whose
#: signature is its own. `app/db/**` IS that layer. Scanning either against the port would
#: compare a function to a contract it does not implement, and the first false positive
#: would be the very pass-through this bug was about.
#: ⚠️ Compared with `_under()`, NOT `str.startswith` on a trailing-separator string. The
#: first cut wrote `os.path.join(_APP, "adapters") + os.sep` and tested
#: `root.startswith(...)`, which never matched the adapters directory ITSELF (os.walk
#: yields it without a trailing separator) — only its subdirectories. It was invisible
#: while the port was correct and surfaced the moment the bite removed `provenance`:
#: `neo4j_graph_store.py:276` was reported as a violation, which is the forwarding call
#: this exclusion exists to permit. An exclusion that excludes nothing is the same defect
#: as a guard that guards nothing.
_NOT_PORT_CALLERS = (
    os.path.join(_APP, "adapters"),
    os.path.join(_APP, "db"),
)


def _under(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent + os.sep)

#: Non-vacuity floor. If the walk finds nothing — a moved tree, a renamed method, an AST
#: shape this misses — it must fail rather than report a clean scan of zero call sites.
#: Measured 2026-08-31: 27 keyword-bearing port calls across the service.
_MIN_CALLS = 15


def _port_methods() -> dict[str, set[str]]:
    """Every public port method, mapped to the keyword names it accepts."""
    out: dict[str, set[str]] = {}
    for name, fn in inspect.getmembers(GraphStore, inspect.isfunction):
        if name.startswith("_"):
            continue
        out[name] = set(inspect.signature(fn).parameters)
    return out


def _port_calls():
    """(file, line, method, keyword) for every `<x>.<port method>(k=...)` outside adapters."""
    methods = _port_methods()
    found = []
    for root, _dirs, files in os.walk(_APP):
        if any(_under(root, d) for d in _NOT_PORT_CALLERS) or "__pycache__" in root:
            continue
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(root, fname)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except SyntaxError:  # not this test's job to police syntax
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                if not isinstance(fn, ast.Attribute) or fn.attr not in methods:
                    continue
                for kw in node.keywords:
                    if kw.arg is None:  # `**kwargs` — nothing statically checkable
                        continue
                    found.append((os.path.relpath(path, _APP), node.lineno, fn.attr, kw.arg))
    return found


def test_no_caller_passes_a_keyword_the_port_does_not_declare():
    methods = _port_methods()
    calls = _port_calls()

    assert len(calls) >= _MIN_CALLS, (
        f"found only {len(calls)} keyword-bearing port call(s), floor is {_MIN_CALLS} — the "
        f"walk is broken, and a scan that finds nothing passes for the wrong reason"
    )

    unknown = [
        f"  {rel}:{line} — {meth}({kw}=...) is not a parameter of GraphStore.{meth}; "
        f"the port accepts {sorted(methods[meth] - {'self'})}"
        for rel, line, meth, kw in calls
        if kw not in methods[meth]
    ]
    assert not unknown, (
        "a caller passes a keyword the port does not declare. Every adapter can match the "
        "port perfectly and this still raises TypeError at runtime, which is exactly how "
        "the create-event route shipped broken:\n" + "\n".join(unknown)
    )


def test_the_walk_actually_reaches_the_route_that_broke():
    """The control. The floor above proves the walk found SOMETHING; this proves it found
    the specific call site whose absence let the bug through, so a future refactor that
    stops reaching `routers/` cannot leave this test green and blind."""
    calls = _port_calls()
    hits = [c for c in calls if c[2] == "merge_event" and "routers" in c[0]]
    assert hits, (
        "the walk found no `merge_event` call under routers/ — that is the exact call site "
        "that raised TypeError in production, so a walk that cannot see it proves nothing"
    )
