package full_check

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/live"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/replayloader"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/state_writer"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/tablemap"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

func frozen(t time.Time) func() time.Time { return func() time.Time { return t } }

// fakeReplayer returns a per-boundary-event ReplayResult (registered by the rig).
// An unregistered event falls to a zero-value result (Status="" → Skippable).
type fakeReplayer struct {
	byEvent map[uuid.UUID]replayloader.ReplayResult
}

func (f *fakeReplayer) Replay(_ context.Context, req replayloader.ReplayRequest) (replayloader.ReplayResult, error) {
	return f.byEvent[req.BoundaryEventID], nil
}

type rig struct {
	loop      *Loop
	src       *InMemCursorSource
	replayer  *fakeReplayer
	persister *state_writer.InMemPersister
}

func newRig(t *testing.T, m lifecycle.ServiceMode, intervalDays int) *rig {
	t.Helper()
	clk := frozen(time.Unix(1700000000, 0).UTC())
	src := NewInMemCursorSource()
	rep := &fakeReplayer{byEvent: map[uuid.UUID]replayloader.ReplayResult{}}
	per := state_writer.NewInMemPersister()
	sw, _ := state_writer.New(state_writer.Config{Persister: per, Clock: clk})
	loop, err := New(Config{
		CursorSource:          src,
		Replayer:              rep,
		StateWriter:           sw,
		Mode:                  StaticMode{M: m},
		Clock:                 clk,
		FullCheckIntervalDays: intervalDays,
	})
	if err != nil {
		t.Fatal(err)
	}
	return &rig{loop: loop, src: src, replayer: rep, persister: per}
}

// addRow seeds one pc row whose live payload is `live`; the replay returns
// `replay` (Found+ok). When live==replay the row is clean; differing = drift.
func (r *rig) addRow(rid uuid.UUID, livePayload, replayPayload string) {
	pcID := uuid.New().String()
	ev := uuid.New()
	r.src.AddRow(rid, "pc_projection", live.SampledRow{
		PK:               map[string]string{"pc_id": pcID},
		EventID:          ev,
		AggregateVersion: 3,
		Payload:          []byte(livePayload),
		Owning:           []tablemap.OwningAggregate{{Type: "pc", ID: pcID}},
	})
	r.replayer.byEvent[ev] = replayloader.ReplayResult{
		Found: true, EventsReplayed: 5, Status: "ok", Payload: []byte(replayPayload),
	}
}

func TestNew_RejectsBadIntervalDays(t *testing.T) {
	clk := frozen(time.Unix(1700000000, 0))
	sw, _ := state_writer.New(state_writer.Config{Persister: state_writer.NewInMemPersister(), Clock: clk})
	_, err := New(Config{
		CursorSource:          NewInMemCursorSource(),
		Replayer:              &fakeReplayer{byEvent: map[uuid.UUID]replayloader.ReplayResult{}},
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
	// 1500 rows, batch=500 → 3 batches; all clean.
	for i := 0; i < 1500; i++ {
		r.addRow(rid, `{"v":42}`, `{"v":42}`)
	}
	stats, err := r.loop.Run(context.Background(), rid, "postgres://shard", []types.TableConfig{
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
	driftIdx := map[int]bool{3: true, 17: true, 41: true, 50: true, 58: true,
		60: true, 72: true, 88: true, 91: true, 99: true}
	for i := 0; i < 100; i++ {
		if driftIdx[i] {
			r.addRow(rid, `{"v":99}`, `{"v":42}`) // live != replay → drift
		} else {
			r.addRow(rid, `{"v":42}`, `{"v":42}`)
		}
	}
	stats, err := r.loop.Run(context.Background(), rid, "postgres://shard", []types.TableConfig{
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
	stats, err := r.loop.Run(context.Background(), uuid.New(), "postgres://shard", []types.TableConfig{
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
	pcID := uuid.New().String()
	// Unregistered replay → zero-value result (Status="" → Skippable). Still
	// produces a persisted report.
	r.src.AddRow(rid, "pc_projection", live.SampledRow{
		PK: map[string]string{"pc_id": pcID}, EventID: uuid.New(),
		Owning: []tablemap.OwningAggregate{{Type: "pc", ID: pcID}},
	})
	_, _ = r.loop.Run(context.Background(), rid, "postgres://shard", []types.TableConfig{
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
	src := &stuckCursorSource{}
	clk := frozen(time.Unix(1700000000, 0))
	sw, _ := state_writer.New(state_writer.Config{Persister: state_writer.NewInMemPersister(), Clock: clk})
	loop, _ := New(Config{
		CursorSource:          src,
		Replayer:              &fakeReplayer{byEvent: map[uuid.UUID]replayloader.ReplayResult{}},
		StateWriter:           sw,
		Mode:                  StaticMode{M: lifecycle.ModeFull},
		Clock:                 clk,
		FullCheckIntervalDays: 30,
	})
	_, err := loop.Run(context.Background(), uuid.New(), "postgres://shard", []types.TableConfig{
		{TableName: "pc_projection", FullScanBatchSize: 100},
	})
	if err == nil {
		t.Fatal("expected error for stuck cursor")
	}
}

func TestRun_RespectsContextCancellation(t *testing.T) {
	r := newRig(t, lifecycle.ModeFull, 30)
	rid := uuid.New()
	for i := 0; i < 5000; i++ {
		r.addRow(rid, `{"v":1}`, `{"v":1}`)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err := r.loop.Run(ctx, rid, "postgres://shard", []types.TableConfig{
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

func (s *stuckCursorSource) NextBatch(_ context.Context, _ uuid.UUID, _, _ string, _ int) ([]live.SampledRow, string, error) {
	s.calls++
	if s.calls > 3 {
		return nil, "", fmt.Errorf("test ran away")
	}
	rows := []live.SampledRow{{
		PK: map[string]string{"pc_id": uuid.New().String()}, EventID: uuid.New(),
		Owning: []tablemap.OwningAggregate{{Type: "pc", ID: "x"}},
	}}
	// Always return "stuck-cursor" — never advances.
	return rows, "stuck-cursor", nil
}
