package usl

// G2 (structural perf-shape gate) — the COMPLEXITY-EXPONENT view, complementary
// to the USL throughput fit. Where FitUSL measures throughput SATURATION
// (contention/coherency), this measures whether per-operation TIME stays roughly
// flat as load N grows, or creeps super-linear — the signature of an O(1)→O(n)
// regression a higher layer can introduce (an N+1, a per-item lock, a per-event
// network round-trip).
//
// We gate the fitted LOG-LOG SLOPE (the power-law exponent p in time ≈ c·N^p),
// NOT the USL γ (`/review-impl` plan finding F9): USL γ/α/β model contention
// saturation, not polynomial blow-up, so γ is the wrong signal for algorithmic
// complexity. The slope is fitted by OLS over ALL sweep points (F8 — not a
// 2-point secant that would average out a high-N bulge).

import (
	"errors"
	"math"
)

// LoadTimePoint is one measured (load/concurrency N, per-operation time) point.
// Distinct from Sample (throughput): here Time is a LATENCY-like quantity in any
// consistent unit, and we fit its growth exponent vs N.
type LoadTimePoint struct {
	N    int     `json:"n"`
	Time float64 `json:"time"`
}

// SlopeFit is the fitted power law time ≈ c·N^p: Exponent is p (the gated
// signal), Intercept is log(c), R2 the log-log goodness-of-fit, Points the count
// of usable points.
type SlopeFit struct {
	Exponent  float64 `json:"exponent"`
	Intercept float64 `json:"intercept"`
	R2        float64 `json:"r2"`
	Points    int     `json:"points"`
}

// FitComplexityExponent fits p by ordinary least squares of log(time) on log(N)
// over EVERY usable point (F8). Requires ≥3 DISTINCT positive N with positive,
// finite time. Errors otherwise (a 2-point line is not a trend).
func FitComplexityExponent(points []LoadTimePoint) (SlopeFit, error) {
	var xs, ys []float64
	distinct := map[int]struct{}{}
	for _, p := range points {
		if p.N < 1 || p.Time <= 0 || math.IsNaN(p.Time) || math.IsInf(p.Time, 0) {
			continue
		}
		xs = append(xs, math.Log(float64(p.N)))
		ys = append(ys, math.Log(p.Time))
		distinct[p.N] = struct{}{}
	}
	if len(distinct) < 3 {
		return SlopeFit{}, errors.New("usl: need >=3 distinct positive N (with positive time) for a log-log slope")
	}

	n := float64(len(xs))
	var sx, sy, sxx, sxy float64
	for i := range xs {
		sx += xs[i]
		sy += ys[i]
		sxx += xs[i] * xs[i]
		sxy += xs[i] * ys[i]
	}
	den := n*sxx - sx*sx
	if den == 0 {
		// All log(N) identical despite ≥3 distinct N is impossible, but guard the
		// division regardless (defense in depth).
		return SlopeFit{}, errors.New("usl: degenerate log-log abscissa")
	}
	slope := (n*sxy - sx*sy) / den
	intercept := (sy - slope*sx) / n

	meanY := sy / n
	var ssRes, ssTot float64
	for i := range xs {
		pred := slope*xs[i] + intercept
		ssRes += (ys[i] - pred) * (ys[i] - pred)
		ssTot += (ys[i] - meanY) * (ys[i] - meanY)
	}
	r2 := 0.0
	if ssTot != 0 {
		r2 = 1 - ssRes/ssTot
	}
	return SlopeFit{Exponent: slope, Intercept: intercept, R2: r2, Points: len(xs)}, nil
}

// WithinBand reports whether the fitted exponent is within the allowed band
// p ≤ 1 + eps. This is the GENERIC band form used by the unit proof
// (`slope_test.go`, eps=0.20 → a 1.20 ceiling, against which a clean p≈0.80 sits
// in-band and a realistic super-linear bite p≈1.30 exits).
//
// The LIVE gate (`scripts/perf/w5-usl-exponent-band.sh --live`) uses a CALIBRATED
// absolute ceiling instead of 1+eps: D-G2-USL-BAND-CALIBRATE was cleared
// 2026-06-15 by a pgbench append-latency-vs-concurrency sweep that measured a
// healthy baseline exponent ≈0.15 (run-to-run stdev ≈0.01); the live ceiling is
// committed at 0.50 (≈3× baseline, well below linear) to absorb cross-rig
// baseline drift while still firing on an O(1)→O(n) creep. See that script's
// header for the full calibration provenance + the --calibrate reproduction mode.
func (s SlopeFit) WithinBand(eps float64) bool {
	return s.Exponent <= 1.0+eps
}
