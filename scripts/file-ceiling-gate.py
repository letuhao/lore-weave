#!/usr/bin/env python3
"""file-ceiling-gate — IMP-D3's 400-line ceiling, enforced instead of aspired.

THE RULE
--------
26_implementation_architecture.md, IMP-D3:

  > "A source file over **400 lines**, or a module with more than one of
  >  {types, laws, I/O, orchestration}, is a gate finding. Ceilings are
  >  arbitrary; **having** one is not — an unbounded file has no moment at which
  >  anyone is obliged to split it."

Only the line half is mechanical, and this gate implements that half. The
"more than one concern" half stays a review question, said out loud here rather
than quietly dropped.

WHY IT EXISTS AT ALL
--------------------
IMP-A7: *"aspirational rules decay."* The evidence is in this repo's own history
— doc 26 recorded `domain.rs` at 592 and `combat.rs` at 456 as already over the
ceiling, and by the time S2 came to split them `domain.rs` had grown to **609**
while everyone was working on something else. Nothing noticed, because nothing
was watching.

SCOPE — a DIRECTORY, never a file list
--------------------------------------
`TIER` names directories. A file created tomorrow anywhere under them is covered
on its first line. This is deliberate and it is the correction of a mistake this
repo has now made several times: an enumerated file list is **default-uncovered**
(docs/standards/non-vacuity.md, NV-3 — the `hot-path-gate` scope bug, the
publisher smoke's hand-picked 2-of-16 migrations).

The scope is the game-logic tier, not the repo. `crates/world-gen` alone has 20+
files over 400 from a different track, and a gate that reds 67 times on its first
run is a gate someone turns off. Stated as a limit rather than presented as
coverage.

THE ALLOWLIST IS VISIBLE DEBT (IMP-D8)
--------------------------------------
Every row carries a reason and a real line count. That count is checked: if an
allowlisted file GROWS past its recorded size, it reds again. An allowlist entry
buys amnesty for the debt that exists, never for more of it.

    python scripts/file-ceiling-gate.py
    python scripts/file-ceiling-gate.py --self-test
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CEILING = 400

# Whole directories — a new file under any of these is covered from line one.
TIER = [
    "crates/game-rules",
    "crates/ruleset-core",
    "crates/ruleset-loader",
    "crates/sim-core",
    "services/commit-service",
]

# path -> (max_lines_permitted, reason). Amnesty for what exists, never for more.
#
# Every row here predates S2. `load.rs` is NOT on this list on purpose: S1a's
# tests pushed it to 428, and allowlisting a violation created by the same commit
# that builds this gate would have started the gate's life compromised. They were
# moved to `tests/classification.rs` instead.
ALLOWLIST: dict[str, tuple[int, str]] = {
    "crates/sim-core/src/island/mod.rs": (
        577, "the island scheduler — the kernel's core loop. Was "
             "`island.rs`; `Q0b B2a` made it a DIRECTORY module and moved the "
             "epoch switch to `island/epoch.rs`, a CHILD so it can still reach "
             "the parent's private fields (a sibling would have forced them "
             "`pub(crate)`, widening the kernel's mutable surface across the "
             "whole crate to satisfy a line count). The row does not grow: the "
             "split paid for the addition rather than the allowlist absorbing it. `B2b` did it AGAIN — `island/registry.rs` — and the row went 650 -> 616 rather than up: two consecutive slices both paid in splits, which is what a ceiling is for. Then the RLS-I1 audit fix did it a THIRD time - `new` joined `restore` in `island/lifecycle.rs`, where the two constructors belong within reading distance of each other - and the row went 616 -> 577"),
    "crates/sim-core/src/types.rs": (
        400, "the kernel's shared type vocabulary. `Q0b B2a` moved the ruleset "
             "vocabulary (digest, epoch, the two refusals) to `ruleset.rs` and "
             "RE-EXPORTS it from here, so the warning this row used to carry - "
             "\"a split changes every consumer's import path across four "
             "crates\" - was answered rather than accepted. 470 -> 400: the "
             "row TIGHTENS, because an allowlist that only ever grows is an "
             "exemption wearing a budget's clothes"),
    "services/commit-service/src/bin/ceilings.rs": (
        610, "a measurement binary — one long table of scenarios, which is the "
             "shape that file is FOR"),
    "services/commit-service/src/bin/spine.rs": (
        425, "the S3a spine wiring binary: bus -> admission -> island -> commit, "
             "one linear sequence that reads worse cut in half. RETIGHTENED "
             "445 -> 425 after Q1 B2b moved the RLS-A3 startup path into "
             "src/ruleset_boot.rs — same rule as digest.rs: a cap left at its old "
             "value after a split is a silent licence to regrow into it"),
    "crates/ruleset-core/tests/digest.rs": (
        455, "the digest verification suite; the per-field mutation tables are "
             "long by design (v2_every_*_field_reaches_the_digest). RETIGHTENED "
             "560 -> 455 after Q1 split the version-machinery tests into "
             "tests/versioning.rs: an allowlist cap left at its old value is a "
             "silent licence to regrow into it"),
    "crates/game-rules/tests/combat_rules.rs": (
        530, "the COMB_001 law suite, one test per spec clause; moved here with the "
             "laws in S2"),
}


def offenders() -> tuple[list[tuple[str, int]], list[str]]:
    """(findings, notes). A finding is (path, lines)."""
    found, notes = [], []
    for d in TIER:
        root = REPO / d
        if not root.is_dir():
            # A tier directory that vanished is a SCOPE failure, not a long file:
            # the gate would otherwise report OK for a directory it never read,
            # which is the default-uncovered shape this whole file exists to
            # avoid. Surfaced as a note + a non-zero exit, never as silence.
            notes.append(("SCOPE", f"tier directory is missing, so nothing under it was checked: {d}"))
            continue
        for f in sorted(root.rglob("*.rs")):
            if "target" in f.parts:
                continue
            rel = str(f.relative_to(REPO)).replace("\\", "/")
            n = len(f.read_text(encoding="utf-8", errors="replace").splitlines())
            if rel in ALLOWLIST:
                cap, _ = ALLOWLIST[rel]
                if n > cap:
                    found.append((rel, n))
                continue
            if n > CEILING:
                found.append((rel, n))
    # An allowlist row for a file that no longer exists is dead policy: it makes
    # the list look like it is doing more work than it is.
    for rel in ALLOWLIST:
        if not (REPO / rel).is_file():
            notes.append(("POLICY", f"allowlist row for a file that no longer exists: {rel}"))
    return found, notes


def _check_tree(files: dict[str, int], allow: dict[str, tuple[int, str]], ceiling: int):
    """Pure core, so the self-test can drive it without touching the repo."""
    out = []
    for rel, n in sorted(files.items()):
        if rel in allow:
            if n > allow[rel][0]:
                out.append((rel, n))
        elif n > ceiling:
            out.append((rel, n))
    return out


def self_test() -> int:
    fails = []
    allow = {"old/big.rs": (500, "pre-existing")}

    if not _check_tree({"a/new.rs": 401}, allow, 400):
        fails.append("did not bite on a 401-line file")
    if _check_tree({"a/new.rs": 400}, allow, 400):
        fails.append("bit on a file exactly at the ceiling (400 is permitted)")
    if _check_tree({"old/big.rs": 500}, allow, 400):
        fails.append("bit on an allowlisted file at its recorded size")
    if not _check_tree({"old/big.rs": 501}, allow, 400):
        fails.append("did NOT bite on an allowlisted file that GREW — amnesty must "
                     "cover the debt that exists, not more of it")

    # The scope must be a directory walk, not a list. If TIER ever becomes a
    # list of files this assertion is the thing that notices (NV-3).
    for d in TIER:
        if d.endswith(".rs"):
            fails.append(f"TIER contains a FILE ({d}); the scope must be directories, "
                         f"or a file created tomorrow is default-uncovered")

    if fails:
        print("file-ceiling-gate SELF-TEST FAILED:")
        for x in fails:
            print(f"  - {x}")
        return 1
    print("file-ceiling-gate: self-test OK — bites at ceiling+1, silent at the "
          "ceiling, silent on allowlisted debt, bites when that debt GROWS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    found, notes = offenders()
    # Two different failures, two different messages. Lumping them under one
    # sentence would tell the reader the scan was INCOMPLETE when in fact it was
    # complete and the policy was stale — a misleading diagnostic is the same
    # defect class as the loader's "unknown field" answer for a forbidden key.
    for kind, msg in notes:
        print(f"file-ceiling-gate: {kind} — {msg}")
    if any(k == "SCOPE" for k, _ in notes):
        print("\nA tier directory was not read, so a clean result cannot be claimed: "
              "the files that would have been checked were never looked at.")
        return 1
    if any(k == "POLICY" for k, _ in notes):
        print("\nThe scan was complete; the ALLOWLIST is stale. A row for a file that no "
              "longer exists makes the list look like it is doing more work than it is "
              "— delete it.")
        return 1
    if found:
        print(f"file-ceiling-gate: {len(found)} finding(s) — IMP-D3, ceiling {CEILING} lines\n")
        for rel, n in found:
            if rel in ALLOWLIST:
                print(f"  {rel}: {n} lines — allowlisted at {ALLOWLIST[rel][0]}, it GREW")
            else:
                print(f"  {rel}: {n} lines")
        print("\nSplit it, or add an allowlist row WITH A REASON and its real size.")
        print("An unbounded file has no moment at which anyone is obliged to split it.")
        return 1

    scanned = sum(1 for d in TIER for f in (REPO / d).rglob("*.rs") if "target" not in f.parts)
    # T56(b) — the CEILING is printed on the PASS path, not only when it is breached. A
    # threshold nobody sees on a green run drifts invisibly until it breaks, which is the
    # `port-adoption-gate` floor bug generalised.
    print(f"file-ceiling-gate: OK — {scanned} file(s) across {len(TIER)} tier directories, "
          f"{len(ALLOWLIST)} carrying recorded debt (ceiling {CEILING} lines/file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
