// Package dispatch routes a consumed xreality event to the right handler.
//
// ## I7 invariant — ALLOWLIST, not default-deny
//
// New event_types must be explicitly registered via Register(). An
// unregistered event_type returns ErrNoHandler — the consumer logs +
// counts a metric (`lw_meta_worker_dispatch_total{outcome=no_handler}`),
// does NOT ACK the message (so retry / dead-letter discipline applies)
// and the event stays in the pending list until a human triages.
//
// This is INTENTIONAL: the meta-worker has cross-tenant blast radius
// (canon propagation across realities). A default-route would let new
// xreality events ship with no handler and silently nop — losing fanout
// in production. The ALLOWLIST forces a code change for every new event.
package dispatch

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"sync"
)

// Handler is the per-event_type dispatch target.
//
// Fields is the parsed message body from XREADGROUP (publisher writes
// JSON-encoded envelope fields per cycle 10 DPS 2 xreality_fanout).
//
// Returning a non-nil error tells the consumer to NACK and retry; nil
// success ACKs the message.
type Handler func(ctx context.Context, fields map[string]any) error

// ErrNoHandler is returned by Dispatch when no handler is registered for
// the given event_type. The consumer treats this as a soft failure (count
// + log; do not ACK).
var ErrNoHandler = errors.New("meta-worker dispatch: no handler registered")

// Dispatcher is the registry. Thread-safe.
type Dispatcher struct {
	mu       sync.RWMutex
	handlers map[string]Handler
}

// New returns an empty Dispatcher. Use Register to populate.
func New() *Dispatcher {
	return &Dispatcher{handlers: map[string]Handler{}}
}

// Register installs a handler for event_type. Re-registering replaces.
// Returns the dispatcher for fluent chaining.
func (d *Dispatcher) Register(eventType string, h Handler) *Dispatcher {
	if eventType == "" {
		panic("dispatch: empty event_type")
	}
	if h == nil {
		panic("dispatch: nil handler")
	}
	d.mu.Lock()
	defer d.mu.Unlock()
	d.handlers[eventType] = h
	return d
}

// Dispatch routes the message to the registered handler. Returns
// ErrNoHandler for unregistered types.
func (d *Dispatcher) Dispatch(ctx context.Context, eventType string, fields map[string]any) error {
	d.mu.RLock()
	h, ok := d.handlers[eventType]
	d.mu.RUnlock()
	if !ok {
		return fmt.Errorf("%w: %s", ErrNoHandler, eventType)
	}
	return h(ctx, fields)
}

// Registered returns the sorted list of event_types this dispatcher
// handles. Used by startup logging + CI lint (assert ALL registry
// xreality.* events have a handler).
func (d *Dispatcher) Registered() []string {
	d.mu.RLock()
	defer d.mu.RUnlock()
	out := make([]string, 0, len(d.handlers))
	for k := range d.handlers {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// ValidateAllowlist enforces the ALLOWLIST invariant — every registered
// event_type MUST start with `xreality.`. Returns an error listing
// non-conforming entries. Called at startup.
func (d *Dispatcher) ValidateAllowlist() error {
	d.mu.RLock()
	defer d.mu.RUnlock()
	var bad []string
	for k := range d.handlers {
		if !strings.HasPrefix(k, "xreality.") {
			bad = append(bad, k)
		}
	}
	if len(bad) > 0 {
		sort.Strings(bad)
		return fmt.Errorf("dispatch: non-xreality handlers registered (I7 violation): %s", strings.Join(bad, ", "))
	}
	return nil
}

// ── V1 skeleton handlers ─────────────────────────────────────────────────
//
// These ship as ALLOWLIST entries so the L2.L wiring is testable end-to-
// end TODAY. Real projection writes land in cycle 12+ (canon_projection
// table doesn't exist yet at cycle 10). The skeletons echo the dispatch
// to a sink slice so tests can assert.

// SkeletonSink captures dispatches for tests. Production binds a real
// projection writer in cycle 12+.
type SkeletonSink struct {
	mu        sync.Mutex
	Dispatched []SkeletonRecord
}

// SkeletonRecord captures one dispatched event.
type SkeletonRecord struct {
	EventType string
	Fields    map[string]any
}

// Append records one dispatch. Thread-safe.
func (s *SkeletonSink) Append(rec SkeletonRecord) {
	s.mu.Lock()
	defer s.mu.Unlock()
	// Defensive copy so caller mutation can't poison sink.
	cp := SkeletonRecord{EventType: rec.EventType, Fields: map[string]any{}}
	for k, v := range rec.Fields {
		cp.Fields[k] = v
	}
	s.Dispatched = append(s.Dispatched, cp)
}

// Records returns a snapshot of dispatched events. Thread-safe + deep-copy
// — mutating a returned record's Fields MUST NOT leak back into the sink.
func (s *SkeletonSink) Records() []SkeletonRecord {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]SkeletonRecord, len(s.Dispatched))
	for i, rec := range s.Dispatched {
		cp := SkeletonRecord{EventType: rec.EventType, Fields: map[string]any{}}
		for k, v := range rec.Fields {
			cp.Fields[k] = v
		}
		out[i] = cp
	}
	return out
}

// NewWithSkeletons builds a V1 dispatcher pre-loaded with skeleton
// handlers for every xreality.* event in the registry. The sink captures
// every dispatch for test assertions.
func NewWithSkeletons(sink *SkeletonSink) *Dispatcher {
	d := New()
	d.Register("xreality.canon.promoted", func(_ context.Context, fields map[string]any) error {
		sink.Append(SkeletonRecord{EventType: "xreality.canon.promoted", Fields: fields})
		return nil
	})
	d.Register("xreality.user.erased", func(_ context.Context, fields map[string]any) error {
		sink.Append(SkeletonRecord{EventType: "xreality.user.erased", Fields: fields})
		return nil
	})
	return d
}
