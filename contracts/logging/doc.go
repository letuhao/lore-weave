// Package logging is the LoreWeave structured logging contract library
// (RAID cycle 32 / L7.E).
//
// # Scope
//
// This package ships the typed primitives every LoreWeave service uses to
// emit logs. Foundation does NOT own the actual Loki/Vector pipeline (Q-L7F-1
// — Loki self-hosted V1 lands in cycle 33+). Foundation DOES own:
//
//   - Typed Level (Debug/Info/Warn/Error)
//   - Typed Field with FieldKind tag (Normal/Sensitive/PII)
//   - Redactor interface (bridges cycle 22 PII SDK — no bare regex)
//   - Compile-time prod-build guard (IsProdBuild const flipped by `prod` build tag)
//   - W3C TraceContext correlation auto-injection point (consumed by L7.G)
//   - JSON-shape contract (single line per event)
//
// # LOCKED decisions consumed
//
//   - S08 §12X.8 — log.PII / log.Sensitive / log.Normal tagged-helpers, compile-time DEBUG guard
//   - Q-L7-3 — NO service mesh; tracing/logging in-library (no Istio sidecar log collector)
//   - Cycle 22 L4.Q — PII redaction via Redactor INTERFACE, never inline regex
//   - Cycle 19 L4.H — observability conventions (Log.Sensitive helper shape)
//   - Cycle 21 L4.D — Q-L6L-1 pattern: typed helper + interface seam +
//     fail-closed in downstream sub-program, NOT here
//
// # Out of scope
//
//   - Loki/Tempo backend, Vector/Fluent-Bit shipper (cycle 33+ L7.F)
//   - Service-side wiring of trace context to actual OTLP exporter (cycle 32 L7.G ships interface seam)
//   - Frontend RUM (Q-L7-4: frontend-game team owns; foundation = backend only)
//
// # Invariants (each enforced by tests)
//
//  1. FieldKindPII never reaches output buffer unredacted in prod build
//     (verified by Logger.Emit + Redactor contract).
//  2. FieldKindSensitive is dropped at Info level in prod build (Debug-only;
//     prod-build constant disables Debug entirely).
//  3. Compile-time guard — `IsProdBuild` is a const set by build tag, NOT
//     a runtime env var (defense vs accidental flip).
//  4. JSON shape stable: {ts, level, msg, trace_id?, correlation_id?, fields{...}}.
//  5. Logger.Emit is allocation-bounded — no unbounded slice growth per call
//     (cycle 21 PROMPT-SPAM holding pattern: keep per-call footprint flat).
package logging
