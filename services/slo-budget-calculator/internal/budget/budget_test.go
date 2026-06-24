package budget

import (
	"errors"
	"math"
	"testing"
	"time"
)

func TestCompute_ZeroFailures_BurnRateZero(t *testing.T) {
	now := time.Unix(1_700_000_000, 0).UTC()
	w := Window{Duration: 30 * 24 * time.Hour}
	// 10 buckets, ratio=1.0 each (no failures)
	samples := make([]Sample, 10)
	for i := range samples {
		samples[i] = Sample{
			At:        now.Add(-time.Duration(i+1) * time.Hour),
			Ratio:     1.0,
			NumEvents: 1000,
		}
	}
	r, err := Compute(0.99, samples, w, now)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if r.ConsumedEvents != 0 {
		t.Errorf("consumed=%v; want 0", r.ConsumedEvents)
	}
	if r.BurnRate != 0 {
		t.Errorf("burn_rate=%v; want 0", r.BurnRate)
	}
	if got := r.PolicyTier(); got != "normal" {
		t.Errorf("policy_tier=%q; want normal", got)
	}
}

func TestCompute_AllFailures_BurnRateOver1(t *testing.T) {
	// Target=99%, but every sample is 0% success → catastrophic burn.
	now := time.Unix(1_700_000_000, 0).UTC()
	w := Window{Duration: 30 * 24 * time.Hour}
	samples := make([]Sample, 5)
	for i := range samples {
		samples[i] = Sample{
			At:        now.Add(-time.Duration(i+1) * time.Hour),
			Ratio:     0.0,
			NumEvents: 1000,
		}
	}
	r, err := Compute(0.99, samples, w, now)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if r.BurnRate < 1.0 {
		t.Errorf("burn_rate=%v; want >= 1.0 (catastrophic)", r.BurnRate)
	}
	if got := r.PolicyTier(); got != "slo-breach-postmortem" {
		t.Errorf("policy_tier=%q; want slo-breach-postmortem", got)
	}
}

func TestCompute_PartialBurn_ReturnsCorrectTier(t *testing.T) {
	// Construct a case that should land in 75-90% tier.
	// Target=99% → error budget = 1% of total events.
	// To hit ~80% burn over the FULL window (fraction_elapsed = 1.0),
	// we need budget_consumed_pct ≈ 0.80, i.e. failures = 0.80 × 0.01 × total.
	// With total = 100_000 events → failures should be ~800.
	now := time.Unix(1_700_000_000, 0).UTC()
	w := Window{Duration: 30 * 24 * time.Hour}
	// Place the oldest sample at exactly window-start so fraction_elapsed=1.
	oldest := now.Add(-w.Duration)
	// 10 buckets evenly spaced; each carries 10_000 events; fail rate ~0.8%.
	samples := make([]Sample, 10)
	for i := range samples {
		samples[i] = Sample{
			At:        oldest.Add(time.Duration(i) * (w.Duration / 10)),
			Ratio:     0.992, // 0.8% fail per bucket
			NumEvents: 10_000,
		}
	}
	r, err := Compute(0.99, samples, w, now)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if r.BurnRate < 0.75 || r.BurnRate > 0.90 {
		t.Errorf(
			"burn_rate=%v; want in [0.75, 0.90] (reliability-review-required tier)",
			r.BurnRate,
		)
	}
	if got := r.PolicyTier(); got != "reliability-review-required" {
		t.Errorf("policy_tier=%q; want reliability-review-required", got)
	}
}

func TestCompute_Deterministic_SameInputsSameOutputs(t *testing.T) {
	// Determinism is critical — calculator is read by alert evaluator;
	// non-deterministic output = flapping alerts.
	now := time.Unix(1_700_000_000, 0).UTC()
	w := Window{Duration: 7 * 24 * time.Hour}
	samples := []Sample{
		{At: now.Add(-1 * time.Hour), Ratio: 0.998, NumEvents: 500},
		{At: now.Add(-2 * time.Hour), Ratio: 0.999, NumEvents: 500},
		{At: now.Add(-3 * time.Hour), Ratio: 1.0, NumEvents: 500},
	}
	r1, err1 := Compute(0.999, samples, w, now)
	r2, err2 := Compute(0.999, samples, w, now)
	if err1 != nil || err2 != nil {
		t.Fatalf("err1=%v err2=%v", err1, err2)
	}
	if r1 != r2 {
		t.Errorf("non-deterministic — r1=%+v r2=%+v", r1, r2)
	}
}

func TestCompute_InvalidTarget(t *testing.T) {
	now := time.Unix(1_700_000_000, 0).UTC()
	w := Window{Duration: 30 * 24 * time.Hour}
	samples := []Sample{{At: now, Ratio: 1.0, NumEvents: 100}}

	if _, err := Compute(0, samples, w, now); !errors.Is(err, ErrInvalidTarget) {
		t.Errorf("target=0: want ErrInvalidTarget; got %v", err)
	}
	if _, err := Compute(1.5, samples, w, now); !errors.Is(err, ErrInvalidTarget) {
		t.Errorf("target=1.5: want ErrInvalidTarget; got %v", err)
	}
}

func TestCompute_EmptyWindow(t *testing.T) {
	now := time.Unix(1_700_000_000, 0).UTC()
	w := Window{Duration: 30 * 24 * time.Hour}
	// All samples 60 days ago — out of 30d window.
	samples := []Sample{{
		At:        now.Add(-60 * 24 * time.Hour),
		Ratio:     1.0,
		NumEvents: 1000,
	}}
	_, err := Compute(0.99, samples, w, now)
	if !errors.Is(err, ErrEmptyWindow) {
		t.Errorf("want ErrEmptyWindow; got %v", err)
	}
}

func TestCompute_WindowingDropsOldSamples(t *testing.T) {
	now := time.Unix(1_700_000_000, 0).UTC()
	w := Window{Duration: 24 * time.Hour}
	samples := []Sample{
		// In-window
		{At: now.Add(-1 * time.Hour), Ratio: 1.0, NumEvents: 100},
		{At: now.Add(-12 * time.Hour), Ratio: 1.0, NumEvents: 100},
		// Out-of-window (older than 24h)
		{At: now.Add(-48 * time.Hour), Ratio: 0.0, NumEvents: 100},
	}
	r, err := Compute(0.99, samples, w, now)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if r.SampleCount != 2 {
		t.Errorf("sample_count=%d; want 2 (out-of-window must be dropped)", r.SampleCount)
	}
	// With 2 fully-successful buckets, consumed should be 0.
	if r.ConsumedEvents != 0 {
		t.Errorf("consumed=%v; want 0", r.ConsumedEvents)
	}
}

func TestCompute_NegativeNumEvents_Rejected(t *testing.T) {
	now := time.Unix(1_700_000_000, 0).UTC()
	w := Window{Duration: 30 * 24 * time.Hour}
	samples := []Sample{
		{At: now.Add(-1 * time.Hour), Ratio: 1.0, NumEvents: -10},
	}
	if _, err := Compute(0.99, samples, w, now); err == nil {
		t.Error("want error for negative num_events; got nil")
	}
}

func TestCompute_RatioOutOfRange_Rejected(t *testing.T) {
	now := time.Unix(1_700_000_000, 0).UTC()
	w := Window{Duration: 30 * 24 * time.Hour}
	cases := []float64{-0.1, 1.1}
	for _, ratio := range cases {
		samples := []Sample{{At: now.Add(-1 * time.Hour), Ratio: ratio, NumEvents: 100}}
		if _, err := Compute(0.99, samples, w, now); err == nil {
			t.Errorf("ratio=%v: want error; got nil", ratio)
		}
	}
}

func TestPolicyTier_AllBoundaries(t *testing.T) {
	cases := []struct {
		burn float64
		want string
	}{
		{0.0, "normal"},
		{0.49, "normal"},
		{0.50, "warn"},
		{0.74, "warn"},
		{0.75, "reliability-review-required"},
		{0.89, "reliability-review-required"},
		{0.90, "approve-reliability-override"},
		{0.99, "approve-reliability-override"},
		{1.00, "slo-breach-postmortem"},
		{1.50, "slo-breach-postmortem"},
	}
	for _, c := range cases {
		r := Result{BurnRate: c.burn}
		if got := r.PolicyTier(); got != c.want {
			t.Errorf("burn=%v: tier=%q; want %q", c.burn, got, c.want)
		}
	}
}

// TestCompute_AssertExactErrorBudgetValue is the regression test that
// fails LOUDLY if anyone changes the formula in non-obvious ways.
// Cycle-19 alert envelope downstream consumers (incident-bot,
// slack-notifier) depend on this exact value.
func TestCompute_AssertExactErrorBudgetValue(t *testing.T) {
	now := time.Unix(1_700_000_000, 0).UTC()
	w := Window{Duration: 30 * 24 * time.Hour}
	// 1_000_000 events total, target 99% → error budget = 10_000.
	samples := []Sample{{
		At:        now.Add(-1 * time.Hour),
		Ratio:     0.995, // 0.5% fail = 5000 of 1M
		NumEvents: 1_000_000,
	}}
	r, err := Compute(0.99, samples, w, now)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	expectedBudget := 10_000.0
	if math.Abs(r.ErrorBudgetEvents-expectedBudget) > 0.001 {
		t.Errorf(
			"error_budget_events=%v; want %v (1M events × (1 - 0.99))",
			r.ErrorBudgetEvents, expectedBudget,
		)
	}
	expectedConsumed := 5000.0
	if math.Abs(r.ConsumedEvents-expectedConsumed) > 0.001 {
		t.Errorf(
			"consumed=%v; want %v (5000 of 1M failed)",
			r.ConsumedEvents, expectedConsumed,
		)
	}
	// budget_consumed_pct = 5000 / 10000 = 0.5
	if math.Abs(r.BudgetConsumedPct-0.5) > 0.001 {
		t.Errorf("budget_consumed_pct=%v; want 0.5", r.BudgetConsumedPct)
	}
}
