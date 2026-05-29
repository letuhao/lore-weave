// Package incidents — L7.D + L7.L shared contract (RAID cycle 37).
//
// This package is the SINGLE source of truth for the incident wire shape
// that crosses the L7.D ↔ L7.L service boundary. Per RAID_WORKFLOW §13.2
// (cross-DPS contract declaration), DPS 1 (incident-bot, postmortem-bot)
// OWNS this package; DPS 2 (statuspage-updater) CONSUMES the same
// IncidentDeclaredV1 / IncidentClosedV1 / IncidentUpdatedV1 shapes so the
// two slices do not race on an ad-hoc JSON shape.
//
// Scope (SR02 §12AE — severity matrix, IC role, war room; SR04 postmortem):
//
//   - events.go        — wire event types emitted by incident-bot and
//     consumed by statuspage-updater + postmortem-bot. Versioned (V1 suffix);
//     additive-only evolution per the platform event-contract convention.
//   - severity.go      — the Severity enum (SEV0..SEV3) + IsValid + ordering.
//   - severity_matrix.go — typed loader for severity_matrix.yaml (the
//     authoritative 4-severity criteria + TTA + comms obligations table).
//
// LOCKED decisions consumed:
//   - Q-L7-1  — incident-bot + statuspage-updater + slo-calc are SEPARATE
//     services; this shared contract is what lets them stay decoupled.
//   - Q-L7L-1 — Statuspage.io V1 (the comms-obligation column drives the
//     statuspage-updater; no direct provider coupling leaks into this pkg).
//
// No secrets, no provider SDKs, no I/O beyond reading the YAML matrix.
package incidents
