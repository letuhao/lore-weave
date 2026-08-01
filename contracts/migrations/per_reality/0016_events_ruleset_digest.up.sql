-- contracts/migrations/per_reality/0016_events_ruleset_digest.up.sql
--
-- F1/B — RLS-A13: pin every event to the ruleset that produced it.
--
-- Adds a nullable `ruleset_digest CHAR(64)` to the append-only `events` log:
-- the BLAKE3 content digest (lowercase hex) of the resolved RealityRuleset the
-- producing island was running, computed by `ruleset_core::Ruleset::digest()`
-- over its canonical encoding (RLS-D5) and stamped at INSERT by the game
-- writer.
--
-- WHY THIS COLUMN EXISTS. Rules live OUTSIDE the event log. Replay a six-month
-- old reality without this and it resolves against TODAY's rules and produces
-- different damage numbers — the canonical event-sourcing configuration trap,
-- and one that defeats the conformance/oracle spine this repo already runs. The
-- digest is what lets a replay notice that the rules moved underneath it.
--
-- WHY THE DIGEST AND NOT THE RULESET (RLS-D6). Full-ruleset-in-event was
-- considered and rejected on re-emission: 200 realities sharing a preset would
-- each write the same kilobytes, repeatedly, forever. Digest + an immutable
-- store keeps the log small and dedupes globally. The dependency this creates
-- (replay needs the ruleset store) is real, and is why that store is
-- append-only and never pruned.
--
-- WHY NOT AN EPOCH REFERENCE. A 4-byte `ruleset_epoch` plus a
-- `(reality_id, epoch) -> digest` lookup table is ~8x cheaper per row. It was
-- rejected: it trades a self-describing row for a mandatory join and a second
-- table that may never be lost. For 28 bytes, that is a false economy — and
-- RLS-A13 says "every event is pinned", not "every event references a pin".
--
-- WHY NULLABLE, AND WHY NOT ZEROS. Two distinct populations carry NULL and both
-- are legitimate:
--   * rows written before this migration — NULL means "written before pinning
--     existed", which is true;
--   * events that do not come from a ruleset-pinned simulation at all (canon
--     writes, Forge edits, admin actions) — NULL means "no ruleset governs
--     this", which is also true.
-- A 64-zero sentinel would instead claim "pinned to the empty ruleset" — a lie,
-- and exactly the class `scripts/zero-digest-gate.py` was added to outlaw after
-- an all-zero `RulesetDigest` sat inert in 15 places.
--
-- CHAR(64) lowercase hex, matching the `content_sha256` precedent (0013) and
-- `contracts/game-wire/common.schema.json#/$defs/Digest` (`^[0-9a-f]{64}$`), so
-- the same value is spelled identically in the DB, on the wire, and in both
-- language envelopes. Format is validated by Envelope.Validate() on both sides.
--
-- Additive + nullable => metadata-only catalog change on the partitioned table
-- (propagates to all partitions, no rewrite, existing rows unaffected).

BEGIN;

ALTER TABLE events ADD COLUMN IF NOT EXISTS ruleset_digest CHAR(64);

COMMENT ON COLUMN events.ruleset_digest IS
    'RLS-A13 content pin: BLAKE3 (lowercase hex, 64 chars) of the resolved RealityRuleset the producing island ran, from ruleset_core::Ruleset::digest() over the RLS-D5 canonical encoding. Stamped at INSERT by the game writer. NULL = no pin, and that is a true statement in two cases: rows written before migration 0016, and events not produced by a ruleset-pinned simulation (canon/Forge/admin). Never a 64-zero sentinel — that would claim a pin to the empty ruleset (see scripts/zero-digest-gate.py). Replay compares this against the ruleset it resolves under; a mismatch is refused (F3).';

COMMIT;
