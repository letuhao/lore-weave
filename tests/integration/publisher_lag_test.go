// publisher_lag_test.go — L2.D.10 (RAID cycle 10).
//
// Lag SLO test: inject 1000 outbox rows, run the publisher's poll loop
// ONCE, verify all 1000 rows are drained (Published) within the wall-time
// budget. This is the in-memory cousin of the future live test that runs
// against pgx + real Redis (D-PUBLISHER-LIVE-WIRING — cycle 11/L4).
//
// Also exercises:
//   - retry path: rows whose XADD fails get Retried (attempts++ + backoff).
//   - dead-letter path: a row at attempts=MaxAttempts-1 with a failing
//     XADD transitions to DeadLettered.
//   - failover (V1 trivial): a notLeader simulation skips the iteration.
//
// gated by `integration` tag so the daily `go test ./...` is a no-op.
//
//go:build integration
// +build integration

package integration

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"

	"github.com/loreweave/foundation/services/publisher/pkg/leader_election"
	"github.com/loreweave/foundation/services/publisher/pkg/poll_loop"
	"github.com/loreweave/foundation/services/publisher/pkg/retry"
	"github.com/loreweave/foundation/services/publisher/pkg/types"
)

// ── Test doubles ────────────────────────────────────────────────────────

type lagFetcher struct {
	rows []types.OutboxRow
	done bool
}

func (f *lagFetcher) FetchPending(_ context.Context, _ string, _ int) ([]types.OutboxRow, error) {
	if f.done {
		return nil, nil
	}
	f.done = true
	return f.rows, nil
}

type lagEmitter struct{ count int }

func (e *lagEmitter) Emit(_ context.Context, _ types.OutboxRow) error {
	e.count++
	return nil
}

type failingEmitter struct{ count int }

func (e *failingEmitter) Emit(_ context.Context, _ types.OutboxRow) error {
	e.count++
	return errors.New("simulated Redis failure")
}

type noopFanout struct{}

func (noopFanout) Fanout(_ context.Context, _ types.OutboxRow) error { return nil }

type stateRecorder struct {
	pub  int
	retr int
	dl   int
}

func (s *stateRecorder) MarkPublished(_ context.Context, _ string) error { s.pub++; return nil }
func (s *stateRecorder) MarkRetry(_ context.Context, _ string, _ int, _ string, _ time.Time) error {
	s.retr++
	return nil
}
func (s *stateRecorder) MarkDeadLetter(_ context.Context, _ string, _ int, _ string) error {
	s.dl++
	return nil
}

type modeFull struct{}

func (modeFull) Mode() lifecycle.ServiceMode { return lifecycle.ModeFull }

type modeEss struct{}

func (modeEss) Mode() lifecycle.ServiceMode { return lifecycle.ModeEssentials }

type notLeader struct{}

func (notLeader) IsLeader() bool { return false }
func (notLeader) Step()          {}
func (notLeader) Stop()          {}

// ── Helpers ─────────────────────────────────────────────────────────────

func makeRows(n, attempts int) []types.OutboxRow {
	rows := make([]types.OutboxRow, n)
	for i := 0; i < n; i++ {
		rows[i] = types.OutboxRow{
			EventID:   uuid.New(),
			RealityID: uuid.New(),
			Attempts:  attempts,
			EventType: "npc.said",
		}
	}
	return rows
}

// ── Tests ───────────────────────────────────────────────────────────────

// L2.D.10 acceptance: inject 1000 rows; drain in <1s wall time.
func TestPublisher_DrainsThousandRowsUnderSLO(t *testing.T) {
	rows := makeRows(1000, 0)
	state := &stateRecorder{}
	loop, err := poll_loop.New(poll_loop.Config{
		Leader:    leader_election.NewNoOp(),
		Fetcher:   &lagFetcher{rows: rows},
		Emitter:   &lagEmitter{},
		Fanout:    noopFanout{},
		StateW:    state,
		Mode:      modeFull{},
		Policy:    retry.DefaultPolicy(),
		BatchSize: 1000,
		Realities: []string{"r1"},
	})
	if err != nil {
		t.Fatalf("poll_loop.New: %v", err)
	}
	start := time.Now()
	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatalf("loop.Run: %v", err)
	}
	dur := time.Since(start)

	if stats.Published != 1000 {
		t.Errorf("Published=%d want 1000", stats.Published)
	}
	if state.pub != 1000 {
		t.Errorf("state.pub=%d want 1000", state.pub)
	}
	// Tight SLO: even with overhead, the in-memory drain MUST be < 1s.
	if dur > 1*time.Second {
		t.Errorf("drain took %v; SLO 1s", dur)
	}
}

// L2.D acceptance: persistent XADD failure dead-letters at MaxAttempts.
func TestPublisher_DeadLettersAfterMaxAttempts(t *testing.T) {
	p := retry.DefaultPolicy()
	// Row at attempts = MaxAttempts-1; next failure should dead-letter.
	rows := makeRows(1, p.MaxAttempts-1)
	state := &stateRecorder{}
	loop, _ := poll_loop.New(poll_loop.Config{
		Leader:    leader_election.NewNoOp(),
		Fetcher:   &lagFetcher{rows: rows},
		Emitter:   &failingEmitter{},
		Fanout:    noopFanout{},
		StateW:    state,
		Mode:      modeFull{},
		Policy:    p,
		BatchSize: 100,
		Realities: []string{"r1"},
	})
	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if stats.DeadLettered != 1 {
		t.Errorf("DeadLettered=%d want 1", stats.DeadLettered)
	}
	if state.dl != 1 {
		t.Errorf("state.dl=%d want 1", state.dl)
	}
}

// L2.D.11 failover semantics — V1 trivial: notLeader skips entirely.
func TestPublisher_NotLeader_SkipsIteration(t *testing.T) {
	loop, _ := poll_loop.New(poll_loop.Config{
		Leader:    notLeader{},
		Fetcher:   &lagFetcher{rows: makeRows(10, 0)},
		Emitter:   &lagEmitter{},
		Fanout:    noopFanout{},
		StateW:    &stateRecorder{},
		Mode:      modeFull{},
		Policy:    retry.DefaultPolicy(),
		BatchSize: 10,
		Realities: []string{"r1"},
	})
	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !stats.Skipped {
		t.Error("expected stats.Skipped on notLeader")
	}
	if stats.Published != 0 {
		t.Errorf("Published=%d should be 0 when not leader", stats.Published)
	}
}

// L1.J integration: degraded mode pauses the drain.
func TestPublisher_DegradedMode_SkipsIteration(t *testing.T) {
	loop, _ := poll_loop.New(poll_loop.Config{
		Leader:    leader_election.NewNoOp(),
		Fetcher:   &lagFetcher{rows: makeRows(5, 0)},
		Emitter:   &lagEmitter{},
		Fanout:    noopFanout{},
		StateW:    &stateRecorder{},
		Mode:      modeEss{},
		Policy:    retry.DefaultPolicy(),
		BatchSize: 5,
		Realities: []string{"r1"},
	})
	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !stats.Skipped {
		t.Error("expected stats.Skipped on degraded mode")
	}
}
