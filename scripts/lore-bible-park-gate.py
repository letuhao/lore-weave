#!/usr/bin/env python3
"""lore-bible-park-gate — the lore-bible track is PARKED, and this is what wakes it.

WHY THIS EXISTS
---------------
`docs/plans/2026-08-14-lore-bible-RUN-STATE.md` is parked, and the park is sound:
opening it was a boundary violation, and the schema it started was being written
against `progression_kinds` and combat tuning — features the PO has not finished
designing. **A contract written against a feature that does not exist is the
orphan shape `orphan-model-gate.py` exists to refuse.**

But `LB0` found something that must NOT be lost, and the board's own words for
carrying it forward are *"carry that finding forward when this track legitimately
reopens"* — which is a wish, and wishes evaporate:

> **`lore-enrichment-service` already ships the corpus sweep `LB2` was going to
> rebuild** — jobs, proposals, a glossary client, a writeback path and an
> approve/reject queue. `MILESTONE.md`'s *"17 docs, zero code"* is true of the
> lore-bible ARTIFACT and misleading about the WORK.

Re-measured 2026-08-22: **253 Python files** (the board recorded 252; it grew).

WHAT THIS GATE ASSERTS
----------------------
That the lore-bible track is still parked — i.e. that no lore-bible CODE artifact
has appeared. The day one does, this gate reds and hands the author `LB0`'s
finding, at the only moment it matters: before the sweep gets rebuilt.

**It does not forbid the work.** It forbids doing the work without reading why the
last attempt stopped. Clearing it is one line — delete the row from `PARKED` — and
the point is that deleting it requires seeing the sentence above.

WHAT COUNTS AS A CODE ARTIFACT, AND WHY DOCS DO NOT
---------------------------------------------------
Docs are how a parked track stays thinkable; `07_lore_bible.md` and the run-state
itself are supposed to exist. What must not appear unnoticed is a SCHEMA or a
PRODUCER — a migration, a contract, a service module. That is the line `LB1`/`LB2`
would cross.

    python scripts/lore-bible-park-gate.py            # check
    python scripts/lore-bible-park-gate.py --selftest # prove it can fail
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Where a lore-bible SCHEMA or PRODUCER would land. Directories, not a glob over
#: the repo: `lore_bible` appears in prose all over `docs/`, and a check that
#: could not tell a design document from a migration would fire on the parked
#: track's own paperwork.
CODE_ROOTS = [
    "contracts",
    "crates",
    "services",
    "sdks",
    "clients",
]

#: The name in any of its spellings.
#:
#: WARNING: the first version used a `\b` word boundary on both ends and ITS
#: OWN SELFTEST caught it. `\b` needs a non-word character, and `_` IS one, so
#: `0099_lore_bible.up.sql` and `lore_bible_section` -- the two shapes this gate
#: most needs to see -- both failed to match. Two of six cases red on the first
#: run, which is the argument for writing the arms before trusting the regex.
#:
#: The guards are LETTER guards instead: `_`, `-` and `.` may sit either side
#: (that is how the name is spelled in a filename and in a column), but a letter
#: may not -- so `folklore_bible` is a different word and does not fire.
NAME = re.compile(r"(?<![A-Za-z])lore[_-]bible(?![A-Za-z])", re.IGNORECASE)

#: Extensions that are CODE or a contract. A `.md` under `services/` is a README,
#: and a parked track is allowed to be described anywhere.
CODE_SUFFIXES = {".sql", ".rs", ".py", ".go", ".ts", ".tsx", ".yaml", ".yml", ".json"}


def offenders(root: Path) -> list[str]:
    """Files under the code roots whose PATH or CONTENT names the lore bible."""
    found: list[str] = []
    for rel in CODE_ROOTS:
        base = root / rel
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in CODE_SUFFIXES:
                continue
            if any(part in {"target", "node_modules", ".venv", "__pycache__"} for part in p.parts):
                continue
            hit = NAME.search(p.name)
            if not hit:
                try:
                    hit = NAME.search(p.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
            if hit:
                found.append(str(p.relative_to(root)).replace("\\", "/"))
    return sorted(found)


REASON = """
`LB0` FOUND THIS BEFORE YOU DID, AND IT IS THE REASON THE TRACK STOPPED:

  `lore-enrichment-service` ALREADY SHIPS the corpus sweep `LB2` was going to
  rebuild — jobs, proposals, a glossary client, a writeback path and an
  approve/reject queue. 253 Python files, re-measured 2026-08-22.
  `MILESTONE.md`'s "17 docs, zero code" is true of the lore-bible ARTIFACT and
  misleading about the WORK.

  The track was also parked because the schema was being written against
  `progression_kinds` and combat tuning — features the PO has not finished
  designing. A contract written against a feature that does not exist is the
  orphan shape `orphan-model-gate.py` refuses.

If the PO has reopened BOOK_TO_GAME and those designs are complete, this gate has
done its job: delete the `D-LORE-BIBLE-PARKED-SWEEP-EXISTS` row from the deferral
registry and this gate with it. If not, the artifact above is premature.

See docs/plans/2026-08-14-lore-bible-RUN-STATE.md.
"""


def check(root: Path = REPO) -> list[str]:
    return offenders(root)


def selftest() -> int:
    import tempfile

    cases: list[tuple[str, int, int]] = []
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)

        # A repo with only DOCS is the parked state and must pass.
        (t / "docs" / "03_planning").mkdir(parents=True)
        (t / "docs" / "03_planning" / "07_lore_bible.md").write_text(
            "the lore bible design, lore_bible everywhere", encoding="utf-8"
        )
        (t / "contracts").mkdir()
        (t / "contracts" / "unrelated.yaml").write_text("nothing to see", encoding="utf-8")
        cases.append(("docs-only is the parked state", len(check(t)), 0))

        # A MIGRATION named for it fires.
        mig = t / "contracts" / "migrations"
        mig.mkdir(parents=True)
        (mig / "0099_lore_bible.up.sql").write_text("CREATE TABLE x();", encoding="utf-8")
        cases.append(("a migration named for it fires", len(check(t)), 1))
        (mig / "0099_lore_bible.up.sql").unlink()

        # CONTENT counts, not just the filename -- a table created in a file
        # called something else is the same arrival.
        (mig / "0099_sections.up.sql").write_text(
            "CREATE TABLE lore_bible_section (id BIGINT);", encoding="utf-8"
        )
        cases.append(("content counts, not only the filename", len(check(t)), 1))
        (mig / "0099_sections.up.sql").unlink()

        # A .md UNDER a code root is a README and must not fire -- otherwise the
        # gate blocks the parked track from being described where it lives.
        (t / "services").mkdir()
        (t / "services" / "README.md").write_text("the lore_bible track is parked", encoding="utf-8")
        cases.append(("a README under a code root does not fire", len(check(t)), 0))

        # NEAR-MISS: the word boundary must hold, or the gate cries wolf.
        (t / "contracts" / "biblio.yaml").write_text("lore_bibliography: []", encoding="utf-8")
        cases.append(("`lore_bibliography` is not `lore_bible`", len(check(t)), 0))
        (t / "contracts" / "biblio.yaml").write_text("folklore_bible: []", encoding="utf-8")
        cases.append(("`folklore_bible` is a different word", len(check(t)), 0))
        (t / "contracts" / "biblio.yaml").unlink()

        # And the check must be able to see a file at all -- a walker that found
        # nothing anywhere would pass every case above for the wrong reason.
        (t / "contracts" / "lore-bible.v1.yaml").write_text("sections: []", encoding="utf-8")
        cases.append(("a contract named for it fires", len(check(t)), 1))

    bad = 0
    for name, got, want in cases:
        ok = got == want
        bad += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: {got} finding(s) (want {want})")
    if bad:
        print(f"lore-bible-park-gate --selftest: {bad} case(s) FAILED")
        return 1
    print(
        "lore-bible-park-gate --selftest: every rule bites, and none cries wolf — "
        "a migration, a table name inside another file and a contract each fire, "
        "while docs, a README under a code root and `lore_bibliography` do not"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="prove the check can fail")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    found = check()
    if found:
        print(f"lore-bible-park-gate: {len(found)} lore-bible CODE artifact(s) — the track is PARKED\n")
        for f in found:
            print(f"  ✗ {f}")
        print(REASON)
        return 1
    print(
        "lore-bible-park-gate: OK — the lore-bible track is parked and no schema or "
        f"producer has appeared under {'/, '.join(CODE_ROOTS)}/. "
        "`D-LORE-BIBLE-PARKED-SWEEP-EXISTS`"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
