package metrics

import (
	"strings"
	"testing"
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
