package breach

import (
	"context"
	"sync"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
	gbf "github.com/loreweave/foundation/services/incident-bot/internal/gdpr_breach_flow"
)

// Monitor periodically re-evaluates open breach records and emits a
// GDPRBreachDeadlineV1 when one crosses the approaching (<=12h) or missed (<=0)
// threshold — ONCE per state (no per-tick alert spam).
//
// IN-PROCESS ONLY: the open set lives in memory, so reminders do NOT survive a
// restart (tracked D-BREACH-DURABLE-STORE). The GDPRBreachOpenedV1 event is the
// durable anchor a future consumer can replay to rebuild this set. Safe for
// concurrent use: the HTTP handler calls Track while the ticker reads.
type Monitor struct {
	emitter  EventEmitter
	now      func() time.Time
	interval time.Duration

	mu   sync.Mutex
	open map[string]*monEntry
}

type monEntry struct {
	rec             *gbf.BreachRecord
	emittedApproach bool
	emittedMissed   bool
}

// NewMonitor builds a Monitor. interval<=0 defaults to 1 minute.
func NewMonitor(emitter EventEmitter, now func() time.Time, interval time.Duration) *Monitor {
	if now == nil {
		now = time.Now
	}
	if interval <= 0 {
		interval = time.Minute
	}
	return &Monitor{emitter: emitter, now: now, interval: interval, open: map[string]*monEntry{}}
}

// Track adds a breach record to the monitored set (idempotent on incident_id).
func (m *Monitor) Track(rec *gbf.BreachRecord) {
	if rec == nil || rec.IncidentID == "" {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, exists := m.open[rec.IncidentID]; !exists {
		m.open[rec.IncidentID] = &monEntry{rec: rec}
	}
}

// Run drives the ticker until ctx is cancelled. Call as a goroutine.
func (m *Monitor) Run(ctx context.Context) {
	t := time.NewTicker(m.interval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			m.tick(ctx)
		}
	}
}

// tick evaluates every open breach once. Extracted from Run so tests can drive
// it deterministically with an injected clock (no wall-clock waits).
func (m *Monitor) tick(ctx context.Context) {
	m.mu.Lock()
	// Snapshot the entries that need an emit under the lock, then emit outside it.
	type pending struct {
		ev     incidents.GDPRBreachDeadlineV1
		entry  *monEntry
		missed bool
	}
	var todo []pending
	now := m.now()
	for _, e := range m.open {
		rem := e.rec.Deadline.Sub(now)
		switch {
		case rem <= 0 && !e.emittedMissed:
			todo = append(todo, pending{
				ev:     incidents.NewGDPRBreachDeadlineV1(e.rec.IncidentID, incidents.BreachDeadlineMissed, rem),
				entry:  e,
				missed: true,
			})
		case rem > 0 && rem <= gbf.ApproachingThreshold && !e.emittedApproach:
			todo = append(todo, pending{
				ev:    incidents.NewGDPRBreachDeadlineV1(e.rec.IncidentID, incidents.BreachDeadlineApproaching, rem),
				entry: e,
			})
		}
	}
	// Optimistically mark emitted under the lock so a concurrent tick can't
	// double-emit; if the emit then fails we clear the flag to allow a retry.
	for _, p := range todo {
		if p.missed {
			p.entry.emittedMissed = true
		} else {
			p.entry.emittedApproach = true
		}
	}
	m.mu.Unlock()

	for _, p := range todo {
		if err := m.emitter.EmitBreachDeadline(ctx, p.ev); err != nil {
			// Emit failed — clear the flag so the next tick retries.
			m.mu.Lock()
			if p.missed {
				p.entry.emittedMissed = false
			} else {
				p.entry.emittedApproach = false
			}
			m.mu.Unlock()
			continue
		}
		if p.missed {
			// "missed" is terminal — Art.33 has no deadline state past it. Prune
			// the entry so `open` cannot grow unbounded and a settled breach is
			// not re-scanned every tick (code-adversary BLOCK).
			m.mu.Lock()
			delete(m.open, p.entry.rec.IncidentID)
			m.mu.Unlock()
		}
	}
}

// Untrack removes a breach from the monitored set — the off-ramp for a future
// "breach resolved / DPO-notified" signal so a still-open breach stops being
// scanned. (Wiring that signal is part of the deferred durable/delivery work.)
func (m *Monitor) Untrack(incidentID string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.open, incidentID)
}

// OpenCount returns the number of tracked breaches (test/observability helper).
func (m *Monitor) OpenCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.open)
}
