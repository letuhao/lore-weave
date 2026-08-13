-- 0019_channels — the channel registry (DP-Ch1 / DP-Ch2 / DP-Ch11 / DP-Ch13).
--
-- WHY THIS DID NOT EXIST UNTIL NOW
-- --------------------------------
-- `FLOW-9`, measured 2026-08-07: `06_data_plane/` has specified this table since
-- Phase 4 and no migration ever shipped. `FLOW-19` is the consequence —
-- `0014_channel_ordering` declares `channel_writer_state.channel_id BIGINT` with
-- **no foreign key**, which it could not have had, because there was nothing to
-- reference. `DP-Ch13` locks that column as `UUID PRIMARY KEY REFERENCES
-- channels(id)`; the shipped table is neither.
--
-- FOUR AMENDMENTS THIS FILE IS WRITTEN AGAINST, ALL FOUND BEFORE IT EXISTED
-- -------------------------------------------------------------------------
-- `REC-103` — `id` is **BIGINT**, not `UUID`. `REC-102a` (PO-approved
--   2026-08-07) settled `ChannelId`'s payload as `i64`: the shipped
--   `crates/dp-kernel/src/channel.rs` says `ChannelId(pub(crate) i64)` and the
--   client wire contract says `Uint64String`. That decision reached the newtype
--   and the code and never reached the schema thirty lines below it.
--
--   ⚠ AMENDED 2026-08-08 (`1b7gap-M1`): this argument had a THIRD leg —
--   *"`DP-Ch11`'s allocator is a monotonic counter seeded from `MAX()`"* — and
--   it cited the wrong allocator. `DP-Ch11` is
--   `13_channel_ordering_and_writer.md:19`, *"`channel_event_id` allocation
--   mechanism"*: it seeds `last_event_id` from
--   `SELECT MAX(channel_event_id) FROM events`, which is the position of an
--   EVENT WITHIN a channel, not the id OF a channel. The conclusion survives on
--   the two legs above, which are the ones `REC-102a` actually rested on.
--   **What the corpus does NOT contain is any specification of how
--   `channels.id` is allocated** — no `DP-Ch*` rule names it. That is a real
--   gap, and it belongs to whichever slice first WRITES this table (see the
--   `FLOW-19` note in the down migration); it is recorded here rather than
--   invented, because inventing an allocator in a comment is how the wrong one
--   got cited in the first place.
--
-- `REC-104` — `CONSTRAINT channels_root_single UNIQUE (id)` was **vacuous**.
--   `id` is the primary key, so uniqueness on it is already total: it could not
--   reject a row. Its NAME states `DP-Ch1`'s real invariant — *a strict tree has
--   exactly one root* — and nothing enforced it. `channels_no_orphan` is
--   adjacent and weaker: it forbids a root at `depth != 0`, and permits any
--   number of roots. Here it is a partial unique index, which is the only shape
--   Postgres offers for "at most one row satisfying a predicate".
--
-- `REC-105` — **`reality_id` is present, and `DP-Ch2` does not have it.** Every
--   other table in this directory carries `reality_id UUID NOT NULL` inside its
--   primary key (`events`, `channel_writer_state`, `channel_event_seq`, …), and
--   the README states no reason — but `channel_writer_state` is
--   `PRIMARY KEY (reality_id, channel_id)`, so a foreign key from it to a
--   single-column `channels(id)` is **not expressible**. Following the spec
--   literally would have re-created `FLOW-19` in the migration that exists to
--   discharge it. The composite key is derived from the shipped tables, not
--   chosen; `DP-Ch2` needs the matching amendment and does not have it yet.
--
-- `REC-106` — **`DP-Ch1`'s anti-cycle mechanism, implemented instead of
--   asserted.** `12_channel_primitives.md:97` states it in full — *"No cycles.
--   Enforced by `depth` field (root = 0, children = parent.depth + 1) +
--   referential integrity on `parent`"* — and the first shipped schema
--   implemented the second half only. `depth` was a free-floating number: a
--   child of the root could declare `depth 16`, a hundred-node chain could sit
--   entirely at `depth 1`, and a two-row cycle took one `UPDATE`. The fix is
--   below and it is the spec's own sentence turned into SQL.

BEGIN;

CREATE TABLE IF NOT EXISTS channels (
    reality_id    UUID     NOT NULL,
    id            BIGINT   NOT NULL,
    parent        BIGINT,
    level_name    TEXT     NOT NULL,
    display_name  TEXT,
    depth         SMALLINT NOT NULL,
    lifecycle     TEXT     NOT NULL,
    metadata      JSONB    NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    dissolved_at  TIMESTAMPTZ,

    -- `REC-106`. Not a fact about this channel — a fact about the one it claims
    -- as a parent, computed from this row so it CANNOT disagree with `depth`.
    -- The root's value is -1, which no row can ever match, and no row needs to:
    -- the root's `parent` is NULL and the foreign key below is `MATCH SIMPLE`.
    parent_depth  SMALLINT GENERATED ALWAYS AS ((depth - 1)::smallint) STORED,

    PRIMARY KEY (reality_id, id),

    -- The target of the foreign key below, and its ONLY purpose. `(reality_id,
    -- id)` is already unique; Postgres still requires a declared unique
    -- constraint on the exact referenced column list.
    CONSTRAINT channels_id_depth_uq UNIQUE (reality_id, id, depth),

    -- `DP-Ch1`, both halves (`REC-106`).
    --
    -- `reality_id` in the key is what stops a channel in reality A claiming a
    -- parent in reality B — structurally, not by a check.
    --
    -- `parent_depth` in the key is what stops CYCLES, and it is worth being
    -- precise about why, because "a check that looks strong" is this repo's
    -- most expensive defect. Along every parent edge, depth DECREASES BY
    -- EXACTLY ONE. Walk any cycle of length k and you return to your starting
    -- row having subtracted k > 0 from its own depth: `d = d - k` has no
    -- solution. That includes the one-node case, which is why
    -- `channels_no_self_parent` is NOT in this table (see below).
    --
    -- ⚠ AMENDED 2026-08-08 (`1b7db-02`, `1b7db-03`) — this said a cycle is "not
    -- REJECTED, it is not REPRESENTABLE", and **the description was stronger
    -- than the mechanism.** Two measured routes, neither exotic:
    --
    --   * `ALTER TABLE channels ALTER COLUMN parent_depth DROP EXPRESSION` needs
    --     only table ownership, no rewrite and no superuser. The column becomes
    --     ordinary, a caller supplies `parent_depth` by hand, and a self-parent
    --     inserts in one statement. **The arithmetic argument rests on
    --     `parent_depth == depth - 1`, and nothing in the database asserted it**
    --     — the guarantee lived in a column DEFINITION, which is DDL, not data.
    --     `channels_parent_depth_derived` below closes that: a CHECK survives
    --     `DROP EXPRESSION` and starts doing work the moment the expression
    --     stops. It is vacuous only while the expression exists, and it exists
    --     precisely to be non-vacuous when that stops being true.
    --   * `SET session_replication_role = replica` or `ALTER TABLE ... DISABLE
    --     TRIGGER ALL` suspends FK enforcement outright; the rows persist, and
    --     `pg_constraint.convalidated` still reports `t` afterwards. **No
    --     table-level mechanism can defend against this** — it is the escape
    --     hatch Postgres gives replication tools. ⚠ It needs superuser, and the
    --     `loreweave` role every service in the compose stack connects as **IS
    --     superuser** — which is a deployment finding, not a schema one, and is
    --     recorded rather than fixed here.
    --
    -- So the honest claim, and the one that survives attack: **through ordinary
    -- SQL a cycle is not representable.** A constraint gives you "rejected, as
    -- long as the thing it depends on is still there", and saying more than that
    -- is the same overreach `REC-104` and `1bF-2` are about.
    --
    -- DEFERRABLE INITIALLY IMMEDIATE, deliberately. Because a parent's `depth`
    -- is referenced by its children, moving a subtree cannot be done one row at
    -- a time; a transaction that re-parents a whole subtree must be able to
    -- pass through an inconsistent middle. The escape hatch does NOT weaken the
    -- guarantee above: the impossibility is arithmetic, so a deferred cycle is
    -- still refused — at COMMIT rather than at the statement. Measured on a live
    -- Postgres 18: `SET CONSTRAINTS channels_parent_fk DEFERRED` followed by a
    -- two-row cycle fails on `COMMIT`.
    CONSTRAINT channels_parent_fk FOREIGN KEY (reality_id, parent, parent_depth)
        REFERENCES channels (reality_id, id, depth)
        DEFERRABLE INITIALLY IMMEDIATE,

    -- `DP-Ch2` verbatim: depth is bounded and the tree has no orphans.
    CONSTRAINT channels_depth_bounded CHECK (depth >= 0 AND depth <= 16),
    -- `DP-A18` verbatim: every channel has exactly one lifecycle state at any
    -- time, drawn from the CLOSED SET {Active, Dormant, Dissolved}. This CHECK
    -- is where that closed set is actually enforced — in SQL, lower-cased,
    -- which is why a case-sensitive grep for `Dormant` finds nothing in Rust
    -- and the rule looks unimplemented. `dp-channels-live-smoke` proves it by
    -- asking it to reject `'zombie'`.
    CONSTRAINT channels_lifecycle_known
        CHECK (lifecycle IN ('active', 'dormant', 'dissolved')),
    CONSTRAINT channels_no_orphan CHECK (
        (parent IS NULL AND depth = 0) OR (parent IS NOT NULL AND depth > 0)
    ),

    -- `REC-106` also settles a question `channels_root_single` alone could not:
    -- that index gives AT MOST one root per reality, and this foreign key gives
    -- AT LEAST one for any non-empty reality — walk `parent` from any row and
    -- `depth` strictly decreases, so the walk terminates, and it can only
    -- terminate at `depth = 0`, which `channels_no_orphan` forces to be a root.
    -- Together: EXACTLY one root per non-empty reality, which is `DP-Ch1`.
    --
    -- NOT PRESENT, ON PURPOSE: `channels_no_self_parent CHECK (parent IS NULL OR
    -- parent <> id)`. It shipped in the first version of this file and
    -- `channels_parent_fk` now makes it unable to fail — a self-parented row
    -- would need a row with its own id at its own depth minus one, and `id` is
    -- unique per reality. A `CHECK` that cannot reject anything is `NV-1`, and
    -- `1bF-2` in this same table is what that costs when nobody notices for
    -- eight weeks. Verified by attack rather than by argument: with the foreign
    -- key in place, `INSERT (id 9, parent 9, depth 1)` is refused by
    -- `channels_parent_fk`; the BITE section of
    -- `scripts/dp-channels-live-smoke.py` drops the foreign key and shows that
    -- same row INSERT. (That sentence named a script that does not exist until
    -- `1b7gap` — a phantom citation in the file arguing against vacuous claims.)

    -- `1b5-M4`: `REC-103` cited the wire contract's unsigned `Uint64String` as a
    -- ground for BIGINT and carried the WIDTH across without the DOMAIN.
    CONSTRAINT channels_id_positive CHECK (id > 0),

    -- `1b7gap-L1`: the domain was fixed at ONE end. `id = 9223372036854775807`
    -- was accepted, and then `SELECT MAX(id) + 1` — the shape any allocator for
    -- this column will have — dies with `bigint out of range`. Reserving the top
    -- value means a successor always exists.
    --
    -- ⚠ The wire contract and this column DISAGREE, and neither this constraint
    -- nor `REC-103` can fix it here: `contracts/game-wire/common.schema.json`
    -- types `Uint64String` as `^(0|[1-9][0-9]{0,19})$` — UNSIGNED, up to 20
    -- digits, and `0` is legal. So it admits `0` (refused above) and values past
    -- `i64::MAX` (refused here) that `ChannelId(i64)` cannot hold either. The
    -- column is the narrower of the two and that is the safe direction; the
    -- contract needs the amendment and this migration is not where it lives.
    CONSTRAINT channels_id_allocatable CHECK (id < 9223372036854775807),

    -- `1b7db-02`. The one assertion that makes `channels_parent_fk`'s arithmetic
    -- a fact about DATA rather than about DDL. While `parent_depth` is GENERATED
    -- this cannot fail; the instant someone runs `ALTER COLUMN parent_depth DROP
    -- EXPRESSION` it becomes the only thing standing between a hand-supplied
    -- `parent_depth` and a two-row cycle. That is not vacuity — it is the
    -- difference between a guarantee that lives in a column definition and one
    -- that lives in the table. Bitten by dropping the expression, not by
    -- dropping the CHECK.
    -- ⚠ `IS NOT NULL` ADDED 2026-08-08 (`1b12-03`), and its absence made the
    -- whole constraint decorative. `parent_depth` is NULLABLE. After
    -- `DROP EXPRESSION` the previous round's smoke hand-supplied a WRONG value
    -- and the CHECK caught it — so the leg passed. **Omit the column instead**
    -- and it is NULL: the CHECK evaluates to NULL, which is not FALSE, so it
    -- passes; and the foreign key is MATCH SIMPLE, so a NULL member skips the
    -- check entirely. A self-parent and a full 2-cycle both INSERT, with
    -- `convalidated = t` on a constraint sitting right there.
    --
    -- The lesson is sharper than the fix: **the leg tested the exact probe the
    -- author imagined, and the hole was one step to the side of it.** Three-
    -- valued logic is where a CHECK stops being a check, and `NOT NULL` is the
    -- only thing that closes it.
    CONSTRAINT channels_parent_depth_derived
        CHECK (parent_depth IS NOT NULL AND parent_depth = depth - 1),
    CONSTRAINT channels_level_name_nonempty CHECK (length(btrim(level_name)) > 0),

    -- `DP-Ch31`..`DP-Ch37` (17_channel_lifecycle.md): a dissolved channel has a
    -- dissolution time and a
    -- live one does not. Stated as a biconditional so neither direction can rot.
    -- (This cited `DP-Ch17` until 1b.5. DP-Ch17 is *Hybrid backing store*,
    -- 14_durable_subscribe.md:76 -- I had read the FILE NUMBER as a stable ID.)
    CONSTRAINT channels_dissolved_at_iff_dissolved CHECK (
        (lifecycle = 'dissolved') = (dissolved_at IS NOT NULL)
    )
);

-- `REC-104`, made able to fail: ONE root per reality. `parent IS NULL` is the
-- predicate; the index key is `reality_id`, so a second root in the same reality
-- collides and a root in a different reality does not.
--
-- `1b5-L3`, written down rather than discovered later: this index ignores
-- `lifecycle`, and `DP-Ch33` keeps a dissolved row indefinitely. So a reality
-- whose root is dissolved cannot gain a second root WHILE THAT ROW EXISTS. That
-- is deliberate: a `lifecycle <> 'dissolved'` predicate would let a reality be
-- re-rooted under a new tree while the old one's events still reference the old
-- root.
--
-- ⚠ AMENDED 2026-08-08 (`1b7gap-M2`) — this said dissolving the root
-- "FORECLOSES that reality — no second root can EVER be created in it", and that
-- was a promise about HISTORY made by a mechanism that only sees the PRESENT.
-- Measured: dissolve the root, watch a second root refused by
-- `channels_root_single`, `DELETE` the dissolved row, and the new root INSERTs.
-- A partial unique index constrains the rows that exist; no index can speak
-- about rows that have been removed.
--
-- The same run killed the other half of that sentence, *"`DP-Ch11` never
-- reissues an id"*. `DP-Ch11` does not say that (`1b7gap-M1`: it allocates
-- `channel_event_id`, not `channels.id`), nothing else says it, and a
-- `MAX(id) + 1` allocator over a table that permits DELETE **provably reissues**
-- — the same run moved `max(id) + 1` from 5 back to 3. Non-reuse of channel ids
-- is a genuine requirement, because events reference them, and it is UNOWNED: it
-- needs a counter that does not read live rows. It belongs to whichever slice
-- first WRITES this table, and it is not claimed here.
CREATE UNIQUE INDEX IF NOT EXISTS channels_root_single
    ON channels (reality_id)
    WHERE parent IS NULL;

CREATE INDEX IF NOT EXISTS channels_parent_idx
    ON channels (reality_id, parent);
CREATE INDEX IF NOT EXISTS channels_level_idx
    ON channels (reality_id, level_name)
    WHERE lifecycle = 'active';
CREATE INDEX IF NOT EXISTS channels_lifecycle_idx
    ON channels (reality_id, lifecycle);

-- `1b5-L5` — `DP-Ch31` claims two things a `CHECK` cannot express, because both
-- are statements about a TRANSITION rather than about a row:
--
--   `17_channel_lifecycle.md:57` — "Dissolved | (any) | — | terminal, no
--     transitions", and :77 names the mechanism as a "row-level rule".
--   `17_channel_lifecycle.md:55` — dissolution requires "all descendants
--     Dissolved".
--
-- Before `1b.5` both fell to a plain `UPDATE`, and :77's "row-level rule" named
-- a mechanism that did not exist anywhere. This is that rule. It is deliberately
-- the DB's and not only the SDK's: `DP-Ch31` says "row-level rule + SDK
-- transition validator", and an SDK-only check is a check the next writer to
-- reach this table does not have.
--
-- ⚠ `1b7gap-H3`, found by a cold-start refuter and REPRODUCED before fixing.
-- This comment used to say: *"Children, not descendants, and that is not a
-- weakening: a child may only reach Dissolved when ITS children are Dissolved,
-- so by induction a Dissolved channel's whole subtree is Dissolved."*
--
-- **That was FALSE, and it was the argument the other two rules leaned on.**
-- Induction over transitions says nothing about CREATION, and the trigger fired
-- `BEFORE UPDATE OF lifecycle` only. Measured on a live Postgres 18: dissolve
-- channel 2, then `INSERT (id 3, parent 2, 'active')` -> `INSERT 0 1`. A live
-- child under a dissolved parent, which `17_channel_lifecycle.md:51` forbids in
-- its own precondition column (*"parent exists, parent not Dissolved"*) and
-- which nothing implemented.
--
-- Three rules now, and the third is what makes the first two's induction TRUE
-- rather than merely stated: a Dissolved channel can gain no new live child, by
-- INSERT or by re-parenting. The trigger is therefore `BEFORE INSERT OR UPDATE`
-- rather than `UPDATE OF lifecycle` — an `UPDATE OF lifecycle` trigger does not
-- fire when only `parent` changes, so re-parenting under a dissolved node was
-- the same hole through a second door.
CREATE OR REPLACE FUNCTION channels_lifecycle_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    parent_lifecycle TEXT;
BEGIN
    -- `DP-Ch34` / 17_channel_lifecycle.md:51 — a channel may not be created
    -- under, or moved under, a Dissolved parent.
    --
    -- ⚠ `FOR UPDATE` ADDED 2026-08-08 (`1b12-02`), and without it this rule
    -- fell to plain READ COMMITTED write-skew — no deferral, no DDL, no
    -- superuser, just two ordinary concurrent writers. T1 inserts a child under
    -- an active parent (this guard reads `active`, passes, uncommitted); T2
    -- dissolves that parent (`DP-Ch33`'s `EXISTS` cannot see T1's uncommitted
    -- row, passes). Both commit, and a live child sits under a dissolved
    -- parent. **Two unlocked predicate reads that each pass are not the same as
    -- the conjunction holding**, which is what write-skew IS.
    --
    -- Locking the PARENT ROW makes the two paths contend on one row, in either
    -- order: an INSERT waits for a concurrent dissolution and then sees
    -- `dissolved`; a dissolution waits for a concurrent INSERT and then
    -- `DP-Ch33` sees the committed child. `SELECT ... INTO ... FOR UPDATE`
    -- rather than `EXISTS (... FOR UPDATE)`, because a row lock inside an
    -- `EXISTS` subquery is not expressible.
    -- ⚠ `reality_id` ADDED TO THE CONDITION 2026-08-08 (`1b14-02`). This read
    -- `NEW.parent IS DISTINCT FROM OLD.parent`, and **`parent` alone does not
    -- identify the parent row** — `(reality_id, parent)` does, because that is
    -- the key this table is built on. So `UPDATE channels SET reality_id = ...`
    -- moved the pointer to a DIFFERENT channel while the guard saw no change,
    -- and put a live child under a dissolved parent with one ordinary statement:
    -- no deferral, no DDL, no superuser, no concurrency. **A guard whose firing
    -- condition does not cover the whole key it guards is wrong regardless of
    -- who can reach it today** — and the FK comment above justifies `reality_id`
    -- as "what stops a channel in reality A claiming a parent in reality B",
    -- which is exactly what happened.
    IF NEW.parent IS NOT NULL
       AND (TG_OP = 'INSERT'
            OR (NEW.reality_id, NEW.parent) IS DISTINCT FROM (OLD.reality_id, OLD.parent)) THEN
        -- `INTO STRICT`, and the reason is a harness property rather than a
        -- runtime one (`1b12-04`). `(reality_id, id)` is the primary key, so
        -- EXACTLY ONE row can match — `STRICT` states that and makes it
        -- enforced. Without it, deleting the `reality_id` filter leaves a
        -- MULTI-ROW query whose first row plain `SELECT INTO` takes ARBITRARILY,
        -- so the cross-tenant defect is nondeterministic and a smoke leg cannot
        -- catch it reliably. That is exactly what happened: the mutation stayed
        -- green. `TOO_MANY_ROWS` turns it into a hard, immediate error.
        --
        -- `NO_DATA_FOUND` is caught rather than raised, because it is LEGAL: the
        -- parent may not exist yet when `channels_parent_fk` is deferred and the
        -- child is inserted first. That case is not this rule's to refuse — the
        -- foreign key refuses it at COMMIT if the parent never arrives, and
        -- `channels_dissolve_order_trg` refuses it on INSERT if the parent
        -- arrives already dissolved (`1b12-01`).
        BEGIN
            SELECT c.lifecycle INTO STRICT parent_lifecycle
              FROM channels c
             WHERE c.reality_id = NEW.reality_id
               AND c.id = NEW.parent
               FOR UPDATE;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                parent_lifecycle := NULL;
        END;

        IF parent_lifecycle = 'dissolved' THEN
            RAISE EXCEPTION
                'channels_no_child_of_dissolved: channel % cannot have dissolved '
                'channel % as its parent (DP-Ch31: dissolution is terminal, so a '
                'dissolved subtree cannot grow)', NEW.id, NEW.parent
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;

    IF OLD.lifecycle = 'dissolved' AND NEW.lifecycle <> 'dissolved' THEN
        RAISE EXCEPTION
            'channels_dissolved_is_terminal: channel % cannot leave lifecycle '
            '''dissolved'' (DP-Ch31: terminal, no transitions)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER channels_lifecycle_guard_trg
    BEFORE INSERT OR UPDATE ON channels
    FOR EACH ROW EXECUTE FUNCTION channels_lifecycle_guard();

-- `DP-Ch33` — descendants first. **A separate, AFTER, CONSTRAINT trigger, and
-- the shape is the finding** (`1b7db-07`).
--
-- As a BEFORE-ROW check this rule made a legitimate operation IMPOSSIBLE rather
-- than merely awkward: dissolving a subtree in one statement failed in EVERY row
-- order, including an explicitly leaf-first `ORDER BY depth DESC`, because a
-- BEFORE-ROW trigger cannot see the other rows the same command is updating. The
-- only working shape was N separate single-row statements, which was nowhere
-- documented and which no caller would guess.
--
-- A CONSTRAINT TRIGGER fires at the END OF THE STATEMENT, so it sees the
-- statement's whole effect: `UPDATE ... WHERE id IN (2,3)` now succeeds, and a
-- parent left with a live child still fails. It is also DEFERRABLE, so a caller
-- dissolving a subtree across several statements can defer to COMMIT — the same
-- escape hatch `channels_parent_fk` has, for the same reason, and it does not
-- weaken the rule: at COMMIT the final state is checked.
CREATE OR REPLACE FUNCTION channels_dissolve_order_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM channels c
                WHERE c.reality_id = NEW.reality_id
                  AND c.parent = NEW.id
                  AND c.lifecycle <> 'dissolved') THEN
        RAISE EXCEPTION
            'channels_dissolve_descendants_first: channel % still has a child '
            'that is not dissolved (DP-Ch33)', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$;

-- ⚠ `INSERT` ADDED 2026-08-08 (`1b12-01`). This fired on UPDATE only, and both
-- guards only ever looked at rows that ALREADY EXIST — so the pair could be
-- walked around by REVERSING THE INSERT ORDER inside the migration's own
-- sanctioned deferral hatch:
--
--     BEGIN; SET CONSTRAINTS channels_parent_fk DEFERRED;
--       INSERT the CHILD   -- its parent does not exist yet, so the
--                          -- no-child-of-dissolved lookup finds nothing
--       INSERT the PARENT, already 'dissolved'
--                          -- NEW.parent IS NULL, so that guard skips; and this
--                          -- trigger was AFTER **UPDATE**, so it never fired
--     COMMIT;              -- the FK is satisfied: both rows now exist
--
-- and the dissolved subtree then GROWS, which is exactly what the other guard's
-- error text says cannot happen. Composed with `DP-Ch33` checking CHILDREN
-- rather than descendants — which is only sound BECAUSE of the induction this
-- rule provides — every ancestor could then be dissolved legally, leaving a
-- fully dissolved tree with a live leaf under it.
--
-- Firing on INSERT closes it: inserting an already-dissolved row whose children
-- exist is checked at end-of-statement like any other dissolution. The hatch is
-- not the defect; **a rule that only inspects the past is**, and an INSERT is
-- how you write a row whose children are already there.
DROP TRIGGER IF EXISTS channels_dissolve_order_trg ON channels;
CREATE CONSTRAINT TRIGGER channels_dissolve_order_trg
    AFTER INSERT OR UPDATE OF lifecycle ON channels
    DEFERRABLE INITIALLY IMMEDIATE
    FOR EACH ROW
    WHEN (NEW.lifecycle = 'dissolved')
    EXECUTE FUNCTION channels_dissolve_order_guard();

-- ⚠ REWRITTEN 2026-08-08 (`1b14-03`). This asserted BOTH claims the slice
-- retracted, 200+ lines below their own retractions in this same file --
-- that `DP-Ch11` allocates `channels.id` (it allocates `channel_event_id`,
-- `1b7gap-M1`) and that cycles are "unrepresentable rather than rejected"
-- (`1b7db-02`/`03`). **This COMMENT is the only artifact of slice 1b that is
-- written into a real per-reality database**, and `dp-channels-schema-gate`
-- does not read `COMMENT ON` -- default-uncovered, `NV-3`. It now says only
-- what survived attack.
COMMENT ON TABLE channels IS
    'DP-Ch2 channel registry, per reality. id is BIGINT (REC-103, REC-102a: ChannelId is '
    'i64). Through ordinary SQL a cycle is not representable (REC-106): parent_depth is '
    'generated from depth and the parent FK carries it, so depth decreases by exactly one '
    'along every parent edge. How channels.id is ALLOCATED is unspecified in the corpus.';

COMMIT;
