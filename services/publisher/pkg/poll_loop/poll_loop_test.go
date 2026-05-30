package poll_loop

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"

	"github.com/loreweave/foundation/services/publisher/pkg/leader_election"
	"github.com/loreweave/foundation/services/publisher/pkg/retry"
	"github.com/loreweave/foundation/services/publisher/pkg/types"
)

// ── In-memory fakes ─────────────────────────────────────────────────────

type retryRec struct {
	attempts int
	lastErr  string
	next     time.Time
}

// fakeBatch records the Mark calls + commit/rollback for one reality drain.
type fakeBatch struct {
	rows         []types.OutboxRow
	published    []uuid.UUID
	retried      map[uuid.UUID]retryRec
	deadLettered []uuid.UUID
	committed    bool
	rolledBack   bool
}

func newFakeBatch(rows []types.OutboxRow) *fakeBatch {
	return &fakeBatch{rows: rows, retried: map[uuid.UUID]retryRec{}}
}

func (b *fakeBatch) Rows() []types.OutboxRow { return b.rows }

func (b *fakeBatch) MarkPublished(_ context.Context, eid string) error {
	u, _ := uuid.Parse(eid)
	b.published = append(b.published, u)
	return nil
}

func (b *fakeBatch) MarkRetry(_ context.Context, eid string, attempts int, lastErr string, next time.Time) error {
	u, _ := uuid.Parse(eid)
	b.retried[u] = retryRec{attempts, lastErr, next}
	return nil
}

func (b *fakeBatch) MarkDeadLetter(_ context.Context, eid string, _ int, _ string) error {
	u, _ := uuid.Parse(eid)
	b.deadLettered = append(b.deadLettered, u)
	return nil
}

func (b *fakeBatch) Commit(_ context.Context) error   { b.committed = true; return nil }
func (b *fakeBatch) Rollback(_ context.Context) error { b.rolledBack = true; return nil }

// fakeSource pops one batch per reality per Begin call and records every
// batch it created so tests can assert on the Mark calls.
type fakeSource struct {
	byReality map[string][][]types.OutboxRow
	batches   []*fakeBatch
}

func (s *fakeSource) Begin(_ context.Context, reality string, _ int) (Batch, error) {
	var rows []types.OutboxRow
	batches := s.byReality[reality]
	if len(batches) > 0 {
		rows = batches[0]
		s.byReality[reality] = batches[1:]
	}
	b := newFakeBatch(rows)
	s.batches = append(s.batches, b)
	return b, nil
}

// lastBatch returns the most recently created batch (single-reality tests).
func (s *fakeSource) lastBatch() *fakeBatch {
	if len(s.batches) == 0 {
		return newFakeBatch(nil)
	}
	return s.batches[len(s.batches)-1]
}

func newFakeSource(reality string, rows []types.OutboxRow) *fakeSource {
	return &fakeSource{byReality: map[string][][]types.OutboxRow{reality: {rows}}}
}

type fakeEmitter struct {
	failEventIDs map[uuid.UUID]bool // these XADDs return error
	emitted      []uuid.UUID
}

func (e *fakeEmitter) Emit(_ context.Context, row types.OutboxRow) error {
	if e.failEventIDs[row.EventID] {
		return errors.New("simulated XADD failure")
	}
	e.emitted = append(e.emitted, row.EventID)
	return nil
}

type fakeFanout struct {
	fanned []uuid.UUID
	errOn  map[uuid.UUID]bool
}

func (f *fakeFanout) Fanout(_ context.Context, row types.OutboxRow) error {
	if f.errOn[row.EventID] {
		return errors.New("fanout fail")
	}
	f.fanned = append(f.fanned, row.EventID)
	return nil
}

type fakeMode struct{ m lifecycle.ServiceMode }

func (f *fakeMode) Mode() lifecycle.ServiceMode { return f.m }

// ── Helpers ─────────────────────────────────────────────────────────────

func uuidN(n int) uuid.UUID {
	u, _ := uuid.Parse("00000000-0000-0000-0000-00000000000" + string(rune('0'+n)))
	return u
}

func newRow(n, attempts int, crossReality bool) types.OutboxRow {
	r := types.OutboxRow{
		EventID:   uuidN(n),
		RealityID: uuidN(9),
		Attempts:  attempts,
		EventType: "npc.said",
	}
	if crossReality {
		r.Metadata = map[string]any{"cross_reality": true}
	}
	return r
}

func newLoop(t *testing.T, source Source, emitter Emitter, fanout XRealityFanout, mode ModeReader, realities []string) *Loop {
	t.Helper()
	loop, err := New(Config{
		Leader:    leader_election.NewNoOp(),
		Source:    source,
		Emitter:   emitter,
		Fanout:    fanout,
		Mode:      mode,
		Policy:    retry.DefaultPolicy(),
		BatchSize: 100,
		Realities: realities,
	})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return loop
}

// ── Tests ───────────────────────────────────────────────────────────────

func TestNew_ValidatesDeps(t *testing.T) {
	good := Config{
		Leader:  leader_election.NewNoOp(),
		Source:  &fakeSource{},
		Emitter: &fakeEmitter{},
		Fanout:  &fakeFanout{},
		Mode:    &fakeMode{},
		Policy:  retry.DefaultPolicy(),
	}
	tests := []func(c *Config){
		func(c *Config) { c.Leader = nil },
		func(c *Config) { c.Source = nil },
		func(c *Config) { c.Emitter = nil },
		func(c *Config) { c.Fanout = nil },
		func(c *Config) { c.Mode = nil },
		func(c *Config) { c.Policy = retry.Policy{} },
	}
	for i, mutate := range tests {
		bad := good
		mutate(&bad)
		if _, err := New(bad); err == nil {
			t.Errorf("case %d: expected nil-dep / bad-policy error", i)
		}
	}
}

func TestRun_HappyPath_PublishesEveryRow(t *testing.T) {
	rows := []types.OutboxRow{newRow(1, 0, false), newRow(2, 0, false)}
	source := newFakeSource("reality_A", rows)
	emitter := &fakeEmitter{}
	fanout := &fakeFanout{}
	mode := &fakeMode{m: lifecycle.ModeFull}
	loop := newLoop(t, source, emitter, fanout, mode, []string{"reality_A"})

	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if stats.Published != 2 {
		t.Errorf("Published=%d want 2", stats.Published)
	}
	if stats.Retried != 0 || stats.DeadLettered != 0 {
		t.Errorf("expected zero retries/dead-letters, got R=%d DL=%d", stats.Retried, stats.DeadLettered)
	}
	b := source.lastBatch()
	if len(b.published) != 2 {
		t.Errorf("expected 2 MarkPublished calls, got %d", len(b.published))
	}
	if !b.committed {
		t.Error("expected batch to be committed")
	}
}

func TestRun_TransientFailureRetries(t *testing.T) {
	rows := []types.OutboxRow{newRow(1, 0, false)}
	source := newFakeSource("r1", rows)
	emitter := &fakeEmitter{failEventIDs: map[uuid.UUID]bool{uuidN(1): true}}
	loop := newLoop(t, source, emitter, &fakeFanout{}, &fakeMode{}, []string{"r1"})

	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if stats.Retried != 1 {
		t.Errorf("Retried=%d want 1", stats.Retried)
	}
	got, ok := source.lastBatch().retried[uuidN(1)]
	if !ok {
		t.Fatal("expected retried entry for event 1")
	}
	if got.attempts != 1 {
		t.Errorf("attempts=%d want 1", got.attempts)
	}
	if got.lastErr == "" {
		t.Error("expected lastErr to be set")
	}
	if !got.next.After(time.Now()) {
		t.Errorf("next attempt %v should be after now", got.next)
	}
}

func TestRun_DeadLettersAtMaxAttempts(t *testing.T) {
	// Row with attempts = MaxAttempts - 1; next failure should dead-letter.
	p := retry.DefaultPolicy()
	row := newRow(1, p.MaxAttempts-1, false)
	source := newFakeSource("r1", []types.OutboxRow{row})
	emitter := &fakeEmitter{failEventIDs: map[uuid.UUID]bool{uuidN(1): true}}
	loop := newLoop(t, source, emitter, &fakeFanout{}, &fakeMode{}, []string{"r1"})

	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if stats.DeadLettered != 1 {
		t.Errorf("DeadLettered=%d want 1", stats.DeadLettered)
	}
	if len(source.lastBatch().deadLettered) != 1 {
		t.Errorf("expected 1 MarkDeadLetter call, got %d", len(source.lastBatch().deadLettered))
	}
}

func TestRun_SkipsWhenNotLeader(t *testing.T) {
	loop, _ := New(Config{
		Leader:    notLeader{},
		Source:    &fakeSource{},
		Emitter:   &fakeEmitter{},
		Fanout:    &fakeFanout{},
		Mode:      &fakeMode{},
		Policy:    retry.DefaultPolicy(),
		Realities: []string{"r1"},
	})
	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !stats.Skipped || stats.SkipReason != "not_leader" {
		t.Errorf("expected skipped=true reason=not_leader, got %+v", stats)
	}
}

type notLeader struct{}

func (notLeader) IsLeader() bool { return false }
func (notLeader) Step()          {}
func (notLeader) Stop()          {}

func TestRun_SkipsWhenDegraded(t *testing.T) {
	loop := newLoop(t, &fakeSource{}, &fakeEmitter{}, &fakeFanout{}, &fakeMode{m: lifecycle.ModeEssentials}, []string{"r1"})
	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !stats.Skipped {
		t.Error("expected skip when mode >= ModeEssentials")
	}
	if stats.SkipReason == "" {
		t.Error("expected non-empty SkipReason")
	}
}

func TestRun_XRealityFanoutInvokedAfterSuccess(t *testing.T) {
	rows := []types.OutboxRow{newRow(1, 0, true /*crossReality*/), newRow(2, 0, false)}
	source := newFakeSource("r1", rows)
	emitter := &fakeEmitter{}
	fanout := &fakeFanout{}
	loop := newLoop(t, source, emitter, fanout, &fakeMode{}, []string{"r1"})
	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if stats.FanoutOK != 1 {
		t.Errorf("FanoutOK=%d want 1", stats.FanoutOK)
	}
	if len(fanout.fanned) != 1 || fanout.fanned[0] != uuidN(1) {
		t.Errorf("only the cross_reality row should fan out, got %v", fanout.fanned)
	}
}

func TestRun_XRealityFanoutErrorIsNonFatal(t *testing.T) {
	row := newRow(1, 0, true)
	source := newFakeSource("r1", []types.OutboxRow{row})
	emitter := &fakeEmitter{}
	fanout := &fakeFanout{errOn: map[uuid.UUID]bool{uuidN(1): true}}
	loop := newLoop(t, source, emitter, fanout, &fakeMode{}, []string{"r1"})
	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatalf("fanout error must NOT abort the loop, got %v", err)
	}
	if stats.FanoutErr != 1 {
		t.Errorf("FanoutErr=%d want 1", stats.FanoutErr)
	}
	if len(source.lastBatch().published) != 1 {
		t.Error("main-stream MarkPublished should still have happened")
	}
}

func TestRun_LagDrainsAllRows_1000RowsCompleteInOneTick(t *testing.T) {
	// L2.D.10 scenario: 1000 outbox rows, single tick must drain all.
	rows := make([]types.OutboxRow, 1000)
	for i := 0; i < 1000; i++ {
		rows[i] = newRow(1, 0, false)
		rows[i].EventID = uuid.New()
	}
	source := newFakeSource("r1", rows)
	loop := newLoop(t, source, &fakeEmitter{}, &fakeFanout{}, &fakeMode{}, []string{"r1"})
	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if stats.Published != 1000 {
		t.Errorf("Published=%d want 1000 — single tick lag drain failed", stats.Published)
	}
}

// fatalBatch fails on MarkPublished so we can assert the reality batch is
// rolled back (not committed) on a state-write error.
type fatalSource struct {
	rows  []types.OutboxRow
	batch *fatalBatch
}

func (s *fatalSource) Begin(_ context.Context, _ string, _ int) (Batch, error) {
	s.batch = &fatalBatch{rows: s.rows}
	return s.batch, nil
}

type fatalBatch struct {
	rows       []types.OutboxRow
	committed  bool
	rolledBack bool
}

func (b *fatalBatch) Rows() []types.OutboxRow { return b.rows }
func (b *fatalBatch) MarkPublished(context.Context, string) error {
	return errors.New("simulated UPDATE failure")
}
func (b *fatalBatch) MarkRetry(context.Context, string, int, string, time.Time) error { return nil }
func (b *fatalBatch) MarkDeadLetter(context.Context, string, int, string) error       { return nil }
func (b *fatalBatch) Commit(context.Context) error                                    { b.committed = true; return nil }
func (b *fatalBatch) Rollback(context.Context) error                                  { b.rolledBack = true; return nil }

// isolationSource fails the named reality's batch on MarkPublished but drains
// the others normally — proves one bad reality doesn't starve the rest.
type isolationSource struct {
	failReality string
	rowsByReal  map[string][]types.OutboxRow
	good        map[string]*fakeBatch
}

func (s *isolationSource) Begin(_ context.Context, reality string, _ int) (Batch, error) {
	if reality == s.failReality {
		return &fatalBatch{rows: s.rowsByReal[reality]}, nil
	}
	b := newFakeBatch(s.rowsByReal[reality])
	if s.good == nil {
		s.good = map[string]*fakeBatch{}
	}
	s.good[reality] = b
	return b, nil
}

func TestRun_PerRealityIsolation_OneBadRealityDoesNotStarveOthers(t *testing.T) {
	src := &isolationSource{
		failReality: "r_bad",
		rowsByReal: map[string][]types.OutboxRow{
			"r_bad":  {newRow(1, 0, false)},
			"r_good": {newRow(2, 0, false), newRow(3, 0, false)},
		},
	}
	loop := newLoop(t, src, &fakeEmitter{}, &fakeFanout{}, &fakeMode{}, []string{"r_bad", "r_good"})
	stats, err := loop.Run(context.Background())
	if err == nil {
		t.Fatal("expected the bad reality to surface an error")
	}
	if stats.RealityErrors != 1 {
		t.Errorf("RealityErrors=%d want 1", stats.RealityErrors)
	}
	if stats.Published != 2 {
		t.Errorf("Published=%d want 2 — good reality must still drain", stats.Published)
	}
	if gb := src.good["r_good"]; gb == nil || !gb.committed {
		t.Error("good reality batch should have committed")
	}
}

func TestRun_StateWriteError_RollsBackAndReturns(t *testing.T) {
	source := &fatalSource{rows: []types.OutboxRow{newRow(1, 0, false)}}
	loop := newLoop(t, source, &fakeEmitter{}, &fakeFanout{}, &fakeMode{}, []string{"r1"})
	_, err := loop.Run(context.Background())
	if err == nil {
		t.Fatal("expected error from MarkPublished failure")
	}
	if !source.batch.rolledBack {
		t.Error("expected batch to be rolled back on Mark error")
	}
	if source.batch.committed {
		t.Error("batch must NOT commit after a Mark error")
	}
}
