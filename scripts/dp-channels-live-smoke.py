#!/usr/bin/env python3
"""dp-channels-live-smoke — `1b.2`, the RUN axis for the `channels` migration.

**This is not a gate and is deliberately not named like one.** It needs a live
Postgres, so `gate-wiring-gate`'s filename predicate must not demand that CI run
it; CI has no database. What it is, is the evidence slice 1b cannot close
without.

WHY IT EXISTS AS A SEPARATE AXIS
--------------------------------
Slice 1 re-derived Axis 2 as *"the compiler on adversarial input"*, because
`crates/dp` declares no I/O and a borrowed live-smoke row would have been a
check that could not fail. **Slice 1b is a migration.** It has a live subject, so
that substitute is not available and claiming it would be the borrowed row the
DoD forbids by name. If Postgres cannot be reached, this slice does not close.

WHAT IT PROVES
--------------
A `CHECK` constraint nobody has inserted against is `REC-104` all over again — a
check that has never been asked to fail. So every constraint the migration
declares is given a row that violates it, and the DATABASE'S OWN ERROR is the
evidence: **the constraint NAME Postgres blames, printed verbatim.**

That is deliberately not `SQLSTATE`. Three artifacts in this slice claimed
`SQLSTATE` was printed — this docstring, the commit message, and the helper below
is still called `sqlstate()` — and none of them printed one (`1b.5 L2`). The name
is the stronger evidence anyway: `23514` says *a check failed*, while
`channels_no_orphan` says *which check*, which is the whole attribution question.
The claim was corrected rather than the output padded to make a false sentence
true.

The negative direction matters as much: a second root in the SAME reality must
collide, and a root in a DIFFERENT reality must be accepted. A unique index that
rejects both would satisfy "it rejects a second root" while breaking the table.

Run:  python scripts/dp-channels-live-smoke.py
      (add --keep to leave the throwaway database in place for inspection)
Exit 0 = every constraint rejected what it names and accepted what it must.
"""
from __future__ import annotations

import subprocess
import sys
import uuid

CONTAINER = "infra-postgres-1"
USER = "loreweave"
# The name carries `test` AND `smoke`. `scripts/db-safety-gate.py` and
# CLAUDE.md's destructive-ops rule both require a throwaway marker before
# anything destructive runs, and this script DROPs the database at the end.
DB = "dp_slice1b_smoke_test"
MIGRATION = "contracts/migrations/per_reality/0019_channels.up.sql"
DOWN = "contracts/migrations/per_reality/0019_channels.down.sql"

REALITY_A = "11111111-1111-4111-8111-111111111111"
REALITY_B = "22222222-2222-4222-8222-222222222222"
# `1b.5 M2` — a reality with NO root, so a "root at depth != 0" row violates
# `channels_no_orphan` and NOTHING ELSE. Using REALITY_B put a second barrier
# (`channels_root_single`) behind it; CHECKs evaluate before index insertion,
# so the attribution assertion passed and the ambiguity was invisible. That is
# the exact hazard `1b.4` exists for, occurring inside `1b.2`.
REALITY_C = "33333333-3333-4333-8333-333333333333"


def guard_throwaway(name: str) -> None:
    """Refuse to touch a database whose name lacks a throwaway marker.

    The rule this obeys is not abstract: an unscoped `DELETE FROM books` in a
    DB-gated test once ran against the real `loreweave_book` and hard-deleted
    every user's books, because a `*_TEST_DATABASE_URL` pointed at production.
    This script creates and DROPs a database, so it checks before it acts.
    """
    markers = ("test", "smoke", "audit")
    hit = [m for m in markers if m in name.lower()]
    if not hit:
        print(f"dp-channels-live-smoke: REFUSING to operate on {name!r} — no throwaway marker "
              f"({'/'.join(markers)}). This script CREATEs and DROPs.", file=sys.stderr)
        sys.exit(2)
    print(f"  guard: {name!r} carries {hit} — safe to create and drop")


def psql(sql: str, db: str = DB, quiet: bool = False) -> tuple[int, str]:
    p = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", USER, "-d", db,
         "-v", "ON_ERROR_STOP=1", "-tAc", sql],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = ((p.stdout or "") + (p.stderr or "")).strip()
    if not quiet:
        pass
    return p.returncode, out


def apply_file(path: str, db: str = DB) -> tuple[int, str]:
    with open(path, "rb") as fh:
        p = subprocess.run(
            ["docker", "exec", "-i", CONTAINER, "psql", "-U", USER, "-d", db,
             "-v", "ON_ERROR_STOP=1"],
            stdin=fh, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


def blamed_constraint(err: str) -> str:
    for line in err.splitlines():
        if "ERROR:" in line:
            return line.split("ERROR:")[1].strip()[:110]
    return err.strip().splitlines()[0][:110] if err.strip() else "(no message)"


def row(reality: str, cid: int, parent, depth: int, lifecycle: str = "active",
        dissolved: str = "NULL", level: str = "cell") -> str:
    par = "NULL" if parent is None else str(parent)
    return (f"INSERT INTO channels (reality_id, id, parent, level_name, depth, lifecycle, "
            f"dissolved_at) VALUES ('{reality}', {cid}, {par}, '{level}', {depth}, "
            f"'{lifecycle}', {dissolved})")


def seed_tree() -> None:
    """The minimal tree every bite leg's rows refer to.

    Needed because `1b.5 M1`'s fix drops and re-creates the table, which wipes
    the rows — and a leg whose `parent` no longer exists is rejected by the
    FOREIGN KEY rather than by the constraint under test. That is the
    wrong-reason failure the whole harness exists to detect, arriving from the
    fix for a different wrong-reason failure.
    """
    for sql in (row(REALITY_A, 1, None, 0, level="reality"),
                row(REALITY_A, 2, 1, 1),
                row(REALITY_A, 3, 2, 2),
                row(REALITY_B, 1, None, 0, level="reality")):
        psql(sql)


def main() -> int:
    print(f"{'=' * 78}\ndp-channels-live-smoke — 1b.2, the RUN axis\n{'=' * 78}")
    guard_throwaway(DB)

    code, _ = psql("SELECT 1", db="postgres")
    if code != 0:
        print("dp-channels-live-smoke: FAIL — no live Postgres. This slice's Axis 2 IS a live "
              "database; `live infra unavailable` is not available to it.", file=sys.stderr)
        return 1

    psql(f"DROP DATABASE IF EXISTS {DB}", db="postgres")
    code, out = psql(f"CREATE DATABASE {DB}", db="postgres")
    if code != 0:
        print(f"dp-channels-live-smoke: FAIL — cannot create {DB}: {out}", file=sys.stderr)
        return 1

    try:
        print(f"\n── apply {MIGRATION}")
        code, out = apply_file(MIGRATION)
        print(f"   exit={code}")
        if code != 0:
            print(out, file=sys.stderr)
            return 1

        results: list[bool] = []

        # ── the tree must be BUILDABLE first. A suite that only proves things
        # are rejected has not shown the table is usable.
        print(f"\n── ACCEPT: the shapes the schema exists to hold")
        for label, sql in [
            ("a root (parent NULL, depth 0)", row(REALITY_A, 1, None, 0, level="reality")),
            ("a child of the root", row(REALITY_A, 2, 1, 1, level="cell")),
            ("a grandchild", row(REALITY_A, 3, 2, 2, level="tavern")),
            ("a SECOND root, in a DIFFERENT reality", row(REALITY_B, 1, None, 0, level="reality")),
            ("a dissolved channel WITH dissolved_at", row(REALITY_A, 4, 1, 1, "dissolved", "now()")),
        ]:
            code, out = psql(sql)
            ok = code == 0
            print(f"   {'OK  ' if ok else 'FAIL'} {label:46s} exit={code}"
                  + ("" if ok else f"  {blamed_constraint(out)}"))
            results.append(ok)

        # ── every constraint must REJECT what its name claims.
        print(f"\n── REJECT: each constraint, asked to fail")
        for label, sql, expect in [
            ("a second root in the SAME reality", row(REALITY_A, 9, None, 0), "channels_root_single"),
            ("a root at depth != 0", row(REALITY_C, 9, None, 3), "channels_no_orphan"),
            ("a child at depth 0", row(REALITY_A, 10, 1, 0), "channels_no_orphan"),
            ("depth past the DP-Ch2 bound of 16", row(REALITY_A, 11, 1, 17), "channels_depth_bounded"),
            ("a negative depth", row(REALITY_A, 12, 1, -1), "channels_depth_bounded"),
            ("an unknown lifecycle", row(REALITY_A, 13, 1, 1, "zombie"), "channels_lifecycle_known"),
            ("a parent that does not exist", row(REALITY_A, 15, 999, 1), "channels_parent_fk"),
            ("a parent in ANOTHER reality", row(REALITY_B, 15, 2, 1), "channels_parent_fk"),
            ("dissolved with no dissolved_at", row(REALITY_A, 16, 1, 1, "dissolved"),
             "channels_dissolved_at_iff_dissolved"),
            ("active WITH a dissolved_at", row(REALITY_A, 17, 1, 1, "active", "now()"),
             "channels_dissolved_at_iff_dissolved"),
            ("a duplicate (reality_id, id)", row(REALITY_A, 2, 1, 1), "channels_pkey"),
            # `1b.5 M4` — REC-103 carried the wire contract's WIDTH across and
            # not its DOMAIN. DP-Ch11 allocates MAX()+1, which starts at 1.
            ("id = 0", row(REALITY_A, 0, 1, 1), "channels_id_positive"),
            ("a negative id", row(REALITY_A, -5, 1, 1), "channels_id_positive"),
            ("an empty level_name", row(REALITY_A, 18, 1, 1, level=""),
             "channels_level_name_nonempty"),
            ("a level_name of only spaces", row(REALITY_A, 19, 1, 1, level="   "),
             "channels_level_name_nonempty"),
        ]:
            code, out = psql(sql)
            named = expect in out
            ok = code != 0 and named
            print(f"   {'OK  ' if ok else 'FAIL'} {label:46s} exit={code}")
            print(f"        {blamed_constraint(out)}")
            if code != 0 and not named:
                print(f"        ^ rejected, but NOT by {expect} — right answer, wrong constraint")
            results.append(ok)

        # ── `REC-106` — `DP-Ch1`'s anti-cycle mechanism, attacked rather than
        # argued. `12_channel_primitives.md:97` states it — *"No cycles.
        # Enforced by `depth` (root = 0, children = parent.depth + 1) +
        # referential integrity on `parent`"* — and the first shipped schema
        # implemented the second half only. `1b5-H2`/`H3` are that gap; these are
        # the attacks that were possible before the depth joined the foreign key.
        #
        # The statements here are not all INSERTs, which is the point: `1b.2`
        # only ever inserted, and the cycle attacks are UPDATEs and DELETEs.
        print(f"\n── REC-106: a cycle must be UNREPRESENTABLE, not merely rejected")
        for label, sql, expect in [
            ("a channel parented to itself",
             row(REALITY_A, 14, 14, 1), "channels_parent_fk"),
            ("a child of the root claiming depth 16",
             row(REALITY_A, 30, 1, 16), "channels_parent_fk"),
            ("a child at its parent's OWN depth (a flat chain)",
             row(REALITY_A, 31, 2, 1), "channels_parent_fk"),
            ("a 2-cycle: point the root at its own child",
             f"UPDATE channels SET parent = 2, depth = 3 WHERE reality_id='{REALITY_A}' AND id = 1",
             "channels_parent_fk"),
            ("a cycle built inside ONE transaction, constraints DEFERRED",
             f"BEGIN; SET CONSTRAINTS channels_parent_fk DEFERRED; "
             f"{row(REALITY_C, 100, 101, 5)}; {row(REALITY_C, 101, 100, 4)}; COMMIT",
             "channels_parent_fk"),
            ("deleting the root out from under the tree",
             f"DELETE FROM channels WHERE reality_id='{REALITY_A}' AND id = 1",
             "channels_parent_fk"),
            ("re-parenting a node whose children still reference its depth",
             f"UPDATE channels SET depth = 5 WHERE reality_id='{REALITY_A}' AND id = 2",
             "channels_parent_fk"),
        ]:
            code, out = psql(sql)
            named = expect in out
            ok = code != 0 and named
            print(f"   {'OK  ' if ok else 'FAIL'} {label:46s} exit={code}")
            print(f"        {blamed_constraint(out)}")
            if code != 0 and not named:
                print(f"        ^ rejected, but NOT by {expect} — right answer, wrong constraint")
            results.append(ok)

        # The DEFERRED leg must fail at COMMIT and leave NOTHING behind. A
        # transaction that half-applied would satisfy "it errored" while having
        # written a cycle, which is the failure this leg exists to exclude.
        _, left = psql(f"SELECT count(*) FROM channels WHERE reality_id='{REALITY_C}'")
        ok = left == "0"
        print(f"   {'OK  ' if ok else 'FAIL'} {'the deferred cycle left no rows behind':46s} "
              f"rows in reality C = {left}")
        results.append(ok)

        # ── the LEGAL half. A schema that refuses everything is not a tree, it
        # is a wall, and `REC-106`'s stated cost is that re-parenting becomes a
        # SUBTREE operation. That cost has to be payable or the constraint is
        # wrong: the escape hatch is one transaction with the check deferred.
        print(f"\n── REC-106: the operations that must still be POSSIBLE")
        for label, sql in [
            ("add a second branch under the root", row(REALITY_A, 40, 1, 1, level="zone2")),
            ("move a subtree one level deeper, deferred, in one transaction",
             f"BEGIN; SET CONSTRAINTS channels_parent_fk DEFERRED; "
             f"UPDATE channels SET parent = 40, depth = 2 WHERE reality_id='{REALITY_A}' AND id = 2; "
             f"UPDATE channels SET depth = 3 WHERE reality_id='{REALITY_A}' AND id = 3; COMMIT"),
        ]:
            code, out = psql(sql)
            ok = code == 0
            print(f"   {'OK  ' if ok else 'FAIL'} {label:46s} exit={code}"
                  + ("" if ok else f"  {blamed_constraint(out)}"))
            results.append(ok)
        _, shape = psql(f"SELECT string_agg(id || ':d' || depth || '<-' || "
                        f"coalesce(parent::text,'root'), ' ' ORDER BY id) FROM channels "
                        f"WHERE reality_id='{REALITY_A}'")
        print(f"        tree after the move: {shape}")

        # ── `1b.5 L5` — DP-Ch31's terminal-Dissolved and DP-Ch33's
        # descendants-first. Both are statements about a TRANSITION, which no
        # CHECK can see, and `17_channel_lifecycle.md:77` attributed them to a
        # "row-level rule" that existed nowhere. Both fell to a plain UPDATE.
        print(f"\n── 1b5-L5: the lifecycle rules DP-Ch31 names")
        psql("DROP TABLE IF EXISTS channels")
        apply_file(MIGRATION)
        seed_tree()
        for label, sql, expect in [
            ("dissolve a parent whose child is still active",
             f"UPDATE channels SET lifecycle='dissolved', dissolved_at=now() "
             f"WHERE reality_id='{REALITY_A}' AND id = 2",
             "channels_dissolve_descendants_first"),
            ("dissolve the LEAF first (must be allowed)",
             f"UPDATE channels SET lifecycle='dissolved', dissolved_at=now() "
             f"WHERE reality_id='{REALITY_A}' AND id = 3", None),
            ("then its parent (must now be allowed)",
             f"UPDATE channels SET lifecycle='dissolved', dissolved_at=now() "
             f"WHERE reality_id='{REALITY_A}' AND id = 2", None),
            ("bring a dissolved channel back to active",
             f"UPDATE channels SET lifecycle='active', dissolved_at=NULL "
             f"WHERE reality_id='{REALITY_A}' AND id = 3",
             "channels_dissolved_is_terminal"),
            ("bring it back to dormant instead",
             f"UPDATE channels SET lifecycle='dormant', dissolved_at=NULL "
             f"WHERE reality_id='{REALITY_A}' AND id = 3",
             "channels_dissolved_is_terminal"),
        ]:
            code, out = psql(sql)
            if expect is None:
                ok = code == 0
                print(f"   {'OK  ' if ok else 'FAIL'} {label:46s} exit={code}"
                      + ("" if ok else f"  {blamed_constraint(out)}"))
            else:
                ok = code != 0 and expect in out
                print(f"   {'OK  ' if ok else 'FAIL'} {label:46s} exit={code}")
                print(f"        {blamed_constraint(out)}")
            results.append(ok)

        psql("DROP TABLE IF EXISTS channels")
        apply_file(MIGRATION)
        seed_tree()

        # ── `1b.4` — THE BITE. Every rejection above named its constraint, so
        # attribution is already proven. What is not proven is that the
        # constraint is the ONLY thing rejecting: a row refused by two barriers
        # looks identical to a row refused by one, and the day someone drops the
        # weaker one nothing changes colour. So each constraint is DROPPED and
        # its violating row is required to INSERT.
        #
        # `REC-104` is why this leg exists at all: `channels_root_single` sat in
        # a LOCKED spec for months as `UNIQUE (id)` on a primary key — a
        # constraint that could not fail, which no amount of inserting against
        # it would have revealed, because nothing ever did.
        # ⚠ `1b5-M2`, RECREATED BY `REC-106` and caught by this harness on the
        # first run after the change. Two legs went red — `no orphan` and `depth
        # bounded` — because their violating rows were now refused TWICE. A child
        # at `depth 0` has `parent_depth = -1`, and a child of the root at `depth
        # 17` needs a parent at `depth 16`: neither exists, so `channels_parent_fk`
        # refused both before the constraint under test ever ran. That is the
        # "an adjacent decision defeats it" shape, and the adjacent decision was
        # the one made two hours earlier in this same slice.
        #
        # Each row below is now chosen so the FOREIGN KEY is SATISFIED and the
        # constraint under test is the only barrier left:
        #   * no orphan     -> a ROOT at depth != 0. `parent IS NULL`, so the
        #                      MATCH SIMPLE key is not checked at all. It goes in
        #                      REALITY_C, which has no root, so
        #                      `channels_root_single` is not a second barrier
        #                      either — that was `1b5-M2`'s original finding.
        #   * depth bounded -> a genuine 17-deep chain, so the violating row's
        #                      parent really is at depth 16. Building it is the
        #                      cost of proving the bound still does independent
        #                      work: past `REC-106`, depth 17 is not reachable by
        #                      declaration, only by digging.
        deep_chain = [row(REALITY_C, 100, None, 0, level="reality")] + [
            row(REALITY_C, 100 + d, 99 + d, d) for d in range(1, 17)]
        print(f"\n── BITE: drop the constraint, the violation must now be LEGAL")
        for label, constraint, drop, sql, setup in [
            ("one root per reality", "channels_root_single",
             "DROP INDEX channels_root_single", row(REALITY_A, 20, None, 0), []),
            ("no orphan", "channels_no_orphan",
             "ALTER TABLE channels DROP CONSTRAINT channels_no_orphan",
             row(REALITY_C, 21, None, 3), []),
            ("depth bounded", "channels_depth_bounded",
             "ALTER TABLE channels DROP CONSTRAINT channels_depth_bounded",
             row(REALITY_C, 200, 116, 17), deep_chain),
            ("lifecycle known", "channels_lifecycle_known",
             "ALTER TABLE channels DROP CONSTRAINT channels_lifecycle_known",
             row(REALITY_A, 23, 1, 1, "zombie"), []),
            ("dissolved_at iff dissolved", "channels_dissolved_at_iff_dissolved",
             "ALTER TABLE channels DROP CONSTRAINT channels_dissolved_at_iff_dissolved",
             row(REALITY_A, 25, 1, 1, "dissolved"), []),
            # `REC-106`. This leg replaces the one that used to read "no self
            # parent": `channels_no_self_parent` was REMOVED because the depth in
            # this key makes a self-parented row unrepresentable, so a CHECK for
            # it could no longer fail (`NV-1`). The evidence for that claim is
            # exactly this leg — drop the foreign key, and the self-parented row
            # that `channels_no_self_parent` used to catch INSERTS.
            ("the parent link, depth included", "channels_parent_fk",
             "ALTER TABLE channels DROP CONSTRAINT channels_parent_fk",
             row(REALITY_A, 24, 24, 1), []),
            ("id is positive", "channels_id_positive",
             "ALTER TABLE channels DROP CONSTRAINT channels_id_positive",
             row(REALITY_A, 0, 1, 1), []),
            ("level_name is not blank", "channels_level_name_nonempty",
             "ALTER TABLE channels DROP CONSTRAINT channels_level_name_nonempty",
             row(REALITY_A, 26, 1, 1, level="  "), []),
        ]:
            for s in setup:
                code_s, out_s = psql(s)
                if code_s != 0:
                    print(f"        x SETUP FAILED for `{label}`: {blamed_constraint(out_s)}")
            before, out_before = psql(sql)
            code_drop, _ = psql(drop)
            after, out_after = psql(sql)
            # Put it back. `1b.5 M1`: re-applying the migration alone was a
            # NO-OP — `CREATE TABLE IF NOT EXISTS` skips, so five of six
            # constraints never returned and legs 2..6 ran on a progressively
            # stripped table. The exclusivity this leg advertises was not what
            # the evidence established. Drop and re-create, then VERIFY.
            psql("DROP TABLE IF EXISTS channels")
            apply_file(MIGRATION)
            seed_tree()
            _, back = psql(f"SELECT count(*) FROM pg_constraint WHERE conname='{constraint}'")
            _, idx = psql(f"SELECT count(*) FROM pg_indexes WHERE indexname='{constraint}'")
            restored_ok = back != "0" or idx != "0"
            if not restored_ok:
                print(f"        x RESTORE FAILED: {constraint} is still absent after re-apply")
                results.append(False)
                continue
            bit = before != 0 and code_drop == 0 and after == 0
            print(f"   {'OK  ' if bit else 'FAIL'} {label:34s} "
                  f"with={before and 'rejected' or 'ACCEPTED'} "
                  f"without={after == 0 and 'accepted' or 'still rejected'}")
            if not bit and after != 0:
                print(f"        ^ still rejected with {constraint} gone: {blamed_constraint(out_after)}")
                print("        Something ELSE is refusing this row, so this constraint was not")
                print("        the thing holding the property.")
            results.append(bit)

        # The lifecycle rules are a TRIGGER, not a constraint, so they need their
        # own bite shape — and they need one for the same reason: a trigger that
        # has never been the sole refuser is a trigger nobody has proven is load
        # bearing. Drop it, and the transition it forbids must go through.
        psql("DROP TABLE IF EXISTS channels")
        apply_file(MIGRATION)
        seed_tree()
        dissolve_leaf = (f"UPDATE channels SET lifecycle='dissolved', dissolved_at=now() "
                         f"WHERE reality_id='{REALITY_A}' AND id = 3")
        revive = (f"UPDATE channels SET lifecycle='active', dissolved_at=NULL "
                  f"WHERE reality_id='{REALITY_A}' AND id = 3")
        dissolve_parent = (f"UPDATE channels SET lifecycle='dissolved', dissolved_at=now() "
                           f"WHERE reality_id='{REALITY_A}' AND id = 2")
        for label, violation, setup in [
            ("DP-Ch31 terminal Dissolved", revive, [dissolve_leaf]),
            ("DP-Ch33 descendants first", dissolve_parent, []),
        ]:
            psql("DROP TABLE IF EXISTS channels")
            apply_file(MIGRATION)
            seed_tree()
            for s in setup:
                psql(s)
            # A refused UPDATE changes nothing, so the state the second attempt
            # sees is the state the first one saw. No re-seed, and none hidden.
            before, _ = psql(violation)
            _, trg_before = psql("SELECT count(*) FROM pg_trigger "
                                 "WHERE tgname='channels_lifecycle_guard_trg'")
            psql("DROP TRIGGER channels_lifecycle_guard_trg ON channels")
            _, trg_after = psql("SELECT count(*) FROM pg_trigger "
                                "WHERE tgname='channels_lifecycle_guard_trg'")
            after, out_after = psql(violation)
            bit = before != 0 and after == 0 and trg_before == "1" and trg_after == "0"
            print(f"   {'OK  ' if bit else 'FAIL'} {label:34s} "
                  f"with={'rejected' if before else 'ACCEPTED'} "
                  f"without={'accepted' if after == 0 else 'still rejected'}  "
                  f"(pg_trigger {trg_before} -> {trg_after})")
            if not bit and after != 0:
                print(f"        ^ still rejected with the trigger gone: "
                      f"{blamed_constraint(out_after)}")
            results.append(bit)

        # The bite dropped and re-created constraints; rebuild a clean tree for
        # the measurements below rather than reporting on a mutated table.
        psql("DROP TABLE IF EXISTS channels")
        apply_file(MIGRATION)
        seed_tree()
        psql(row(REALITY_A, 4, 1, 1, "dissolved", "now()"))

        # ── DP-Ch11's allocator: MAX()+1, per reality.
        print(f"\n── MEASURE")
        for label, sql in [
            ("rows in reality A", f"SELECT count(*) FROM channels WHERE reality_id='{REALITY_A}'"),
            ("rows in reality B", f"SELECT count(*) FROM channels WHERE reality_id='{REALITY_B}'"),
            ("DP-Ch11 next id, reality A", f"SELECT coalesce(max(id),0)+1 FROM channels "
                                           f"WHERE reality_id='{REALITY_A}'"),
            ("DP-Ch11 next id, reality B", f"SELECT coalesce(max(id),0)+1 FROM channels "
                                           f"WHERE reality_id='{REALITY_B}'"),
            ("roots (must be one per reality)", "SELECT count(*) FROM channels WHERE parent IS NULL"),
        ]:
            _, out = psql(sql)
            print(f"   {label:46s} = {out}")

        # ── the down migration must actually reverse it.
        print(f"\n── apply {DOWN}")
        code, out = apply_file(DOWN)
        _, remains = psql("SELECT count(*) FROM information_schema.tables "
                          "WHERE table_name='channels'")
        print(f"   exit={code}   channels tables remaining = {remains}")
        results.append(code == 0 and remains == "0")

        print(f"\n{'=' * 78}")
        if all(results):
            print(f"dp-channels-live-smoke: PASS — {len(results)} check(s) on a live Postgres. "
                  f"Every constraint rejected what its name claims, and accepted what it must.")
            return 0
        print(f"dp-channels-live-smoke: FAIL — {sum(results)}/{len(results)}")
        return 1
    finally:
        if "--keep" not in sys.argv:
            psql(f"DROP DATABASE IF EXISTS {DB}", db="postgres")
            print(f"   (dropped {DB})")


if __name__ == "__main__":
    sys.exit(main())
