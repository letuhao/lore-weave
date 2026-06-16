package live

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/metrics"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/replayloader"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/state_writer"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/tablemap"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

// ── fakes ──────────────────────────────────────────────────────────────────

type staticMode struct{ m lifecycle.ServiceMode }

func (s staticMode) Mode() lifecycle.ServiceMode { return s.m }

type fakeSampler struct {
	rows []SampledRow
	err  error
}

func (f *fakeSampler) SampleRows(_ context.Context, _ uuid.UUID, _ /*dsn*/ string, _ /*table*/ string, _ int) ([]SampledRow, error) {
	return f.rows, f.err
}

type fakeReplayer struct {
	fn func(req replayloader.ReplayRequest) (replayloader.ReplayResult, error)
}

func (f *fakeReplayer) Replay(_ context.Context, req replayloader.ReplayRequest) (replayloader.ReplayResult, error) {
	return f.fn(req)
}

func fixedClock() func() time.Time {
	base := time.Date(2026, 6, 3, 12, 0, 0, 0, time.UTC)
	n := 0
	return func() time.Time { n++; return base.Add(time.Duration(n) * time.Second) }
}

func newChecker(t *testing.T, s RowSampler, r Replayer, mode lifecycle.ServiceMode) (*Checker, *state_writer.InMemPersister) {
	t.Helper()
	per := state_writer.NewInMemPersister()
	w, err := state_writer.New(state_writer.Config{Persister: per, Clock: time.Now})
	if err != nil {
		t.Fatal(err)
	}
	c, err := NewChecker(Config{Sampler: s, Replayer: r, Writer: w, Mode: staticMode{mode}, Clock: fixedClock()})
	if err != nil {
		t.Fatal(err)
	}
	return c, per
}

func uid(n byte) uuid.UUID {
	var u uuid.UUID
	u[15] = n
	return u
}

func pcRow(pcID string, payload string, ev byte) SampledRow {
	return SampledRow{
		PK:               map[string]string{"pc_id": pcID},
		EventID:          uid(ev),
		AggregateVersion: 3,
		Payload:          []byte(payload),
		Owning:           []tablemap.OwningAggregate{{Type: "pc", ID: pcID}},
	}
}

// ── ResolveOwning ───────────────────────────────────────────────────────────

func TestResolveOwning_SingleAggregateUsesEventLookup(t *testing.T) {
	called := false
	lookup := func(_ context.Context, ev uuid.UUID) (string, string, error) {
		called = true
		return "pc", "pc-7", nil
	}
	owners, err := ResolveOwning(context.Background(), "pc_projection", map[string]string{"pc_id": "pc-7"}, uid(1), lookup)
	if err != nil {
		t.Fatal(err)
	}
	if !called {
		t.Error("single-aggregate must call the event lookup")
	}
	if len(owners) != 1 || owners[0] != (tablemap.OwningAggregate{Type: "pc", ID: "pc-7"}) {
		t.Errorf("owners = %+v", owners)
	}
}

func TestResolveOwning_CrossAggregateDerivesFromPKWithoutLookup(t *testing.T) {
	owners, err := ResolveOwning(
		context.Background(),
		"npc_session_memory_projection",
		map[string]string{"npc_id": "n-1", "session_id": "s-2"},
		uid(1),
		nil, // lookup MUST NOT be needed for cross-aggregate
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(owners) != 2 {
		t.Fatalf("owners = %+v", owners)
	}
}

func TestResolveOwning_Errors(t *testing.T) {
	if _, err := ResolveOwning(context.Background(), "not_a_table", nil, uid(1), nil); err == nil {
		t.Error("unknown table must error")
	}
	if _, err := ResolveOwning(context.Background(), "pc_projection", nil, uid(1), nil); err == nil {
		t.Error("single-aggregate with nil lookup must error")
	}
	failing := func(_ context.Context, _ uuid.UUID) (string, string, error) { return "", "", errors.New("db down") }
	if _, err := ResolveOwning(context.Background(), "pc_projection", nil, uid(1), failing); err == nil {
		t.Error("lookup error must propagate")
	}
	empty := func(_ context.Context, _ uuid.UUID) (string, string, error) { return "", "", nil }
	if _, err := ResolveOwning(context.Background(), "pc_projection", nil, uid(1), empty); err == nil {
		t.Error("empty owner must error")
	}
}

// ── CheckTable verdicts ─────────────────────────────────────────────────────

func TestCheckTable_CleanWhenReplayMatches(t *testing.T) {
	// Replay returns the SAME payload (different key order → canonicalize equal).
	s := &fakeSampler{rows: []SampledRow{pcRow("pc-1", `{"a":1,"b":2}`, 0xa1)}}
	r := &fakeReplayer{fn: func(_ replayloader.ReplayRequest) (replayloader.ReplayResult, error) {
		return replayloader.ReplayResult{Found: true, EventsReplayed: 5, Status: "ok", Payload: []byte(`{"b":2,"a":1}`)}, nil
	}}
	c, per := newChecker(t, s, r, lifecycle.ModeFull)
	rep, err := c.CheckTable(context.Background(), uid(9), "dsn", types.TableConfig{TableName: "pc_projection", SampleSize: 20})
	if err != nil {
		t.Fatal(err)
	}
	if rep.DriftCount != 0 || rep.Skipped != 0 || rep.SampleSize != 1 {
		t.Errorf("report = %+v", rep)
	}
	if len(per.Calls) != 1 {
		t.Fatalf("expected 1 persist, got %d", len(per.Calls))
	}
}

func TestCheckTable_DriftWhenReplayDiffers(t *testing.T) {
	s := &fakeSampler{rows: []SampledRow{pcRow("pc-1", `{"name":"Aria"}`, 0xb2)}}
	r := &fakeReplayer{fn: func(_ replayloader.ReplayRequest) (replayloader.ReplayResult, error) {
		return replayloader.ReplayResult{Found: true, EventsReplayed: 5, Status: "ok", Payload: []byte(`{"name":"Bria"}`)}, nil
	}}
	c, per := newChecker(t, s, r, lifecycle.ModeFull)
	rep, _ := c.CheckTable(context.Background(), uid(9), "dsn", types.TableConfig{TableName: "pc_projection", SampleSize: 20})
	if rep.DriftCount != 1 {
		t.Fatalf("expected 1 drift, got %+v", rep)
	}
	if rep.LastDriftedEventID != uid(0xb2) {
		t.Errorf("last drifted event = %v", rep.LastDriftedEventID)
	}
	if rep.LastDriftedAggregateID == uuid.Nil {
		t.Error("drift must set a non-nil aggregate id (state_writer CHECK)")
	}
	if len(per.Calls) != 1 {
		t.Errorf("expected persist even on drift")
	}
}

func TestCheckTable_OrphanRowIsDrift(t *testing.T) {
	// Replay ran (events>0) but produced NO row at the PK → orphan drift.
	s := &fakeSampler{rows: []SampledRow{pcRow("pc-1", `{"x":1}`, 0xc3)}}
	r := &fakeReplayer{fn: func(_ replayloader.ReplayRequest) (replayloader.ReplayResult, error) {
		return replayloader.ReplayResult{Found: false, EventsReplayed: 4, Status: "ok"}, nil
	}}
	c, _ := newChecker(t, s, r, lifecycle.ModeFull)
	rep, _ := c.CheckTable(context.Background(), uid(9), "dsn", types.TableConfig{TableName: "pc_projection", SampleSize: 20})
	if rep.DriftCount != 1 {
		t.Fatalf("orphan row must be a drift: %+v", rep)
	}
}

func TestCheckTable_SkipCases(t *testing.T) {
	cases := []struct {
		name string
		res  replayloader.ReplayResult
		err  error
	}{
		{"zero events", replayloader.ReplayResult{Found: false, EventsReplayed: 0, Status: "ok"}, nil},
		{"replay error", replayloader.ReplayResult{Status: "error", Error: "boom"}, nil},
		{"hard run error", replayloader.ReplayResult{}, errors.New("exit 2")},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			s := &fakeSampler{rows: []SampledRow{pcRow("pc-1", `{"x":1}`, 0xd4)}}
			r := &fakeReplayer{fn: func(_ replayloader.ReplayRequest) (replayloader.ReplayResult, error) {
				return tc.res, tc.err
			}}
			c, _ := newChecker(t, s, r, lifecycle.ModeFull)
			rep, err := c.CheckTable(context.Background(), uid(9), "dsn", types.TableConfig{TableName: "pc_projection", SampleSize: 20})
			if err != nil {
				t.Fatal(err)
			}
			if rep.Skipped != 1 || rep.DriftCount != 0 {
				t.Errorf("expected 1 skip 0 drift, got %+v", rep)
			}
		})
	}
}

func TestCheckTable_PassesBoundaryAndOwningToReplayer(t *testing.T) {
	s := &fakeSampler{rows: []SampledRow{{
		PK:      map[string]string{"npc_id": "n-3", "session_id": "s-9"},
		EventID: uid(0xe5),
		Payload: []byte(`{}`),
		Owning:  []tablemap.OwningAggregate{{Type: "session", ID: "s-9"}, {Type: "npc", ID: "n-3"}},
	}}}
	var got replayloader.ReplayRequest
	r := &fakeReplayer{fn: func(req replayloader.ReplayRequest) (replayloader.ReplayResult, error) {
		got = req
		return replayloader.ReplayResult{Found: true, EventsReplayed: 1, Status: "ok", Payload: []byte(`{}`)}, nil
	}}
	c, _ := newChecker(t, s, r, lifecycle.ModeFull)
	if _, err := c.CheckTable(context.Background(), uid(9), "the-dsn", types.TableConfig{TableName: "npc_session_memory_projection", SampleSize: 5}); err != nil {
		t.Fatal(err)
	}
	if got.BoundaryEventID != uid(0xe5) || got.DSN != "the-dsn" || got.Projection != "npc_session_memory_projection" {
		t.Errorf("request not threaded: %+v", got)
	}
	if len(got.Owning) != 2 {
		t.Errorf("owning not threaded: %+v", got.Owning)
	}
}

// ── Run / degraded-mode ─────────────────────────────────────────────────────

func TestRun_SkipsEntirelyInDegradedMode(t *testing.T) {
	s := &fakeSampler{rows: []SampledRow{pcRow("pc-1", `{}`, 1)}}
	r := &fakeReplayer{fn: func(_ replayloader.ReplayRequest) (replayloader.ReplayResult, error) {
		t.Fatal("replayer must NOT run in degraded mode")
		return replayloader.ReplayResult{}, nil
	}}
	c, per := newChecker(t, s, r, lifecycle.ModeEssentials)
	it, err := c.Run(context.Background(), uid(9), "dsn", []types.TableConfig{{TableName: "pc_projection", SampleSize: 20}})
	if err != nil {
		t.Fatal(err)
	}
	if !it.Skipped || len(it.Reports) != 0 {
		t.Errorf("degraded run must skip: %+v", it)
	}
	if len(per.Calls) != 0 {
		t.Error("degraded run must not persist")
	}
}

func TestRun_ChecksEachTable(t *testing.T) {
	s := &fakeSampler{rows: []SampledRow{pcRow("pc-1", `{"a":1}`, 1)}}
	r := &fakeReplayer{fn: func(_ replayloader.ReplayRequest) (replayloader.ReplayResult, error) {
		return replayloader.ReplayResult{Found: true, EventsReplayed: 2, Status: "ok", Payload: []byte(`{"a":1}`)}, nil
	}}
	c, per := newChecker(t, s, r, lifecycle.ModeFull)
	it, err := c.Run(context.Background(), uid(9), "dsn", []types.TableConfig{
		{TableName: "pc_projection", SampleSize: 20},
		{TableName: "npc_projection", SampleSize: 20},
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(it.Reports) != 2 || len(per.Calls) != 2 {
		t.Errorf("expected 2 table reports + 2 persists, got %d/%d", len(it.Reports), len(per.Calls))
	}
}

func TestDriftAggregateUUID_FallsBackToEventForNonUUIDOwner(t *testing.T) {
	// world_kv's owner id is not a UUID → fall back to the event_id.
	row := SampledRow{EventID: uid(0xf6), Owning: []tablemap.OwningAggregate{{Type: "world", ID: "the-world"}}}
	if driftAggregateUUID(row) != uid(0xf6) {
		t.Error("non-UUID owner must fall back to event_id")
	}
	// pc's owner id IS a uuid → use it.
	owner := uid(0x42)
	row2 := SampledRow{EventID: uid(0xf6), Owning: []tablemap.OwningAggregate{{Type: "pc", ID: owner.String()}}}
	if driftAggregateUUID(row2) != owner {
		t.Error("uuid owner must be used directly")
	}
}

// ── ErrOwnerPruned skip path (MED-1: monthly full-scan over archived rows) ───

func TestResolveOwning_PrunedOwnerReturnsBareSentinel(t *testing.T) {
	lookup := func(_ context.Context, _ uuid.UUID) (string, string, error) {
		return "", "", fmt.Errorf("pgsource: no event for event_id x: %w", ErrOwnerPruned)
	}
	owners, err := ResolveOwning(context.Background(), "pc_projection",
		map[string]string{"pc_id": "pc-1"}, uid(1), lookup)
	if !errors.Is(err, ErrOwnerPruned) {
		t.Fatalf("pruned owner must propagate ErrOwnerPruned, got %v", err)
	}
	if owners != nil {
		t.Errorf("pruned owner must yield nil owners, got %v", owners)
	}
}

func TestCheckRow_NilOwningSkipsWithoutReplay(t *testing.T) {
	called := false
	rep := &fakeReplayer{fn: func(replayloader.ReplayRequest) (replayloader.ReplayResult, error) {
		called = true
		return replayloader.ReplayResult{}, nil
	}}
	drifted, skipped := CheckRow(context.Background(), rep, uid(1), "dsn", "pc_projection",
		SampledRow{PK: map[string]string{"pc_id": "pc-1"}, EventID: uid(2), Owning: nil})
	if drifted || !skipped {
		t.Errorf("nil-Owning (pruned) row must SKIP, not drift: drifted=%v skipped=%v", drifted, skipped)
	}
	if called {
		t.Error("replayer must NOT be invoked for a nil-Owning row (the bin requires >=1 aggregate)")
	}
}

// ── lag gauge (153): emitted only when the sampler implements LagReader ──────

type lagSampler struct {
	fakeSampler
	lag float64
	ok  bool
}

func (s *lagSampler) TableLagSeconds(_ context.Context, _ string) (float64, bool, error) {
	return s.lag, s.ok, nil
}

func TestCheckTable_EmitsLagWhenSamplerSupportsIt(t *testing.T) {
	s := &lagSampler{
		fakeSampler: fakeSampler{rows: []SampledRow{pcRow("pc-1", `{"a":1}`, 0xe5)}},
		lag:         42.0, ok: true,
	}
	r := &fakeReplayer{fn: func(_ replayloader.ReplayRequest) (replayloader.ReplayResult, error) {
		return replayloader.ReplayResult{Found: true, EventsReplayed: 1, Status: "ok", Payload: []byte(`{"a":1}`)}, nil
	}}
	per := state_writer.NewInMemPersister()
	w, _ := state_writer.New(state_writer.Config{Persister: per, Clock: time.Now})
	em := metrics.NewInMemEmitter()
	c, err := NewChecker(Config{
		Sampler: s, Replayer: r, Writer: w,
		Mode: staticMode{lifecycle.ModeFull}, Clock: fixedClock(), Emitter: em,
	})
	if err != nil {
		t.Fatal(err)
	}
	rid := uid(9)
	it, err := c.Run(context.Background(), rid, "dsn",
		[]types.TableConfig{{TableName: "pc_projection", SampleSize: 20}})
	if err != nil {
		t.Fatal(err)
	}
	if !it.Reports[0].HasLag || it.Reports[0].LagSeconds != 42.0 {
		t.Errorf("report lag: HasLag=%v lag=%v", it.Reports[0].HasLag, it.Reports[0].LagSeconds)
	}
	if got := em.Lag[rid.String()+"|pc_projection"]; got != 42.0 {
		t.Errorf("emitted lag = %v, want 42.0 (emitter map=%v)", got, em.Lag)
	}
}

func TestCheckTable_LagAbsentWhenSamplerLacksLagReader(t *testing.T) {
	// The plain fakeSampler does NOT implement LagReader → no lag reported.
	s := &fakeSampler{rows: []SampledRow{pcRow("pc-1", `{"a":1}`, 0xe6)}}
	r := &fakeReplayer{fn: func(_ replayloader.ReplayRequest) (replayloader.ReplayResult, error) {
		return replayloader.ReplayResult{Found: true, EventsReplayed: 1, Status: "ok", Payload: []byte(`{"a":1}`)}, nil
	}}
	c, _ := newChecker(t, s, r, lifecycle.ModeFull)
	rep, err := c.CheckTable(context.Background(), uid(9), "dsn",
		types.TableConfig{TableName: "pc_projection", SampleSize: 20})
	if err != nil {
		t.Fatal(err)
	}
	if rep.HasLag {
		t.Error("a sampler without LagReader must leave HasLag=false")
	}
}

func TestCheckTable_LagOmittedWhenTableEmpty(t *testing.T) {
	// LagReader reports ok=false (empty table) → no lag on the report.
	s := &lagSampler{
		fakeSampler: fakeSampler{rows: []SampledRow{pcRow("pc-1", `{"a":1}`, 0xe7)}},
		lag:         0, ok: false,
	}
	r := &fakeReplayer{fn: func(_ replayloader.ReplayRequest) (replayloader.ReplayResult, error) {
		return replayloader.ReplayResult{Found: true, EventsReplayed: 1, Status: "ok", Payload: []byte(`{"a":1}`)}, nil
	}}
	c, _ := newChecker(t, s, r, lifecycle.ModeFull)
	rep, _ := c.CheckTable(context.Background(), uid(9), "dsn",
		types.TableConfig{TableName: "pc_projection", SampleSize: 20})
	if rep.HasLag {
		t.Error("ok=false (empty table) must leave HasLag=false")
	}
}
