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

type fakeFetcher struct {
	byReality map[string][][]types.OutboxRow // pop one batch per call
}

func (f *fakeFetcher) FetchPending(_ context.Context, reality string, _ int) ([]types.OutboxRow, error) {
	batches := f.byReality[reality]
	if len(batches) == 0 {
		return nil, nil
	}
	out := batches[0]
	f.byReality[reality] = batches[1:]
	return out, nil
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

type fakeStateW struct {
	published    []uuid.UUID
	retried      map[uuid.UUID]struct {
		attempts int
		lastErr  string
		next     time.Time
	}
	deadLettered []uuid.UUID
}

func newFakeStateW() *fakeStateW {
	return &fakeStateW{retried: map[uuid.UUID]struct {
		attempts int
		lastErr  string
		next     time.Time
	}{}}
}

func (s *fakeStateW) MarkPublished(_ context.Context, eid string) error {
	u, _ := uuid.Parse(eid)
	s.published = append(s.published, u)
	return nil
}

func (s *fakeStateW) MarkRetry(_ context.Context, eid string, attempts int, lastErr string, next time.Time) error {
	u, _ := uuid.Parse(eid)
	s.retried[u] = struct {
		attempts int
		lastErr  string
		next     time.Time
	}{attempts, lastErr, next}
	return nil
}

func (s *fakeStateW) MarkDeadLetter(_ context.Context, eid string, _ int, _ string) error {
	u, _ := uuid.Parse(eid)
	s.deadLettered = append(s.deadLettered, u)
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

func newLoop(t *testing.T, fetcher Fetcher, emitter Emitter, fanout XRealityFanout, stateW StateWriter, mode ModeReader, realities []string) *Loop {
	t.Helper()
	loop, err := New(Config{
		Leader:    leader_election.NewNoOp(),
		Fetcher:   fetcher,
		Emitter:   emitter,
		Fanout:    fanout,
		StateW:    stateW,
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
		Leader: leader_election.NewNoOp(),
		Fetcher: &fakeFetcher{},
		Emitter: &fakeEmitter{},
		Fanout: &fakeFanout{},
		StateW: newFakeStateW(),
		Mode: &fakeMode{},
		Policy: retry.DefaultPolicy(),
	}
	tests := []func(c *Config){
		func(c *Config) { c.Leader = nil },
		func(c *Config) { c.Fetcher = nil },
		func(c *Config) { c.Emitter = nil },
		func(c *Config) { c.Fanout = nil },
		func(c *Config) { c.StateW = nil },
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
	fetcher := &fakeFetcher{byReality: map[string][][]types.OutboxRow{"reality_A": {rows}}}
	emitter := &fakeEmitter{}
	fanout := &fakeFanout{}
	stateW := newFakeStateW()
	mode := &fakeMode{m: lifecycle.ModeFull}
	loop := newLoop(t, fetcher, emitter, fanout, stateW, mode, []string{"reality_A"})

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
	if len(stateW.published) != 2 {
		t.Errorf("expected 2 MarkPublished calls, got %d", len(stateW.published))
	}
}

func TestRun_TransientFailureRetries(t *testing.T) {
	rows := []types.OutboxRow{newRow(1, 0, false)}
	fetcher := &fakeFetcher{byReality: map[string][][]types.OutboxRow{"r1": {rows}}}
	emitter := &fakeEmitter{failEventIDs: map[uuid.UUID]bool{uuidN(1): true}}
	stateW := newFakeStateW()
	loop := newLoop(t, fetcher, emitter, &fakeFanout{}, stateW, &fakeMode{}, []string{"r1"})

	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if stats.Retried != 1 {
		t.Errorf("Retried=%d want 1", stats.Retried)
	}
	got, ok := stateW.retried[uuidN(1)]
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
	fetcher := &fakeFetcher{byReality: map[string][][]types.OutboxRow{"r1": {{row}}}}
	emitter := &fakeEmitter{failEventIDs: map[uuid.UUID]bool{uuidN(1): true}}
	stateW := newFakeStateW()
	loop := newLoop(t, fetcher, emitter, &fakeFanout{}, stateW, &fakeMode{}, []string{"r1"})

	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if stats.DeadLettered != 1 {
		t.Errorf("DeadLettered=%d want 1", stats.DeadLettered)
	}
	if len(stateW.deadLettered) != 1 {
		t.Errorf("expected 1 MarkDeadLetter call, got %d", len(stateW.deadLettered))
	}
}

func TestRun_SkipsWhenNotLeader(t *testing.T) {
	loop, _ := New(Config{
		Leader:    notLeader{},
		Fetcher:   &fakeFetcher{},
		Emitter:   &fakeEmitter{},
		Fanout:    &fakeFanout{},
		StateW:    newFakeStateW(),
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
	loop := newLoop(t, &fakeFetcher{}, &fakeEmitter{}, &fakeFanout{}, newFakeStateW(), &fakeMode{m: lifecycle.ModeEssentials}, []string{"r1"})
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
	fetcher := &fakeFetcher{byReality: map[string][][]types.OutboxRow{"r1": {rows}}}
	emitter := &fakeEmitter{}
	fanout := &fakeFanout{}
	loop := newLoop(t, fetcher, emitter, fanout, newFakeStateW(), &fakeMode{}, []string{"r1"})
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
	fetcher := &fakeFetcher{byReality: map[string][][]types.OutboxRow{"r1": {{row}}}}
	emitter := &fakeEmitter{}
	fanout := &fakeFanout{errOn: map[uuid.UUID]bool{uuidN(1): true}}
	stateW := newFakeStateW()
	loop := newLoop(t, fetcher, emitter, fanout, stateW, &fakeMode{}, []string{"r1"})
	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatalf("fanout error must NOT abort the loop, got %v", err)
	}
	if stats.FanoutErr != 1 {
		t.Errorf("FanoutErr=%d want 1", stats.FanoutErr)
	}
	if len(stateW.published) != 1 {
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
	fetcher := &fakeFetcher{byReality: map[string][][]types.OutboxRow{"r1": {rows}}}
	stateW := newFakeStateW()
	loop := newLoop(t, fetcher, &fakeEmitter{}, &fakeFanout{}, stateW, &fakeMode{}, []string{"r1"})
	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if stats.Published != 1000 {
		t.Errorf("Published=%d want 1000 — single tick lag drain failed", stats.Published)
	}
}
