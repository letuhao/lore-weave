-- 021_incidents.down.sql
DROP INDEX IF EXISTS idx_incidents_postmortem_due;
DROP INDEX IF EXISTS idx_incidents_active;
DROP INDEX IF EXISTS idx_incidents_severity_declared;
DROP INDEX IF EXISTS idx_incidents_status_declared;
DROP TABLE IF EXISTS incidents;
