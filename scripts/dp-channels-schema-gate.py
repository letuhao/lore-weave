#!/usr/bin/env python3
"""dp-channels-schema-gate — `1b.3`, the `V.2` oracle for the channel registry.

**Spec and code are BOTH SQL here, which is rare and worth exploiting.**

`FLOW-2` is this project's recurring defect: a correction decided, applied where
the author was looking, and not applied where they were not. It has now been
measured four times in this corpus, and `REC-103` is the sharpest instance —
`REC-102a` ruled `ChannelId` to be `i64`, that ruling reached the newtype and the
Rust code in the same commit, and it **never reached the schema thirty lines
below it**. The one artifact a migration would be written from still declared
`UUID`, and nothing said so for the eight weeks in between.

`crates/dp/tests/spec_oracle.rs` compares LOCKED markdown to Rust `const`s. This
does the same for the one place both sides are the same language: `DP-Ch2`'s
`CREATE TABLE` in `12_channel_primitives.md`, against
`contracts/migrations/per_reality/0019_channels.up.sql`.

WHAT IT COMPARES, AND WHY NOT MORE
----------------------------------
  * every column's NAME and TYPE, in order
  * the set of named CONSTRAINTS
  * the presence of `channels_root_single` as a PARTIAL UNIQUE INDEX on both
    sides — `REC-104`'s subject, and the one constraint that spent months in the
    spec as a form that could not fail

It does **not** normalise or compare CHECK *bodies*. `(depth >= 0 AND depth <=
16)` and `(depth BETWEEN 0 AND 16)` are the same predicate and different text,
and a comparison that called them different would cry wolf until someone
switched it off. **Stated rather than glossed:** a constraint can be present on
both sides under one name and mean two things, and this gate would not know.
Closing that needs the live smoke (`scripts/dp-channels-live-smoke.py`), which
asks each constraint to actually reject a row — which is why that script exists
and why `1b` does not close without it.

Run: ``python scripts/dp-channels-schema-gate.py`` — wired pre-commit.
Exit 0 = they agree; 1 = they do not; 2 = one of them could not be parsed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "docs/03_planning/LLM_MMO_RPG/06_data_plane/12_channel_primitives.md"
MIGRATION = REPO / "contracts/migrations/per_reality/0019_channels.up.sql"

_TABLE = re.compile(r"CREATE TABLE(?: IF NOT EXISTS)? channels \((.*?)\n\);", re.S)
_COL = re.compile(r"^([a-z_]+)\s+([A-Z]+)")


def strip_sql_comments(text: str) -> str:
    return "\n".join(line.split("--")[0] for line in text.splitlines())


def columns(text: str, who: str) -> list[tuple[str, str]]:
    m = _TABLE.search(text)
    if not m:
        print(f"dp-channels-schema-gate: MISUSE — no `CREATE TABLE channels (..)` in {who}. "
              f"The parse found nothing, and a comparison against nothing agrees with anything.",
              file=sys.stderr)
        sys.exit(2)
    out = []
    for line in strip_sql_comments(m.group(1)).splitlines():
        line = line.strip().rstrip(",")
        c = _COL.match(line)
        if c:
            out.append((c.group(1), c.group(2)))
    return out


def constraints(text: str) -> list[str]:
    return sorted(set(re.findall(r"CONSTRAINT (\w+)", strip_sql_comments(text))))


def root_index(text: str) -> str | None:
    """`REC-104`'s subject: a PARTIAL unique index, not a plain UNIQUE."""
    m = re.search(
        r"CREATE UNIQUE INDEX(?: IF NOT EXISTS)? channels_root_single\s*"
        r"ON channels \(([^)]*)\)\s*WHERE ([^;]+);",
        strip_sql_comments(text), re.S)
    if not m:
        return None
    return f"({m.group(1).strip()}) WHERE {m.group(2).strip()}"


def self_test() -> int:
    """Cases on synthetic SQL, both directions."""
    bad = []
    good = "CREATE TABLE channels (\n  reality_id UUID NOT NULL,\n  id BIGINT NOT NULL\n);"
    if columns(good, "self-test") != [("reality_id", "UUID"), ("id", "BIGINT")]:
        bad.append("the column parse does not read a plain table")
    drifted = good.replace("id BIGINT", "id UUID")
    if columns(good, "s") == columns(drifted, "s"):
        bad.append("a changed column TYPE is invisible — this gate's whole subject (REC-103)")
    renamed = good.replace("reality_id UUID", "realm_id UUID")
    if columns(good, "s") == columns(renamed, "s"):
        bad.append("a changed column NAME is invisible")
    if columns(good, "s") == columns(good.replace("  id BIGINT NOT NULL\n", ""), "s"):
        bad.append("a DROPPED column is invisible")
    if constraints("CONSTRAINT a CHECK (1)") != ["a"]:
        bad.append("the constraint parse does not read a named constraint")
    # `REC-104`: a plain UNIQUE must NOT satisfy the partial-index check.
    if root_index("CONSTRAINT channels_root_single UNIQUE (id)") is not None:
        bad.append("a plain `UNIQUE (id)` reads as the partial index — REC-104 exactly")
    if root_index("CREATE UNIQUE INDEX channels_root_single ON channels (reality_id) "
                  "WHERE parent IS NULL;") != "(reality_id) WHERE parent IS NULL":
        bad.append("the partial index is not read when it IS present")
    if bad:
        print("dp-channels-schema-gate: SELF-TEST FAIL")
        for b in bad:
            print("  " + b)
        return 1
    print("dp-channels-schema-gate: SELF-TEST PASS — a changed type, a changed name and a dropped "
          "column are each visible, and a plain `UNIQUE (id)` does NOT read as REC-104's partial "
          "index (non-vacuous in both directions)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if self_test() != 0:
        return 2

    for f in (SPEC, MIGRATION):
        if not f.is_file():
            print(f"dp-channels-schema-gate: MISUSE — {f} does not exist", file=sys.stderr)
            return 2

    spec = SPEC.read_bytes().decode("utf-8")
    mig = MIGRATION.read_bytes().decode("utf-8")

    findings = []
    s_cols, m_cols = columns(spec, "DP-Ch2"), columns(mig, "0019_channels.up.sql")
    if s_cols != m_cols:
        findings.append(f"COLUMNS differ.\n      DP-Ch2      : {s_cols}\n"
                        f"      0019_channels: {m_cols}")
    s_con, m_con = constraints(spec), constraints(mig)
    if s_con != m_con:
        findings.append(f"CONSTRAINTS differ.\n      only in DP-Ch2      : "
                        f"{sorted(set(s_con) - set(m_con))}\n"
                        f"      only in 0019_channels: {sorted(set(m_con) - set(s_con))}")
    s_root, m_root = root_index(spec), root_index(mig)
    if s_root is None or m_root is None or s_root != m_root:
        findings.append(f"channels_root_single differs — REC-104's subject.\n"
                        f"      DP-Ch2      : {s_root}\n      0019_channels: {m_root}")

    if findings:
        print(f"dp-channels-schema-gate: {len(findings)} disagreement(s) between the LOCKED spec "
              f"and the migration\n")
        for f in findings:
            print(f"  {f}")
        print("\nDP-Ch2 in 12_channel_primitives.md and 0019_channels.up.sql are two statements of")
        print("one schema. FLOW-2 is what happens when one moves and the other does not — REC-103")
        print("is that exact defect, and it went unnoticed for eight weeks.")
        return 1

    print(f"dp-channels-schema-gate: OK — DP-Ch2 and 0019_channels agree on {len(m_cols)} column(s) "
          f"and {len(m_con)} named constraint(s), and channels_root_single is a partial unique "
          f"index {m_root} on both sides")
    return 0


if __name__ == "__main__":
    sys.exit(main())
