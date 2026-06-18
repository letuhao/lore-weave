package tracing

import (
	"crypto/rand"
	"encoding/binary"
	"sync/atomic"
)

// SamplingDecision is the typed outcome of Sampler.ShouldSample.
type SamplingDecision int

const (
	// SamplingDrop — span MUST NOT be exported. Sampled bit cleared.
	SamplingDrop SamplingDecision = iota
	// SamplingRecord — span exported but parent sampled bit unchanged.
	// Reserved for V2+ when we wire OTel record-only semantics.
	SamplingRecord
	// SamplingRecordAndSample — span exported AND sampled bit set so
	// downstream services see and continue the sample.
	SamplingRecordAndSample
)

// String returns the lowercase wire-form.
func (d SamplingDecision) String() string {
	switch d {
	case SamplingDrop:
		return "drop"
	case SamplingRecord:
		return "record"
	case SamplingRecordAndSample:
		return "record_and_sample"
	}
	return "invalid"
}

// SamplingHint is per-call context that overrides the default rate.
// Used by:
//
//   - SEV0/SEV1 alert paths (force sample for postmortem reconstruction)
//   - Admin-cli debug mode (force sample via header)
//   - Cycle-7 chaos drills (force sample for fault injection forensics)
type SamplingHint struct {
	// Force=true bypasses the rate check and ALWAYS samples.
	// Cycle 19 L4.H: SEV0/SEV1 set Force=true (100% sampling).
	Force bool

	// Drop=true bypasses the rate check and NEVER samples.
	// Used to suppress noisy health checks.
	Drop bool
}

// Sampler decides whether a span is exported.
type Sampler interface {
	// ShouldSample is called once per span start with the parent
	// context (if any — tc.IsZero() for a brand new trace), the
	// proposed span name, and an optional hint.
	//
	// MUST be allocation-bounded — hot path.
	ShouldSample(parent TraceContext, spanName string, hint SamplingHint) SamplingDecision
}

// AlwaysOnSampler is the simplest sampler — always samples. Useful for
// tests + dev environments. Production SHOULD use ProbabilisticSampler.
type AlwaysOnSampler struct{}

// ShouldSample always returns SamplingRecordAndSample.
func (AlwaysOnSampler) ShouldSample(_ TraceContext, _ string, _ SamplingHint) SamplingDecision {
	return SamplingRecordAndSample
}

// AlwaysOffSampler never samples. Used to disable tracing entirely.
type AlwaysOffSampler struct{}

// ShouldSample always returns SamplingDrop.
func (AlwaysOffSampler) ShouldSample(_ TraceContext, _ string, _ SamplingHint) SamplingDecision {
	return SamplingDrop
}

// ProbabilisticSampler samples a fixed fraction of spans.
//
// rate ∈ [0.0, 1.0]: 0.01 = 1% baseline (cycle 19 L4.H prod default).
// hint.Force=true → ALWAYS sample. hint.Drop=true → NEVER sample.
//
// If a parent context is sampled, we INHERIT the parent decision (so the
// trace stays contiguous). This is the W3C-recommended pattern.
type ProbabilisticSampler struct {
	// rate is fixed at construction.
	rate uint64 // rate as uint64 in [0, MaxUint64]: 1% ≈ MaxUint64/100

	// decisions counts (drop, record_and_sample) for the metric
	// `lw_trace_sampling_decisions_total`.
	dropped atomic.Uint64
	sampled atomic.Uint64
}

// NewProbabilisticSampler constructs a ProbabilisticSampler. rateFraction
// must be in [0.0, 1.0]; out-of-range values are clamped.
func NewProbabilisticSampler(rateFraction float64) *ProbabilisticSampler {
	if rateFraction < 0 {
		rateFraction = 0
	}
	if rateFraction > 1 {
		rateFraction = 1
	}
	// Convert fraction to uint64 threshold: random u64 < threshold → sample.
	// Note: float64(maxU64) is not exactly representable; casting back to
	// uint64 from a near-MaxU64 float can overflow to 0. Treat full-rate
	// as a special case (threshold = MaxU64) so 100% is honored.
	const maxU64 = uint64(0xFFFFFFFFFFFFFFFF)
	var threshold uint64
	if rateFraction >= 1.0 {
		threshold = maxU64
	} else if rateFraction <= 0.0 {
		threshold = 0
	} else {
		threshold = uint64(rateFraction * float64(maxU64))
	}
	return &ProbabilisticSampler{rate: threshold}
}

// ShouldSample applies the probability + hint policy.
func (p *ProbabilisticSampler) ShouldSample(parent TraceContext, _ string, hint SamplingHint) SamplingDecision {
	if hint.Force {
		p.sampled.Add(1)
		return SamplingRecordAndSample
	}
	if hint.Drop {
		p.dropped.Add(1)
		return SamplingDrop
	}
	if !parent.IsZero() && parent.Sampled() {
		// Inherit parent sample decision.
		p.sampled.Add(1)
		return SamplingRecordAndSample
	}
	// Fast paths to avoid RNG calls on extreme rates.
	if p.rate == 0 {
		p.dropped.Add(1)
		return SamplingDrop
	}
	const maxU64 = uint64(0xFFFFFFFFFFFFFFFF)
	if p.rate == maxU64 {
		p.sampled.Add(1)
		return SamplingRecordAndSample
	}
	// Random u64.
	var buf [8]byte
	if _, err := rand.Read(buf[:]); err != nil {
		// Fail-safe: on RNG failure, sample (better to over-sample than
		// silently drop traces during an incident).
		p.sampled.Add(1)
		return SamplingRecordAndSample
	}
	u := binary.LittleEndian.Uint64(buf[:])
	if u < p.rate {
		p.sampled.Add(1)
		return SamplingRecordAndSample
	}
	p.dropped.Add(1)
	return SamplingDrop
}

// Stats returns (dropped, sampled) counts. Test + metric helper.
func (p *ProbabilisticSampler) Stats() (dropped, sampled uint64) {
	return p.dropped.Load(), p.sampled.Load()
}
