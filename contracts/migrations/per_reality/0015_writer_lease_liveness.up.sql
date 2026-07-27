-- 0015 — IMG-A2: give the writer lease an EXPIRY and a HOLDER.
--
-- DP-A16's epoch fence already guarantees SAFETY (never two writers): one
-- atomic CAS is both the channel_event_id allocator and the fence, so a stale
-- writer fails at the DB layer. What it never had is LIVENESS — audit finding
-- CNC-F9: nothing assigns a channel, notices a dead holder, or reassigns.
--
-- The fix goes in the SAME ROW rather than into a coordination service
-- (IMG-D1), for the same reason the fence itself was good: no new service to
-- deploy or keep available, no split-brain beyond what the CAS already
-- resolves, and no new failure mode when "the coordinator" is down, because
-- there is no coordinator. When the platform CP lands it takes over ISSUANCE
-- POLICY over this same table with this same fence.
--
-- Both columns are NULLABLE on purpose: rows written before this migration
-- exist, and a NULL expiry reads as "unheld, claimable" rather than making
-- them permanently unownable.

ALTER TABLE channel_writer_state
    ADD COLUMN IF NOT EXISTS holder_id        UUID,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

COMMENT ON COLUMN channel_writer_state.holder_id IS
    'IMG-A2: the process currently holding the writer lease. Renew and release '
    'are scoped to it, so a fenced-out holder cannot extend a lease it lost.';
COMMENT ON COLUMN channel_writer_state.lease_expires_at IS
    'IMG-A2: wall-clock expiry, always compared against Postgres now() and never '
    'a node clock (IMG-D2). NULL = unheld/legacy, therefore claimable.';

-- Claim scans for expired or unheld leases. Small table (one row per active
-- channel), but the index keeps a fleet-wide sweep from degrading into a seq
-- scan as channel count grows.
CREATE INDEX IF NOT EXISTS channel_writer_state_expiry_idx
    ON channel_writer_state (lease_expires_at);
