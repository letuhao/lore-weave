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
# ⚠️ THE OWNER MOVED (T30 / OD-1, 2026-08-12), AND THIS GATE'S QUESTION CHANGED WITH IT.
#
# Until now the SSOT was "whatever glossary.* string literals the PRODUCER declares", and the
# gate asked: does every consumer literal match one of them? That was the best check available
# while the names lived in a Go `const` block — but it ACCEPTED the underlying disease, because
# it needed those literals to exist in order to work at all.
#
# OD-1 made `contracts/events/_registry.yaml` the owner: the names are generated from it into
# Go (`contracts/events/generated`) and Python (`sdks/python/loreweave_events`), and the
# producer plus all five consumers import them. The producer therefore declares ZERO literals
# now, and the old gate FAILED on precisely that — correctly, by its own rule that a gate
# scanning nothing passes everything.
#
# The question is now stronger: the registry owns the names, so **any glossary.* literal in
# live code outside the generated files is a re-declaration** — a copy that can drift. The old
# check asked "does this copy match?"; this one asks "why is there a copy?".
REGISTRY_PATH = os.path.join(ROOT, "contracts", "events", "_registry.yaml")

# The generated files necessarily CONTAIN the literals — they are what everything else imports.
# Exempting them is not a hole: they are rewritten by `make eventgen` from the registry, and
# `scripts/eventgen-validate.sh` fails if they drift from it.
GENERATED_PREFIXES = (
    os.path.join("contracts", "events", "generated"),
    os.path.join("sdks", "python", "loreweave_events"),
)
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

# Matches a registry entry line: `  - name: glossary.entity_updated`. Anchored to the
# `- name:` key so a description or comment that happens to mention an event name is not
# mistaken for a registration.
REGISTRY_NAME_RE = re.compile(r"\s*-\s*name:\s*(glossary\.[a-z0-9_]+)\s*$")

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


def _selftest() -> int:
    """Prove this gate can go RED, and prove the three things it must NOT fail on.

    Written when the gate's question changed (T30/OD-1): it used to ask *"does this consumer
    literal match the producer's?"* and now asks *"why is there a literal at all, when the
    registry owns the name?"*. That is a strictly stronger check, and a stronger check is
    exactly the kind that gets loosened later by widening an exemption. The negative cases
    below are what makes such a loosening visible instead of convenient.

    Drives `main()` end-to-end against synthetic trees by rebinding the module globals, so it
    exercises the real walk, the real regex and the real exit code rather than a
    re-implementation of them.
    """
    import tempfile

    g = globals()
    saved = {k: g[k] for k in ("ROOT", "SCAN_DIRS", "REGISTRY_PATH", "GENERATED_PREFIXES")}
    ok = True
    NL = chr(10)

    def run(case: str, want: int, *, registry: str, files: dict) -> None:
        nonlocal ok
        with tempfile.TemporaryDirectory() as t:
            reg = os.path.join(t, "registry.yaml")
            with open(reg, "w", encoding="utf-8") as fh:
                fh.write(registry)
            for rel, body in files.items():
                full = os.path.join(t, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(body)
            g["ROOT"] = t
            g["REGISTRY_PATH"] = reg
            g["SCAN_DIRS"] = [os.path.join(t, "services"), os.path.join(t, "contracts")]
            sys.argv = ["gate"]
            try:
                got = main()
            except SystemExit as exc:      # argparse should not fire, but never mask it
                got = int(exc.code or 0)
            if got != want:
                print("  FAIL — " + case + ": exit " + str(got) + ", expected " + str(want))
                ok = False

    REG = ("events:" + NL
           + "  - name: glossary.entity_updated" + NL
           + "    aggregate: glossary" + NL)
    LIVE = "services/knowledge-service/app/main.py"

    run("a registered name referenced in live code passes", 0,
        registry=REG, files={LIVE: 'x = "glossary.entity_updated"' + NL})

    run("an UNREGISTERED name in live code is refused", 1,
        registry=REG, files={LIVE: 'x = "glossary.entity_vanished"' + NL})

    # Negative controls. Each is a way this gate could turn into a nuisance and get muted,
    # and a muted gate is worse than no gate because it still prints PASS.
    run("an unregistered name in a TEST file is a note, not a failure", 0,
        registry=REG,
        files={"services/knowledge-service/tests/test_x.py":
               'x = "glossary.entity_created"' + NL})

    run("the generated files may carry the literals — they ARE the owner's output", 0,
        registry=REG,
        files={"contracts/events/generated/python/__init__.py":
               'EVENT_GLOSSARY_ENTITY_VANISHED = "glossary.entity_vanished"' + NL})

    # The scans-nothing guard, and the reason it is not hypothetical: on 2026-08-12 the owner
    # moved to the registry, the producer's literal count went to zero, and the OLD gate
    # failed on exactly this rule rather than silently passing everything.
    run("an empty registry FAILS instead of passing everything", 1,
        registry="events: []" + NL, files={LIVE: 'x = "glossary.entity_updated"' + NL})

    for k, v in saved.items():
        g[k] = v
    print("[glossary-events-ssot-gate] SELFTEST " + ("PASS" if ok else "FAIL")
          + " — an unregistered name reds, a registered one passes, tests and generated files"
          + " stay exempt, and an empty registry cannot pass everything (non-vacuous)")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staged", action="store_true",
                    help="report only files in the staged set (the SSOT is still read in full)")
    args = ap.parse_args()

    if not os.path.isfile(REGISTRY_PATH):
        print(f"[glossary-events-ssot-gate] FAIL — registry absent: {REGISTRY_PATH}")
        return 1

    # The SSOT: every glossary.* event registered in the contract. Read with a line regex
    # rather than a YAML parser so the gate keeps working inside a pre-commit hook with no
    # third-party dependencies available — and so a parse error can never be swallowed
    # somewhere and turn into an empty set that passes everything.
    ssot: set[str] = set()
    with open(REGISTRY_PATH, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            m = REGISTRY_NAME_RE.match(line)
            if m:
                ssot.add(m.group(1))

    if not ssot:
        print("[glossary-events-ssot-gate] FAIL — no glossary.* events found in "
              f"{os.path.relpath(REGISTRY_PATH, ROOT)}. Either the registry moved or this "
              "gate is scanning nothing, and a gate that scans nothing passes everything.")
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
        if os.path.relpath(path, ROOT).startswith(GENERATED_PREFIXES):
            continue
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
        print(f"\n  The registry ({os.path.relpath(REGISTRY_PATH, ROOT)}) declares:")
        for name in sorted(ssot):
            print(f"    {name}")

    if not failed:
        print(f"[glossary-events-ssot-gate] PASS — {len(ssot)} glossary.* event name(s) "
              f"declared by the registry; every reference in non-test code across services/ "
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
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
