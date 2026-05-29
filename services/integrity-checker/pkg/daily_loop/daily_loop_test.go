package daily_loop

import (
	"context"
	"math/rand"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/comparator"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/sampler"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/state_writer"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

func frozen(t time.Time) func() time.Time { return func() time.Time { return t } }

// rig wires up sampler+comparator+fetcher+state-writer with all in-mem fakes.
type rig struct {
	loop      *Loop
	rowSrc    *sampler.InMemRowSource
	loader    *comparator.InMemLoader
	fetcher   *InMemFetcher
	persister *state_writer.InMemPersister
}

func newRig(t *testing.T, m lifecycle.ServiceMode) *rig {
	t.Helper()
	clk := frozen(time.Unix(1700000000, 0).UTC())
	src := sampler.NewInMemRowSource()
	smp, err := sampler.New(src, rand.New(rand.NewSource(7)))
	if err != nil {
		t.Fatal(err)
	}
	loader := comparator.NewInMemLoader()
	cmp, err := comparator.New(comparator.Config{Loader: loader, Clock: clk})
	if err != nil {
		t.Fatal(err)
	}
	per := state_writer.NewInMemPersister()
	sw, err := state_writer.New(state_writer.Config{Persister: per, Clock: clk})
	if err != nil {
		t.Fatal(err)
	}
	f := NewInMemFetcher()
	loop, err := New(Config{Sampler: smp, Comparator: cmp, Fetcher: f, StateWriter: sw, Mode: StaticMode{M: m}, Clock: clk})
	if err != nil {
		t.Fatal(err)
	}
	return &rig{loop: loop, rowSrc: src, loader: loader, fetcher: f, persister: per}
}

func TestRun_DegradedMode_Skips(t *testing.T) {
	r := newRig(t, lifecycle.ModeEssentials)
	stats, err := r.loop.Run(context.Background(), uuid.New(), []types.TableConfig{
		{TableName: "pc_projection", SampleSize: 20},
	})
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if !stats.Skipped {
		t.Error("expected SKIPPED at ModeEssentials")
	}
	if len(r.persister.Calls) != 0 {
		t.Error("no DB writes expected in degraded mode")
	}
}

func TestRun_AllSamplesMatch_ZeroDrift(t *testing.T) {
	r := newRig(t, lifecycle.ModeFull)
	rid := uuid.New()
	// Seed 5 rows; replay matches all.
	for i := 0; i < 5; i++ {
		aggID := "pc-" + string(rune('a'+i))
		ver := uint64(i + 1)
		payload := []byte(`{"v":42}`)
		r.rowSrc.AddRow(rid, "pc_projection", sampler.ProjectionRow{
			AggregateID: aggID, AggregateType: "pc", AggregateVersion: ver,
			EventID: uuid.New(), PayloadJSON: payload,
		})
		r.fetcher.AddRow(rid, "pc_projection", aggID, ver, payload)
		r.loader.AddState(rid, "pc", aggID, ver, payload)
	}

	stats, err := r.loop.Run(context.Background(), rid, []types.TableConfig{
		{TableName: "pc_projection", SampleSize: 5},
	})
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if len(stats.Reports) != 1 {
		t.Fatalf("1 report expected, got %d", len(stats.Reports))
	}
	r0 := stats.Reports[0]
	if r0.DriftCount != 0 {
		t.Errorf("expected 0 drift, got %d", r0.DriftCount)
	}
	if r0.SampleSize != 5 {
		t.Errorf("expected SampleSize=5, got %d", r0.SampleSize)
	}
}

// THE acceptance test from the brief: inject drift; sampler+comparator
// detects + drift_count > 0 + state_writer persists.
func TestRun_InjectedDrift_DetectedAndPersisted(t *testing.T) {
	r := newRig(t, lifecycle.ModeFull)
	rid := uuid.New()
	// Seed 5 rows where row #2's projection payload diverges from replay.
	for i := 0; i < 5; i++ {
		aggUUID := uuid.New()
		aggID := aggUUID.String()
		ver := uint64(i + 1)
		good := []byte(`{"v":42}`)
		bad := []byte(`{"v":99}`)
		projectionPayload := good
		replayPayload := good
		if i == 2 {
			// drift injection: replay would have produced {v:42}, but
			// the projection row holds {v:99} — a real divergence.
			projectionPayload = bad
		}
		r.rowSrc.AddRow(rid, "pc_projection", sampler.ProjectionRow{
			AggregateID: aggID, AggregateType: "pc", AggregateVersion: ver,
			EventID: uuid.New(), PayloadJSON: projectionPayload,
		})
		r.fetcher.AddRow(rid, "pc_projection", aggID, ver, projectionPayload)
		r.loader.AddState(rid, "pc", aggID, ver, replayPayload)
	}

	stats, err := r.loop.Run(context.Background(), rid, []types.TableConfig{
		{TableName: "pc_projection", SampleSize: 5},
	})
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if stats.Reports[0].DriftCount != 1 {
		t.Errorf("expected DriftCount=1 (1 injection), got %d", stats.Reports[0].DriftCount)
	}
	if stats.Reports[0].LastDriftedAggregateID == uuid.Nil {
		t.Error("LastDriftedAggregateID should be set on drift")
	}
	if len(r.persister.Calls) != 1 {
		t.Fatalf("1 state-writer call expected, got %d", len(r.persister.Calls))
	}
	if r.persister.Calls[0].Report.DriftCount != 1 {
		t.Errorf("state_writer call should carry DriftCount=1, got %d", r.persister.Calls[0].Report.DriftCount)
	}
	// 24h next-sweep delay for daily mode.
	if got := r.persister.Calls[0].ExpectedNextSweepAt.Sub(time.Unix(1700000000, 0).UTC()); got != 24*time.Hour {
		t.Errorf("expected 24h delay, got %v", got)
	}
}

func TestRun_FetcherMiss_CountsAsSkippedNotDrift(t *testing.T) {
	r := newRig(t, lifecycle.ModeFull)
	rid := uuid.New()
	aggID := uuid.New().String()
	ver := uint64(1)
	r.rowSrc.AddRow(rid, "pc_projection", sampler.ProjectionRow{
		AggregateID: aggID, AggregateType: "pc", AggregateVersion: ver,
		EventID: uuid.New(), PayloadJSON: []byte(`{"v":42}`),
	})
	// NOTE: no fetcher row → FetchPayload returns "not found".
	// loader still has a valid replay state (so we can prove the SKIP is
	// the fetcher miss, not a load error).
	r.loader.AddState(rid, "pc", aggID, ver, []byte(`{"v":42}`))

	stats, _ := r.loop.Run(context.Background(), rid, []types.TableConfig{
		{TableName: "pc_projection", SampleSize: 1},
	})
	if stats.Reports[0].Skipped != 1 {
		t.Errorf("expected Skipped=1, got %d", stats.Reports[0].Skipped)
	}
	if stats.Reports[0].DriftCount != 0 {
		t.Errorf("fetcher miss MUST NOT count as drift; got DriftCount=%d", stats.Reports[0].DriftCount)
	}
}

func TestRun_AllTablesScanned(t *testing.T) {
	r := newRig(t, lifecycle.ModeFull)
	rid := uuid.New()
	tbls := []types.TableConfig{
		{TableName: "pc_projection", SampleSize: 5},
		{TableName: "npc_projection", SampleSize: 5},
		{TableName: "region_projection", SampleSize: 5},
	}
	// No rows seeded for any table → all reports have SampleSize=0.
	stats, err := r.loop.Run(context.Background(), rid, tbls)
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if len(stats.Reports) != 3 {
		t.Errorf("expected 3 reports (one per table), got %d", len(stats.Reports))
	}
	for i, rep := range stats.Reports {
		if rep.TableName != tbls[i].TableName {
			t.Errorf("report[%d].TableName=%s, want %s", i, rep.TableName, tbls[i].TableName)
		}
	}
}

func TestRun_RecordsDurationSeconds(t *testing.T) {
	// Variable clock — first call = start, second call = end.
	ticks := []time.Time{
		time.Unix(1700000000, 0).UTC(),
		time.Unix(1700000003, 500_000_000).UTC(), // +3.5s
	}
	i := 0
	clk := func() time.Time {
		if i >= len(ticks) {
			return ticks[len(ticks)-1]
		}
		v := ticks[i]
		i++
		return v
	}
	src := sampler.NewInMemRowSource()
	smp, _ := sampler.New(src, rand.New(rand.NewSource(1)))
	loader := comparator.NewInMemLoader()
	cmp, _ := comparator.New(comparator.Config{Loader: loader, Clock: frozen(time.Unix(1700000000, 0))})
	per := state_writer.NewInMemPersister()
	sw, _ := state_writer.New(state_writer.Config{Persister: per, Clock: clk})
	f := NewInMemFetcher()
	loop, _ := New(Config{Sampler: smp, Comparator: cmp, Fetcher: f, StateWriter: sw, Mode: StaticMode{M: lifecycle.ModeFull}, Clock: clk})

	stats, err := loop.Run(context.Background(), uuid.New(), []types.TableConfig{
		{TableName: "pc_projection", SampleSize: 1},
	})
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if got := stats.Reports[0].DurationSeconds; got != 3.5 {
		t.Errorf("DurationSeconds: got %v want 3.5", got)
	}
}
