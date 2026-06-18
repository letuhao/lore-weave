package sli

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/loreweave/foundation/services/canary-controller/internal/canary"
)

func TestBuildQuery(t *testing.T) {
	q := buildQuery("dep-1", canary.Stage10pct)
	if !strings.Contains(q, `deploy_id="dep-1"`) || !strings.Contains(q, `stage="2"`) {
		t.Fatalf("query missing labels: %s", q)
	}
	if !strings.HasPrefix(q, "lw_canary_sli_cohort{") {
		t.Fatalf("query metric name wrong: %s", q)
	}
}

func TestParseInstantScalar(t *testing.T) {
	ok := []byte(`{"status":"success","data":{"resultType":"vector","result":[{"metric":{},"value":[1717000000,"0.0123"]}]}}`)
	if v, err := parseInstantScalar(200, ok); err != nil || v != 0.0123 {
		t.Fatalf("ok vector -> 0.0123, got (%v,%v)", v, err)
	}
	if _, err := parseInstantScalar(500, []byte("boom")); err == nil {
		t.Fatal("non-200 must error")
	}
	if _, err := parseInstantScalar(200, []byte(`{"status":"error","errorType":"bad_data","error":"oops"}`)); err == nil {
		t.Fatal("status!=success must error")
	}
	empty := []byte(`{"status":"success","data":{"resultType":"vector","result":[]}}`)
	if _, err := parseInstantScalar(200, empty); err == nil {
		t.Fatal("empty result MUST error (a missing series must not read as 0 burn)")
	}
	if _, err := parseInstantScalar(200, []byte("{not json")); err == nil {
		t.Fatal("bad JSON must error")
	}
	badVal := []byte(`{"status":"success","data":{"result":[{"value":[1,"NaNaN"]}]}}`)
	if _, err := parseInstantScalar(200, badVal); err == nil {
		t.Fatal("unparseable scalar must error")
	}
}

func TestObserveRequestShape(t *testing.T) {
	var gotPath, gotQuery string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotQuery = r.URL.Query().Get("query")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"success","data":{"resultType":"vector","result":[{"value":[1717000000,"0.5"]}]}}`))
	}))
	defer srv.Close()

	fixed := time.Date(2026, 6, 3, 14, 0, 0, 0, time.UTC)
	src := NewPrometheusSource(srv.URL+"/", func() time.Time { return fixed }) // trailing slash trimmed
	obs, err := src.Observe(context.Background(), "dep-9", canary.Stage1pct)
	if err != nil {
		t.Fatal(err)
	}
	if gotPath != "/api/v1/query" {
		t.Fatalf("path = %s, want /api/v1/query", gotPath)
	}
	if !strings.Contains(gotQuery, `deploy_id="dep-9"`) {
		t.Fatalf("query param missing deploy label: %s", gotQuery)
	}
	// Both fields populated from the single series; Now from the injected clock.
	if obs.CohortBurn != 0.5 || obs.ErrorRate != 0.5 {
		t.Fatalf("burn/err = %v/%v, want 0.5/0.5", obs.CohortBurn, obs.ErrorRate)
	}
	if !obs.Now.Equal(fixed) {
		t.Fatalf("Now = %s, want injected %s", obs.Now, fixed)
	}
}

func TestObserveServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
	}))
	defer srv.Close()
	src := NewPrometheusSource(srv.URL, nil)
	if _, err := src.Observe(context.Background(), "d", canary.Stage1pct); err == nil {
		t.Fatal("502 from prometheus must surface as an error")
	}
}
