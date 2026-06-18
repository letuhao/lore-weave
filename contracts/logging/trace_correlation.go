package logging

// TraceCorrelation is the typed bridge between cycle 32 L7.E (this package)
// and cycle 32 L7.G (`contracts/tracing`). To prevent a Go import cycle,
// the logging library defines its OWN minimal typed view of the trace
// context — L7.G's contracts/tracing.TraceContext is shape-compatible and
// services convert at the boundary.
//
// # Why duplicate the type
//
// Same pattern as cycle 21 L4.L `contracts/ws` defining a local
// `ServiceMode` mirror of `contracts/lifecycle.ServiceMode` (Q-L4-1 parity
// invariant): one-way contract dep — logging never imports tracing, never
// imports prompt, never imports anything except std + cycle-22 Redactor
// interface (no concrete dep). This keeps L7.E reusable from any layer.
//
// # JSON shape
//
// Embedded in the Logger output as:
//
//	{"trace_id": "<32-hex>", "span_id": "<16-hex>", "correlation_id": "<uuid>"}
//
// All fields are omitted (not emitted with empty string) when zero — JSON
// search shape stays terse for non-traced log lines.
type TraceCorrelation struct {
	// TraceID is the W3C trace_id hex form (32 lowercase hex chars).
	// Empty when no trace context is active.
	TraceID string

	// SpanID is the W3C parent_id hex form (16 lowercase hex chars).
	// Empty when no span is active.
	SpanID string

	// CorrelationID is the cycle-3 / event-envelope correlation_id
	// (UUID v4 string) — propagates across service boundaries via the
	// cycle 8 event envelope metadata.
	CorrelationID string
}

// IsZero returns true when no trace correlation is set. Logger uses this
// to skip emitting the three keys when they would all be empty.
func (tc TraceCorrelation) IsZero() bool {
	return tc.TraceID == "" && tc.SpanID == "" && tc.CorrelationID == ""
}
