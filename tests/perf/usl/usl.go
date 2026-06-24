// Package usl fits Neil Gunther's Universal Scalability Law to a measured
// throughput-vs-concurrency series and reports the saturation point.
//
//	X(N) = γN / (1 + α(N−1) + βN(N−1))
//
// where γ is ideal per-unit throughput, α is the contention (serialization)
// coefficient, β is the coherency (crosstalk) coefficient, and the peak
// concurrency is Nmax = √((1−α)/β).
//
// S7 deliverable F1 (docs/specs/2026-06-13-S7-perf-harness.md §3). The fit is
// the load-bearing perf-method artifact: β is an OUTPUT measured from real data
// (the spec forbids asserting it), and the fitter ships a coefficient-recovery
// bite-test proving it is non-vacuous.
package usl

import (
	"errors"
	"math"

	"gonum.org/v1/gonum/optimize"
)

// Sample is one measured point of the USL curve.
//
// N is CONCURRENCY — the number of parallel workers/clients — NOT load size or
// event-count (S7 review HIGH-1). α and β are concurrency-scaling coefficients;
// feeding a throughput-vs-load-size series here would be a category error (its
// "knee" would be per-call overhead amortization, not contention/coherency).
type Sample struct {
	N          int     `json:"n"`
	Throughput float64 `json:"throughput"`
}

// Fit is the fitted USL model plus its derived saturation point.
type Fit struct {
	Gamma float64 `json:"gamma"` // γ — ideal per-unit throughput (X at N=1)
	Alpha float64 `json:"alpha"` // α — contention / serialization
	Beta  float64 `json:"beta"`  // β — coherency / crosstalk (MEASURED, never asserted)
	Nmax  float64 `json:"nmax"`  // peak concurrency √((1−α)/β); +Inf if no coherency knee
	Xmax  float64 `json:"xmax"`  // throughput at Nmax; +Inf when Nmax is +Inf
	R2    float64 `json:"r2"`    // coefficient of determination (goodness-of-fit)
	// Degenerate is true when α≥1 or β≤0 — i.e. the data has no coherency knee
	// (linear or super-contention). Nmax is then +Inf rather than a silent NaN
	// from √ of a negative (S7 review MED-4).
	Degenerate bool `json:"degenerate"`
}

// Predict returns the fitted throughput at concurrency n.
func (f Fit) Predict(n float64) float64 {
	denom := 1 + f.Alpha*(n-1) + f.Beta*n*(n-1)
	if denom <= 0 {
		return math.Inf(1)
	}
	return f.Gamma * n / denom
}

// nmaxFrom derives the USL peak concurrency from (α, β). It is the single guard
// for the degeneracy cases (S7 review MED-4) and is unit-tested directly so the
// guard does not depend on fit noise:
//   - β ≤ 0 (linear / no coherency cost)  → +Inf, degenerate
//   - α ≥ 1 (super-contention)            → +Inf, degenerate (avoids √ of <0 → NaN)
//   - otherwise                           → √((1−α)/β), not degenerate
func nmaxFrom(alpha, beta float64) (nmax float64, degenerate bool) {
	// Non-finite α/β (a NaN/Inf that slipped through the fit) is degenerate too —
	// otherwise √((1−NaN)/NaN)=NaN would leak past the α≥1/β≤0 branches (both of
	// which are false for NaN). Defense in depth for the FitUSL output guard.
	if !isFinite(alpha) || !isFinite(beta) || beta <= 0 || alpha >= 1 {
		return math.Inf(1), true
	}
	return math.Sqrt((1 - alpha) / beta), false
}

// isFinite reports whether x is neither NaN nor ±Inf.
func isFinite(x float64) bool { return !math.IsNaN(x) && !math.IsInf(x, 0) }

// FitUSL fits the USL to the samples: a Gunther linearization seed, then a
// gonum/optimize Nelder-Mead refine of the full nonlinear model. α,β are
// projected to ≥0 (a slightly-negative coefficient from noise is physically 0).
// Errors on fewer than 4 distinct N or non-finite input.
func FitUSL(samples []Sample) (Fit, error) {
	if err := validate(samples); err != nil {
		return Fit{}, err
	}

	gamma0, alpha0, beta0 := guntherSeed(samples)

	// Refine: minimise the sum of squared residuals over (γ, α, β). Nelder-Mead
	// is gradient-free + robust for this smooth 3-parameter surface; α,β are
	// clamped to ≥0 and γ to >0 INSIDE the objective so the search cannot wander
	// into the physically-meaningless region.
	problem := optimize.Problem{Func: func(x []float64) float64 {
		return ssr(x, samples)
	}}
	x0 := []float64{gamma0, alpha0, beta0}
	res, err := optimize.Minimize(problem, x0, nil, &optimize.NelderMead{})
	var x []float64
	if err != nil || res == nil {
		// Refine failed to converge — fall back to the linearized seed rather
		// than erroring; the seed is still a usable estimate.
		x = x0
	} else {
		x = res.X
	}

	gamma := math.Max(x[0], 0)
	alpha := math.Max(x[1], 0)
	beta := math.Max(x[2], 0)

	// Guard a non-finite optimizer result (review MED-1): if the refine produced
	// NaN/Inf, fall back to the Gunther seed, which is finite by construction.
	// Without this, math.Max(NaN,0)=NaN would propagate silently into the Fit.
	if !isFinite(gamma) || !isFinite(alpha) || !isFinite(beta) {
		gamma, alpha, beta = math.Max(gamma0, 0), math.Max(alpha0, 0), math.Max(beta0, 0)
	}

	f := Fit{Gamma: gamma, Alpha: alpha, Beta: beta}
	f.Nmax, f.Degenerate = nmaxFrom(alpha, beta)
	if f.Degenerate {
		f.Xmax = math.Inf(1)
	} else {
		f.Xmax = f.Predict(f.Nmax)
	}
	f.R2 = rSquared(f, samples)
	return f, nil
}

// validate enforces ≥4 distinct N and all-finite, positive-throughput input.
func validate(samples []Sample) error {
	if len(samples) < 4 {
		return errors.New("usl: need at least 4 samples to fit 3 parameters")
	}
	distinct := map[int]struct{}{}
	for _, s := range samples {
		if s.N < 1 {
			return errors.New("usl: concurrency N must be >= 1")
		}
		if math.IsNaN(s.Throughput) || math.IsInf(s.Throughput, 0) || s.Throughput < 0 {
			return errors.New("usl: throughput must be finite and non-negative")
		}
		distinct[s.N] = struct{}{}
	}
	if len(distinct) < 4 {
		return errors.New("usl: need at least 4 DISTINCT concurrency levels")
	}
	return nil
}

// guntherSeed produces a closed-form starting estimate.
//
// γ₀: X(N)/N = γ/(1+…) is maximised at N=1 (=γ), so max_i X_i/N_i is a good
// lower-bound seed for γ that equals γ exactly at a noise-free N=1 sample.
//
// α₀,β₀: with C(N)=X(N)/γ₀, the USL rearranges to N/C(N)−1 = (N−1)(α+βN), so
// y = (N/C(N)−1)/(N−1) is linear in N for N>1 → OLS gives intercept α₀, slope β₀.
// (γ is re-fit as a free parameter in the refine, so the seed's sensitivity to
// the single X(1) sample only affects convergence, not the final estimate —
// S7 review LOW-5.)
func guntherSeed(samples []Sample) (gamma0, alpha0, beta0 float64) {
	gamma0 = 0
	for _, s := range samples {
		if r := s.Throughput / float64(s.N); r > gamma0 {
			gamma0 = r
		}
	}
	if gamma0 <= 0 {
		gamma0 = 1
	}

	// OLS of y on N over the N>1 points.
	var sx, sy, sxx, sxy float64
	var k float64
	for _, s := range samples {
		if s.N <= 1 {
			continue
		}
		n := float64(s.N)
		c := s.Throughput / gamma0
		if c <= 0 {
			continue
		}
		y := (n/c - 1) / (n - 1)
		sx += n
		sy += y
		sxx += n * n
		sxy += n * y
		k++
	}
	if k >= 2 {
		den := k*sxx - sx*sx
		if den != 0 {
			beta0 = (k*sxy - sx*sy) / den
			alpha0 = (sy - beta0*sx) / k
		}
	}
	alpha0 = math.Max(alpha0, 0)
	beta0 = math.Max(beta0, 0)
	return gamma0, alpha0, beta0
}

// ssr is the sum of squared residuals of the USL at (γ,α,β)=x over the samples,
// with γ>0 and α,β≥0 enforced so the optimiser stays in the physical region.
func ssr(x []float64, samples []Sample) float64 {
	g := x[0]
	if g <= 0 {
		g = 1e-12
	}
	a := math.Max(x[1], 0)
	b := math.Max(x[2], 0)
	var sum float64
	for _, s := range samples {
		n := float64(s.N)
		denom := 1 + a*(n-1) + b*n*(n-1)
		pred := g * n / denom
		d := pred - s.Throughput
		sum += d * d
	}
	return sum
}

// rSquared is 1 − SSR/SST; 0 when the data has no variance.
func rSquared(f Fit, samples []Sample) float64 {
	var mean float64
	for _, s := range samples {
		mean += s.Throughput
	}
	mean /= float64(len(samples))

	var ssRes, ssTot float64
	for _, s := range samples {
		pred := f.Predict(float64(s.N))
		ssRes += (s.Throughput - pred) * (s.Throughput - pred)
		ssTot += (s.Throughput - mean) * (s.Throughput - mean)
	}
	if ssTot == 0 {
		return 0
	}
	return 1 - ssRes/ssTot
}
