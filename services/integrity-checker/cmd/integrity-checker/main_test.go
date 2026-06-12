package main

import (
	"testing"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/metrics"
)

func TestRequiredMetrics_ConstantsCovered(t *testing.T) {
	// Guard against accidental rename of one of the metric constants
	// without updating requiredMetrics — main() would no longer enforce
	// the ABI check on the renamed name.
	want := []string{
		metrics.MetricProjectionLagSeconds,
		metrics.MetricProjectionDriftCount,
		metrics.MetricProjectionCheckDurationSeconds,
		metrics.MetricProjectionCheckRunsTotal,
	}
	if len(want) != len(requiredMetrics) {
		t.Fatalf("requiredMetrics size mismatch: want %d got %d", len(want), len(requiredMetrics))
	}
	for i, w := range want {
		if requiredMetrics[i] != w {
			t.Errorf("requiredMetrics[%d]=%q want %q", i, requiredMetrics[i], w)
		}
	}
}
