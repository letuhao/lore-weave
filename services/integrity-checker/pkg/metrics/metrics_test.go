package metrics

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestMetricNames_FollowConvention(t *testing.T) {
	names := []string{
		MetricProjectionLagSeconds,
		MetricProjectionDriftCount,
		MetricProjectionCheckDurationSeconds,
		MetricProjectionCheckRunsTotal,
	}
	for _, n := range names {
		if !strings.HasPrefix(n, "lw_projection_") {
			t.Errorf("metric %q must start with lw_projection_ for inventory namespace", n)
		}
	}
}

func TestCheckOutcome_IsValid(t *testing.T) {
	if !OutcomeOK.IsValid() || !OutcomeError.IsValid() {
		t.Error("OK + Error should be valid")
	}
	if CheckOutcome("paged").IsValid() {
		t.Error("unbounded outcomes must be rejected (cardinality control)")
	}
}

func TestInMemEmitter_RecordsAllMethods(t *testing.T) {
	e := NewInMemEmitter()
	e.SetProjectionLagSeconds("r-1", "pc_projection", 12.5)
	e.SetProjectionDriftCount("r-1", "pc_projection", 3)
	e.ObserveCheckDuration("daily", "pc_projection", 1.2)
	e.IncCheckRun("daily", OutcomeOK)
	e.IncCheckRun("daily", OutcomeError)
	e.IncCheckRun("daily", OutcomeOK)

	if e.Lag["r-1|pc_projection"] != 12.5 {
		t.Errorf("lag not recorded; got map=%v", e.Lag)
	}
	if e.Drift["r-1|pc_projection"] != 3 {
		t.Errorf("drift not recorded; got map=%v", e.Drift)
	}
	if len(e.Durations) != 1 || e.Durations[0].Seconds != 1.2 {
		t.Errorf("duration not recorded; got %+v", e.Durations)
	}
	if e.Runs["daily|ok"] != 2 || e.Runs["daily|error"] != 1 {
		t.Errorf("runs not recorded; got %v", e.Runs)
	}
}

func TestPromEmitter_RegistersAndGathersAllFamilies(t *testing.T) {
	e := NewPromEmitter()
	e.SetProjectionDriftCount("r-1", "pc_projection", 3)
	e.SetProjectionLagSeconds("r-1", "pc_projection", 12.5)
	e.ObserveCheckDuration("daily", "pc_projection", 1.2)
	e.IncCheckRun("daily", OutcomeOK)
	e.IncCheckRun("daily", OutcomeError)

	mfs, err := e.registry.Gather()
	if err != nil {
		t.Fatalf("gather: %v", err)
	}
	got := map[string]bool{}
	for _, mf := range mfs {
		got[mf.GetName()] = true
	}
	for _, want := range []string{
		MetricProjectionLagSeconds, MetricProjectionDriftCount,
		MetricProjectionCheckDurationSeconds, MetricProjectionCheckRunsTotal,
	} {
		if !got[want] {
			t.Errorf("registry missing family %q (gathered: %v)", want, got)
		}
	}
}

func TestPromEmitter_DriftGaugeValueAndRunsCounter(t *testing.T) {
	e := NewPromEmitter()
	e.SetProjectionDriftCount("r-9", "npc_projection", 7)
	if v := testutil.ToFloat64(e.drift.WithLabelValues("r-9", "npc_projection")); v != 7 {
		t.Errorf("drift gauge = %v, want 7", v)
	}
	// Counter accumulates per (mode, outcome).
	e.IncCheckRun("monthly", OutcomeError)
	e.IncCheckRun("monthly", OutcomeError)
	if v := testutil.ToFloat64(e.runs.WithLabelValues("monthly", "error")); v != 2 {
		t.Errorf("runs counter = %v, want 2", v)
	}
}

// TestPromEmitter_PushTransmitsFamilies exercises the real push HTTP path against
// a stub gateway (no real Pushgateway needed): assert the request lands and the
// serialized body carries an emitted family.
func TestPromEmitter_PushTransmitsFamilies(t *testing.T) {
	got := make(chan string, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		got <- string(b)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	e := NewPromEmitter()
	e.SetProjectionDriftCount("r-1", "pc_projection", 5)
	if err := e.Push(srv.URL); err != nil {
		t.Fatalf("push: %v", err)
	}
	body := <-got
	if !strings.Contains(body, MetricProjectionDriftCount) {
		t.Errorf("push body missing %q: %q", MetricProjectionDriftCount, body)
	}
}

// PromEmitter must satisfy the Emitter interface (compile-time guard mirrors the
// production var _ Emitter assertion).
var _ Emitter = NewPromEmitter()
