package cohort_router

import (
	"context"
	"testing"

	"github.com/loreweave/foundation/services/canary-controller/internal/canary"
)

func mkSource() *StaticSource {
	return &StaticSource{Realities: []Reality{
		{RealityID: "r-c0", DeployCohort: 0, Tier: "free", Status: "active"},
		{RealityID: "r-c5", DeployCohort: 5, Tier: "paid", Status: "active"},
		{RealityID: "r-c30", DeployCohort: 30, Tier: "premium", Status: "active"},
		{RealityID: "r-c75", DeployCohort: 75, Tier: "free", Status: "active"},
		{RealityID: "r-frozen", DeployCohort: 0, Tier: "free", Status: "frozen"}, // not active
	}}
}

func TestRouter_New_NilSource(t *testing.T) {
	if _, err := New(nil); err == nil {
		t.Fatal("New(nil) must error")
	}
}

func TestRealitiesInStage_1pct(t *testing.T) {
	r, _ := New(mkSource())
	got, err := r.RealitiesInStage(context.Background(), canary.Stage1pct)
	if err != nil {
		t.Fatal(err)
	}
	// Only cohort 0 in 1% band; frozen cohort-0 reality excluded.
	if len(got) != 1 || got[0].RealityID != "r-c0" {
		t.Fatalf("got %+v want [r-c0]", got)
	}
}

func TestRealitiesInStage_10pct_IncludesLowerBands(t *testing.T) {
	r, _ := New(mkSource())
	got, err := r.RealitiesInStage(context.Background(), canary.Stage10pct)
	if err != nil {
		t.Fatal(err)
	}
	// cohort 0 (1%) + cohort 5 (10% band) live; sorted by cohort.
	if len(got) != 2 || got[0].RealityID != "r-c0" || got[1].RealityID != "r-c5" {
		t.Fatalf("got %+v want [r-c0 r-c5]", got)
	}
}

func TestRealitiesInStage_Full_AllActive(t *testing.T) {
	r, _ := New(mkSource())
	got, err := r.RealitiesInStage(context.Background(), canary.StageFull)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 4 {
		t.Fatalf("got %d realities want 4 (all active across cohorts)", len(got))
	}
	// deterministic sort by cohort
	wantOrder := []string{"r-c0", "r-c5", "r-c30", "r-c75"}
	for i, w := range wantOrder {
		if got[i].RealityID != w {
			t.Errorf("pos %d = %s want %s", i, got[i].RealityID, w)
		}
	}
}

func TestRealitiesInStage_Internal_NoRealities(t *testing.T) {
	r, _ := New(mkSource())
	got, _ := r.RealitiesInStage(context.Background(), canary.StageInternal)
	if len(got) != 0 {
		t.Errorf("internal stage must route no realities, got %d", len(got))
	}
}

func TestCohortsInStage_Distinct(t *testing.T) {
	src := mkSource()
	src.Realities = append(src.Realities, Reality{RealityID: "r-c5b", DeployCohort: 5, Tier: "free", Status: "active"})
	r, _ := New(src)
	got, err := r.CohortsInStage(context.Background(), canary.Stage10pct)
	if err != nil {
		t.Fatal(err)
	}
	// cohorts 0 and 5 (5 appears twice but distinct).
	if len(got) != 2 || got[0] != 0 || got[1] != 5 {
		t.Fatalf("got %v want [0 5]", got)
	}
}
