#!/usr/bin/env python3
"""graph-tenancy-coupling-gate — the shared graph is safe for a reason NOTHING states.

Measured on iso 2026-08-30: `g_shared` holds **5683 entities across 10+ projects**. The service
builds `AgeGraphStore(pool, graph_name_for(None))` deliberately — the provider's own comment says
the shared graph "reproduces Neo4j exactly", because Neo4j holds every project in one database and
scopes by `user_id`/`project_id` PROPERTIES. So tenant isolation in the graph is a predicate, not
a database boundary.

**And the traversal has no predicate.** `neighborhood` filters the ANCHOR by project:

    MATCH (e:Entity) WHERE ... e.project_id = '<pid>' RETURN e

then walks edges by id alone:

    MATCH (subj:Entity)-[r:RELATES_TO]->(obj:Entity)
    WHERE (subj.id = '<id>' OR obj.id = '<id>') ...

Nothing there names a project. That query returns only same-project rows for exactly one reason:

    key = f"v{canonical_version}:{user_id}:{project_id or 'global'}:{kind}:{canonical}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]

**`project_id` is IN THE HASH.** Two projects cannot mint the same entity id, so an id match can
never cross a tenant. Measured: 0 of 5683 ids appear under more than one project, and all 33
endpoints of a live 50-edge read sat in one project.

WHY THIS IS A GATE AND NOT A COMMENT
────────────────────────────────────
Dropping `project_id` from a hash key is an ordinary-looking refactor — the docstring above it
even calls the id "collision-free at any conceivable scale for a single user x project namespace",
which reads like the scope is handled elsewhere. **MEASURED, not assumed:**

    BITE 1  remove the project segment outright   -> 1 of 1026 SDK tests reds, and it is an
            incidental one inside `test_entity_extractor.py` asserting global != a project
    BITE 2  keep the project's PRESENCE, lose its IDENTITY
            (`{project_id and 'global' or 'global'}`)
            -> **1026 passed, 9 skipped, 0 failed** — and `entity_canonical_id('u', 'A', 'Kai',
            'person') == entity_canonical_id('u', 'B', 'Kai', 'person')`

`test_canonical.py`, the file that owns this function, does not contain the word "project". The
one assertion in the SDK compares global against a project, never project A against project B —
so the collapse that actually enables a cross-tenant read is invisible to the whole suite.

So this asserts the COUPLING rather than either half:

    shared graph + no endpoint predicate  =>  the id MUST be project-scoped

Either mechanism alone is sufficient, which is why the verdict names WHICH one is holding — a gate
that demanded both would red on a correct design that chose the other.

Usage
    python scripts/graph-tenancy-coupling-gate.py --selftest
    python scripts/graph-tenancy-coupling-gate.py
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "sdks" / "python" / "loreweave_extraction" / "canonical.py"
ADAPTER = ROOT / "services" / "knowledge-service" / "app" / "adapters" / "age_graph_store.py"
PROVIDER = ROOT / "services" / "knowledge-service" / "app" / "adapters" / "graph_store_provider.py"

KEYED, FILTERED, UNPROTECTED, NOT_SHARED, ERROR = (
    "KEYED", "FILTERED", "UNPROTECTED", "NOT-SHARED", "ERROR")


def id_is_project_scoped(canonical_src: str | None = None) -> bool | None:
    """Do two DIFFERENT projects mint different entity ids? Asked by CALLING the function.

    This was a substring check on the `key = f"..."` line, and a held-out mutation walked
    straight through it: `{project_id and 'global' or 'global'}` names `project_id`, reads
    "scoped", and collapses every project into one namespace. The detector had been validated
    only on mutations derived from the text it read — green by construction.

    So it now runs the thing. `canonical_src` is accepted for the selftest, which writes a
    variant to a temp module and imports THAT; None means the repo's own function.
    """
    import hashlib  # noqa: F401 — available to an exec'd variant
    try:
        if canonical_src is None:
            sys.path.insert(0, str(ROOT / "sdks" / "python"))
            try:
                from loreweave_extraction.canonical import entity_canonical_id as fn
            finally:
                sys.path.pop(0)
        else:
            ns: dict = {}
            exec(compile(canonical_src, "<variant>", "exec"), ns)  # noqa: S102 — selftest only
            fn = ns.get("entity_canonical_id")
            if fn is None:
                return None
        a = fn("u", "01a00000-0000-7000-8000-00000000000a", "Kai", "person")
        b = fn("u", "01a00000-0000-7000-8000-00000000000b", "Kai", "person")
        g = fn("u", None, "Kai", "person")
    except Exception:  # noqa: BLE001 — an unrunnable source is never read as safe
        return None
    # Both halves matter: A != B is the cross-tenant property, and a project differing from
    # `global` is what the SDK suite's one incidental assertion already covers.
    return a != b and a != g


def traversal_filters_project(adapter_src: str) -> bool | None:
    """Does the edge traversal constrain BOTH endpoints to a project?

    One endpoint is not enough: an edge is returned when EITHER end matches the anchor, so a
    predicate on `subj` alone still admits a foreign `obj`.
    """
    m = re.search(r"MATCH \((\w+):Entity\)-\[(\w+):\w+\]->\((\w+):Entity\)", adapter_src)
    if not m:
        return None
    subj, _rel, obj = m.group(1), m.group(2), m.group(3)
    tail = adapter_src[m.end(): m.end() + 1200]
    return f"{subj}.project_id" in tail and f"{obj}.project_id" in tail


def uses_shared_graph(provider_src: str) -> bool | None:
    """Does the SERVICE construct its AGE store on the shared graph?

    `graph_name_for(None)` is the shared graph; `graph_name_for(project_id)` is one graph per
    project, under which the coupling is moot because the engine enforces the boundary.
    """
    if "AgeGraphStore(" not in provider_src:
        return None
    return "graph_name_for(None)" in provider_src


def verdict(shared: bool | None, filtered: bool | None, keyed: bool | None) -> dict:
    """Pure. Either mechanism suffices; the verdict says WHICH one is carrying the isolation."""
    if shared is None or filtered is None or keyed is None:
        return {"verdict": ERROR, "reason":
                "a source this gate derives from could not be parsed — an unreadable input is "
                "never read as safe"}
    if not shared:
        return {"verdict": NOT_SHARED, "reason":
                "the service builds a graph PER PROJECT, so the engine enforces the boundary and "
                "an unfiltered traversal cannot cross one"}
    if filtered:
        return {"verdict": FILTERED, "reason":
                "the traversal constrains both endpoints to the project, so isolation holds "
                "independently of how entity ids are derived"}
    if keyed:
        return {"verdict": KEYED, "reason":
                "the traversal names no project, and isolation rests ENTIRELY on `project_id` "
                "being inside the entity-id hash. A key that keeps the project's PRESENCE "
                "but loses its IDENTITY leaves the SDK suite fully green (measured: 1026 "
                "passed) while two projects mint the same id"}
    return {"verdict": UNPROTECTED, "reason":
            "the projects share one graph, the traversal constrains neither endpoint, and the "
            "entity id is NOT project-scoped — two projects naming an entity alike collide, and "
            "an id match returns the other tenant's relationships"}


def _selftest() -> int:
    real_keyed = id_is_project_scoped()
    real_filtered = traversal_filters_project(ADAPTER.read_text(encoding="utf-8"))
    real_shared = uses_shared_graph(PROVIDER.read_text(encoding="utf-8"))

    V = 'import hashlib\ndef entity_canonical_id(user_id, project_id, name, kind, canonical_version=1):\n    key = f"v{canonical_version}:{user_id}:%s:{kind}:{name}"\n    return hashlib.sha256(key.encode(\'utf-8\')).hexdigest()[:32]\n'
    scoped = V % "{project_id or 'global'}"
    dropped = V % "fixed"
    #: THE HELD-OUT CASE. Names `project_id`, so the substring check this replaced read it as
    #: scoped — and every project collapses into one namespace.
    collapsed = V % "{project_id and 'global' or 'global'}"

    bare = ("MATCH (subj:Entity)-[r:RELATES_TO]->(obj:Entity) "
            "WHERE (subj.id = {x} OR obj.id = {x}) ")
    both = bare.replace("OR obj.id = {x}) ",
                        "OR obj.id = {x}) AND subj.project_id = {p} AND obj.project_id = {p} ")
    one = bare.replace("OR obj.id = {x}) ", "OR obj.id = {x}) AND subj.project_id = {p} ")

    cases = [
        ("TODAY'S SHAPE: shared graph, unfiltered walk, project inside the id",
         verdict(True, False, True), KEYED),
        ("THE REGRESSION: an id that stops separating projects, nothing else changed",
         verdict(True, False, False), UNPROTECTED),
        ("a traversal that filters both ends is safe even with an unscoped id",
         verdict(True, True, False), FILTERED),
        ("per-project graphs make the coupling moot", verdict(False, False, False), NOT_SHARED),
        ("...and that stays true however the id is derived", verdict(False, False, True),
         NOT_SHARED),
        ("an unparseable source is ERROR, never a pass", verdict(True, None, True), ERROR),
        ("THE SCOPING PROBE is behavioural: a project-keyed id separates two projects",
         id_is_project_scoped(scoped), True),
        ("...an id ignoring the project does not", id_is_project_scoped(dropped), False),
        ("THE HELD-OUT MUTATION: a key that NAMES `project_id` and still collapses every "
         "project is caught — the substring check this replaced returned KEYED here",
         id_is_project_scoped(collapsed), False),
        ("a source with no such function is None, not False",
         id_is_project_scoped("x = 1"), None),
        ("a source that raises is None, never a pass",
         id_is_project_scoped("def entity_canonical_id(*a, **k):" + chr(10)
                              + "    raise RuntimeError"), None),
        ("THE ENDPOINT PARSER: both endpoints constrained reads filtered",
         traversal_filters_project(both), True),
        ("ONE endpoint is NOT enough — an edge matches on either end, so a foreign peer is "
         "still admitted", traversal_filters_project(one), False),
        ("no traversal at all is None", traversal_filters_project("MATCH (n) RETURN n"), None),
        ("the REAL entity_canonical_id runs, and separates two projects", real_keyed, True),
        ("the REAL adapter parses, and its traversal names no project", real_filtered, False),
        ("the REAL provider parses, and the service uses the SHARED graph", real_shared, True),
    ]
    failures = 0
    print("graph-tenancy-coupling-gate - selftest (offline)")
    for label, got, want in cases:
        actual = got["verdict"] if isinstance(got, dict) else got
        ok = actual == want
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: expected {want}, got {actual}")
    print(chr(10) + "  all checks passed" if not failures
          else chr(10) + f"  {failures} FAILED")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()

    try:
        shared = uses_shared_graph(PROVIDER.read_text(encoding="utf-8"))
        filtered = traversal_filters_project(ADAPTER.read_text(encoding="utf-8"))
        keyed = id_is_project_scoped()
    except OSError as e:
        print(f"[graph-tenancy-coupling] ERROR — {e}")
        return 1

    v = verdict(shared, filtered, keyed)
    print(f"[graph-tenancy-coupling] shared_graph={shared} · traversal_filters_project={filtered}"
          f" · id_is_project_scoped={keyed}")
    print(f"[graph-tenancy-coupling] {v['verdict']} — {v['reason']}")
    return 0 if v["verdict"] in (KEYED, FILTERED, NOT_SHARED) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
