package emit

// W4.2 (D-S12-T0T1-MICRO) — micro-bench the two inner write ticks of the event
// sourcing path, measured where they actually live ADJACENTLY in one TX:
//
//	T0 = INSERT INTO events …    (the full many-column event row + jsonb payload +
//	                              the W3.4 content_sha256 hash — the heavy tick)
//	T1 = INSERT INTO events_outbox …  (a 2-column pointer row — the light tick)
//
// It reuses the PRODUCTION SQL verbatim (emit.insertEventsSQL for T0,
// events.OutboxInsertSQL for T1) so the measured cost is the real path, not a
// re-implementation. Per the S7 discipline it ships a METHOD + a RELATIVE gate
// (T1.p50 < T0.p50 — a pointer INSERT must be cheaper than a full event append),
// NOT an absolute µs threshold.

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"slices"
	"time"

	events "github.com/loreweave/foundation/contracts/events"
	"github.com/loreweave/foundation/tests/workload-gen/internal/gen"
)

// biteOutboxSQL is the NON-VACUITY bite: a genuinely-expensive REAL outbox INSERT
// (it forces ~200k rows of generate_series work in PG before inserting the same
// pointer row) so T1 becomes more expensive than T0. The relative gate must then
// FIRE. A harness that returned a constant (rather than timing the real exec)
// would not move — this proves the measurement is of the actual per-call latency.
const biteOutboxSQL = `INSERT INTO events_outbox (event_id, reality_id)
	SELECT $1, $2 WHERE (SELECT count(*) FROM generate_series(1, 200000)) >= 0`

// MicroResult holds the per-tick latency distribution.
type MicroResult struct {
	N            int
	T0p50, T0p99 time.Duration
	T1p50, T1p99 time.Duration
}

// GatePass reports the relative gate: the light outbox tick (T1) must be cheaper
// at the median than the heavy event-append tick (T0).
func (r MicroResult) GatePass() bool { return r.T1p50 < r.T0p50 }

// MicroBench writes each event in s as the production path does (events INSERT
// then outbox INSERT, one TX per event) but times EACH exec separately, and
// returns the p50/p99 for both ticks. With biteT1, the outbox exec uses the
// expensive variant so the gate is expected to FAIL (the bite).
func MicroBench(ctx context.Context, db *sql.DB, s gen.Stream, biteT1 bool) (MicroResult, error) {
	outboxSQL := events.OutboxInsertSQL
	if biteT1 {
		outboxSQL = biteOutboxSQL
	}
	t0s := make([]time.Duration, 0, len(s))
	t1s := make([]time.Duration, 0, len(s))

	for i, e := range s {
		payload, err := json.Marshal(e.Payload)
		if err != nil {
			return MicroResult{}, fmt.Errorf("microbench: marshal payload %d: %w", i, err)
		}
		var metadata any
		if e.Metadata != nil {
			mb, err := json.Marshal(e.Metadata)
			if err != nil {
				return MicroResult{}, fmt.Errorf("microbench: marshal metadata %d: %w", i, err)
			}
			metadata = mb
		}

		tx, err := db.BeginTx(ctx, nil)
		if err != nil {
			return MicroResult{}, fmt.Errorf("microbench: begin %d: %w", i, err)
		}

		// T0 — the production events INSERT (insertEventsSQL: 11 binds, $8 reused by
		// the content_sha256 expression).
		st := time.Now()
		_, err = tx.ExecContext(ctx, insertEventsSQL,
			e.EventID, e.RealityID, e.AggregateType, e.AggregateID, int64(e.AggregateVersion),
			e.EventType, int32(e.EventVersion), payload, metadata, e.OccurredAt, e.RecordedAt,
		)
		t0 := time.Since(st)
		if err != nil {
			_ = tx.Rollback()
			return MicroResult{}, fmt.Errorf("microbench: T0 insert %d: %w", i, err)
		}

		// T1 — the outbox pointer INSERT (production OutboxInsertSQL, or the bite).
		st = time.Now()
		_, err = tx.ExecContext(ctx, outboxSQL, e.EventID, e.RealityID)
		t1 := time.Since(st)
		if err != nil {
			_ = tx.Rollback()
			return MicroResult{}, fmt.Errorf("microbench: T1 insert %d: %w", i, err)
		}

		if err := tx.Commit(); err != nil {
			return MicroResult{}, fmt.Errorf("microbench: commit %d: %w", i, err)
		}
		t0s = append(t0s, t0)
		t1s = append(t1s, t1)
	}

	if len(t0s) == 0 {
		return MicroResult{}, fmt.Errorf("microbench: empty stream — nothing measured")
	}
	return MicroResult{
		N:     len(t0s),
		T0p50: pct(t0s, 0.50), T0p99: pct(t0s, 0.99),
		T1p50: pct(t1s, 0.50), T1p99: pct(t1s, 0.99),
	}, nil
}

// pct returns the p-quantile (0..1) of ds by nearest-rank on a sorted copy.
func pct(ds []time.Duration, p float64) time.Duration {
	c := append([]time.Duration(nil), ds...)
	slices.Sort(c)
	idx := int(p * float64(len(c)-1))
	return c[idx]
}
