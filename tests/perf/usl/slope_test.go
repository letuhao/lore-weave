package usl

import (
	"math"
	"math/rand"
	"testing"
)

// genPow synthesises a log-log series time = c·N^p with small seeded jitter, so
// the fit is exercised on noisy-but-known data (a stub fitter returning a
// constant fails the recovery assertions below).
func genPow(ns []int, c, p float64, seed int64) []LoadTimePoint {
	rng := rand.New(rand.NewSource(seed))
	out := make([]LoadTimePoint, 0, len(ns))
	for _, n := range ns {
		t := c * math.Pow(float64(n), p)
		t *= 1 + (rng.Float64()-0.5)*0.04 // ±2% multiplicative jitter
		out = append(out, LoadTimePoint{N: n, Time: t})
	}
	return out
}

// TestComplexityExponentBand_BitesSuperlinear is the G2 non-vacuity proof (F6/F8/
// F9). It fixes a band p ≤ 1+ε and asserts:
//
//   - a CLEAN sub-linear series (true p≈0.8) is recovered AND sits within the
//     band — the fitter is non-vacuous (recovers the known exponent, not a
//     constant), and the gate does not false-fire on healthy growth; and
//   - a BITE series whose true exponent sits JUST PAST the band (p≈1.30 vs a
//     1.20 ceiling — a REALISTIC small super-linearity, F6, not a 2× blow-up)
//     is recovered AND EXITS the band, so the gate fires.
//
// The exponents straddle the band tightly (0.8 in, 1.3 out, ceiling 1.2) so the
// test proves the band DISCRIMINATES, not merely that extremes differ.
func TestComplexityExponentBand_BitesSuperlinear(t *testing.T) {
	const eps = 0.20 // placeholder band ceiling 1.20 pending live calibration (F7)
	ns := []int{2, 4, 8, 16, 32, 64, 128}

	// CLEAN — true exponent 0.80, within the 1.20 ceiling.
	clean, err := FitComplexityExponent(genPow(ns, 5.0, 0.80, 11))
	if err != nil {
		t.Fatalf("FitComplexityExponent(clean): %v", err)
	}
	if math.Abs(clean.Exponent-0.80) > 0.05 {
		t.Fatalf("non-vacuity: clean exponent should recover ~0.80, got %.3f (fitter not measuring)", clean.Exponent)
	}
	if !clean.WithinBand(eps) {
		t.Fatalf("clean p=%.3f must be WITHIN the band (ceiling %.2f) — gate false-fires", clean.Exponent, 1+eps)
	}
	if clean.R2 < 0.95 {
		t.Fatalf("clean log-log fit R2=%.3f too low — the slope is not a real trend", clean.R2)
	}

	// BITE — true exponent 1.30, just past the 1.20 ceiling.
	bite, err := FitComplexityExponent(genPow(ns, 5.0, 1.30, 12))
	if err != nil {
		t.Fatalf("FitComplexityExponent(bite): %v", err)
	}
	if math.Abs(bite.Exponent-1.30) > 0.05 {
		t.Fatalf("non-vacuity: bite exponent should recover ~1.30, got %.3f", bite.Exponent)
	}
	if bite.WithinBand(eps) {
		t.Fatalf("BITE p=%.3f must EXIT the band (ceiling %.2f) — the gate is VACUOUS", bite.Exponent, 1+eps)
	}
}

// TestComplexityExponent_FitsOverAllPoints pins F8: the slope is an OLS over all
// points, NOT a 2-point secant. A series that is flat at low N and steepens at
// high N must yield a slope BETWEEN the two regimes (a secant on the endpoints
// would over- or under-state it). Here a piecewise series (flat 0 then steep)
// must produce an intermediate, all-points exponent.
func TestComplexityExponent_FitsOverAllPoints(t *testing.T) {
	// Low-N flat (p≈0), high-N steep (p≈2). An all-points OLS lands in between;
	// a naive endpoint secant (log(t_last/t_first)/log(N_last/N_first)) would too,
	// but the MID points pull the OLS — assert the fit uses them by checking the
	// exponent is meaningfully below the endpoint secant.
	pts := []LoadTimePoint{
		{N: 1, Time: 10}, {N: 2, Time: 10}, {N: 4, Time: 11}, // flat regime
		{N: 8, Time: 14}, {N: 16, Time: 30}, {N: 32, Time: 110}, // steepening
	}
	fit, err := FitComplexityExponent(pts)
	if err != nil {
		t.Fatalf("FitComplexityExponent: %v", err)
	}
	// Endpoint secant exponent.
	secant := math.Log(110.0/10.0) / math.Log(32.0/1.0)
	if fit.Points != 6 {
		t.Fatalf("expected all 6 points used, got %d", fit.Points)
	}
	if fit.Exponent >= secant {
		t.Fatalf("all-points OLS exponent %.3f should differ from (here, be below) the endpoint secant %.3f — flat low-N points must pull it",
			fit.Exponent, secant)
	}
}

// TestComplexityExponent_RejectsTooFewPoints pins the ≥3-distinct-N guard.
func TestComplexityExponent_RejectsTooFewPoints(t *testing.T) {
	_, err := FitComplexityExponent([]LoadTimePoint{{N: 1, Time: 1}, {N: 2, Time: 2}})
	if err == nil {
		t.Fatal("expected error for <3 distinct N")
	}
}
