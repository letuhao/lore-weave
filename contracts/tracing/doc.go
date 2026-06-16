// Package tracing is the LoreWeave distributed-tracing contract library
// (RAID cycle 32 / L7.G).
//
// # Scope
//
// This package ships the typed primitives every LoreWeave service uses to
// emit + propagate spans. Foundation does NOT bundle an OTLP/OpenTelemetry
// SDK — services bind an OTel adapter in main.go (same Q-L4D-1 OPAQUE-payload
// pattern as the prompt SDK). Foundation DOES own:
//
//   - W3C Trace Context (`traceparent` 55-char hex form) parse/format
//   - TraceContext typed struct (16-byte TraceID, 8-byte SpanID, Flags, State)
//   - Propagation Inject/Extract over `http.Header` and event-envelope metadata
//   - Span interface (Start/End/SetAttribute/RecordError) + InMemorySpan
//   - Tracer interface + NoopTracer default + sampler hook
//   - Sampler interface + adaptive sev-tier override
//   - Exporter interface (OPAQUE payload — production binds OTLP)
//
// # LOCKED decisions consumed
//
//   - Q-L7-3 — NO service mesh (Istio/Linkerd); tracing in-library via SDK
//   - Q-L7-4 — foundation = backend tracing only; frontend-game team owns RUM
//   - Q-L4D-1 (carry-forward) — exporter payload OPAQUE; no direct OTel SDK use
//   - Cycle 8 event envelope — trace context propagates as `traceparent` +
//     `tracestate` entries in `EventEnvelope.Metadata` map
//   - Cycle 19 L4.H observability conventions — span name regex enforced
//   - Cycle 22 L4.Q PII SDK — span attributes route through Redactor
//
// # W3C Trace Context format
//
// `traceparent` = `00-<32-hex-trace-id>-<16-hex-parent-id>-<2-hex-flags>`
//
//	(version=00, trace_id=128b, parent_id=64b, flags=8b sampled-bit)
//
// Total length: 55 chars including dashes. Anything else is rejected by
// ParseTraceparent.
//
// # Adaptive sampling (cycle 19 L4.H)
//
// Sampler.ShouldSample returns true for:
//
//	1. 100% when severity >= Sev0/Sev1 (set via TraceContext.OverrideSampled)
//	2. Probabilistic rate (default 1%) otherwise
//	3. 100% when ForceSample=true (admin-cli debug mode)
//
// # Out of scope
//
//   - Tempo/Grafana backend (cycle 33+ L7.G.6)
//   - Service mesh sidecar (Q-L7-3: NOT V1)
//   - Frontend OTel-JS (Q-L7-4: frontend-game team)
//   - Real OTLP exporter — foundation ships the interface; service main.go
//     binds an OTel SDK + OTLP exporter
package tracing
