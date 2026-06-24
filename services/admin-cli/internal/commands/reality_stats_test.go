package commands

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

type fakeRealityReader struct {
	stats *RealityStats
	err   error
}

func (f fakeRealityReader) ReadRealityStats(_ context.Context, _ uuid.UUID) (*RealityStats, error) {
	return f.stats, f.err
}

func TestRunRealityStats_Formats(t *testing.T) {
	id := uuid.New()
	at := time.Date(2026, 5, 31, 12, 0, 0, 0, time.UTC)
	r := fakeRealityReader{stats: &RealityStats{
		RealityID: id, Status: "active", StatusTransitionAt: at, Locale: "en",
		DeployCohort: 2, SessionMaxPCs: 50, SessionMaxNPCs: 200, SessionMaxTotal: 250,
	}}
	out, err := RunRealityStats(context.Background(), id, r)
	if err != nil {
		t.Fatalf("RunRealityStats: %v", err)
	}
	for _, want := range []string{id.String(), "status:        active", "locale:        en", "deploy_cohort: 2", "pcs=50 npcs=200 total=250"} {
		if !strings.Contains(out, want) {
			t.Errorf("output missing %q:\n%s", want, out)
		}
	}
	// A healthy live reality shows no lifecycle markers.
	if strings.Contains(out, "close:") || strings.Contains(out, "drop:") {
		t.Errorf("unset lifecycle markers must be omitted:\n%s", out)
	}
}

func TestRunRealityStats_LifecycleMarkers(t *testing.T) {
	id := uuid.New()
	at := time.Date(2026, 5, 31, 12, 0, 0, 0, time.UTC)
	closed := at.Add(-time.Hour)
	r := fakeRealityReader{stats: &RealityStats{
		RealityID: id, Status: "closing", StatusTransitionAt: at, Locale: "vi",
		CloseInitiatedAt: &closed, CloseReason: "ops drain",
	}}
	out, _ := RunRealityStats(context.Background(), id, r)
	if !strings.Contains(out, "close:") || !strings.Contains(out, "ops drain") {
		t.Errorf("set close marker must be shown:\n%s", out)
	}
}

func TestRunRealityStats_NotFound(t *testing.T) {
	r := fakeRealityReader{err: ErrRealityNotFound}
	if _, err := RunRealityStats(context.Background(), uuid.New(), r); !errors.Is(err, ErrRealityNotFound) {
		t.Fatalf("expected ErrRealityNotFound, got %v", err)
	}
}

func TestRunRealityStats_NilReader(t *testing.T) {
	if _, err := RunRealityStats(context.Background(), uuid.New(), nil); err == nil {
		t.Fatal("nil reader must error")
	}
}
