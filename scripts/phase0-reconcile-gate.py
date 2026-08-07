#!/usr/bin/env python3
"""phase0-reconcile-gate — Phase 0's QUESTION 1, which has never had a mechanism.

THE FAILURE THIS EXISTS TO STOP
-------------------------------
`CLAUDE.md`'s Phase 0 asks three questions before any design:

  1. What already models this concept?  grep the tables, the crates, the
     projectors, AND THE PLANNING DOCS. A name from a different track counts.
  2. Does it have a PRODUCER?           <- scripts/orphan-model-gate.py
  3. Does it CONFLICT with a decision this round will make?

**Only question 2 has a gate, and CLAUDE.md says so itself** — it names the
script for 2 and names nothing for 1 and 3.

Question 1 is the one that keeps failing:

  * 2026-08-04, and written into CLAUDE.md as the canonical Phase-0 incident:
    the actor-hub round designed feature #1 without auditing what already
    modelled an actor. Ten projection tables, seven of them `pc_*`/`npc_*`,
    with no producer at all.
  * 2026-08-06, found by the PO: **the same round** wrote three specs for a
    tier that already had 25 LOCKED documents governing it
    (`03_planning/LLM_MMO_RPG/06_data_plane/`, `DP-A1..A19` · `DP-T0..T3` ·
    `DP-R1..R8`). Measured: `DP-` appears ZERO times in all three.
  * The same day, a third time: this gate's own author wrote a 600-line
    `DPA-*` spec re-deriving `DP-A1`, `DP-A5`, `DP-A10` and `DP-A12`, having
    read the Phase-0 section in the same session.

**The mechanism built after the first one answers question 2.** So question 1
failed again, in the same round, and nothing said anything. That is not loose
discipline — it is `NV-3` at the process level: question 1 is
**default-uncovered**, so it fails structurally rather than by character.

WHAT THIS CHECKS, AND WHAT IT HONESTLY CANNOT
---------------------------------------------
You cannot grep for "a concept". What you CAN do is force the ACTION that
failed all three times: **opening `docs/standards/README.md`**, the file
`CLAUDE.md`'s first Key Rule calls *"the Standards index (start here)"*.

  RULE  A spec dated on or after CUTOFF must carry a `Reconciles:` line naming
        one or more rows of the standards index — or `Reconciles: none — <why,
        and the command that showed it>`.

Every name given must resolve to a real row. A `Reconciles:` pointing at
nothing is the phantom-registration shape `design-lint` already refuses.

⚠ **STATED LIMIT — this forces the LOOK, not the CONCLUSION.** An author can
cite a row that is not the relevant one and pass. It is the same class as
`DP-R2` (a review gate that forces a table to be written). It is worth having
anyway because the action that failed three times was *not opening the file*,
and this refuses a spec that did not.

WHY A DATE CUTOFF AND NOT A BACKFILL
------------------------------------
Keying on an `Id family:` header would scope the gate to ONE file — the only
spec in the tree that has one is the one its author wrote — which is the
`NV-3` shape this gate is about, reproduced inside it. Keying on the id
catalog would demand 81 backfills.

The date cutoff gives a subject set that is **empty today and grows by
itself**: the convention `docs/specs/YYYY-MM-DD-<topic>.md` is already in
`CLAUDE.md`, so the trigger is the filename the author already has to choose.
The one spec that failed is backfilled by hand, so the check is not vacuous on
its first run.

Exit 0 = clean; 1 = findings; 2 = misuse.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INDEX = REPO / "docs" / "standards" / "README.md"

#: Specs dated on or after this must reconcile. The day the law was agreed.
CUTOFF = "2026-08-06"

#: Both trees `CLAUDE.md` names for new specs — plus `docs/plans`, added
#: 2026-08-08 (`1b7gap-M8`).
#:
#: A cold-start critic measured the hole: `governed_specs()` returned exactly
#: THREE files, and **the Phase-0 discipline for the whole `crates/dp` build was
#: performed in `docs/plans/2026-08-06-game-tier-build-RUN-STATE.md`** — a file
#: this gate could not see, using entry names it would have rejected. `CLAUDE.md`
#: lists `docs/plans/YYYY-MM-DD-<feature>.md` as a first-class PLAN artifact in
#: the same table as `docs/specs`, so leaving it out was an omission rather than
#: a decision: `NV-3` at the process level, in the gate written to stop Phase 0
#: being skipped.
SPEC_ROOTS = ("docs/specs", "docs/03_planning", "docs/plans")

DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})-.+\.md$")
FIELD = re.compile(r"^\s*\**Reconciles:?\**\s*:?\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
NONE_FORM = re.compile(r"^\s*none\b\s*[-—]\s*\S", re.IGNORECASE)


def index_rows() -> list[str]:
    """The first cell of every table row in the standards index.

    The index is a set of markdown tables; a row's first cell is the thing it
    governs. Matching is done on that cell so a `Reconciles:` entry can name a
    family (`DP-A1-A19`) or a phrase (`Actor hub`) — whichever the row uses.
    """
    if not INDEX.is_file():
        print(f"phase0-reconcile-gate: MISUSE — no standards index at {INDEX}", file=sys.stderr)
        sys.exit(2)
    rows = []
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|- :"):
            continue
        cell = line.split("|")[1].strip()
        if cell and not cell.lower().startswith(("family", "standard", "i'm working on", "id")):
            rows.append(cell)
    return rows


def _norm(s: str) -> str:
    """Comparison form: lowercase alphanumerics only.

    Markdown decorations (`**`, backticks, links) differ between how a row is
    written and how an author cites it; comparing the letters makes the check
    about the reference rather than the formatting.
    """
    return re.sub(r"[^a-z0-9]", "", s.lower())


def governed_specs() -> list[Path]:
    out = []
    for root in SPEC_ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        for f in base.rglob("*.md"):
            m = DATED.match(f.name)
            if m and m.group(1) >= CUTOFF:
                out.append(f)
    return sorted(out)


def check(spec: Path, rows: list[str]) -> list[str]:
    text = spec.read_text(encoding="utf-8", errors="replace")
    rel = str(spec.relative_to(REPO)).replace("\\", "/")
    m = FIELD.search(text)
    if not m:
        return [
            f"{rel}: no `Reconciles:` line.\n"
            f"      Phase 0 question 1 — what ALREADY models this? Open\n"
            f"      docs/standards/README.md (CLAUDE.md: \"Standards index — start here\")\n"
            f"      and name the row(s) this overlaps, or write\n"
            f"      `Reconciles: none — <why, and the command that showed it>`."
        ]
    value = m.group(1).strip()
    if NONE_FORM.match(value):
        return []
    if _norm(value) in ("none", ""):
        return [f"{rel}: `Reconciles: none` with no reason. State WHY and the command that showed it."]

    # THE FIELD'S SHAPE:  Reconciles: <names> — <what the reconciliation FOUND>
    #
    # Names first, separated by `·` or `,`; an em-dash starts the prose. The
    # first version of this parser split the whole value on `·` and read the
    # rationale as a name, so it reported a phantom row against a correct line.
    # Caught by running it on the three real specs rather than on the selftest —
    # which is the reason a gate is run against the tree before it is believed.
    # The separator is REQUIRED rather than inferred: a field that is half list
    # and half essay cannot be checked, and the rationale is the useful half.
    names = re.split(r"\s+[-—]{1,2}\s+", value, maxsplit=1)[0]

    norm_rows = [_norm(r) for r in rows]
    bad = []
    for part in re.split(r"[·,;]| and ", names):
        part = part.strip(" *`[]()")
        if not part:
            continue
        n = _norm(part)
        if not any(n in r or r in n for r in norm_rows if r):
            bad.append(part)
    if bad:
        return [
            f"{rel}: `Reconciles:` names {len(bad)} entr(y/ies) with no row in the "
            f"standards index: {', '.join(repr(b) for b in bad)}.\n"
            f"      A reference pointing at nothing is the phantom-registration shape."
        ]
    return []


def selftest(rows: list[str]) -> int:
    """Non-vacuous in both directions, on synthetic input."""
    bad = []
    real = rows[0] if rows else "Data Plane"
    cases = [
        ("a spec with no Reconciles line", "# X\n\nbody\n", True),
        ("a real row cited", f"# X\n\n**Reconciles:** {real}\n", False),
        ("a bare `none`", "# X\n\n**Reconciles:** none\n", True),
        ("`none` WITH a reason", "# X\n\nReconciles: none — new concept; `grep -r Foo docs/` empty\n", False),
        ("a row that does not exist", "# X\n\nReconciles: Quantum Flux Standard\n", True),
        # The two below are the shape the parser got wrong on its first real run.
        ("names, then an em-dash rationale", f"# X\n\nReconciles: {real} — this overlaps, and here is what it found\n", False),
        ("a phantom name BEFORE the em-dash still reds",
         "# X\n\nReconciles: Quantum Flux Standard — with a rationale attached\n", True),
    ]
    for label, text, want_finding in cases:
        tmp = REPO / f"__phase0_selftest_{abs(hash(label))}.md"
        tmp.write_text(text, encoding="utf-8")
        try:
            got = bool(check(tmp, rows))
        finally:
            tmp.unlink(missing_ok=True)
        if got != want_finding:
            bad.append(f"{label}: expected finding={want_finding}, got {got}")
    if bad:
        print("phase0-reconcile-gate: SELFTEST FAIL")
        for b in bad:
            print("  " + b)
        return 1
    print(f"phase0-reconcile-gate: SELFTEST PASS — {len(cases)} case(s); it flags a missing "
          f"line, a bare `none` and a phantom row, and does NOT flag a real citation or a "
          f"reasoned `none` (non-vacuous in both directions)")
    return 0


def main() -> int:
    rows = index_rows()

    # A scan whose reference set is empty passes everything. Two gates shipped
    # that bug this week; it is checked here rather than trusted.
    if len(rows) < 20:
        print(f"phase0-reconcile-gate: FAIL — parsed only {len(rows)} row(s) from the standards "
              f"index. A `Reconciles:` check against an empty index accepts anything.",
              file=sys.stderr)
        return 1

    if "--selftest" in sys.argv:
        return selftest(rows)
    if selftest(rows) != 0:
        return 2

    specs = governed_specs()
    findings = []
    for s in specs:
        findings += check(s, rows)

    if findings:
        print(f"phase0-reconcile-gate: {len(findings)} finding(s) — Phase 0 question 1")
        print()
        for f in findings:
            print("  " + f)
        print()
        print("A new spec for a tier that already has one is how this repo got TWO locked")
        print("law families for the game tier, neither citing the other. Question 1 is the")
        print("one that keeps failing, and it is the one that had no gate.")
        return 1

    print(f"phase0-reconcile-gate: OK — {len(specs)} spec(s) dated >= {CUTOFF} checked against "
          f"{len(rows)} standards-index row(s); each names its prior art")
    return 0


if __name__ == "__main__":
    sys.exit(main())
