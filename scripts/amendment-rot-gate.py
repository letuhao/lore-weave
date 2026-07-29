#!/usr/bin/env python3
"""amendment-rot-gate — an amendment row that nothing watches is a wish with a number on it.

WHAT THIS EXISTS TO ACT ON (measured 2026-07-30)
------------------------------------------------
The PO asked: *"PROPOSED rồi chả dùng, có khi lại bị trôi và kiến trúc thì rot"* —
proposed and then never used, drifting while the architecture rots. It was measured
rather than argued, across the `LLM_MMO_RPG` design track:

  · **15 of 25 `WSA-R*` amendment ids were UNGREPPABLE.** Docs 31 and 32 wrote
    their rows as bare `**R01**` … `**R24**`, with no prefix. An id you cannot
    grep cannot be tracked, audited, or closed. Corpus-wide greppable amendment
    ids went 37 -> 52 the moment this was fixed.

  · **SIX stable-ID prefixes had never been registered at all** — `XST` `PRD`
    `ONT` `EXC` `WSA` `QTY`, introduced by docs 27-35. Unlike the four prior
    RECORD CORRECTIONs in `_boundaries/_LOCK.md`, these docs asserted nothing
    false; they were simply invisible to `01_feature_ownership_matrix.md`, which
    is the file that is supposed to BE the inventory.

  · **A gated batch did not run at its gate.** `19_reconciliation_register.md`
    §15 routed five boundary registrations to *"next `_boundaries` lock claim —
    one batch"*. The next claim happened and did not do them. Root cause is the
    gate's shape, not the claimant's care: *"the next lock claim"* names an
    OCCASION, not an OWNER, so it belongs to nobody and the claimant has no
    reason to open the file that gated it. Recorded as REC-92.

  · And in the other direction: **three rows were already SHIPPED while still
    reading as open** (`XST-R1/R2/R3`, all delivered by the ruleset-core arc).
    Debt already paid that keeps ringing is worse than unpaid debt — it makes
    real work look like backlog and hides how much is genuinely left.

    Intent is not a mechanism. `boundaries-lock-gate` and `deferral-gate`
    exist because the same conclusion was reached twice before. This is
    the third.

WHAT IT CHECKS
--------------
A — PREFIX HYGIENE. No amendment row may carry a bare `**R<n>**` id. Every row
    id must be `PREFIX-R<n>`, so it is greppable from anywhere in the corpus.
    (This is exactly the defect found on 2026-07-30 and fixed in docs 31 + 32.)

B — PREFIX REGISTRATION. Every `PREFIX-R<n>` appearing in the track must have a
    `` `PREFIX-*` `` row in `_boundaries/01_feature_ownership_matrix.md`. The
    matrix is declared the inventory; a prefix absent from it is invisible.

    WHY THIS IS NOT A DUPLICATE OF `design-lint`. That lint already has an
    `unregistered-prefix` check, and it reported **0 findings** while seven
    prefixes were unregistered. It was not broken and it was not vacuous — it
    validates against a DIFFERENT registry: `00_foundation/06_id_catalog.md`.
    All seven prefixes WERE in the catalog; none was in the matrix. The corpus
    keeps two registries and each gate saw only one.

    Its sibling `phantom-registration` was silent for a second, also-correct
    reason: it fires on a line that CLAIMS "(registered …)" for a prefix absent
    from the matrix — the four RECORD CORRECTIONs in `_LOCK.md`. These docs
    claimed nothing, so there was nothing false to catch.

    So the three checks are complementary, not overlapping:
      design-lint symbol        : prefix known to the ID CATALOG?
      design-lint registration  : a registration CLAIM that is false?
      this check                : prefix present in the OWNERSHIP MATRIX?
    The gap that let seven prefixes through was exactly the third question,
    which nothing was asking.

C — GATED-QUEUE DISCHARGE. Items the reconciliation register routes to a
    boundary-registration queue must each appear in the matrix, or be named
    there with an explicit blocked-reason. Parsed from the register, not
    hardcoded, so adding a queue item automatically extends the check.

Each check is BITE-TESTED in `--selftest`: it constructs the exact defect it
claims to catch and asserts the check goes red. A check that cannot fail is not
a check (docs/standards/non-vacuity.md NV-1).

USAGE
-----
    python scripts/amendment-rot-gate.py            # scan; exit 1 on any finding
    python scripts/amendment-rot-gate.py --selftest # prove each check can fail
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACK = ROOT / "docs" / "03_planning" / "LLM_MMO_RPG"
MATRIX = TRACK / "_boundaries" / "01_feature_ownership_matrix.md"
REGISTER = TRACK / "19_reconciliation_register.md"

# A qualified amendment id: `WSA-R19`, `SPG-R1`, `XST-R13`.
QUALIFIED = re.compile(r"\b([A-Z]{2,4})-R(\d+)\b")

# A table row whose first cell is a BARE amendment id — `| **R19** | ...`.
# This is the ungreppable shape. `\*\*R\d` and nothing before it but the pipe.
BARE_ROW = re.compile(r"^\|\s*\*\*R(\d+)\*\*")

# A prefix registration in the matrix: a cell containing `` `WSA-*` ``.
def _prefix_registered(matrix_text: str, prefix: str) -> bool:
    return f"`{prefix}-*`" in matrix_text


def _rel(p: Path) -> str:
    """Repo-relative path, falling back to the absolute one.

    The fallback is load-bearing for `--selftest`, which builds fixture files in a
    temp dir outside the repo. Without it the selftest crashed instead of running —
    i.e. the bite test could not bite, which is the very failure this gate is about.
    """
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _track_docs() -> list[Path]:
    """Design docs in the track. Excludes `_boundaries/` (the inventory itself)."""
    out = []
    for p in sorted(TRACK.rglob("*.md")):
        if "_boundaries" in p.parts:
            continue
        out.append(p)
    return out


# ── Check A ───────────────────────────────────────────────────────────────────
def check_bare_ids(docs: list[Path]) -> list[str]:
    """Flag bare `**R<n>**` ids — but ONLY inside an amendment table.

    FALSE POSITIVE THIS NARROWING KILLS (found by the gate's own first run, against
    its author): `TMP_008b_llm_contract_spec.md` has a `| Rule | Check |` table whose
    rows are validation rules `**R1**..**R5**`. Those are correctly scoped to their
    table and are not amendment ids at all — renaming them would have been damage
    done by a gate that was too eager.

    The discriminator is the table HEADER. Every amendment table in this corpus is
    `| # | Target | Change | Confidence |`; a rules table is not. So the check arms
    itself only after seeing a header containing `Target`, and disarms at the next
    header or blank line. This keeps it able to fail (it still reds on docs 31/32/33/34)
    while removing the class it should never have flagged.
    """
    findings = []
    for p in docs:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        in_amendment_table = False
        for n, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("|"):
                # A header row names its columns; an amendment table names `Target`.
                if "---" not in stripped and "Target" in stripped:
                    in_amendment_table = True
                    continue
            elif not stripped:
                in_amendment_table = False
                continue
            if not in_amendment_table:
                continue
            m = BARE_ROW.match(line)
            if m:
                rel = _rel(p)
                findings.append(
                    f"{rel}:{n}: bare amendment id `**R{m.group(1)}**` — "
                    f"an id without its prefix is ungreppable, therefore untrackable. "
                    f"Use `**XXX-R{m.group(1)}**` with the doc's registered prefix."
                )
    return findings


# ── Check B ───────────────────────────────────────────────────────────────────
def check_prefix_registration(docs: list[Path], matrix_text: str) -> list[str]:
    seen: dict[str, str] = {}  # prefix -> first "file:line" that used it
    for p in docs:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(lines, 1):
            for m in QUALIFIED.finditer(line):
                seen.setdefault(m.group(1), f"{_rel(p)}:{n}")

    findings = []
    for prefix, where in sorted(seen.items()):
        if not _prefix_registered(matrix_text, prefix):
            findings.append(
                f"{where}: prefix `{prefix}-*` is used by an amendment row but has NO row in "
                f"{MATRIX.relative_to(ROOT).as_posix()}. The matrix is the declared inventory; "
                f"a prefix missing from it is invisible to every audit that reads the inventory. "
                f"(Six prefixes sat like this from docs 27-35 until 2026-07-30.)"
            )
    return findings


# ── Check C ───────────────────────────────────────────────────────────────────
GATED_ROW = re.compile(r"^\|\s*\*\*Boundary registrations\*\*\s*\|(?P<items>.*?)\|", re.S)


def _gated_items(register_text: str) -> list[str]:
    """Backtick-quoted tokens in the register's boundary-registration queue row.

    Parsed rather than hardcoded so that adding a queue item extends this check
    automatically — a hardcoded list would rot the same way the queue did.
    """
    for line in register_text.splitlines():
        m = GATED_ROW.match(line)
        if m:
            return re.findall(r"`([^`]+)`", m.group("items"))
    return []


def check_gated_queue(register_text: str, matrix_text: str) -> list[str]:
    findings = []
    for item in _gated_items(register_text):
        # `ruleset.*` in the queue is a namespace token; the matrix registers it
        # by name. Strip a trailing `.*` / `*` so both spellings match.
        needle = item.rstrip("*").rstrip(".")
        if not needle:
            continue
        if needle not in matrix_text:
            findings.append(
                f"{REGISTER.relative_to(ROOT).as_posix()}: gated boundary registration `{item}` "
                f"is still absent from {MATRIX.relative_to(ROOT).as_posix()}. The register routed it "
                f'to "next `_boundaries` lock claim" — an OCCASION, not an OWNER, which is why it was '
                f"missed once already (REC-92). Register it, or name it in the matrix with an "
                f"explicit blocked-reason."
            )
    return findings


# ── selftest (NV-1: prove each check can fail) ────────────────────────────────
def selftest() -> int:
    import tempfile

    failures = []

    # A — construct the exact defect docs 31/32 carried.
    with tempfile.TemporaryDirectory() as td:
        hdr = "| # | Target | Change | Confidence |\n|---|---|---|---|\n"
        bad = Path(td) / "fake.md"
        bad.write_text(hdr + "| **R19** | `EF_001` | add a variant | verified |\n", encoding="utf-8")
        if not check_bare_ids([bad]):
            failures.append("A: bare-id check did NOT red on `| **R19** |` in an amendment table")
        good = Path(td) / "ok.md"
        good.write_text(hdr + "| **WSA-R19** | `EF_001` | add a variant | verified |\n", encoding="utf-8")
        if check_bare_ids([good]):
            failures.append("A: bare-id check reded on a correctly-prefixed row (false positive)")
        # The narrowing itself must be bite-tested, or it silently disarms check A.
        rules = Path(td) / "rules.md"
        rules.write_text(
            "| Rule | Check |\n|---|---|\n| **R1** | Every input zone_id has a narration |\n",
            encoding="utf-8",
        )
        if check_bare_ids([rules]):
            failures.append("A: reded on a `| Rule | Check |` table — the TMP_008b false positive is back")

    # B — a used prefix that the matrix does not carry.
    with tempfile.TemporaryDirectory() as td:
        doc = Path(td) / "fake.md"
        doc.write_text("see `ZZZ-R7` for the amendment\n", encoding="utf-8")
        if not check_prefix_registration([doc], "matrix with no ZZZ row"):
            failures.append("B: registration check did NOT red on an unregistered prefix")
        if check_prefix_registration([doc], "row: `ZZZ-*` owns it"):
            failures.append("B: registration check reded on a registered prefix (false positive)")

    # C — a queue item absent from the matrix.
    reg = "| **Boundary registrations** | `Foo:Bar` · `baz.*` namespace | next claim |\n"
    if not check_gated_queue(reg, "matrix containing baz but not the other one"):
        failures.append("C: gated-queue check did NOT red on a missing registration")
    if check_gated_queue(reg, "matrix containing Foo:Bar and baz"):
        failures.append("C: gated-queue check reded when both were present (false positive)")

    if failures:
        print("SELFTEST FAILED — a check that cannot fail is not a check (NV-1):")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print("amendment-rot-gate selftest: OK — all 3 checks red on their defect and green without it")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="prove each check can fail")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if not TRACK.is_dir():
        print(f"amendment-rot-gate: track not found at {TRACK} — nothing to check")
        return 0

    matrix_text = MATRIX.read_text(encoding="utf-8") if MATRIX.exists() else ""
    register_text = REGISTER.read_text(encoding="utf-8") if REGISTER.exists() else ""
    docs = _track_docs()

    findings = (
        check_bare_ids(docs)
        + check_prefix_registration(docs, matrix_text)
        + check_gated_queue(register_text, matrix_text)
    )

    if findings:
        print(f"amendment-rot-gate: {len(findings)} finding(s)\n")
        for f in findings:
            print(f"  ✗ {f}\n")
        return 1

    ids = set()
    for p in docs:
        try:
            ids.update(QUALIFIED.findall(p.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    print(
        f"amendment-rot-gate: OK — {len(docs)} docs scanned; "
        f"every amendment id is prefixed, every prefix is registered, "
        f"every gated boundary registration is discharged or named."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
