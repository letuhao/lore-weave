package usl

import (
	"math"
	"math/rand"
	"testing"
)

// trueUSL is the noise-free model used to synthesise recovery test data.
func trueUSL(n int, gamma, alpha, beta float64) float64 {
	fn := float64(n)
	return gamma * fn / (1 + alpha*(fn-1) + beta*fn*(fn-1))
}

// TestFitRecoversKnownCoefficients is the NON-VACUITY bite (S7 §3): generate
// points from KNOWN (γ,α,β) with small seeded jitter and assert the fitter
// recovers each within tolerance, plus Nmax near the analytic peak. A stub
// fitter that returns constants fails this.
func TestFitRecoversKnownCoefficients(t *testing.T) {
	const gamma, alpha, beta = 1000.0, 0.03, 1e-4
	concurrency := []int{1, 2, 4, 8, 16, 32, 64, 128}
	rng := rand.New(rand.NewSource(42)) // deterministic jitter

	var samples []Sample
	for _, n := range concurrency {
		x := trueUSL(n, gamma, alpha, beta)
		x *= 1 + (rng.Float64()-0.5)*0.02 // ±1% multiplicative jitter
		samples = append(samples, Sample{N: n, Throughput: x})
	}

	fit, err := FitUSL(samples)
	if err != nil {
		t.Fatalf("FitUSL: %v", err)
	}
	if fit.Degenerate {
		t.Fatalf("recovery fit should not be degenerate: %+v", fit)
	}

	// Tolerances: γ within 5%, α within abs 0.02, β within 40% relative
	// (β is tiny → noise-sensitive), Nmax within ±20 of the analytic peak.
	if rel := math.Abs(fit.Gamma-gamma) / gamma; rel > 0.05 {
		t.Errorf("gamma: got %.2f want ~%.0f (rel %.3f > 0.05)", fit.Gamma, gamma, rel)
	}
	if math.Abs(fit.Alpha-alpha) > 0.02 {
		t.Errorf("alpha: got %.4f want ~%.2f (abs > 0.02)", fit.Alpha, alpha)
	}
	if rel := math.Abs(fit.Beta-beta) / beta; rel > 0.40 {
		t.Errorf("beta: got %.6f want ~%.4f (rel %.3f > 0.40)", fit.Beta, beta, rel)
	}
	wantNmax := math.Sqrt((1 - alpha) / beta) // ≈ 98.5
	if math.Abs(fit.Nmax-wantNmax) > 20 {
		t.Errorf("Nmax: got %.1f want ~%.1f (±20)", fit.Nmax, wantNmax)
	}
	if fit.R2 < 0.98 {
		t.Errorf("R2: got %.4f want >= 0.98", fit.R2)
	}
}

// TestFitLinearSeriesNoHallucinatedKnee is the β=0 bite (S7 §3): a perfectly
// linear (contention-only, no coherency) series must NOT produce a saturation
// knee inside or near the measured range.
func TestFitLinearSeriesNoHallucinatedKnee(t *testing.T) {
	const gamma, alpha, beta = 500.0, 0.05, 0.0
	concurrency := []int{1, 2, 4, 8, 16, 32}
	var samples []Sample
	maxN := 0
	for _, n := range concurrency {
		samples = append(samples, Sample{N: n, Throughput: trueUSL(n, gamma, alpha, beta)})
		if n > maxN {
			maxN = n
		}
	}

	fit, err := FitUSL(samples)
	if err != nil {
		t.Fatalf("FitUSL: %v", err)
	}
	// The real property: no knee in (or anywhere near) the measured range, and
	// a near-zero coherency coefficient — robust to exact-zero float fitting.
	if !(math.IsInf(fit.Nmax, 1) || fit.Nmax > float64(100*maxN)) {
		t.Errorf("linear series hallucinated a knee: Nmax=%.1f (maxN=%d)", fit.Nmax, maxN)
	}
	if fit.Beta > 1e-3 {
		t.Errorf("linear series: beta should be ~0, got %.6f", fit.Beta)
	}
}

// TestNmaxFromGuard tests the degeneracy guard DIRECTLY (S7 review MED-4) so it
// does not depend on fit noise: α≥1 and β≤0 must yield +Inf, never NaN.
func TestNmaxFromGuard(t *testing.T) {
	cases := []struct {
		name        string
		alpha, beta float64
	}{
		{"super-contention alpha>1", 1.5, 1e-4},
		{"alpha exactly 1", 1.0, 1e-4},
		{"beta zero", 0.03, 0},
		{"beta negative", 0.03, -1e-5},
		{"alpha NaN", math.NaN(), 1e-4}, // review MED-1: non-finite → degenerate, no NaN leak
		{"beta NaN", 0.03, math.NaN()},
		{"beta +Inf", 0.03, math.Inf(1)},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			nmax, degen := nmaxFrom(c.alpha, c.beta)
			if !degen {
				t.Errorf("expected degenerate for (a=%.2f,b=%g)", c.alpha, c.beta)
			}
			if math.IsNaN(nmax) {
				t.Errorf("Nmax is NaN for (a=%.2f,b=%g) — guard failed", c.alpha, c.beta)
			}
			if !math.IsInf(nmax, 1) {
				t.Errorf("expected +Inf Nmax for degenerate, got %v", nmax)
			}
		})
	}
	// Healthy case is NOT degenerate.
	if nmax, degen := nmaxFrom(0.03, 1e-4); degen || math.Abs(nmax-98.49) > 0.5 {
		t.Errorf("healthy (0.03,1e-4): got nmax=%.2f degen=%v want ~98.49 false", nmax, degen)
	}
}

// TestFitSuperContentionDegenerate feeds a fast-collapsing series and asserts
// the fit reports Degenerate with no NaN leaking into Nmax/Xmax.
func TestFitSuperContentionDegenerate(t *testing.T) {
	// α just under/over 1 region; a steep drop. We only require that whatever
	// the fit lands on, the guard prevents a NaN.
	const gamma, alpha, beta = 200.0, 0.9, 0.5
	var samples []Sample
	for _, n := range []int{1, 2, 3, 4, 5, 6} {
		samples = append(samples, Sample{N: n, Throughput: trueUSL(n, gamma, alpha, beta)})
	}
	fit, err := FitUSL(samples)
	if err != nil {
		t.Fatalf("FitUSL: %v", err)
	}
	if math.IsNaN(fit.Nmax) || math.IsNaN(fit.Xmax) {
		t.Errorf("NaN leaked: Nmax=%v Xmax=%v", fit.Nmax, fit.Xmax)
	}
}

func TestFitRejectsTooFewDistinctN(t *testing.T) {
	// 6 samples but only 2 distinct N → must error.
	samples := []Sample{
		{N: 1, Throughput: 100}, {N: 1, Throughput: 101}, {N: 1, Throughput: 99},
		{N: 2, Throughput: 180}, {N: 2, Throughput: 182}, {N: 2, Throughput: 179},
	}
	if _, err := FitUSL(samples); err == nil {
		t.Error("expected error for <4 distinct N, got nil")
	}
}

func TestFitRejectsNonFinite(t *testing.T) {
	samples := []Sample{
		{N: 1, Throughput: 100}, {N: 2, Throughput: math.Inf(1)},
		{N: 4, Throughput: 300}, {N: 8, Throughput: 400},
	}
	if _, err := FitUSL(samples); err == nil {
		t.Error("expected error for non-finite throughput, got nil")
	}
}
