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

# Each entry needs a reason here, so the coupling is visible in the diff that
# introduces it. It was empty until CP-2.1, and the first entry is a decision the
# board made rather than a convenience: BUILD-VS-BUY.md 2 records P4 (Assembly) as
# BUY, and 4.4 as "P4 stops being ours to design".
ALLOWED_EXTERNAL: dict[str, str] = {
    "pydantic_ai": (
        "CP-2.1 - P4 Assembly is BOUGHT (BUILD-VS-BUY 2). The toolset API is what "
        "makes 'withheld' and 'never existed' different states: .defer_loading() "
        "hides a declaration and keeps it discoverable, .filtered() deletes it."
    ),
}

# An allowed external module is allowed IN NAMED FILES, not package-wide.
#
# The allowlist's argument is that a coupling should be a decision someone makes on
# purpose; a module admitted everywhere is one decision that then covers every file
# written afterwards, which is the default-permitted shape the allowlist exists to
# avoid. Keyed on the file NAME because the selftest runs `_violations_in` over
# probe files in a temp directory - a path-based key would silently pass every probe.
#
# A module in ALLOWED_EXTERNAL with no entry here is allowed package-wide, and that
# should stay a conscious omission rather than the easy default.
ALLOWED_EXTERNAL_SCOPE: dict[str, frozenset[str]] = {
    "pydantic_ai": frozenset({"assembly.py"}),
}

# THE CEILING METHODS - CP-2.1, and this is the item rather than a detail of it.
#
# `AbstractToolset` publishes both reductions about fifty lines apart. `.filtered()`
# REMOVES a declaration: it is not on the wire, not searchable, and identical from
# the model's side to one that was never admitted. `.prepared()` is the same power
# with a different name - its prepare function returns a list, and a shorter list is
# a deletion. `.defer_loading()` marks instead of removing, so the declaration stays
# reachable and CP-2.4 ("the model can tell withheld from never existed") is still
# available to be built.
#
# A removal cannot be un-done by a later item, so this is refused at the API rather
# than checked at the result - the M2 argument applied one layer up. If a future
# item genuinely needs one, it arrives here with a reason, in that diff.
CEILING_METHODS: dict[str, str] = {
    "filtered": "removes the declaration - withheld becomes indistinguishable from absent",
    "prepared": "a prepare func returning a shorter list is the same deletion, renamed",
}

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
NL = chr(10)


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


def _external_verdict(module: str, *, from_file: Path) -> str | None:
    """`None` if this external import is allowed from this file, else why it is not.

    ONE implementation, called from both the `import` and the `from ... import`
    branch. They used to hold a copy each, two lines apart and identical - and this
    run has already paid for that exact shape twice: a duplicated walk where a new
    clause went into one copy, and a claim corrected in one of three files. A rule
    with two implementations has two behaviours the moment either is edited.
    """
    key = module if module in ALLOWED_EXTERNAL else _root(module)
    if key not in ALLOWED_EXTERNAL:
        return ""
    scope = ALLOWED_EXTERNAL_SCOPE.get(key)
    if scope is not None and from_file.name not in scope:
        return (f" - {key} is allowed only in {'/'.join(sorted(scope))}, not "
                f"{from_file.name}; the coupling is scoped on purpose")
    return None


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
            why = _external_verdict(mod, from_file=path)
            if why is None:
                continue
            out.append((node.lineno, f"from {mod} import ...{why}"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if _root(mod) in FORBIDDEN_MODULES:
                    out.append((node.lineno, f"import {mod} - dynamic import, unanalysable"))
                    continue
                if _is_internal(mod, from_file=path) or _root(mod) in _STDLIB:
                    continue
                why = _external_verdict(mod, from_file=path)
                if why is None:
                    continue
                out.append((node.lineno, f"import {mod}{why}"))
        elif isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name in FORBIDDEN_CALLS:
                out.append((node.lineno, f"dynamic import via {name}() - unanalysable"))
            # CP-2.1. Only as an ATTRIBUTE call: `t.filtered(...)` is the toolset
            # API, while a bare `filtered(...)` is somebody's local function and
            # convicting it would be a gate firing on a name rather than on a thing.
            elif isinstance(fn, ast.Attribute) and fn.attr in CEILING_METHODS:
                out.append((node.lineno,
                            f".{fn.attr}() - a CEILING api: {CEILING_METHODS[fn.attr]}. "
                            f"CP-2.1 assembles with .defer_loading()"))
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

# CP-1.8c / ARCHITECTURE 0.14.4 - the PURITY BOUNDARY.
#
# Until this existed the gate could not see a single ambient capability: it permits
# the whole standard library, and every ambient capability in Python IS standard
# library. It was green on `os`, `time`, `random`, `uuid` and `open()` - measured, not
# assumed - while 0.13 claimed the boundary was "enforced by the membrane gate, which
# already walks the import graph". The walk was real; the check did not exist.
#
# WHAT THIS CANNOT SEE, and it belongs here rather than in a later discovery: the check
# is BY DIRECT NAME. An ambient read reached through an intermediate helper, or through
# a callable handed in as an argument, is invisible to it. It raises the COST of
# crossing the boundary; it does not make crossing impossible.
_AMBIENT_REL = "services/chat-service/app/agentruntime/ambient.py"
# `secrets` is here because §0.14.4's word is "randomness", and a list that named only `random`
# and `uuid` let the most obviously random module in the stdlib through — a verifier measured it.
AMBIENT_MODULES = {
    "os", "time", "datetime", "random", "uuid", "socket", "platform", "secrets",
}
AMBIENT_CALLS = {
    "getenv", "urandom", "now", "today", "monotonic", "time_ns", "uuid4", "uuid1",
    "perf_counter", "process_time", "token_hex", "token_bytes", "token_urlsafe",
}
AMBIENT_BUILTINS = {"open", "input"}
# Path methods that touch the filesystem. `Path` itself is pure string manipulation.
#
# 🔴 `resolve`, `cwd`, `home`, `touch`, `is_file`, `is_dir` and `lstat` were added after a verifier
# executed twelve probe shapes against this list and found seven it did not know — including a LIVE
# one: `manifest.py` called `Path(__file__).resolve()`, which reads both the filesystem AND the
# layout of the checkout, in a non-boundary module, with the gate green. The disclosure below says
# the check is by direct NAME; it did not say the name list was incomplete, and "a filesystem method
# we did not think to list" is a different failure from the one that was disclosed.
AMBIENT_PATH_METHODS = {
    "exists", "read_text", "read_bytes", "write_text", "write_bytes",
    "mkdir", "unlink", "rglob", "glob", "iterdir", "stat", "lstat",
    "resolve", "cwd", "home", "touch", "is_file", "is_dir", "samefile", "expanduser",
}


def _ambient_violations_in(path: Path) -> list[tuple[int, str]]:
    """Ambient reads outside the boundary module."""
    out: list[tuple[int, str]] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if _root(a.name) in AMBIENT_MODULES:
                    out.append((node.lineno, f"import {a.name} - ambient"))
        elif isinstance(node, ast.ImportFrom):
            if _root(node.module or "") in AMBIENT_MODULES:
                out.append((node.lineno, f"from {node.module} import ... - ambient"))
        elif isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None)
            attr = getattr(fn, "attr", None)
            if name in AMBIENT_BUILTINS:
                out.append((node.lineno, f"{name}() - ambient"))
            if attr in AMBIENT_CALLS or attr in AMBIENT_PATH_METHODS:
                # `ambient.exists(p)` is a call INTO the boundary - the thing every other
                # module is supposed to do. Flagging it would make the boundary unusable,
                # which the gate proved on its first run by reddening all five call sites
                # that had just been moved behind it.
                receiver = getattr(fn.value, "id", None) if isinstance(fn, ast.Attribute) else None
                if receiver != "ambient":
                    out.append((node.lineno, f".{attr}() - ambient"))
        elif isinstance(node, ast.Attribute) and node.attr == "environ":
            out.append((node.lineno, "os.environ - ambient"))
    return out


def _purity_boundary() -> int:
    failures = 0
    for path in sorted(PACKAGE.rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel == _AMBIENT_REL:
            continue
        for lineno, what in _ambient_violations_in(path):
            print(f"FAIL {rel}:{lineno}: {what}", file=sys.stderr)
            print(f"     ambient state is read in {_AMBIENT_REL} and passed in as a parameter; "
                  f"an ambient read elsewhere is an input no record captures "
                  f"(ARCHITECTURE 0.14.4)", file=sys.stderr)
            failures += 1
    return failures

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
    # 🔴 **M1's DRIFT GATE WAS `build([])`, AND THAT HELD ONLY WHILE THE MANIFEST WAS EMPTY.**
    # §0.14.1c predicted it: *"byte-equality holds only while the manifest is empty; it reds
    # unconditionally the moment CP-4 admits anything."* It did, on the first admitted declaration.
    #
    # The replacement is stronger rather than looser: the committed file is compared against what
    # the generator produces when every declaration the file NAMES is **re-derived from the frozen
    # catalogue**. An empty manifest still reduces to `build([])`, so the original property is a
    # special case of this one — and a non-empty manifest is now checked field by field against its
    # own producer, which is what makes a hand-edited row detectable. Editing `cost` by hand, or
    # adding a row nobody derived, no longer survives this gate.
    from app.agentruntime.admission import admit as _admit
    from app.agentruntime.derive import derive_one as _derive_one

    _baseline = REPO / "contracts" / "agent-runtime-baseline" / "tools-list.snapshot.json"
    _cat = {t["name"]: t for t in _json.loads(_baseline.read_text(encoding="utf-8"))["tools"]}
    # 🔴 **THE UNION, FOR THE SAME REASON `agentruntime-admit.py` TAKES IT (CP-5, §4's *"all 324"*).**
    # Without it this gate reads the admission path's catalogue MINUS the four tools chat-service
    # serves itself, so an admitted local row would be reported as *"names nothing derivable, it was
    # hand-written"* — the gate calling the producer a forger because the gate is looking at a
    # smaller catalogue than the producer used. Raising beats degrading here for the usual reason:
    # a partial catalogue makes this check pass over rows it never examined.
    try:
        from app.services.local_tools import local_tool_defs as _local_defs
        for _d in _local_defs():
            _fn = _d.get("function", _d)
            _cat[_fn["name"]] = _d
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: cannot read chat-service's own tool definitions ({exc}); the drift check "
              f"would run against a catalogue smaller than the one the producer writes from",
              file=sys.stderr)
        return 1
    _ids = [r["id"] for r in doc.get("declarations", [])]
    _absent = [i for i in _ids if i not in _cat]
    if _absent:
        print(f"FAIL: manifest names {_absent}, which the frozen catalogue does not contain",
              file=sys.stderr)
        print("     every admitted declaration is DERIVED from a catalogue entry; a row naming "
              "nothing derivable was hand-written, which is the one thing the generator being the "
              "sole writer is supposed to make impossible", file=sys.stderr)
        return 1
    # 🔴 **AND RE-DERIVATION ALONE STOPPED REPRODUCING THE FILE THE MOMENT DERIVATION STOPPED
    # SELF-RELEASING (CP-5.2).** `derive_one` yields `draft`; a released row says `admitted`; so
    # this compared a registration against a registration-plus-a-decision and reported drift on
    # every serving row. It was red from that change until this one.
    #
    # The fix is not to exempt `lifecycle` — that would let a hand-typed `admitted` through, which
    # is the entire class this check exists for. It is to reproduce the **whole** pipeline:
    # re-derive, then re-run the release decision the file records. `promote()` refuses a tool
    # whose contract is incomplete, so an `admitted` row that no longer satisfies rung 2 fails
    # HERE, at the file, and not only at the command that wrote it. That is §6.1's layer 3 applied
    # to the release decision: **a type may express an invariant; it may not be the only thing
    # enforcing one across a persistence boundary.**
    from app.agentruntime.contract import Declaration as _Declaration
    from app.agentruntime.promotion import promote as _promote
    from app.agentruntime.toolcontract import ToolContractViolation as _TCV

    _registry_path = REPO / "contracts" / "agent-runtime-tool-contracts.json"
    _registry = (_json.loads(_registry_path.read_text(encoding="utf-8"))
                 if _registry_path.exists() else {})
    _recorded = {r["id"]: r["lifecycle"] for r in doc.get("declarations", [])}
    _reproduced = []
    for i in _ids:
        _decl = _derive_one(_cat[i]).declaration
        if _recorded.get(i) == "admitted":
            try:
                _decl = _promote(_decl, _cat[i], registry=_registry)
            except _TCV as exc:
                print(f"FAIL: {i} is recorded `admitted` but rung 2 refuses it: {exc}",
                      file=sys.stderr)
                print("     a released row must satisfy the tool contract every time the file is "
                      "read, not only when it was written", file=sys.stderr)
                return 1
        elif _recorded.get(i) not in (None, _decl.lifecycle):
            # deprecated / retired are recorded decisions this gate does not re-take.
            _decl = _Declaration(id=_decl.id, kind=_decl.kind, source_path=_decl.source_path,
                                 lifecycle=_recorded[i], members=_decl.members)
        _reproduced.append(_admit(_decl))
    expected = build(_reproduced, definitions={i: _cat[i] for i in _ids})
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
    failures += _purity_boundary()

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
          f"{len(ALLOWED_EXTERNAL)} allowed external import(s) "
          f"({len(ALLOWED_EXTERNAL_SCOPE)} file-scoped), "
          f"{len(CEILING_METHODS)} refused ceiling api(s), "
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
        # CP-2.1. An allowlist entry is scoped to named files, so the probe (probe.py)
        # is the WRONG file for `pydantic_ai` and must still be convicted. Without
        # this case the scope map could be deleted and every case above stays green.
        ("scoped external outside its file", "import pydantic_ai\n"),
        ("scoped external, from-form", "from pydantic_ai.toolsets import abstract\n"),
        # The ceiling APIs. Both delete a declaration; the item is that the assembly
        # uses neither.
        ("ceiling api .filtered", "def f(t, g):\n    return t.filtered(g)\n"),
        ("ceiling api .prepared", "def f(t, g):\n    return t.prepared(g)\n"),
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

    # CP-2.1's two NEGATIVE controls, and they are not decoration: a gate that
    # convicts the scoped import in its own file, or convicts `.defer_loading()`,
    # would make the item unshippable while every red-ness case above passed.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "assembly.py"
        p.write_text("from pydantic_ai.tools import ToolDefinition" + NL
                     + "def f(t, names):" + NL
                     + "    return t.defer_loading(names)" + NL, encoding="utf-8")
        if _violations_in(p):
            failed.append("the scoped import + .defer_loading() are convicted in assembly.py")

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

    ambient_cases = [
        ("os import", "import os" + NL),
        ("env read", "import x" + NL + "def f():" + NL + "    return x.os.environ.get(1)" + NL),
        ("clock", "import time" + NL),
        ("randomness", "from random import choice" + NL),
        ("uuid", "import uuid" + NL),
        ("open()", "def f():" + NL + "    return open(1)" + NL),
        ("filesystem probe", "def f(q):" + NL + "    return q.exists()" + NL),
        # The seven a verifier measured this gate blind to. `.resolve()` was LIVE in the package
        # while the gate was green, so these are not hypotheticals — they are the shapes that
        # already got through once, and a probe apiece is what stops the list silently shrinking.
        ("path resolve", "def f(q):" + NL + "    return q.resolve()" + NL),
        ("cwd", "from pathlib import x" + NL + "def f():" + NL + "    return x.Path.cwd()" + NL),
        ("home", "def f(q):" + NL + "    return q.home()" + NL),
        ("touch", "def f(q):" + NL + "    return q.touch()" + NL),
        ("is_file", "def f(q):" + NL + "    return q.is_file()" + NL),
        ("perf_counter", "def f(q):" + NL + "    return q.perf_counter()" + NL),
        ("secrets", "import secrets" + NL),
    ]
    for label, src in ambient_cases:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "probe.py"
            p.write_text(src, encoding="utf-8")
            if not _ambient_violations_in(p):
                failed.append(f"purity boundary: {label}")

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "pure.py"
        p.write_text("import json" + NL + "def f(a, b):" + NL
                     + "    return json.dumps(sorted([a, b]))" + NL, encoding="utf-8")
        if _ambient_violations_in(p):
            failed.append("purity boundary fires on a pure module")

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "unrelated.py"
        p.write_text("object.__setattr__(x, 'y', 1)\n", encoding="utf-8")
        if _forgery_violations_in(p):
            failed.append("forgery scan fires on a module that never touches agentruntime")

    if failed:
        print("SELFTEST FAILED - the gate did not fire on: " + ", ".join(failed), file=sys.stderr)
        return 1
    print(f"agentruntime-membrane-gate selftest OK - fires on {len(cases)} import shapes + "
          f"{len(forgery_cases)} forgery + {len(ambient_cases)} ambient shapes, silent on a pure module")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
