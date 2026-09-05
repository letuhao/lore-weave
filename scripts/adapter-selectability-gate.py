#!/usr/bin/env python3
"""adapter-selectability-gate.py — an adapter you can TEST but cannot SELECT is not shipped.

T56(a), from spec §8.4's rot table. The sharpest pattern this plan hit, in its own words:

    T42/T43 closed green with 30 conformance tests passing while the thing they built could
    not be selected — which is T54's entire existence.

`AgeGraphStore` was written, conformance-tested against a real AGE database, compared in a
shadow differential, and `KNOWLEDGE_GRAPH_BACKEND=age` **raised**. Every suite was green. The
gap between "the adapter works" and "the adapter is reachable" is invisible to a test suite,
because a suite constructs the adapter itself — that is exactly what makes it a suite.

── THE RULE ─────────────────────────────────────────────────────────────────────────────────
An adapter exercised by a conformance / parity / shadow suite must either be

  * **CONSTRUCTIBLE BY A PROVIDER** — some `*_provider.py` names its class, so a configuration
    value reaches it; or
  * **DECLARED EVALUATION-ONLY** below, with the reason.

The second arm is not a loophole, it is the point. `KuzuGraphStore` is deliberately not
selectable and that fact should be *written down* rather than inferred from a provider that
happens not to mention it — which is indistinguishable, from the outside, from having
forgotten.

⚠️ **Both halves are DERIVED.** A hand-list of "adapters with suites" would go stale the day
someone adds one, which is the failure mode `knowledge-http-surface-gate` had for four
federated reads (T55a). The suites and the providers are both read off disk.

Usage:
  python scripts/adapter-selectability-gate.py             # scan
  python scripts/adapter-selectability-gate.py --selftest  # prove it can go red
"""
from __future__ import annotations

import ast
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ADAPTER_DIR = os.path.join("services", "knowledge-service", "app", "adapters")
SUITE_DIR = os.path.join("services", "knowledge-service", "tests", "integration", "db")

#: A test file whose NAME says it exercises adapters interchangeably. A suite that constructs
#: two implementations and compares them is precisely where an unreachable adapter hides: it
#: passes, and nothing it asserts has anything to do with being selectable.
_SUITE_MARKERS = ("conformance", "parity", "shadow", "differential")

#: Adapters that are exercised on purpose and NOT meant to be selectable. Each needs a reason,
#: and the reason is checked for existence — an empty string is a silent exemption wearing a
#: declaration's clothes.
EVALUATION_ONLY: dict[str, str] = {
    "KuzuGraphStore": (
        "X1 engine candidate, compared by the shadow harness and never served from. Kuzu is "
        "EMBEDDED with a single write handle per database file, which the plan records as "
        "'the single biggest input to the engine choice' — a service process cannot hold it "
        "the way it holds a Neo4j driver or an asyncpg pool. It is measured, not deployed."
    ),
    "FakeGraphStore": (
        "the in-memory double the port's own 14 tests run against. A provider that could "
        "return it would let a misconfiguration serve an empty graph that answers every read."
    ),
    "ShadowGraphStore": (
        "the comparison harness itself — it WRAPS two real stores rather than being one. "
        "T43 constructs it explicitly; selecting it from configuration would mean running "
        "every production read twice."
    ),
}


def _classes_defined(path: str) -> list[str]:
    """Top-level class names defined in `path`."""
    try:
        tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
    except (OSError, SyntaxError):
        return []
    return [n.name for n in tree.body if isinstance(n, ast.ClassDef)]


def adapter_classes(root: str) -> dict[str, str]:
    """`{class name: module}` for every class defined under the adapters package."""
    out: dict[str, str] = {}
    adir = os.path.join(root, ADAPTER_DIR)
    if not os.path.isdir(adir):
        return out
    for fname in sorted(os.listdir(adir)):
        if not fname.endswith(".py") or fname == "__init__.py":
            continue
        for cls in _classes_defined(os.path.join(adir, fname)):
            out[cls] = fname[:-3]
    return out


def _constructed_in(src: str) -> set[str]:
    """Class names this source CALLS — `Foo(...)`, not merely imports."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            out.add(node.func.id)
    return out


def provider_reachable(root: str) -> set[str]:
    """Classes some `*_provider.py` can construct — i.e. configuration can reach them."""
    out: set[str] = set()
    adir = os.path.join(root, ADAPTER_DIR)
    if not os.path.isdir(adir):
        return out
    for fname in sorted(os.listdir(adir)):
        if not fname.endswith("_provider.py"):
            continue
        try:
            src = open(os.path.join(adir, fname), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        out |= _constructed_in(src)
    return out


def suite_exercised(root: str, known: dict[str, str]) -> dict[str, list[str]]:
    """`{class name: [suite files]}` for adapters an interchangeability suite constructs."""
    out: dict[str, list[str]] = {}
    sdir = os.path.join(root, SUITE_DIR)
    if not os.path.isdir(sdir):
        return out
    for fname in sorted(os.listdir(sdir)):
        if not fname.endswith(".py"):
            continue
        if not any(m in fname for m in _SUITE_MARKERS):
            continue
        try:
            src = open(os.path.join(sdir, fname), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for cls in _constructed_in(src) & set(known):
            out.setdefault(cls, []).append(fname)
    return out


def check(root: str) -> list[str]:
    """Adapters a suite exercises that neither a provider can build nor a declaration excuses."""
    known = adapter_classes(root)
    reachable = provider_reachable(root)
    findings = []
    for cls, suites in sorted(suite_exercised(root, known).items()):
        if cls in reachable:
            continue
        reason = EVALUATION_ONLY.get(cls)
        if reason and reason.strip():
            continue
        findings.append(
            f"{cls} ({known[cls]}.py) is exercised by {', '.join(suites)} but no provider can "
            f"construct it and it is not declared EVALUATION_ONLY"
        )
    return findings


def selftest() -> int:
    ok = True
    print("adapter-selectability-gate - selftest (offline)")

    def expect(label: str, got, want) -> None:
        nonlocal ok
        good = got == want
        ok = ok and good
        print(f"  {'PASS' if good else 'FAIL'}  {label}: expected {want!r}, got {got!r}")

    # The founding case, reconstructed: an adapter a suite builds and no provider can.
    expect("a suite-exercised adapter with no provider and no declaration is FLAGGED",
           bool(_would_flag({"AgeGraphStore"}, set(), {"AgeGraphStore"}, {})), True)
    expect("...the same adapter, once a provider can construct it",
           bool(_would_flag({"AgeGraphStore"}, {"AgeGraphStore"}, {"AgeGraphStore"}, {})), False)
    expect("...or once it is DECLARED evaluation-only with a reason",
           bool(_would_flag({"AgeGraphStore"}, set(), {"AgeGraphStore"},
                            {"AgeGraphStore": "measured, never served"})), False)
    expect("an EMPTY reason is not a declaration",
           bool(_would_flag({"AgeGraphStore"}, set(), {"AgeGraphStore"},
                            {"AgeGraphStore": "   "})), True)
    expect("an adapter no suite exercises is none of this gate's business",
           bool(_would_flag({"PgVectorStore"}, set(), set(), {})), False)

    # Derivation, on cases it was not written from.
    expect("a class is 'constructed' by a CALL, not by an import",
           "Foo" in _constructed_in("from x import Foo\ny = Foo"), False)
    expect("...and IS by a call", "Foo" in _constructed_in("y = Foo(1)"), True)
    expect("a suite file is recognised by name",
           any(m in "test_graph_store_conformance.py" for m in _SUITE_MARKERS), True)
    expect("an ordinary repo test is not a suite",
           any(m in "test_entities_repo.py" for m in _SUITE_MARKERS), False)

    # The live tree must have something to say — a gate that finds no suites is blind.
    live = suite_exercised(REPO_ROOT, adapter_classes(REPO_ROOT))
    expect("the real tree yields at least one suite-exercised adapter", bool(live), True)
    expect("every EVALUATION_ONLY entry carries a non-empty reason",
           all(v and v.strip() for v in EVALUATION_ONLY.values()), True)

    print(f"{chr(10)}  {'all checks passed' if ok else 'SELFTEST FAILED'}")
    return 0 if ok else 1


def _would_flag(known: set[str], reachable: set[str], exercised: set[str],
                declared: dict[str, str]) -> list[str]:
    """The rule, isolated from disk, so the selftest exercises the RULE and not a fixture."""
    out = []
    for cls in sorted(exercised & known):
        if cls in reachable:
            continue
        reason = declared.get(cls)
        if reason and reason.strip():
            continue
        out.append(cls)
    return out


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    findings = check(REPO_ROOT)
    known = adapter_classes(REPO_ROOT)
    exercised = suite_exercised(REPO_ROOT, known)
    if not findings:
        print(f"[adapter-selectability-gate] OK — {len(exercised)} adapter(s) exercised by a "
              f"conformance/parity/shadow suite; every one is either constructible from a "
              f"provider or declared evaluation-only ({len(EVALUATION_ONLY)} declared)")
        return 0
    print("[adapter-selectability-gate] FAIL — built, tested, and UNSELECTABLE:\n")
    for f in findings:
        print(f"    {f}")
    print(
        "\n  An adapter a suite constructs is not thereby reachable: the suite builds it "
        "itself.\n  T42/T43 closed green with 30 conformance tests while "
        "`KNOWLEDGE_GRAPH_BACKEND=age`\n  raised, and closing that gap is T54's entire "
        "existence.\n\n  Either let a provider construct it, or declare it EVALUATION_ONLY "
        "in this file WITH\n  the reason — so 'deliberately not selectable' is written down "
        "rather than inferred\n  from a provider that happens not to mention it.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
