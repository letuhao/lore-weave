package full_check

import (
	"context"
	"errors"
	"fmt"
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

type rig struct {
	loop      *Loop
	src       *InMemCursorSource
	loader    *comparator.InMemLoader
	fetcher   *InMemFetcher
	persister *state_writer.InMemPersister
}

func newRig(t *testing.T, m lifecycle.ServiceMode, intervalDays int) *rig {
	t.Helper()
	clk := frozen(time.Unix(1700000000, 0).UTC())
	src := NewInMemCursorSource()
	loader := comparator.NewInMemLoader()
	cmp, _ := comparator.New(comparator.Config{Loader: loader, Clock: clk})
	per := state_writer.NewInMemPersister()
	sw, _ := state_writer.New(state_writer.Config{Persister: per, Clock: clk})
	f := NewInMemFetcher()
	loop, err := New(Config{
		CursorSource:          src,
		Comparator:            cmp,
		Fetcher:               f,
		StateWriter:           sw,
		Mode:                  StaticMode{M: m},
		Clock:                 clk,
		FullCheckIntervalDays: intervalDays,
	})
	if err != nil {
		t.Fatal(err)
	}
	return &rig{loop: loop, src: src, loader: loader, fetcher: f, persister: per}
}

func TestNew_RejectsBadIntervalDays(t *testing.T) {
	clk := frozen(time.Unix(1700000000, 0))
	cmp, _ := comparator.New(comparator.Config{Loader: comparator.NewInMemLoader(), Clock: clk})
	sw, _ := state_writer.New(state_writer.Config{Persister: state_writer.NewInMemPersister(), Clock: clk})
	_, err := New(Config{
		CursorSource:          NewInMemCursorSource(),
		Comparator:            cmp,
		Fetcher:               NewInMemFetcher(),
		StateWriter:           sw,
		Mode:                  StaticMode{M: lifecycle.ModeFull},
		Clock:                 clk,
		FullCheckIntervalDays: 0,
	})
	if err == nil {
		t.Fatal("expected error for FullCheckIntervalDays=0")
	}
}

func TestRun_WalksAllRowsViaCursorBatching(t *testing.T) {
	r := newRig(t, lifecycle.ModeFull, 30)
	rid := uuid.New()
	// 1500 rows, batch=500 → 3 batches.
	for i := 0; i < 1500; i++ {
		aggUUID := uuid.New()
		aggID := aggUUID.String()
		ver := uint64(i + 1)
		payload := []byte(`{"v":42}`)
		r.src.AddRow(rid, "pc_projection", sampler.ProjectionRow{
			AggregateID: aggID, AggregateType: "pc", AggregateVersion: ver,
			EventID: uuid.New(), PayloadJSON: payload,
		})
		r.fetcher.AddRow(rid, "pc_projection", aggID, ver, payload)
		r.loader.AddState(rid, "pc", aggID, ver, payload)
	}

	stats, err := r.loop.Run(context.Background(), rid, []types.TableConfig{
		{TableName: "pc_projection", FullScanBatchSize: 500},
	})
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if stats.Reports[0].SampleSize != 1500 {
		t.Errorf("expected SampleSize=1500 (full scan), got %d", stats.Reports[0].SampleSize)
	}
	if stats.Reports[0].DriftCount != 0 {
		t.Errorf("expected 0 drift, got %d", stats.Reports[0].DriftCount)
	}
}

func TestRun_DetectsDriftAcrossFullScan(t *testing.T) {
	r := newRig(t, lifecycle.ModeFull, 30)
	rid := uuid.New()
	// 100 aggregates, 10 drifted.
	driftIdx := map[int]bool{3: true, 17: true, 41: true, 50: true, 58: true,
		60: true, 72: true, 88: true, 91: true, 99: true}
	for i := 0; i < 100; i++ {
		aggUUID := uuid.New()
		aggID := aggUUID.String()
		ver := uint64(i + 1)
		replayPayload := []byte(`{"v":42}`)
		projectionPayload := replayPayload
		if driftIdx[i] {
			projectionPayload = []byte(`{"v":99}`)
		}
		r.src.AddRow(rid, "pc_projection", sampler.ProjectionRow{
			AggregateID: aggID, AggregateType: "pc", AggregateVersion: ver,
			EventID: uuid.New(), PayloadJSON: projectionPayload,
		})
		r.fetcher.AddRow(rid, "pc_projection", aggID, ver, projectionPayload)
		r.loader.AddState(rid, "pc", aggID, ver, replayPayload)
	}

	stats, err := r.loop.Run(context.Background(), rid, []types.TableConfig{
		{TableName: "pc_projection", FullScanBatchSize: 25},
	})
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if stats.Reports[0].DriftCount != 10 {
		t.Errorf("expected 10 drifts, got %d", stats.Reports[0].DriftCount)
	}
	if stats.Reports[0].SampleSize != 100 {
		t.Errorf("expected SampleSize=100, got %d", stats.Reports[0].SampleSize)
	}
}

func TestRun_DegradedMode_Skips(t *testing.T) {
	r := newRig(t, lifecycle.ModeEssentials, 30)
	stats, err := r.loop.Run(context.Background(), uuid.New(), []types.TableConfig{
		{TableName: "pc_projection", FullScanBatchSize: 500},
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

func TestRun_MonthlyDelayWritten(t *testing.T) {
	r := newRig(t, lifecycle.ModeFull, 30)
	rid := uuid.New()
	r.src.AddRow(rid, "pc_projection", sampler.ProjectionRow{
		AggregateID: uuid.New().String(), AggregateType: "pc", AggregateVersion: 1,
		EventID: uuid.New(),
	})
	// Replay state missing → comparator SKIPS. Still produces a persisted report.
	_, _ = r.loop.Run(context.Background(), rid, []types.TableConfig{
		{TableName: "pc_projection", FullScanBatchSize: 500},
	})
	if len(r.persister.Calls) != 1 {
		t.Fatalf("1 persist call expected, got %d", len(r.persister.Calls))
	}
	got := r.persister.Calls[0].ExpectedNextSweepAt.Sub(time.Unix(1700000000, 0).UTC())
	want := 30 * 24 * time.Hour
	if got != want {
		t.Errorf("monthly delay: got %v want %v", got, want)
	}
}

func TestRun_AbortsOnStuckCursor(t *testing.T) {
	// Buggy cursor source that always returns the same cursor.
	src := &stuckCursorSource{}
	clk := frozen(time.Unix(1700000000, 0))
	cmp, _ := comparator.New(comparator.Config{Loader: comparator.NewInMemLoader(), Clock: clk})
	sw, _ := state_writer.New(state_writer.Config{Persister: state_writer.NewInMemPersister(), Clock: clk})
	loop, _ := New(Config{
		CursorSource:          src,
		Comparator:            cmp,
		Fetcher:               NewInMemFetcher(),
		StateWriter:           sw,
		Mode:                  StaticMode{M: lifecycle.ModeFull},
		Clock:                 clk,
		FullCheckIntervalDays: 30,
	})
	_, err := loop.Run(context.Background(), uuid.New(), []types.TableConfig{
		{TableName: "pc_projection", FullScanBatchSize: 100},
	})
	if err == nil {
		t.Fatal("expected error for stuck cursor")
	}
}

func TestRun_RespectsContextCancellation(t *testing.T) {
	r := newRig(t, lifecycle.ModeFull, 30)
	rid := uuid.New()
	// 5K rows, cancel context BEFORE Run.
	for i := 0; i < 5000; i++ {
		aggUUID := uuid.New()
		r.src.AddRow(rid, "pc_projection", sampler.ProjectionRow{
			AggregateID: aggUUID.String(), AggregateType: "pc", AggregateVersion: uint64(i + 1),
			EventID: uuid.New(),
		})
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err := r.loop.Run(ctx, rid, []types.TableConfig{
		{TableName: "pc_projection", FullScanBatchSize: 500},
	})
	if err == nil {
		t.Fatal("expected error on cancelled context")
	}
	if !errors.Is(err, context.Canceled) {
		t.Errorf("expected context.Canceled wrapped, got %v", err)
	}
}

// stuckCursorSource is a buggy cursor source for the stuck-cursor guard test.
type stuckCursorSource struct{ calls int }

func (s *stuckCursorSource) NextBatch(_ context.Context, _ uuid.UUID, _, cursor string, batchSize int) ([]sampler.ProjectionRow, string, error) {
	s.calls++
	if s.calls > 3 {
		return nil, "", fmt.Errorf("test ran away")
	}
	rows := []sampler.ProjectionRow{{
		AggregateID: "x", AggregateType: "pc", AggregateVersion: 1,
		EventID: uuid.New(),
	}}
	// Always return "stuck-cursor" — never advances.
	return rows, "stuck-cursor", nil
}
