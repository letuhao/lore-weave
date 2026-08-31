#!/usr/bin/env python3
"""migration-idempotency-validator — non-idempotent SQL in EITHER migration tree.

`scripts/migration-idempotency-validator.sh` is now a thin wrapper around this
file, the same shape `workflow-gate.sh` → `workflow-gate.py` already has in this
repo and for the same two reasons: Windows, and something the shell version
could not do at all (below). Both CI legs still invoke the `.sh` by name.

WHAT CHANGED, AND WHY EACH CHANGE WAS FORCED BY A MEASUREMENT
--------------------------------------------------------------
**1 · It walks BOTH trees.** The shell version's default target set was
`contracts/migrations/per_reality` only. `migrations/meta` — 78 files, including
the ownership migrations `036`/`037` — was walked by nothing. That is `NV-3`,
and it is the *second* time this exact script has had it: the version before
2026-08-07 enumerated two filenames while the directory held thirty-eight.
A glob, per tree, so tomorrow's file is covered by existing.

Widening it found **two real violations on the first run** —
`036_reality_ownership` creates `idx_reality_registry_owner` without
`IF NOT EXISTS` and drops it without `IF EXISTS`, so a retried migration fails
on the create and a re-run down fails on the drop.

**2 · The checks are STATEMENT-aware, not line-anchored.** Every pattern was a
`grep -E` anchored to one line, and the meta tree writes

    ALTER TABLE reality_registry
        DROP COLUMN owner_user_id,
        DROP COLUMN owner_kind;

which no single-line regex can see. Measured across both trees: **8 of 13
`ALTER TABLE … COLUMN` statements are multi-line**, four of them in the tree the
lint already walked. So the widening alone would have "covered" the meta tree
while seeing almost none of it — a walk is not a check, and a file count is not
a finding count.

**3 · A tree that yields ZERO files is a REFUSAL (exit 2), not a pass.** The
shell version printed *"no targets specified and no migrations found"* and
**exited 0**. A wrong path, a renamed directory or a moved tree would report
success forever. That is the failure mode this whole widening exists to remove,
so it must not be reachable through the widening itself.

WHAT THIS CANNOT SEE — unchanged, and worth keeping in front of the reader
---------------------------------------------------------------------------
It reads TEXT; the property is BEHAVIOUR. "Idempotent" covers two claims:

  RETRY-SAFETY (real, and what this is a proxy for) — a runner dies half way
  through migration N and retries N. `scripts/dp-migration-chain-smoke.py`
  checks this by behaviour against a live Postgres.

  WHOLE-HISTORY REPLAY (not real, and NOT a defect) — re-running 0001..NNNN
  against a database that already has them. This FAILS on `0001_initial` and
  `0007_drift_metadata` for reasons that are correct, and a versioned runner
  never produces that scenario. Written down because a naive chain test does
  exactly this and looks like a finding against this script.

    python scripts/migration-idempotency-validator.py
    python scripts/migration-idempotency-validator.py path.sql ...
    python scripts/migration-idempotency-validator.py --self-test
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Tree -> the minimum number of `.sql` files that must be found there.
#
# A floor rather than a bare "> 0": both trees are large and long-lived, so a
# walk that suddenly finds three files has lost something, and the difference
# between "found nothing" and "found nearly nothing" is not worth a second
# failure mode. The numbers are deliberately well below today's counts (39 and
# 78) so ordinary growth and the occasional deletion never trip them.
TREES: dict[str, int] = {
    "contracts/migrations/per_reality": 20,
    "migrations/meta": 40,
}


def strip_noise(sql: str) -> str:
    """Blank comments, string literals and dollar-quoted bodies, keeping offsets.

    Offsets are preserved (blank, never delete) so a violation can still be
    reported at its real line. Dollar-quoted bodies matter here specifically:
    `0019_channels.up.sql` defines a trigger function whose body contains `;`
    and SQL keywords, and a splitter that walked into it would manufacture
    statements nobody wrote.
    """
    out = list(sql)
    i, n = 0, len(sql)
    while i < n:
        if sql.startswith("--", i):
            while i < n and sql[i] != "\n":
                out[i] = " "
                i += 1
            continue
        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            end = n if end < 0 else end + 2
            for k in range(i, end):
                if sql[k] != "\n":
                    out[k] = " "
            i = end
            continue
        if sql[i] == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'" and j + 1 < n and sql[j + 1] == "'":
                    j += 2
                    continue
                if sql[j] == "'":
                    break
                j += 1
            for k in range(i, min(j + 1, n)):
                if sql[k] != "\n":
                    out[k] = " "
            i = min(j + 1, n)
            continue
        if sql[i] == "$":
            m = re.match(r"\$[A-Za-z_]*\$", sql[i:])
            if m:
                tag = m.group(0)
                end = sql.find(tag, i + len(tag))
                end = n if end < 0 else end + len(tag)
                for k in range(i, end):
                    if sql[k] != "\n":
                        out[k] = " "
                i = end
                continue
        i += 1
    return "".join(out)


def statements(sql: str) -> list[tuple[int, str]]:
    """[(1-based start line, whitespace-collapsed statement)]."""
    clean = strip_noise(sql)
    out: list[tuple[int, str]] = []
    start = 0
    for end in [m.end() for m in re.finditer(r";", clean)] + [len(clean)]:
        chunk = clean[start:end]
        if chunk.strip():
            line = clean.count("\n", 0, start + (len(chunk) - len(chunk.lstrip()))) + 1
            out.append((line, " ".join(chunk.split())))
        start = end
    return out


# (label, the statement shape, the idempotent form it must carry)
#
# Each is matched against a whitespace-collapsed STATEMENT, so a clause on its
# own line is the same subject as one written inline. `re.I` throughout: this
# corpus writes SQL keywords in both cases.
CHECKS: list[tuple[str, re.Pattern[str], re.Pattern[str]]] = [
    (
        "CREATE TABLE missing IF NOT EXISTS",
        re.compile(r"\bCREATE\s+(?:UNLOGGED\s+)?TABLE\b", re.I),
        re.compile(r"\bCREATE\s+(?:UNLOGGED\s+)?TABLE\s+IF\s+NOT\s+EXISTS\b", re.I),
    ),
    (
        "CREATE INDEX missing IF NOT EXISTS",
        re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.I),
        re.compile(
            r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?IF\s+NOT\s+EXISTS\b", re.I
        ),
    ),
    (
        "DROP TABLE missing IF EXISTS",
        re.compile(r"\bDROP\s+TABLE\b", re.I),
        re.compile(r"\bDROP\s+TABLE\s+IF\s+EXISTS\b", re.I),
    ),
    (
        "DROP INDEX missing IF EXISTS",
        re.compile(r"\bDROP\s+INDEX\b", re.I),
        re.compile(r"\bDROP\s+INDEX\s+(?:CONCURRENTLY\s+)?IF\s+EXISTS\b", re.I),
    ),
    (
        "ALTER TABLE ADD COLUMN missing IF NOT EXISTS",
        re.compile(r"\bALTER\s+TABLE\b.*\bADD\s+COLUMN\b", re.I),
        # EVERY `ADD COLUMN` in the statement must carry it, not just the first.
        # `ALTER TABLE t ADD COLUMN IF NOT EXISTS a INT, ADD COLUMN b INT;` is a
        # statement that fails on retry, and a first-match test calls it clean.
        None,  # type: ignore[list-item]
    ),
    (
        "ALTER TABLE DROP COLUMN missing IF EXISTS",
        re.compile(r"\bALTER\s+TABLE\b.*\bDROP\s+COLUMN\b", re.I),
        None,  # type: ignore[list-item]
    ),
    (
        # Added with the meta widening, and it is the tree's OWN convention
        # rather than a new rule imposed on it: measured across both trees,
        # **13 of 18** `DROP CONSTRAINT`s already carry `IF EXISTS`. The five
        # that do not include `036` and `037` — the two down-migrations this
        # widening exists to exercise — so without this check the validator
        # would have walked them, passed them, and left the statement that
        # actually fails on a re-run unreported.
        #
        # There is no `ADD CONSTRAINT IF NOT EXISTS` in Postgres, so the
        # symmetric check does not exist and is not silently implied.
        "ALTER TABLE DROP CONSTRAINT missing IF EXISTS",
        re.compile(r"\bALTER\s+TABLE\b.*\bDROP\s+CONSTRAINT\b", re.I),
        None,  # type: ignore[list-item]
    ),
]

ADD_COL = re.compile(r"\bADD\s+COLUMN\b(?!\s+IF\s+NOT\s+EXISTS)", re.I)
DROP_COL = re.compile(r"\bDROP\s+COLUMN\b(?!\s+IF\s+EXISTS)", re.I)
DROP_CON = re.compile(r"\bDROP\s+CONSTRAINT\b(?!\s+IF\s+EXISTS)", re.I)


ADD_CON_NAMED = re.compile(r"\bADD\s+CONSTRAINT\s+([A-Za-z_][\w]*)", re.I)


def unguarded_added_constraints(sql: str) -> list[tuple[int, str]]:
    """`ADD CONSTRAINT x` with no `DROP CONSTRAINT IF EXISTS x` before it.

    # Why this is a check and not a convention

    Postgres has **no `ADD CONSTRAINT IF NOT EXISTS`**, so the only way to make
    a constraint-adding migration retry-safe is to drop it first. This tree
    already knows that — measured 2026-08-10, **seven of nine** constraint-adding
    migrations do exactly `DROP CONSTRAINT IF EXISTS x;` immediately before
    `ADD CONSTRAINT x`.

    The two that did not were `036` and `037`, and the cost was measured rather
    than reasoned about: re-applying `036_reality_ownership.up.sql` against a
    throwaway meta database died with `ERROR: constraint
    "reality_registry_owner_kind_enum" for relation "reality_registry" already
    exists`. A convention that seven files follow and two do not is not a
    convention, it is a coin flip — so it becomes a rule.

    Order matters and is checked: a drop AFTER the add leaves the retry broken
    while looking, in a diff, exactly like a fix.
    """
    out: list[tuple[int, str]] = []
    stmts = statements(sql)
    for idx, (line, st) in enumerate(stmts):
        for m in ADD_CON_NAMED.finditer(st):
            name = m.group(1)
            guard = re.compile(
                r"\bDROP\s+CONSTRAINT\s+IF\s+EXISTS\s+" + re.escape(name) + r"\b", re.I
            )
            # Anywhere earlier in the file, or earlier in this same statement —
            # `ALTER TABLE t DROP CONSTRAINT IF EXISTS c, ADD CONSTRAINT c …` is
            # one statement and is retry-safe.
            before = [s for _, s in stmts[:idx]] + [st[: m.start()]]
            if not any(guard.search(s) for s in before):
                out.append((line, name))
    return out


def check_sql(sql: str) -> list[tuple[int, str, str]]:
    """[(line, label, statement excerpt)] for one file's text."""
    found = []
    for line, name in unguarded_added_constraints(sql):
        found.append((
            line,
            "ADD CONSTRAINT with no preceding DROP CONSTRAINT IF EXISTS",
            f"ADD CONSTRAINT {name} — Postgres has no ADD CONSTRAINT IF NOT EXISTS, so a "
            f"retried migration fails here. Add `DROP CONSTRAINT IF EXISTS {name};` before it, "
            f"as seven sibling migrations already do",
        ))
    for line, st in statements(sql):
        for label, shape, ok in CHECKS:
            if not shape.search(st):
                continue
            if ok is None:
                # Clause-level: EVERY occurrence must carry its guard, not just
                # the first. Keyed off the label's own words so a check added
                # tomorrow cannot silently fall through to the wrong clause
                # matcher — the `"ADD" in label` two-way test this replaced
                # would have routed DROP CONSTRAINT to the DROP COLUMN regex
                # and reported clean forever.
                clause = {
                    "ADD COLUMN": ADD_COL,
                    "DROP COLUMN": DROP_COL,
                    "DROP CONSTRAINT": DROP_CON,
                }
                matcher = next((r for k, r in clause.items() if k in label), None)
                if matcher is None:
                    raise AssertionError(
                        f"clause-level check {label!r} has no matcher — it would report clean "
                        f"on everything, which is worse than not existing"
                    )
                if matcher.search(st):
                    found.append((line, label, st[:160]))
            elif not ok.search(st):
                found.append((line, label, st[:160]))
    return found


def default_targets() -> tuple[list[Path], list[str]]:
    """(files, problems) across every configured tree."""
    files: list[Path] = []
    problems: list[str] = []
    for rel, floor in TREES.items():
        d = REPO / rel
        if not d.is_dir():
            problems.append(f"tree {rel} does not exist — the walk is pointed at nothing")
            continue
        found = sorted(p for p in d.glob("*.sql"))
        print(f"[idempotency] {rel}: {len(found)} file(s)")
        if len(found) < floor:
            problems.append(
                f"tree {rel} yielded {len(found)} file(s), below its floor of {floor}. "
                f"A walk that finds (almost) nothing exits 0 and reads as coverage — which is "
                f"the exact failure this validator was widened to remove."
            )
        files += found
    return files, problems


# ── self-test ────────────────────────────────────────────────────────────────

_MULTILINE_DROP = """
ALTER TABLE reality_registry
    DROP COLUMN owner_user_id,
    DROP COLUMN owner_kind;
"""

_MULTILINE_OK = """
ALTER TABLE reality_registry
    DROP COLUMN IF EXISTS owner_user_id,
    DROP COLUMN IF EXISTS owner_kind;
"""

_PARTIAL_ADD = """
ALTER TABLE t ADD COLUMN IF NOT EXISTS a INT, ADD COLUMN b INT;
"""

_IN_COMMENT = """
-- DROP INDEX idx_foo;
-- CREATE TABLE bar (x INT);
CREATE TABLE IF NOT EXISTS bar (x INT);
"""

_IN_FUNCTION_BODY = """
CREATE OR REPLACE FUNCTION f() RETURNS trigger AS $$
BEGIN
    -- a body may legitimately talk about anything
    RAISE EXCEPTION 'DROP TABLE x';
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_CLEAN = """
CREATE TABLE IF NOT EXISTS t (x INT);
CREATE INDEX IF NOT EXISTS i ON t (x);
ALTER TABLE t ADD COLUMN IF NOT EXISTS y INT;
ALTER TABLE t DROP CONSTRAINT IF EXISTS c;
DROP INDEX IF EXISTS i;
DROP TABLE IF EXISTS t;
"""


def self_test() -> int:
    fails: list[str] = []

    def labels(sql: str) -> set[str]:
        return {lbl for _, lbl, _ in check_sql(sql)}

    if "ALTER TABLE DROP COLUMN missing IF EXISTS" not in labels(_MULTILINE_DROP):
        fails.append("a MULTI-LINE `DROP COLUMN` was not seen — the whole reason for this rewrite")
    if labels(_MULTILINE_OK):
        fails.append("a multi-line DROP COLUMN IF EXISTS was flagged (false positive)")
    if "ALTER TABLE ADD COLUMN missing IF NOT EXISTS" not in labels(_PARTIAL_ADD):
        fails.append(
            "a statement whose SECOND `ADD COLUMN` lacks IF NOT EXISTS was called clean — "
            "a first-match test passes the exact statement that fails on retry"
        )
    if labels(_IN_COMMENT):
        fails.append("a pattern inside an SQL comment was counted")
    if labels(_IN_FUNCTION_BODY):
        fails.append("a pattern inside a dollar-quoted function body was counted")
    if labels(_CLEAN):
        fails.append("fully idempotent SQL was flagged (false positive)")

    # The ADD CONSTRAINT idiom, all four directions.
    con = "ADD CONSTRAINT with no preceding DROP CONSTRAINT IF EXISTS"
    if con not in labels("ALTER TABLE t ADD CONSTRAINT c CHECK (x > 0);"):
        fails.append("a bare ADD CONSTRAINT was not flagged")
    if labels(
        "ALTER TABLE t DROP CONSTRAINT IF EXISTS c;\nALTER TABLE t ADD CONSTRAINT c CHECK (x > 0);"
    ):
        fails.append("the guarded DROP-then-ADD idiom was flagged (false positive)")
    if labels("ALTER TABLE t DROP CONSTRAINT IF EXISTS c, ADD CONSTRAINT c CHECK (x > 0);"):
        fails.append("a single-statement DROP IF EXISTS + ADD was flagged (false positive)")
    if con not in labels(
        "ALTER TABLE t ADD CONSTRAINT c CHECK (x > 0);\nALTER TABLE t DROP CONSTRAINT IF EXISTS c;"
    ):
        fails.append(
            "a DROP placed AFTER the ADD was accepted — the retry is still broken and the "
            "diff looks like a fix"
        )
    # ...and the guard must name the RIGHT constraint. A "is there a drop
    # somewhere above" test would accept this, and 036 is precisely a file that
    # drops three constraints and adds three: name-blindness there would have
    # certified all of them off any one drop.
    if con not in labels(
        "ALTER TABLE t DROP CONSTRAINT IF EXISTS other;\n"
        "ALTER TABLE t ADD CONSTRAINT c CHECK (x > 0);"
    ):
        fails.append("a DROP of a DIFFERENT constraint satisfied the guard (name-blind)")

    # Each single-statement arm must fire on its own bad shape. Written as a
    # loop over the real CHECKS list rather than six hand-written cases: a check
    # added tomorrow with no self-test case would otherwise be uncovered, which
    # is this file's own headline defect one level up.
    bad_shapes = {
        "CREATE TABLE missing IF NOT EXISTS": "CREATE TABLE t (x INT);",
        "CREATE INDEX missing IF NOT EXISTS": "CREATE INDEX i ON t (x);",
        "DROP TABLE missing IF EXISTS": "DROP TABLE t;",
        "DROP INDEX missing IF EXISTS": "DROP INDEX i;",
        "ALTER TABLE ADD COLUMN missing IF NOT EXISTS": "ALTER TABLE t ADD COLUMN a INT;",
        "ALTER TABLE DROP COLUMN missing IF EXISTS": "ALTER TABLE t DROP COLUMN a;",
        "ALTER TABLE DROP CONSTRAINT missing IF EXISTS": "ALTER TABLE t DROP CONSTRAINT c;",
    }
    for label, _, _ in CHECKS:
        if label not in bad_shapes:
            fails.append(f"check {label!r} has no self-test case — it is unproven")
            continue
        if label not in labels(bad_shapes[label]):
            fails.append(f"check {label!r} did NOT fire on {bad_shapes[label]!r}")

    # And the zero-walk refusal, which is the arm that makes "it walks both
    # trees" a claim rather than a hope.
    if not [p for p in default_targets()[1]] == []:
        fails.append("a configured tree is missing or below its floor on this checkout")

    if fails:
        print("[idempotency] SELF-TEST FAILED:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(
        # `+ 1` is the ADD CONSTRAINT idiom check, which is not a CHECKS row
        # because it is cross-statement rather than a statement shape. Counted
        # explicitly so the printed number is the number of checks, not the
        # length of one list that happens to hold most of them.
        f"[idempotency] self-test OK — {len(CHECKS) + 1} check(s), each proven to fire on its own "
        f"bad shape; multi-line and partial-clause statements are seen; comments and "
        f"dollar-quoted bodies are not; clean SQL is not flagged"
    )
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv or "--selftest" in argv:
        return self_test()
    if self_test() != 0:
        return 2

    explicit = [a for a in argv if not a.startswith("-")]
    if explicit:
        targets = [Path(a) if Path(a).is_absolute() else REPO / a for a in explicit]
        problems: list[str] = []
    else:
        targets, problems = default_targets()

    if problems:
        for p in problems:
            print(f"[idempotency] MISUSE — {p}")
        return 2

    violations = 0
    for f in targets:
        if not f.is_file() or f.suffix != ".sql" or f.stat().st_size == 0:
            continue
        rel = str(f.relative_to(REPO)).replace("\\", "/") if REPO in f.parents else str(f)
        for line, label, excerpt in check_sql(f.read_text(encoding="utf-8", errors="replace")):
            print(f"[idempotency] {rel}:{line}: {label}")
            print(f"    {excerpt}")
            violations += 1

    if violations:
        print(f"[idempotency] FAIL — {violations} non-idempotent pattern(s) found")
        return 1
    print(f"[idempotency] PASS — {len(targets)} file(s) across {len(TREES)} tree(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
