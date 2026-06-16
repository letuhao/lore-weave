-- contracts/migrations/per_reality/0013_events_content_sha256.up.sql
--
-- W3.4 — stored content checksum for byte-rot / tamper detection.
--
-- Adds a nullable `content_sha256 CHAR(64)` column to the append-only `events`
-- log. Writers (dp-kernel event_store_pg.rs append + the workload-gen emit path)
-- populate it AT INSERT with the PG-canonical hash of the event's JSONB CONTENT
-- — BOTH payload AND metadata, combined unambiguously:
--
--     encode(sha256(convert_to(
--         jsonb_build_object('p', payload, 'm', metadata)::text, 'UTF8')), 'hex')
--
-- COVERAGE — payload AND metadata. metadata carries projection-relevant fields
-- (e.g. npc.said's session_id, read by the npc_session_memory projection), so a
-- payload-only checksum would leave metadata byte-rot undetectable. The
-- jsonb_build_object envelope combines them with no concatenation ambiguity:
-- NULL metadata hashes as {"m": null} (distinct from {} — proven), and tampering
-- EITHER column changes the combined canonical text.
--
-- DESIGN — PG is the single canonicalizer (dissolves the cross-language hashing
-- risk, Wave-3 plan R1). The hash is taken over Postgres's own deterministic
-- jsonb text form (keys sorted, whitespace canonical). Because both the Go and
-- the Rust writer emit the SAME SQL expression, and PG normalizes the bound jsonb
-- identically regardless of the writer's key order / whitespace, the two writers
-- produce byte-identical hashes for equal content — no Go≡Rust canonical-JSON
-- library needed, and ONE SQL checker covers every writer.
--
-- PLAIN (NON-generated) column on purpose: a GENERATED column would RECOMPUTE on
-- any `UPDATE events SET payload/metadata = …`, masking the very tampering this
-- column exists to catch. As a plain column the baseline is frozen at insert, so
-- a later content mutation makes the re-derived hash diverge from the stored one.
--
-- Additive + nullable ⇒ metadata-only catalog change on the partitioned table
-- (propagates to all partitions, no table rewrite, existing rows unaffected).
-- Pre-0013 rows keep content_sha256 = NULL: they have no baseline, so the checker
-- SKIPS them (byte-rot on a pre-migration row is undetectable — the documented
-- coverage boundary: protection covers rows written after this migration only).

BEGIN;

ALTER TABLE events ADD COLUMN IF NOT EXISTS content_sha256 CHAR(64);

COMMENT ON COLUMN events.content_sha256 IS
    'SHA-256 (hex, 64 chars) over the canonical jsonb text of jsonb_build_object(p:payload, m:metadata), set at INSERT by both the dp-kernel append + the Go emit path (identical SQL expression; PG is the single canonicalizer so Go+Rust agree). Covers payload AND metadata. PLAIN (non-generated): an UPDATE to payload/metadata does NOT recompute it, so post-write byte-rot/tamper is detectable by re-deriving + comparing. NULL for pre-0013 rows (no baseline → skipped by the ledger -check-checksum). W3.4.';

COMMIT;
