package observability

import (
	"context"
	"sync"
)

// BudgetBreachRow is the typed shape of one row in the
// `observability_budget_breaches` (meta) table. The actual SQL writer
// lives in `contracts/meta/observability_budget_breach_writer.sql.go`
// when the full meta-DB writer ships (cycle 20-22); cycle 19 ships the
// typed buffer + flush abstraction so callers can wire it now.
type BudgetBreachRow struct {
	MetricName string
	Labels     map[string]string
	Reason     string // "unregistered_metric" | "unregistered_label"
	Mode       AdmissionMode
	OccurredAt int64 // unix-nanos
}

// BudgetBreachBuffer is a bounded in-memory ring of recent breaches.
// Production wires a Flush goroutine that periodically drains to the
// meta DB; tests inspect the buffer directly.
//
// Bounded design: emissions on the hot path must NEVER block. If the
// buffer is full, the oldest entry is dropped (FIFO eviction) and an
// internal `dropped` counter is incremented. Operators monitor the
// counter to know when to bump the buffer size.
type BudgetBreachBuffer struct {
	mu       sync.Mutex
	rows     []BudgetBreachRow
	capacity int
	head     int
	size     int
	dropped  uint64
}

// NewBudgetBreachBuffer constructs a ring buffer with the given
// capacity. Capacity MUST be > 0.
func NewBudgetBreachBuffer(capacity int) *BudgetBreachBuffer {
	if capacity <= 0 {
		capacity = 1024
	}
	return &BudgetBreachBuffer{rows: make([]BudgetBreachRow, capacity), capacity: capacity}
}

// Write enqueues one breach. Non-blocking; if the buffer is full, the
// oldest row is evicted and dropped++ is incremented.
func (b *BudgetBreachBuffer) Write(row BudgetBreachRow) {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.size == b.capacity {
		// Evict oldest by advancing head; overwrite tail.
		b.head = (b.head + 1) % b.capacity
		b.dropped++
	} else {
		b.size++
	}
	tail := (b.head + b.size - 1) % b.capacity
	b.rows[tail] = row
}

// Drain returns + clears all buffered rows. Snapshot semantics: the
// returned slice is owned by the caller (safe to mutate); the
// internal buffer is reset to empty.
func (b *BudgetBreachBuffer) Drain() []BudgetBreachRow {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.size == 0 {
		return nil
	}
	out := make([]BudgetBreachRow, b.size)
	for i := 0; i < b.size; i++ {
		idx := (b.head + i) % b.capacity
		out[i] = b.rows[idx]
	}
	b.head = 0
	b.size = 0
	return out
}

// DroppedCount returns the total number of rows dropped due to
// capacity overflow since construction.
func (b *BudgetBreachBuffer) DroppedCount() uint64 {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.dropped
}

// Size returns the current number of buffered (un-drained) rows.
func (b *BudgetBreachBuffer) Size() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.size
}

// AsBreachWriter adapts BudgetBreachBuffer to the BreachWriter
// callback signature expected by Admission.
func (b *BudgetBreachBuffer) AsBreachWriter() BreachWriter {
	return func(br Breach) {
		b.Write(BudgetBreachRow{
			MetricName: br.MetricName,
			Labels:     br.Labels,
			Reason:     br.Reason,
			Mode:       br.Mode,
			OccurredAt: br.At.UnixNano(),
		})
	}
}

// BreachFlusher is the interface a meta-DB writer implements when
// wiring the buffer to durable storage. The cycle-20+ implementation
// lives in contracts/meta/.
type BreachFlusher interface {
	FlushBreaches(ctx context.Context, rows []BudgetBreachRow) error
}
