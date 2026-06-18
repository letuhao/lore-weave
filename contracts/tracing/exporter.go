package tracing

import (
	"sync"
	"time"
)

// SpanSnapshot is the immutable point-in-time view of a finished span,
// handed off to Exporter.Export.
//
// Production exporters convert this to OTLP protobuf at the boundary. The
// foundation does NOT depend on the OTel SDK (Q-L4D-1 OPAQUE-payload
// pattern carried forward from the prompt SDK).
type SpanSnapshot struct {
	TraceID    [16]byte
	SpanID     [8]byte
	Name       string
	Kind       SpanKind
	Status     Status
	StartedAt  time.Time
	EndedAt    time.Time
	Attributes map[string]any
	Errors     []error
}

// Duration returns EndedAt - StartedAt.
func (s SpanSnapshot) Duration() time.Duration {
	return s.EndedAt.Sub(s.StartedAt)
}

// Exporter is the seam between this foundation library and the OTLP/Tempo
// pipeline (cycle 33+ L7.G.6). Production binds an OTLP gRPC exporter;
// tests use InMemoryExporter.
//
// Export MUST be allocation-bounded and non-blocking. Production exporter
// implementations typically batch + ship asynchronously.
type Exporter interface {
	// Export submits a single finished span. Returns no error — the
	// exporter is responsible for its own retry/dead-letter handling.
	Export(snapshot SpanSnapshot)
}

// NoopExporter discards all spans. Default for services that have not
// wired an exporter yet (no panic, no data — just dropped).
type NoopExporter struct{}

// Export discards snapshot.
func (NoopExporter) Export(_ SpanSnapshot) {}

// InMemoryExporter is the test/reference exporter. Accumulates all spans
// in a bounded ring buffer (default capacity = 1024).
type InMemoryExporter struct {
	mu       sync.Mutex
	capacity int
	spans    []SpanSnapshot
	dropped  int
}

// NewInMemoryExporter constructs an InMemoryExporter with the given ring
// capacity. capacity <= 0 defaults to 1024.
func NewInMemoryExporter(capacity int) *InMemoryExporter {
	if capacity <= 0 {
		capacity = 1024
	}
	return &InMemoryExporter{capacity: capacity}
}

// Export appends the snapshot to the ring buffer; oldest is dropped if
// the ring is full.
func (e *InMemoryExporter) Export(snapshot SpanSnapshot) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if len(e.spans) >= e.capacity {
		// Drop oldest (FIFO eviction matches the cycle-19 budget breach
		// buffer pattern).
		e.spans = e.spans[1:]
		e.dropped++
	}
	e.spans = append(e.spans, snapshot)
}

// Spans returns a copy of the current ring contents (oldest first).
func (e *InMemoryExporter) Spans() []SpanSnapshot {
	e.mu.Lock()
	defer e.mu.Unlock()
	out := make([]SpanSnapshot, len(e.spans))
	copy(out, e.spans)
	return out
}

// Dropped returns the cumulative count of spans evicted from the ring.
func (e *InMemoryExporter) Dropped() int {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.dropped
}

// Len returns the number of spans currently in the ring.
func (e *InMemoryExporter) Len() int {
	e.mu.Lock()
	defer e.mu.Unlock()
	return len(e.spans)
}
