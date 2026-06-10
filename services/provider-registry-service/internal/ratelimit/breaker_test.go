package ratelimit

import (
	"testing"
	"time"
)

const cooldown = 30 * time.Second

// ── decideAllow ────────────────────────────────────────────────────────────

func TestDecideAllow_ClosedAllows(t *testing.T) {
	eff, allow := decideAllow(StateClosed, 0, 1000, cooldown)
	if !allow || eff != StateClosed {
		t.Fatalf("closed should allow & stay closed; got %s allow=%v", eff, allow)
	}
}

func TestDecideAllow_OpenRejectsWithinCooldown(t *testing.T) {
	opened := int64(1000)
	now := opened + cooldown.Milliseconds() - 1 // still inside cooldown
	eff, allow := decideAllow(StateOpen, opened, now, cooldown)
	if allow || eff != StateOpen {
		t.Fatalf("open within cooldown must reject & stay open; got %s allow=%v", eff, allow)
	}
}

func TestDecideAllow_OpenToHalfOpenAfterCooldown(t *testing.T) {
	opened := int64(1000)
	now := opened + cooldown.Milliseconds() // cooldown elapsed
	eff, allow := decideAllow(StateOpen, opened, now, cooldown)
	if !allow || eff != StateHalfOpen {
		t.Fatalf("open after cooldown must allow a probe & become half_open; got %s allow=%v", eff, allow)
	}
}

func TestDecideAllow_HalfOpenAllows(t *testing.T) {
	eff, allow := decideAllow(StateHalfOpen, 1000, 9999, cooldown)
	if !allow || eff != StateHalfOpen {
		t.Fatalf("half_open must allow the probe; got %s allow=%v", eff, allow)
	}
}

// ── decideRecord ───────────────────────────────────────────────────────────

func TestDecideRecord_SuccessCloses(t *testing.T) {
	st, nf, oa := decideRecord(StateClosed, 2, 3, true, 5000)
	if st != StateClosed || nf != 0 || oa != 0 {
		t.Fatalf("success must reset to closed/0; got %s %d %d", st, nf, oa)
	}
}

func TestDecideRecord_FailureBelowThresholdStaysClosed(t *testing.T) {
	st, nf, _ := decideRecord(StateClosed, 1, 3, false, 5000)
	if st != StateClosed || nf != 2 {
		t.Fatalf("below threshold stays closed, count bumps; got %s %d", st, nf)
	}
}

func TestDecideRecord_FailureAtThresholdOpens(t *testing.T) {
	st, nf, oa := decideRecord(StateClosed, 2, 3, false, 5000)
	if st != StateOpen || nf != 3 || oa != 5000 {
		t.Fatalf("reaching threshold opens & stamps opened_at; got %s %d %d", st, nf, oa)
	}
}

func TestDecideRecord_HalfOpenProbeFailureReopens(t *testing.T) {
	st, _, oa := decideRecord(StateHalfOpen, 0, 3, false, 7000)
	if st != StateOpen || oa != 7000 {
		t.Fatalf("half_open probe failure must re-open immediately; got %s oa=%d", st, oa)
	}
}

func TestDecideRecord_HalfOpenProbeSuccessCloses(t *testing.T) {
	st, nf, _ := decideRecord(StateHalfOpen, 5, 3, true, 7000)
	if st != StateClosed || nf != 0 {
		t.Fatalf("half_open probe success must close; got %s %d", st, nf)
	}
}
