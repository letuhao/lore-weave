#!/usr/bin/env python3
"""glossary-events-ssot-gate — the `glossary.*` event names get one owner (plan T30).

WHAT THIS CLOSES
----------------
`D-GLOSSARY-EVENTS-NO-SOT`: `contracts/events/_registry.yaml` calls itself the *"AUTHORITATIVE
list of every event_type emitted by LoreWeave services"* and contains **zero** `glossary.*`
entries. The real list is a set of Go `const` declarations in glossary-service, **hand-mirrored
by five consumers, with no generator and no drift gate.**

The architecture overview (RT-10) states the consequence plainly: *"Moving a producer under
that is silent breakage by construction."* Rename `glossary.entity_updated` in the producer and
every consumer keeps matching on the old string — no compile error, no test failure, no alert.
The events simply stop being handled, and the first symptom is a stale mirror somebody notices
weeks later. That is exactly the failure QC-4 caught once already.

WHAT IT ENFORCES
----------------
1. **One owner.** The authoritative list is the set of `glossary.*` string literals declared in
   glossary-service's PRODUCER files (`internal/api/`). That is where the wire value is
   decided, so that is what everything else must agree with.
2. **No unknown names anywhere.** Every `glossary.*` literal in any service — producer,
   consumer, any language — must be one the producer emits. A consumer matching on
   `glossary.entity_delete` (singular) is a dead branch that looks alive; this fails it.
3. **No orphan handlers.** A name that only consumers use and no producer emits is reported,
   because a handler for an event nobody sends is indistinguishable from a working one.

WHY THIS AND NOT REGISTRY ADOPTION — recorded rather than quietly substituted
-----------------------------------------------------------------------------
The obvious reading of T30 is "add the nine events to `_registry.yaml`". Measured, that does
NOT close the deferral, and the repo already contains the proof:

  * `contracts/events/registry.go:108` **requires a non-empty `go_struct`** for every entry,
    and `tools/eventgen` generates Go/Rust/TS/Python bindings from it. There is no
    contract-only entry.
  * So registering means writing nine payload structs — second definitions of payloads that
    already exist in glossary-service.
  * `contracts/events/canon.go` is the precedent, and it says so in capitals:
    *"THIS FILE DOES NOT MODIFY services/glossary-service/."* The canon.* events are
    registered, structs and all, while the producer continues to declare its own strings.

Registering the glossary events the same way would add a **tenth, eleventh… parallel list**
rather than removing the five that exist — the deferral's own disease, with a YAML file on top.
Real adoption means glossary-service importing the generated constants, which is a module
dependency plus a rewrite of every emit site, and `canon.go` records that as a separate
sub-program on purpose.

**So this gate delivers the property RT-10 asks for — a producer rename can no longer land
silently — without minting another copy of the list.** Full registry adoption remains open and
is flagged for the PO in the plan entry; this is not a claim that it was unnecessary.

    python scripts/glossary-events-ssot-gate.py [--staged]

Exit 0 = the names agree · 1 = drift.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCER_DIR = os.path.join(ROOT, "services", "glossary-service", "internal", "api")
SCAN_DIRS = [os.path.join(ROOT, "services"), os.path.join(ROOT, "contracts")]
SCAN_EXT = (".go", ".py", ".ts", ".tsx", ".js", ".yaml", ".yml", ".sql")

# Matches a COMPLETE string literal, not a substring, and only the event families that exist.
#
# The first version matched bare `glossary.<word>` anywhere and produced 28 findings, all of
# them noise: Python attribute access (`glossary.get`), module names (`glossary.py`), metric
# labels (`glossary.select_for_context`), even `glossary.entity_` from an f-string prefix. A
# gate whose output is mostly false positives gets silenced, and a silenced gate is worse than
# no gate because it still prints PASS.
#
# The wire values are `glossary.entity_*` plus `glossary.name_confirmed`, so that is the
# family policed. This is not a narrowing of the RISK — a producer rename lands inside this
# family by construction — it is a narrowing of what counts as a reference to one.
EVENT_RE = re.compile(
    r"""(?P<q>["'`])(?P<name>glossary\.(?:entity_[a-z0-9_]+|name_confirmed))(?P=q)"""
)

# `glossary.batch` is a confirm-token DESCRIPTION (`action_confirm_token.go`), never an
# event_type on the wire. It is outside the families above and so never reaches this set;
# kept named here so the next reader does not "fix" its absence.
NOT_EVENTS: set[str] = set()

# Documentation and history are allowed to name events that no longer exist — that is what
# history is for. Only live code is held to the contract.
SKIP_PATH_PARTS = (
    os.sep + "node_modules" + os.sep,
    os.sep + "__pycache__" + os.sep,
    os.sep + "generated" + os.sep,
    os.sep + "dist" + os.sep,
    os.sep + ".venv" + os.sep,
)


def strip_comments(text: str, ext: str) -> str:
    """Blank comments, keeping string literals.

    Load-bearing, not hygiene: T28's gate certified a silenced function because a COMMENT
    mentioned it, and a sibling gate reported a rule that lived only in a doc comment. A gate
    that reads prose is a gate that can be argued with.
    """
    # Python triple-quoted strings are stripped as PROSE. They are string literals to the
    # parser, but in practice they are docstrings, and a docstring that names an event is
    # describing behaviour rather than matching on a wire value. Keeping them turned two
    # knowledge-service docstrings into "dead branches" when the real finding is narrower and
    # different: the documentation is wrong, the code is not.
    if ext == ".py":
        text = re.sub(r'"""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'',
                      lambda m: "\n" * m.group(0).count("\n"), text)
    out = []
    i, n = 0, len(text)
    line_tok = "#" if ext in (".py", ".yaml", ".yml") else "//"
    block = ext in (".go", ".ts", ".tsx", ".js")
    if ext == ".sql":
        line_tok = "--"
    while i < n:
        ch = text[i]
        if ch in "\"'`":
            quote = ch
            out.append(ch)
            i += 1
            while i < n:
                if text[i] == "\\" and quote != "`":
                    out.append(text[i:i + 2]); i += 2; continue
                out.append(text[i])
                if text[i] == quote:
                    i += 1; break
                i += 1
            continue
        if text.startswith(line_tok, i):
            while i < n and text[i] != "\n":
                out.append(" "); i += 1
            continue
        if block and text.startswith("/*", i):
            while i < n and not text.startswith("*/", i):
                out.append("\n" if text[i] == "\n" else " "); i += 1
            out.append("  "); i += 2
            continue
        out.append(ch); i += 1
    return "".join(out)


def events_in(path: str) -> set[str]:
    ext = os.path.splitext(path)[1]
    try:
        raw = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return set()
    return {m.group("name") for m in EVENT_RE.finditer(strip_comments(raw, ext))
            if m.group("name") not in NOT_EVENTS}


def is_test(path: str) -> bool:
    base = os.path.basename(path)
    return (base.endswith("_test.go") or base.startswith("test_")
            or base.endswith(".test.ts") or base.endswith(".spec.ts")
            or (os.sep + "tests" + os.sep) in path)


def walk(dirs: list[str]) -> list[str]:
    found = []
    for d in dirs:
        for base, subdirs, files in os.walk(d):
            subdirs[:] = [s for s in subdirs if s not in
                          ("node_modules", "__pycache__", "dist", ".venv", "generated")]
            for f in files:
                if f.endswith(SCAN_EXT):
                    p = os.path.join(base, f)
                    if not any(part in p for part in SKIP_PATH_PARTS):
                        found.append(p)
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staged", action="store_true",
                    help="report only files in the staged set (the SSOT is still read in full)")
    args = ap.parse_args()

    if not os.path.isdir(PRODUCER_DIR):
        print(f"[glossary-events-ssot-gate] SKIP — producer dir not present: {PRODUCER_DIR}")
        return 0

    # The SSOT: every glossary.* literal the producer declares.
    ssot: set[str] = set()
    for base, _, files in os.walk(PRODUCER_DIR):
        for f in files:
            if f.endswith(".go") and not f.endswith("_test.go"):
                ssot |= events_in(os.path.join(base, f))

    if not ssot:
        print("[glossary-events-ssot-gate] FAIL — no glossary.* event names found in the "
              "producer. Either the producer moved (update PRODUCER_DIR) or the gate is "
              "scanning nothing, and a gate that scans nothing passes everything.")
        return 1

    staged: set[str] = set()
    if args.staged:
        try:
            out = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=ROOT,
                                 capture_output=True, text=True, check=False).stdout
            staged = {os.path.normpath(os.path.join(ROOT, p.strip()))
                      for p in out.splitlines() if p.strip()}
        except OSError:
            staged = set()

    unknown: dict[str, set[str]] = {}
    in_tests: dict[str, set[str]] = {}
    used: set[str] = set()
    for path in walk(SCAN_DIRS):
        names = events_in(path)
        if not names:
            continue
        used |= names
        bad = names - ssot
        if not bad:
            continue
        if args.staged and os.path.normpath(path) not in staged:
            continue
        # Tests are reported, not failed. A NEGATIVE test — "this event must be ignored" —
        # legitimately names an event that does not exist, and today all three such references
        # are exactly that. Failing them would push the next author to delete the assertion
        # rather than the drift. The wire is what this gate defends, and tests are not on it.
        if is_test(path):
            in_tests.setdefault(os.path.relpath(path, ROOT), set()).update(bad)
        else:
            unknown.setdefault(os.path.relpath(path, ROOT), set()).update(bad)

    orphans = sorted(used - ssot)
    failed = False

    if unknown:
        failed = True
        print("[glossary-events-ssot-gate] FAIL — event names no producer emits:\n")
        for path in sorted(unknown):
            for name in sorted(unknown[path]):
                print(f"  {path}: {name!r}")
        print("\n  These are dead branches that look alive. Either the producer renamed the")
        print("  event and this consumer was not updated, or the name is a typo — both are")
        print("  silent: no compile error, no failing test, the handler simply never runs.")
        print(f"\n  The producer ({os.path.relpath(PRODUCER_DIR, ROOT)}) emits:")
        for name in sorted(ssot):
            print(f"    {name}")

    if not failed:
        print(f"[glossary-events-ssot-gate] PASS — {len(ssot)} glossary.* event name(s) "
              f"declared by the producer; every reference in non-test code across services/ "
              f"and contracts/ matches one of them")
    if in_tests:
        print("  note — names referenced only by TESTS that no producer emits:")
        for path in sorted(in_tests):
            for name in sorted(in_tests[path]):
                print(f"    {path}: {name!r}")
        print("    (all three of these are negative tests — 'this event must be ignored'.")
        print("     Worth knowing rather than fixing: if such a name ever DID start being")
        print("     emitted, the assertion would quietly become a claim about the wrong thing.)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
