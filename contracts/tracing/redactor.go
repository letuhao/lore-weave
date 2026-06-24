package tracing

// Redactor is the seam between this tracing library and the cycle 22 PII
// SDK (`contracts/pii`). The tracing library NEVER imports the PII SDK
// directly — same one-way contract dep pattern as the cycle-32 logging
// library.
//
// Span attributes flagged via the per-Tracer PII allow-list (see
// TracerConfig.PIIAttributeKeys) route through Redactor.Redact before
// landing on the InMemorySpan attribute map or exported snapshot.
//
// # Production wiring
//
// Services bind a cycle-22 PII SDK redactor adapter in main.go. Tests
// use the NoopRedactor below.
type Redactor interface {
	// Redact masks value if it is PII. Returns (masked, true) when
	// applied; (original, false) when not.
	Redact(value any) (masked any, redacted bool)
}

// NoopRedactor passes everything through.
type NoopRedactor struct{}

// Redact returns value unchanged and reports redacted=false.
func (NoopRedactor) Redact(value any) (any, bool) { return value, false }
