#!/usr/bin/env python3
"""agentruntime-membrane-gate — M2: the new surface can reach nothing but its own manifest.

WHAT THIS ENFORCES, AND WHY IT IS AN IMPORT GATE RATHER THAN A TEST
-------------------------------------------------------------------
`ARCHITECTURE.md` §3 forbids a **code path**, not a wrong result:

    Old declarations are not hidden. They are ABSENT. There is no branch in the
    new assembler that can read the old catalog - not one that is disabled, not
    one behind a flag.

A behavioural test cannot establish that. It shows that the path was not taken on
the inputs it tried; the claim is that the path does not exist. This repository
has produced "invisibility implemented as a filter" thirteen times, and every
instance eventually leaked or deleted the wrong thing - a filter passes its tests
right up until the input that finds its gap.

M2 is the load-bearing membrane property for exactly that reason. M1, M3 and M4
are enforceable by tests, and M2 is what makes those tests MEAN something, by
removing the possibility rather than sampling it.

AN ALLOWLIST, NOT A DENYLIST - AND THAT CHOICE IS THE GATE
-----------------------------------------------------------
A denylist of legacy modules is DEFAULT-PERMITTED: a legacy module written
tomorrow is reachable until someone remembers to add it. That is the same
default-uncovered mistake `gate-wiring-gate` exists to stop, and this repo has
made it enough times to have a standard about it.

So: `app/agentruntime/**` may import the standard library and itself. Nothing
else. A future need is an explicit line in ALLOWED_EXTERNAL with a reason - which
is a decision someone makes on purpose, in a diff, rather than a coupling that
accretes.

WHAT IT CANNOT SEE, SAID OUT LOUD
----------------------------------
Static imports only. `importlib.import_module(name)` with a computed name, or a
value handed in at runtime from a caller that DID import the legacy catalog, are
outside what this can prove - so it also rejects `importlib` and `__import__`
inside the package, which is the reachable half of that hole. The unreachable
half is a caller passing legacy data in through a normal argument; that is the
type system's job (`build()` takes `Admitted`, which only `admit()` produces) and
V-CODE's, not this gate's. A gate that claimed otherwise would be the more
dangerous thing: a check that reports safety it does not have.

Run:  python scripts/agentruntime-membrane-gate.py [--selftest]
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "services" / "chat-service" / "app" / "agentruntime"
PACKAGE_MODULE = "app.agentruntime"

# Nothing yet, and that emptiness is the point. Each future entry needs a reason
# in this dict, so the coupling is visible in the diff that introduces it.
ALLOWED_EXTERNAL: dict[str, str] = {}

# Dynamic import machinery. Static analysis cannot follow these, so inside this
# package they are refused outright rather than silently unchecked.
#
# NOTE, and the selftest is why this comment exists: `importlib` is STDLIB, so an
# earlier version of this gate allowed `import importlib` through the stdlib
# branch and only rejected `importlib.import_module(...)` as a Call. The gate's
# own --selftest caught it on the first run. Forbidden modules are therefore
# checked BEFORE the stdlib allowance, not after - a denylist that runs second is
# a denylist that never runs.
FORBIDDEN_CALLS = {"__import__", "importlib"}
FORBIDDEN_MODULES = {"importlib"}

_STDLIB = set(sys.stdlib_module_names)


def _root(module: str) -> str:
    return module.split(".", 1)[0]


def _is_internal(module: str, *, from_file: Path) -> bool:
    """A relative import, or an absolute one naming this package.

    🔴 THE TRAILING DOT IS THE GATE. This read `module.startswith(PACKAGE_MODULE)`, so
    `app.agentruntime_bridge` and `app.agentruntimeX` were both treated as INTERNAL and
    waved through - a sibling module one underscore away could import the entire
    legacy catalog and re-export it, defeating M2 completely while the gate stayed
    green. A prefix test on a dotted namespace must anchor on the separator, or it
    matches names that merely start with the same letters.
    """
    for root in (PACKAGE_MODULE, "agentruntime"):
        if module == root or module.startswith(root + "."):
            return True
    return False


def _violations_in(path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:      # `from .x import y` - inside the package
                continue
            mod = node.module or ""
            if _root(mod) in FORBIDDEN_MODULES:
                out.append((node.lineno, f"from {mod} import ... - dynamic import, unanalysable"))
                continue
            if _is_internal(mod, from_file=path) or _root(mod) in _STDLIB:
                continue
            if mod in ALLOWED_EXTERNAL or _root(mod) in ALLOWED_EXTERNAL:
                continue
            out.append((node.lineno, f"from {mod} import ..."))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if _root(mod) in FORBIDDEN_MODULES:
                    out.append((node.lineno, f"import {mod} - dynamic import, unanalysable"))
                    continue
                if _is_internal(mod, from_file=path) or _root(mod) in _STDLIB:
                    continue
                if mod in ALLOWED_EXTERNAL or _root(mod) in ALLOWED_EXTERNAL:
                    continue
                out.append((node.lineno, f"import {mod}"))
        elif isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name in FORBIDDEN_CALLS:
                out.append((node.lineno, f"dynamic import via {name}() - unanalysable"))
    return out


# Types whose construction must stay single-sited, and what each one guarantees.
#
#   Admitted - ARCHITECTURE 6.1 row 5. `admit()` is the ONLY producer; a second
#     construction site is that guarantee gone, and it reads as ordinary code.
#   Surface  - CP-1.7 / P1. A Surface built outside `assemble()` can carry `names`
#     that its `withheld` does not account for, bypassing the post-condition that
#     enforces `offered + registered == admitted`.
#
# WHAT THIS CHECK IS WORTH, MEASURED RATHER THAN ASSERTED. It counts a plain
# in-package `Surface(...)` call. Executed on four spellings by a verifier: an
# attribute call (`_m.Surface(...)`), an alias, and any construction OUTSIDE this
# package all pass. So it raises the COST of a second site; it does not make one
# impossible, and no sentence here may say otherwise.
#
# THE THIRD COPY LIVED HERE. This comment used to say "assemble() is the only
# place a declaration can be dropped" - false, because `discover(kind=)` drops
# them too (it registers, but it drops). The same sentence was corrected in
# surface.py, then found again in narrowing.py a round later, then found HERE a
# round after that. Three files, three rounds, one claim: a correction applied
# where the verifier was looking, and nowhere else.
SINGLE_SITED = {"Admitted": 1, "Surface": 1}


def _construction_sites(type_name: str) -> list[tuple[Path, int]]:
    sites: list[tuple[Path, int]] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == type_name:
                sites.append((path, node.lineno))
    return sites


MANIFEST = REPO / "contracts" / "agent-runtime-manifest.json"

# ARCHITECTURE 6.1 layer 2 - the DETECTION boundary, and it has to be a real scan.
#
# The clause claims a deliberate bypass of `Admitted` is "loud in a diff" because it
# must name a private symbol or call object.__setattr__. A verifier checked whether
# anything performed that scan and found NOTHING did: the claim was a description of
# what a gate COULD do, written as though it did. That is the same defect the same
# clause was amended twice to remove, one row below the correction. So it is a scan now.
#
# Scope is the whole repo EXCEPT admission.py, which legitimately holds the token and
# uses object.__setattr__ in its own __init__ - the boundary is "outside the module
# that defines it", not "nowhere".
_ADMISSION_REL = "services/chat-service/app/agentruntime/admission.py"
BYPASS_SIGNALS = {
    "_TOKEN": "imports or names the private admission token",
    "_AdmissionToken": "names the admission token type",
}


def _forgery_violations_in(path: Path) -> list[tuple[int, str]]:
    """Token-naming and frozen-bypass signals in one file. Separate from the walk so the
    self-test can fire it on synthetic files - a scan nobody has watched go red is the
    thing this gate exists to stop other people shipping."""
    out: list[tuple[int, str]] = []
    try:
        src = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    if "agentruntime" not in src and "Admitted" not in src:
        return out
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.Name):
            names = [node.id]
        elif isinstance(node, ast.Attribute):
            names = [node.attr]
        for n in names:
            if n in BYPASS_SIGNALS:
                out.append((node.lineno, f"{BYPASS_SIGNALS[n]} ({n})"))
        # object.__setattr__(...) - the frozen-dataclass bypass. `frozen` blocks
        # `a.x = ...` and not this form, which is how an Admitted is mutated or a
        # forged one is filled.
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "__setattr__"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "object"):
            out.append((node.lineno, "object.__setattr__ in a module that touches agentruntime"))
    return out


def _forgery_scan() -> int:
    """Every place outside `admission.py` that names the token, or mutates an Admitted."""
    failures = 0
    for path in sorted(REPO.rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel == _ADMISSION_REL or "/.venv/" in rel or "/node_modules/" in rel:
            continue
        for lineno, what in _forgery_violations_in(path):
            print(f"FAIL {rel}:{lineno}: {what}", file=sys.stderr)
            print("     admit() is the only producer of an Admitted; a deliberate bypass must be "
                  "visible in the diff that introduces it (ARCHITECTURE 6.1 layer 2)",
                  file=sys.stderr)
            failures += 1
    return failures


def _manifest_drift() -> int:
    """M1 — the committed manifest must be what the GENERATOR would produce, not what a text
    editor left behind.

    ARCHITECTURE §3 names this gate ("manifest row count == admitted count; drift reds CI") and
    `manifest.py` referred to it in a docstring — and **it did not exist**. A capability named in
    prose is not a capability; this repository has a standing rule about exactly that, and the
    finding here is that the rule caught its author.

    CP-1 admits nothing, so the check is concrete: the committed document must equal what
    `build([])` produces. **That is not vacuous** — typing a row into the JSON reds it, which is the
    one bypass the write-side `Admitted` type cannot see, because JSON on disk has no types. When
    CP-4 admits the first declaration this comparison gains a real right-hand side; until then it
    holds the file at the only state the membrane can prove.
    """
    if not MANIFEST.exists():
        print(f"FAIL: {MANIFEST.relative_to(REPO).as_posix()} is missing - M1 has no artifact",
              file=sys.stderr)
        return 1
    sys.path.insert(0, str(REPO / "services" / "chat-service"))
    try:
        from app.agentruntime import build, validate_document
    except Exception as exc:  # pragma: no cover - import failure IS the finding
        print(f"FAIL: cannot import app.agentruntime: {exc!r}", file=sys.stderr)
        print("     the package must import cleanly from a bare interpreter; a path expression "
              "that counts directory levels encodes the CHECKOUT layout, not the deployed one",
              file=sys.stderr)
        return 1
    import json as _json
    try:
        doc = _json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: manifest is not valid JSON: {exc}", file=sys.stderr)
        return 1
    try:
        validate_document(doc, source="contracts/agent-runtime-manifest.json")
    except Exception as exc:
        print(f"FAIL: manifest row failed the contract: {exc}", file=sys.stderr)
        return 1
    expected = build([])
    if doc != expected:
        print("FAIL: manifest drift - the committed file is not what the generator produces",
              file=sys.stderr)
        print(f"     expected {expected}", file=sys.stderr)
        print(f"     found    {doc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true",
                    help="ONLY the self-test; the default runs it first, then the lint")
    ap.add_argument("--no-selftest", action="store_true",
                    help="skip the self-test bite (for debugging the lint alone)")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    # DEFAULT MODE RUNS THE SELF-TEST FIRST, then the lint. CI invokes every entry in the
    # lint-foundation matrix as a bare `python scripts/<name>.py`, so a self-test behind a flag is
    # a self-test CI never runs - and this gate's whole value is the claim that it CAN fire. The
    # claim was worth making mechanical: the first --selftest run found a real hole in this file
    # (`import importlib` slipped through the stdlib branch). Precedent in the same matrix:
    # meta-actor-uuid-lint and emit-migration-0013-lint.
    if not args.no_selftest:
        rc = _selftest()
        if rc != 0:
            return rc

    if not PACKAGE.exists():
        print(f"FAIL: {PACKAGE} does not exist - M2 has no subject", file=sys.stderr)
        return 1

    failures = 0
    files = sorted(PACKAGE.rglob("*.py"))
    if not files:
        print(f"FAIL: {PACKAGE} contains no modules - a gate with no subject reports safety",
              file=sys.stderr)
        return 1

    for path in files:
        for lineno, what in _violations_in(path):
            rel = path.relative_to(REPO).as_posix()
            print(f"FAIL {rel}:{lineno}: {what}", file=sys.stderr)
            print("     the membrane is construction, not filtering: the new assembler may import "
                  "the standard library and itself, and nothing else (ARCHITECTURE 3 / M2)",
                  file=sys.stderr)
            failures += 1

    failures += _manifest_drift()
    failures += _forgery_scan()

    for type_name, expected in sorted(SINGLE_SITED.items()):
        sites = _construction_sites(type_name)
        if len(sites) != expected:
            for path, lineno in sites:
                print(f"FAIL {path.relative_to(REPO).as_posix()}:{lineno}: "
                      f"{type_name}() constructed here", file=sys.stderr)
            print(f"     expected exactly {expected} construction site for {type_name}, found "
                  f"{len(sites)}. A second one is the guarantee gone, and it reads as ordinary "
                  f"code in review (ARCHITECTURE 6.1 / M4, CP-1.7 / P1)", file=sys.stderr)
            failures += 1

    if failures:
        print(f"\nagentruntime-membrane-gate: {failures} violation(s)", file=sys.stderr)
        return 1
    print(f"agentruntime-membrane-gate OK - {len(files)} module(s), "
          f"{len(ALLOWED_EXTERNAL)} allowed external import(s), "
          f"{len(SINGLE_SITED)} single-sited type(s)")
    return 0


def _selftest() -> int:
    """NV-1: prove the gate fires. A gate that cannot go red reports safety it has not checked.

    Runs against a temporary tree so it never edits a tracked file - the audit rule this project
    broke three times is that a proof must not mutate the artifact it is proving.
    """
    import tempfile

    cases = [
        ("legacy import", "from app.services.tool_surface import budget_names_by_tokens\n"),
        ("bare legacy import", "import app.services.stream_service\n"),
        ("third-party import", "import httpx\n"),
        ("dynamic import", "import importlib\n"),
        ("dynamic call", "def f(n):\n    return __import__(n)\n"),
        # The prefix hole a verifier found: one underscore away from the package name,
        # waved through as "internal" by a startswith with no separator anchor.
        ("sibling-prefix module", "from app.agentruntime_bridge import legacy_catalog\n"),
        ("sibling-prefix bare", "import app.agentruntimeX\n"),
    ]
    failed = []
    for label, src in cases:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "probe.py"
            p.write_text(src, encoding="utf-8")
            if not _violations_in(p):
                failed.append(label)

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "clean.py"
        p.write_text("import json\nfrom .contract import Declaration\n", encoding="utf-8")
        if _violations_in(p):
            failed.append("false positive on a legal module")

    # ARCHITECTURE 6.1 layer 2. The clause claims a deliberate bypass is loud in a diff;
    # these are the shapes that claim rests on, and each one is watched going red here.
    forgery_cases = [
        ("token import", "from app.agentruntime.admission import _TOKEN, Admitted\n"),
        ("token type import", "from app.agentruntime.admission import _AdmissionToken\n"),
        ("frozen bypass", "from app.agentruntime import Admitted\n"
                          "def f(a):\n    object.__setattr__(a, 'declaration', None)\n"),
    ]
    for label, src in forgery_cases:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "probe.py"
            p.write_text(src, encoding="utf-8")
            if not _forgery_violations_in(p):
                failed.append(f"forgery scan: {label}")

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "unrelated.py"
        p.write_text("object.__setattr__(x, 'y', 1)\n", encoding="utf-8")
        if _forgery_violations_in(p):
            failed.append("forgery scan fires on a module that never touches agentruntime")

    if failed:
        print("SELFTEST FAILED - the gate did not fire on: " + ", ".join(failed), file=sys.stderr)
        return 1
    print(f"agentruntime-membrane-gate selftest OK - fires on {len(cases)} import shapes + "
          f"{len(forgery_cases)} forgery shapes, silent on a legal module")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
