package supply_chain

import (
	"context"
	"sync"
)

// SBOMComponent is one component entry in a CycloneDX SBOM (subset).
type SBOMComponent struct {
	Ecosystem Ecosystem
	Name      string
	Version   string
	License   string
	Purl      string // package URL (RFC TBD)
	Hashes    map[string]string
}

// SBOMEmitRow is the typed shape of one row in the
// `supply_chain_events` (meta) table (cycle 20+ writes this to PG).
type SBOMEmitRow struct {
	Service        string
	BuildID        string
	Format         string // cyclonedx | spdx
	SpecVersion    string // 1.5
	DocumentRef    string // s3://bucket/prefix/sbom.json (where the full doc lives)
	ComponentCount int
	OccurredAt     int64 // unix nanos
}

// SBOMBuffer is a bounded in-memory ring of emitted SBOM rows.
// Same eviction semantics as observability.BudgetBreachBuffer.
type SBOMBuffer struct {
	mu       sync.Mutex
	rows     []SBOMEmitRow
	capacity int
	head     int
	size     int
	dropped  uint64
}

// NewSBOMBuffer constructs a ring buffer with the given capacity.
func NewSBOMBuffer(capacity int) *SBOMBuffer {
	if capacity <= 0 {
		capacity = 256
	}
	return &SBOMBuffer{rows: make([]SBOMEmitRow, capacity), capacity: capacity}
}

// Write enqueues one SBOM emit row. Non-blocking.
func (b *SBOMBuffer) Write(row SBOMEmitRow) {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.size == b.capacity {
		b.head = (b.head + 1) % b.capacity
		b.dropped++
	} else {
		b.size++
	}
	tail := (b.head + b.size - 1) % b.capacity
	b.rows[tail] = row
}

// Drain returns + clears all buffered rows.
func (b *SBOMBuffer) Drain() []SBOMEmitRow {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.size == 0 {
		return nil
	}
	out := make([]SBOMEmitRow, b.size)
	for i := 0; i < b.size; i++ {
		idx := (b.head + i) % b.capacity
		out[i] = b.rows[idx]
	}
	b.head = 0
	b.size = 0
	return out
}

// DroppedCount returns the total rows dropped to capacity overflow.
func (b *SBOMBuffer) DroppedCount() uint64 {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.dropped
}

// Size returns the current number of buffered (un-drained) rows.
func (b *SBOMBuffer) Size() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.size
}

// SBOMFlusher is the interface a meta-DB writer implements when wiring
// the buffer to durable storage. cycle-20+ wires this.
type SBOMFlusher interface {
	FlushSBOMs(ctx context.Context, rows []SBOMEmitRow) error
}
