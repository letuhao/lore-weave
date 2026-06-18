package canary

import (
	"testing"
	"time"
)

var t0 = time.Date(2026, 5, 30, 10, 0, 0, 0, time.UTC)

func TestStageTable_WindowsMatchSpec(t *testing.T) {
	cases := map[Stage]time.Duration{
		StageInternal: 10 * time.Minute,
		Stage1pct:     30 * time.Minute,
		Stage10pct:    2 * time.Hour,
		Stage50pct:    4 * time.Hour,
		StageFull:     0,
	}
	for st, want := range cases {
		if got := MonitorWindow(st); got != want {
			t.Errorf("stage %d window = %s want %s", st, got, want)
		}
	}
}

func TestDecide_Stage0_HoldBeforeWindow(t *testing.T) {
	st := State{Stage: StageInternal, StageEnteredAt: t0}
	d := Decide(st, Observation{ErrorRate: 0, Now: t0.Add(5 * time.Minute)})
	if d.Action != ActionHold {
		t.Errorf("action = %s want hold (5m of 10m window)", d.Action)
	}
}

func TestDecide_Stage0_AdvanceAtWindow(t *testing.T) {
	st := State{Stage: StageInternal, StageEnteredAt: t0}
	d := Decide(st, Observation{ErrorRate: 0, Now: t0.Add(10 * time.Minute)})
	if d.Action != ActionAdvance || d.NextStage != Stage1pct {
		t.Errorf("action = %s next = %d want advance→1", d.Action, d.NextStage)
	}
}

func TestDecide_Stage0_AbortOnAnyError(t *testing.T) {
	st := State{Stage: StageInternal, StageEnteredAt: t0}
	// Even past the window, a nonzero error rate aborts stage 0.
	d := Decide(st, Observation{ErrorRate: 0.001, Now: t0.Add(20 * time.Minute)})
	if d.Action != ActionAbort {
		t.Errorf("action = %s want abort (stage-0 error rate > 0)", d.Action)
	}
}

func TestDecide_Stage1_AdvanceWhenHealthy(t *testing.T) {
	st := State{Stage: Stage1pct, StageEnteredAt: t0, BaselineBurn: 0.5}
	d := Decide(st, Observation{CohortBurn: 0.6, Now: t0.Add(30 * time.Minute)})
	if d.Action != ActionAdvance || d.NextStage != Stage10pct {
		t.Errorf("action = %s next = %d want advance→2 (burn 0.6 < 1.0 threshold)", d.Action, d.NextStage)
	}
}

func TestDecide_Stage1_AbortOnBurnOver2xBaseline(t *testing.T) {
	st := State{Stage: Stage1pct, StageEnteredAt: t0, BaselineBurn: 0.5}
	// baseline 0.5 × 2 = 1.0 threshold; burn 1.01 breaches → abort even early.
	d := Decide(st, Observation{CohortBurn: 1.01, Now: t0.Add(2 * time.Minute)})
	if d.Action != ActionAbort {
		t.Fatalf("action = %s want abort (burn 1.01 > 2× baseline 1.0)", d.Action)
	}
	if d.Reason == "" {
		t.Error("abort must carry a reason for audit + paging")
	}
}

func TestDecide_Stage1_AbortPrecedesWindow(t *testing.T) {
	// Burn breach in minute 1 must abort without waiting out the 30m window.
	st := State{Stage: Stage1pct, StageEnteredAt: t0, BaselineBurn: 1.0}
	d := Decide(st, Observation{CohortBurn: 2.5, Now: t0.Add(1 * time.Minute)})
	if d.Action != ActionAbort {
		t.Errorf("action = %s want abort (precedes window)", d.Action)
	}
}

func TestDecide_Stage1_AtExactly2xBaseline_DoesNotAbort(t *testing.T) {
	// §12AH.4 says burn > 2× baseline; exactly 2× is the boundary and holds.
	st := State{Stage: Stage1pct, StageEnteredAt: t0, BaselineBurn: 0.5}
	d := Decide(st, Observation{CohortBurn: 1.0, Now: t0.Add(5 * time.Minute)})
	if d.Action == ActionAbort {
		t.Errorf("burn == 2× baseline must NOT abort (strict >)")
	}
}

func TestDecide_Full_Complete(t *testing.T) {
	st := State{Stage: StageFull, StageEnteredAt: t0}
	d := Decide(st, Observation{Now: t0.Add(time.Hour)})
	if d.Action != ActionComplete {
		t.Errorf("action = %s want complete", d.Action)
	}
}

func TestDecide_AlreadyAborted(t *testing.T) {
	st := State{Stage: Stage10pct, StageEnteredAt: t0, Aborted: true}
	d := Decide(st, Observation{Now: t0})
	if d.Action != ActionAbort {
		t.Errorf("action = %s want abort (sticky)", d.Action)
	}
}

func TestDecide_FullProgression(t *testing.T) {
	// Walk a healthy deploy through all stages.
	st := State{Stage: StageInternal, StageEnteredAt: t0, BaselineBurn: 0.4}
	now := t0
	wantNext := []Stage{Stage1pct, Stage10pct, Stage50pct, StageFull}
	for i := 0; st.Stage < StageFull; i++ {
		w := MonitorWindow(st.Stage)
		now = now.Add(w)
		d := Decide(st, Observation{CohortBurn: 0.5, ErrorRate: 0, Now: now})
		if d.Action != ActionAdvance {
			t.Fatalf("stage %d: action = %s want advance", st.Stage, d.Action)
		}
		if d.NextStage != wantNext[i] {
			t.Fatalf("stage %d: next = %d want %d", st.Stage, d.NextStage, wantNext[i])
		}
		st.Stage = d.NextStage
		st.StageEnteredAt = now
	}
	final := Decide(st, Observation{Now: now})
	if final.Action != ActionComplete {
		t.Errorf("final action = %s want complete", final.Action)
	}
}

func TestCohortInStage(t *testing.T) {
	cases := []struct {
		cohort int
		stage  Stage
		want   bool
	}{
		{0, StageInternal, false}, // internal includes no realities
		{0, Stage1pct, true},      // cohort 0 in the 1% band
		{5, Stage1pct, false},     // cohort 5 not yet (10% band)
		{5, Stage10pct, true},     // cohort 5 in 10% band at stage 2
		{0, Stage10pct, true},     // lower bands stay live as we advance
		{30, Stage50pct, true},    // cohort 30 in 50% band
		{30, Stage10pct, false},   // not yet at stage 2
		{75, StageFull, true},     // cohort 75 only live at 100%
		{75, Stage50pct, false},
		{100, StageFull, false}, // out of range
		{-1, StageFull, false},
	}
	for _, c := range cases {
		if got := CohortInStage(c.cohort, c.stage); got != c.want {
			t.Errorf("CohortInStage(%d, %d) = %v want %v", c.cohort, c.stage, got, c.want)
		}
	}
}
