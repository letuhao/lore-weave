-- Down for 038 — orphan_scan_finding.
--
-- Safe: the table is STATE, not history. Every row is re-derivable by running
-- `orphan_scanner` again against the same shard, so dropping it loses nothing
-- but `first_seen_at` (how long a finding has been outstanding). Contrast the
-- 036 down, which destroys tenancy data nothing else records and therefore
-- carries a guard.

DROP INDEX IF EXISTS idx_orphan_scan_finding_shard_first_seen;
DROP TABLE IF EXISTS orphan_scan_finding;
