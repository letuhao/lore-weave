//go:build integration

// L3.E acceptance test (cycle 15). End-to-end exercise of the
// integrity-checker daily-mode pipeline using in-memory fakes for the
// per-reality DB + the load_aggregate (cycle-12) reader.
//
// What this test pins:
//   1. Drift injected into a sampled aggregate is DETECTED by the
//      sampler→comparator→state_writer pipeline.
//   2. The aggregate's drift bubbles up to projection_drift_state via
//      state_writer (in-mem fake records the write, asserting shape).
//   3. Non-drifted aggregates do NOT inflate the drift_count (no false
//      positives within the sample).
//   4. The cross-package wiring (config → sampler/comparator/state_writer
//      → daily_loop) holds together in one assembled rig.
//
// Cycle 15 also ships the per-package unit tests inside each pkg/ tree;
// THIS integration test pins the assembly (since one of cycle-15's risks
// per the brief is "is the comparator REALLY using load_aggregate, not
// duplicated logic" — assembling all packages here catches accidental
// re-implementation).

package integration

import (
	"context"
	"math/rand"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/comparator"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/config"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/daily_loop"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/sampler"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/state_writer"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

func TestIntegrityChecker_DriftInjection_DetectedAndPersisted(t *testing.T) {
	cfg := config.Default()
	if err := cfg.Validate(); err != nil {
		t.Fatalf("default config invalid: %v", err)
	}

	clk := func() time.Time { return time.Unix(1700000000, 0).UTC() }
	rowSrc := sampler.NewInMemRowSource()
	smp, err := sampler.New(rowSrc, rand.New(rand.NewSource(11)))
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
	fetcher := daily_loop.NewInMemFetcher()
	loop, err := daily_loop.New(daily_loop.Config{
		Sampler:     smp,
		Comparator:  cmp,
		Fetcher:     fetcher,
		StateWriter: sw,
		Mode:        daily_loop.StaticMode{M: lifecycle.ModeFull},
		Clock:       clk,
	})
	if err != nil {
		t.Fatal(err)
	}

	// Build a per-reality population: 20 PC aggregates, of which 3 have
	// drift injected (projection diverges from replay).
	rid := uuid.New()
	driftAt := map[int]bool{4: true, 11: true, 17: true}
	for i := 0; i < 20; i++ {
		aggUUID := uuid.New()
		aggID := aggUUID.String()
		ver := uint64(i + 1)
		replayState := []byte(`{"value":42}`)
		projectionState := replayState
		if driftAt[i] {
			projectionState = []byte(`{"value":99}`)
		}
		rowSrc.AddRow(rid, "pc_projection", sampler.ProjectionRow{
			AggregateID: aggID, AggregateType: "pc",
			AggregateVersion: ver, EventID: uuid.New(),
			PayloadJSON: projectionState,
		})
		fetcher.AddRow(rid, "pc_projection", aggID, ver, projectionState)
		loader.AddState(rid, "pc", aggID, ver, replayState)
	}

	// Run only pc_projection (mirrors a real per-table sweep iteration).
	stats, err := loop.Run(context.Background(), rid, []types.TableConfig{
		{TableName: "pc_projection", SampleSize: 20},
	})
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if len(stats.Reports) != 1 {
		t.Fatalf("1 report expected, got %d", len(stats.Reports))
	}
	report := stats.Reports[0]

	if report.SampleSize != 20 {
		t.Errorf("SampleSize: got %d want 20", report.SampleSize)
	}
	if report.DriftCount != 3 {
		t.Errorf("DriftCount: got %d want 3 (we injected 3)", report.DriftCount)
	}
	if report.Skipped != 0 {
		t.Errorf("Skipped: got %d want 0 (no missing data)", report.Skipped)
	}
	if report.LastDriftedAggregateID == uuid.Nil {
		t.Error("LastDriftedAggregateID should be populated when drift > 0")
	}
	if string(report.CheckMode) != string(types.CheckModeDaily) {
		t.Errorf("CheckMode: got %q want %q", report.CheckMode, types.CheckModeDaily)
	}

	// State writer recorded the persist call with correct delay.
	if len(per.Calls) != 1 {
		t.Fatalf("1 state writer call expected, got %d", len(per.Calls))
	}
	wantDelay := 24 * time.Hour
	got := per.Calls[0].ExpectedNextSweepAt.Sub(time.Unix(1700000000, 0).UTC())
	if got != wantDelay {
		t.Errorf("ExpectedNextSweepAt delay: got %v want %v (daily cadence)", got, wantDelay)
	}
}

func TestIntegrityChecker_AllGreenSample_ZeroDrift(t *testing.T) {
	// No drift injected; the pipeline must report DriftCount=0.
	clk := func() time.Time { return time.Unix(1700000000, 0).UTC() }
	rowSrc := sampler.NewInMemRowSource()
	smp, _ := sampler.New(rowSrc, rand.New(rand.NewSource(99)))
	loader := comparator.NewInMemLoader()
	cmp, _ := comparator.New(comparator.Config{Loader: loader, Clock: clk})
	per := state_writer.NewInMemPersister()
	sw, _ := state_writer.New(state_writer.Config{Persister: per, Clock: clk})
	fetcher := daily_loop.NewInMemFetcher()
	loop, _ := daily_loop.New(daily_loop.Config{
		Sampler: smp, Comparator: cmp, Fetcher: fetcher, StateWriter: sw,
		Mode: daily_loop.StaticMode{M: lifecycle.ModeFull}, Clock: clk,
	})

	rid := uuid.New()
	for i := 0; i < 10; i++ {
		aggID := uuid.New().String()
		ver := uint64(i + 1)
		state := []byte(`{"value":42}`)
		rowSrc.AddRow(rid, "npc_projection", sampler.ProjectionRow{
			AggregateID: aggID, AggregateType: "npc",
			AggregateVersion: ver, EventID: uuid.New(), PayloadJSON: state,
		})
		fetcher.AddRow(rid, "npc_projection", aggID, ver, state)
		loader.AddState(rid, "npc", aggID, ver, state)
	}

	stats, _ := loop.Run(context.Background(), rid, []types.TableConfig{
		{TableName: "npc_projection", SampleSize: 10},
	})
	if stats.Reports[0].DriftCount != 0 {
		t.Errorf("DriftCount: got %d want 0 (no false positives)", stats.Reports[0].DriftCount)
	}
}
