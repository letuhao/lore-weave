package pager

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestBuildEventBody(t *testing.T) {
	b, err := buildEventBody("rk-123", "dep-1", "burn breach")
	if err != nil {
		t.Fatal(err)
	}
	var ev pagerEvent
	if err := json.Unmarshal(b, &ev); err != nil {
		t.Fatal(err)
	}
	if ev.RoutingKey != "rk-123" {
		t.Fatalf("routing_key = %s", ev.RoutingKey)
	}
	if ev.EventAction != "trigger" {
		t.Fatalf("event_action = %s", ev.EventAction)
	}
	if ev.DedupKey != "canary-abort:dep-1" {
		t.Fatalf("dedup_key = %s (must coalesce a flapping abort into one incident)", ev.DedupKey)
	}
	if ev.Payload.Severity != "critical" || ev.Payload.Source != "canary-controller" {
		t.Fatalf("payload meta wrong: %+v", ev.Payload)
	}
	if !strings.Contains(ev.Payload.Summary, "dep-1") || !strings.Contains(ev.Payload.Summary, "burn breach") {
		t.Fatalf("summary missing context: %s", ev.Payload.Summary)
	}
	if ev.Payload.CustomDetails["deploy_id"] != "dep-1" {
		t.Fatalf("custom_details deploy_id = %v", ev.Payload.CustomDetails["deploy_id"])
	}
}

func TestPageSRERequestShape(t *testing.T) {
	var gotMethod, gotPath string
	var ev pagerEvent
	status := http.StatusAccepted
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod, gotPath = r.Method, r.URL.Path
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &ev)
		w.WriteHeader(status)
	}))
	defer srv.Close()

	p := NewPagerDutyPager(srv.URL+"/", "rk-xyz") // trailing slash trimmed
	if err := p.PageSRE(context.Background(), "dep-5", "stage 0 error"); err != nil {
		t.Fatal(err)
	}
	if gotMethod != http.MethodPost || gotPath != "/v2/enqueue" {
		t.Fatalf("method/path = %s %s", gotMethod, gotPath)
	}
	if ev.RoutingKey != "rk-xyz" || ev.Payload.CustomDetails["reason"] != "stage 0 error" {
		t.Fatalf("event wrong: %+v", ev)
	}
	// Non-202 must surface (a dropped page on auto-abort is a sev incident).
	status = http.StatusBadRequest
	if err := p.PageSRE(context.Background(), "dep-5", "x"); err == nil {
		t.Fatal("400 must error")
	}
}
