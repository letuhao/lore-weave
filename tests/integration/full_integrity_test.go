//go:build integration

// L3.F acceptance test (cycle 15). End-to-end exercise of the
// integrity-checker monthly-mode pipeline using in-memory fakes.
//
// What this test pins:
//   1. Monthly full check walks ALL aggregates (not a sample).
//   2. Drift injected at 10 different positions in a 100-aggregate
//      population is detected by the full scan (not the daily sampler's
//      "miss because not sampled" failure mode).
//   3. Cursor batching iterates the whole table without infinite loops
//      and without skipping rows.
//   4. The monthly state_writer uses a multi-day delay
//      (FullCheckIntervalDays * 24h) instead of the daily 24h delay.

package integration

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/comparator"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/full_check"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/sampler"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/state_writer"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

func TestFullIntegrityCheck_AllDriftDetectedAcrossFullScan(t *testing.T) {
	clk := func() time.Time { return time.Unix(1700000000, 0).UTC() }
	src := full_check.NewInMemCursorSource()
	loader := comparator.NewInMemLoader()
	cmp, _ := comparator.New(comparator.Config{Loader: loader, Clock: clk})
	per := state_writer.NewInMemPersister()
	sw, _ := state_writer.New(state_writer.Config{Persister: per, Clock: clk})
	fetcher := full_check.NewInMemFetcher()
	loop, err := full_check.New(full_check.Config{
		CursorSource:          src,
		Comparator:            cmp,
		Fetcher:               fetcher,
		StateWriter:           sw,
		Mode:                  full_check.StaticMode{M: lifecycle.ModeFull},
		Clock:                 clk,
		FullCheckIntervalDays: 30,
	})
	if err != nil {
		t.Fatal(err)
	}

	rid := uuid.New()
	// 100 aggregates, 10 of which have drift (synthetic 10% bug rate).
	driftAt := map[int]bool{
		3: true, 17: true, 22: true, 29: true, 41: true,
		50: true, 67: true, 75: true, 88: true, 99: true,
	}
	driftedIDs := make(map[string]bool)
	for i := 0; i < 100; i++ {
		aggUUID := uuid.New()
		aggID := aggUUID.String()
		ver := uint64(i + 1)
		replayState := []byte(`{"v":42}`)
		projState := replayState
		if driftAt[i] {
			projState = []byte(`{"v":99}`)
			driftedIDs[aggID] = true
		}
		src.AddRow(rid, "pc_projection", sampler.ProjectionRow{
			AggregateID: aggID, AggregateType: "pc",
			AggregateVersion: ver, EventID: uuid.New(), PayloadJSON: projState,
		})
		fetcher.AddRow(rid, "pc_projection", aggID, ver, projState)
		loader.AddState(rid, "pc", aggID, ver, replayState)
	}

	stats, err := loop.Run(context.Background(), rid, []types.TableConfig{
		{TableName: "pc_projection", FullScanBatchSize: 25}, // 25 × 4 = 100 batches
	})
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if len(stats.Reports) != 1 {
		t.Fatalf("1 report expected, got %d", len(stats.Reports))
	}
	r0 := stats.Reports[0]
	if r0.SampleSize != 100 {
		t.Errorf("SampleSize: got %d want 100 (full scan)", r0.SampleSize)
	}
	if r0.DriftCount != 10 {
		t.Errorf("DriftCount: got %d want 10 (injected 10)", r0.DriftCount)
	}
	if string(r0.CheckMode) != string(types.CheckModeMonthly) {
		t.Errorf("CheckMode: got %q want %q", r0.CheckMode, types.CheckModeMonthly)
	}

	// Persist call uses monthly delay (30 * 24h), not 24h.
	if len(per.Calls) != 1 {
		t.Fatalf("1 persist call expected, got %d", len(per.Calls))
	}
	wantDelay := 30 * 24 * time.Hour
	got := per.Calls[0].ExpectedNextSweepAt.Sub(time.Unix(1700000000, 0).UTC())
	if got != wantDelay {
		t.Errorf("ExpectedNextSweepAt delay: got %v want %v (monthly cadence)", got, wantDelay)
	}
}

func TestFullIntegrityCheck_BatchSizeDoesNotAffectCorrectness(t *testing.T) {
	// 200 rows, vary batch sizes — should always find the same drift count.
	for _, bs := range []int{1, 7, 50, 200, 1000} {
		t.Run("batch="+itoa(bs), func(t *testing.T) {
			clk := func() time.Time { return time.Unix(1700000000, 0).UTC() }
			src := full_check.NewInMemCursorSource()
			loader := comparator.NewInMemLoader()
			cmp, _ := comparator.New(comparator.Config{Loader: loader, Clock: clk})
			per := state_writer.NewInMemPersister()
			sw, _ := state_writer.New(state_writer.Config{Persister: per, Clock: clk})
			fetcher := full_check.NewInMemFetcher()
			loop, _ := full_check.New(full_check.Config{
				CursorSource: src, Comparator: cmp, Fetcher: fetcher, StateWriter: sw,
				Mode: full_check.StaticMode{M: lifecycle.ModeFull}, Clock: clk,
				FullCheckIntervalDays: 30,
			})
			rid := uuid.New()
			drifted := 0
			for i := 0; i < 200; i++ {
				aggID := uuid.New().String()
				ver := uint64(i + 1)
				replayState := []byte(`{"v":42}`)
				projState := replayState
				if i%17 == 0 { // every 17th row drifts
					projState = []byte(`{"v":99}`)
					drifted++
				}
				src.AddRow(rid, "pc_projection", sampler.ProjectionRow{
					AggregateID: aggID, AggregateType: "pc",
					AggregateVersion: ver, EventID: uuid.New(), PayloadJSON: projState,
				})
				fetcher.AddRow(rid, "pc_projection", aggID, ver, projState)
				loader.AddState(rid, "pc", aggID, ver, replayState)
			}
			stats, err := loop.Run(context.Background(), rid, []types.TableConfig{
				{TableName: "pc_projection", FullScanBatchSize: bs},
			})
			if err != nil {
				t.Fatalf("Run batch=%d: %v", bs, err)
			}
			if stats.Reports[0].SampleSize != 200 {
				t.Errorf("batch=%d: SampleSize=%d want 200", bs, stats.Reports[0].SampleSize)
			}
			if stats.Reports[0].DriftCount != drifted {
				t.Errorf("batch=%d: DriftCount=%d want %d", bs, stats.Reports[0].DriftCount, drifted)
			}
		})
	}
}

// itoa is a local helper to avoid pulling strconv into the test name.
func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := false
	if n < 0 {
		neg = true
		n = -n
	}
	buf := [20]byte{}
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
