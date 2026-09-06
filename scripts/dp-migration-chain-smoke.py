#!/usr/bin/env python3
"""dp-migration-chain-smoke — the per-reality migration chain, on a live Postgres.

**Not a gate, and deliberately not named like one.** It needs a database, so
`gate-wiring-gate`'s filename predicate must not demand that CI run it; CI has no
Postgres. Same shape and same reason as `scripts/dp-channels-live-smoke.py`.

WHY IT EXISTS — the live smoke has a hole it cannot see
-------------------------------------------------------
`dp-channels-live-smoke.py` applies `0019_channels.up.sql` **alone, into an empty
database**. That is the right shape for testing the table's constraints, and it
means the smoke is structurally blind to everything about the other eighteen
migrations: an ordering problem, a dependency on a table an earlier migration
creates, a name that collides with something `0014` already made. `1b.5` recorded
*"the migration applies cleanly on the real 0001->0019 chain"* as evidence — and
that was measured BEFORE `REC-106` rewrote the file, so by the time it mattered
it was a claim about a previous version.

WHAT IT MEASURES, AND THE DISTINCTION THAT TOOK A WRONG TURN TO FIND
-------------------------------------------------------------------
Two different properties wear the word *idempotent*, and only one of them is real:

  **RETRY-SAFETY (real).** A migration runner dies half way through applying
  migration N and retries N. Applying N twice in a row must succeed. This is what
  `scripts/migration-idempotency-validator.sh` checks textually, and it is
  checked here by BEHAVIOUR: apply each file, immediately apply it again.
  **Measured 2026-08-08: 19 of 19 migrations retry cleanly** (18 before the
  image gained pgvector -- `0008` could not apply at all, and was skipped).

  **WHOLE-HISTORY REPLAY (not real, and not a defect).** Re-running the entire
  `0001..0019` sequence against a database that has already had all of it. This
  FAILS on `0001_initial` (a later migration changed `events`' key, so `0001`'s
  foreign key no longer matches) and on `0007_drift_metadata` (`0017`/`0018`
  narrowed `projection_drift_table_name_allowlist`, so `0007`'s seed rows are now
  refused). **Both are CORRECT behaviour**, and a versioned runner never produces
  the scenario. It is recorded here because a naive chain test does exactly this,
  reports two failures, and looks like a finding. It is not one. The precise test
  — retry each migration at the point it is applied — is what settles it, and
  that is the one this script runs.

`0008_pgvector_setup` is skipped when the `vector` extension is unavailable in
the container. That is an environment fact, reported rather than swallowed: the
run says so, and the count it prints excludes it rather than counting it as a
pass. **It no longer skips**: the stack image builds pgvector from source
against its own `pg_config` (`infra/postgres-pgvector.Dockerfile`). The skip
path is kept, because the honest report of an absent extension is exactly what
surfaced `1b14-05` -- a migration the provisioner would die on.

Run:  python scripts/dp-migration-chain-smoke.py
      (add --keep to leave the throwaway database in place)
Exit 0 = the chain applies, every migration retries, the down chain reverses to
an empty schema, and `channels` as BUILT BY POSTGRES matches what 0019 declares.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO / "contracts/migrations/per_reality"
CONTAINER = "infra-postgres-1"
USER = "loreweave"
# Carries `test` AND `smoke`. `scripts/db-safety-gate.py` and CLAUDE.md's
# destructive-ops rule both require a throwaway marker; this script DROPs.
# Per-run suffix for the reason its sibling carries one (`1b7db-12`,
# `1b12-08`): a shared name means two concurrent runs drop each other's
# database mid-run, and the corruption presents as a schema defect.
DB = f"dp_chain_smoke_test_{os.getpid()}"

# What `0019_channels.up.sql` declares. Compared against what POSTGRES REPORTS
# after the whole chain has run, not against the file — the file is the claim,
# `pg_catalog` is the fact, and a migration that silently loses a constraint to
# an ordering problem is exactly what this catches.
EXPECT_COLUMNS = {
    "reality_id", "id", "parent", "level_name", "display_name", "depth",
    "lifecycle", "metadata", "created_at", "dissolved_at", "parent_depth",
}
EXPECT_CONSTRAINTS = {
    "channels_pkey", "channels_id_depth_uq", "channels_parent_fk",
    "channels_depth_bounded", "channels_lifecycle_known", "channels_no_orphan",
    "channels_id_positive", "channels_level_name_nonempty",
    "channels_dissolved_at_iff_dissolved",
    # `1b7db-L1` and `1b7db-02`.
    "channels_id_allocatable", "channels_parent_depth_derived",
    # A CONSTRAINT TRIGGER gets a `pg_constraint` row of its own, which is the
    # only place its DEFERRABILITY is recorded — and the deferrability is what
    # makes a one-statement subtree dissolve possible (`1b7db-07`). Asserting it
    # here means downgrading it to a plain BEFORE trigger reds from the DATABASE
    # side, not just from the file comparison.
    "channels_dissolve_order_trg",
    # Postgres 17+ records NOT NULL in `pg_constraint`, which is a gift here:
    # `1b5-H4`'s finding was that the schema gate could not see `NOT NULL` at
    # all, and a four-way mutant dropping it applied cleanly. These seven are
    # asserted rather than filtered out, so the NULLABLE columns are asserted
    # too by their absence — `parent`, `display_name`, `dissolved_at` and the
    # generated `parent_depth` must NOT appear.
    "channels_reality_id_not_null", "channels_id_not_null",
    "channels_level_name_not_null", "channels_depth_not_null",
    "channels_lifecycle_not_null", "channels_metadata_not_null",
    "channels_created_at_not_null",
}
EXPECT_INDEXES = {
    "channels_pkey", "channels_id_depth_uq", "channels_root_single",
    "channels_parent_idx", "channels_level_idx", "channels_lifecycle_idx",
}
EXPECT_TRIGGERS = {"channels_lifecycle_guard_trg", "channels_dissolve_order_trg"}


def guard_throwaway(name: str) -> None:
    markers = ("test", "smoke", "audit")
    hit = [m for m in markers if m in name.lower()]
    if not hit:
        print(f"dp-migration-chain-smoke: REFUSING to operate on {name!r} — no throwaway marker "
              f"({'/'.join(markers)}). This script CREATEs and DROPs.", file=sys.stderr)
        sys.exit(2)
    print(f"  guard: {name!r} carries {hit} — safe to create and drop")


def psql(sql: str, db: str = DB) -> tuple[int, str]:
    p = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", USER, "-d", db,
         "-v", "ON_ERROR_STOP=1", "-tAc", sql],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


def apply_file(path: Path, db: str = DB) -> tuple[int, str]:
    with open(path, "rb") as fh:
        p = subprocess.run(
            ["docker", "exec", "-i", CONTAINER, "psql", "-U", USER, "-d", db,
             "-v", "ON_ERROR_STOP=1"],
            stdin=fh, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


def first_error(out: str) -> str:
    for line in out.splitlines():
        if "ERROR:" in line:
            return line.split("ERROR:")[1].strip()[:100]
    return "(no ERROR line)"


def names(sql: str) -> set[str]:
    code, out = psql(sql)
    return set(filter(None, out.splitlines())) if code == 0 else set()


def main() -> int:
    print(f"{'=' * 78}\ndp-migration-chain-smoke — the real 0001..NNNN chain\n{'=' * 78}")
    guard_throwaway(DB)

    if psql("SELECT 1", db="postgres")[0] != 0:
        print("dp-migration-chain-smoke: FAIL — no live Postgres.", file=sys.stderr)
        return 1

    ups = sorted(MIGRATIONS.glob("*.up.sql"))
    downs = sorted(MIGRATIONS.glob("*.down.sql"), reverse=True)
    if not ups:
        print(f"dp-migration-chain-smoke: MISUSE — no migrations under {MIGRATIONS}",
              file=sys.stderr)
        return 2

    psql(f"DROP DATABASE IF EXISTS {DB}", db="postgres")
    if psql(f"CREATE DATABASE {DB}", db="postgres")[0] != 0:
        print(f"dp-migration-chain-smoke: FAIL — cannot create {DB}", file=sys.stderr)
        return 1

    ok = True
    skipped: list[str] = []
    retried = 0
    try:
        print(f"\n── FORWARD, and each migration RETRIED immediately (the property a "
              f"crashed runner needs)")
        for f in ups:
            code, out = apply_file(f)
            if code != 0:
                err = first_error(out)
                # An absent extension is an environment fact, not a migration
                # defect. Reported and EXCLUDED from the count rather than
                # counted as a pass — a skip that inflates a total is how a
                # suite comes to claim coverage it does not have.
                if "is not available" in err or "could not open extension" in err:
                    skipped.append(f"{f.name}: {err}")
                    print(f"   SKIP {f.name:48s} {err}")
                    continue
                print(f"   FAIL {f.name:48s} {err}")
                ok = False
                continue
            code2, out2 = apply_file(f)
            if code2 != 0:
                print(f"   RETRY-FAIL {f.name:42s} {first_error(out2)}")
                ok = False
            else:
                retried += 1
                print(f"   ok   {f.name:48s} (applied + retried)")

        # ── DATA. Not "the file says so" — what Postgres reports it built.
        print(f"\n── MEASURE: `channels` as POSTGRES reports it, after the whole chain")
        cols = names("SELECT column_name FROM information_schema.columns "
                     "WHERE table_name='channels'")
        cons = names("SELECT conname FROM pg_constraint WHERE conrelid='channels'::regclass")
        idxs = names("SELECT indexname FROM pg_indexes WHERE tablename='channels'")
        trgs = names("SELECT tgname FROM pg_trigger WHERE tgrelid='channels'::regclass "
                     "AND NOT tgisinternal")
        gen, = (names("SELECT generation_expression FROM information_schema.columns "
                      "WHERE table_name='channels' AND column_name='parent_depth'")
                or {"(absent)"})
        for label, got, want in [("columns", cols, EXPECT_COLUMNS),
                                 ("constraints", cons, EXPECT_CONSTRAINTS),
                                 ("indexes", idxs, EXPECT_INDEXES)]:
            missing, extra = sorted(want - got), sorted(got - want)
            good = not missing and not extra
            print(f"   {'OK  ' if good else 'FAIL'} {label:12s} {len(got):2d} present"
                  + ("" if good else f"   missing={missing} unexpected={extra}"))
            ok &= good
        good = trgs == EXPECT_TRIGGERS
        print(f"   {'OK  ' if good else 'FAIL'} triggers     {sorted(trgs)}"
              + ("" if good else f"   expected {sorted(EXPECT_TRIGGERS)}"))
        ok &= good
        print(f"   parent_depth generated as: {gen}")

        # `1b12-07` — a THIRD ownership-only route to a cycle, and the only one
        # the database can still tell you about. PG18's
        # `ALTER TABLE ... ALTER CONSTRAINT ... NOT ENFORCED` needs no superuser,
        # leaves the constraint definition in place, and flips `conenforced` to
        # `f`; `pg_get_constraintdef` still prints the whole FOREIGN KEY clause,
        # so a gate reading the DEFINITION TEXT sees nothing wrong. Reading the
        # catalog flag is the difference between "the constraint is declared" and
        # "the constraint is doing anything".
        unenforced = names("SELECT conname FROM pg_constraint "
                           "WHERE conrelid='channels'::regclass "
                           "AND (NOT conenforced OR NOT convalidated)")
        good = not unenforced
        print(f"   {'OK  ' if good else 'FAIL'} every constraint is ENFORCED and VALIDATED"
              + ("" if good else f"   not enforced/validated: {sorted(unenforced)}"))
        ok &= good
        # `REC-106`'s whole mechanism is this expression. If a later migration
        # ever redefines it, the cycle argument silently stops being true.
        if "depth - 1" not in gen.replace("(", "").replace(")", ""):
            print("   FAIL parent_depth is not `depth - 1` — REC-106's argument does not hold")
            ok = False

        print(f"\n── the tree still works when built by the CHAIN, not by 0019 alone")
        r = "11111111-1111-4111-8111-111111111111"
        psql(f"INSERT INTO channels (reality_id,id,parent,level_name,depth,lifecycle) VALUES "
             f"('{r}',1,NULL,'reality',0,'active'),('{r}',2,1,'cell',1,'active')")
        code, out = psql(f"UPDATE channels SET parent=2, depth=2 WHERE reality_id='{r}' AND id=1")
        cycle_refused = code != 0 and "channels_parent_fk" in out
        print(f"   {'OK  ' if cycle_refused else 'FAIL'} a 2-cycle is refused: {first_error(out)}")
        ok &= cycle_refused
        _, n = psql("SELECT count(*) FROM channels")
        print(f"        rows = {n}")

        print(f"\n── REVERSE")
        for f in downs:
            code, out = apply_file(f)
            if code != 0 and "0008" not in f.name:
                print(f"   FAIL {f.name:48s} {first_error(out)}")
                ok = False
        _, left = psql("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        _, fn = psql("SELECT count(*) FROM pg_proc WHERE proname='channels_lifecycle_guard'")
        print(f"   tables left = {left}   channels_lifecycle_guard() left = {fn}")
        # The trigger drops with the table; the FUNCTION does not, and a leftover
        # one makes the next forward `CREATE OR REPLACE` inherit an older body.
        ok &= left == "0" and fn == "0"

        print(f"\n{'=' * 78}")
        if skipped:
            print(f"dp-migration-chain-smoke: {len(skipped)} migration(s) SKIPPED, not passed:")
            for s in skipped:
                print(f"   {s}")
        if ok:
            print(f"dp-migration-chain-smoke: PASS — {retried} migration(s) applied AND retried, "
                  f"`channels` as built by the chain matches 0019's declaration, a cycle is "
                  f"refused, and the down chain leaves an empty schema.")
            return 0
        print("dp-migration-chain-smoke: FAIL")
        return 1
    finally:
        if "--keep" not in sys.argv:
            psql(f"DROP DATABASE IF EXISTS {DB}", db="postgres")
            print(f"   (dropped {DB})")


if __name__ == "__main__":
    sys.exit(main())
