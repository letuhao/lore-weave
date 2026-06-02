package executor

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/loreweave/foundation/services/canary-controller/internal/canary"
)

func TestNewGitHubExecutorValidation(t *testing.T) {
	if _, err := NewGitHubExecutor("", "no-slash", "tok"); err == nil {
		t.Fatal("repo without owner/repo must error")
	}
	if _, err := NewGitHubExecutor("", "owner/", "tok"); err == nil {
		t.Fatal("empty repo half must error")
	}
	if _, err := NewGitHubExecutor("", "owner/repo", ""); err == nil {
		t.Fatal("empty token must error (no unauthenticated dispatch)")
	}
	if _, err := NewGitHubExecutor("", "owner/repo", "tok"); err != nil {
		t.Fatalf("valid args: %v", err)
	}
}

func TestBuildDispatchBody(t *testing.T) {
	b, err := buildDispatchBody(eventPromote, map[string]any{"deploy_id": "d1", "stage": 2})
	if err != nil {
		t.Fatal(err)
	}
	var got dispatchBody
	if err := json.Unmarshal(b, &got); err != nil {
		t.Fatal(err)
	}
	if got.EventType != "canary-promote" || got.ClientPayload["deploy_id"] != "d1" {
		t.Fatalf("body wrong: %s", b)
	}
}

func TestPromoteRequestShape(t *testing.T) {
	var gotMethod, gotPath, gotAuth, gotAccept string
	var body dispatchBody
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod, gotPath = r.Method, r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		gotAccept = r.Header.Get("Accept")
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &body)
		w.WriteHeader(http.StatusNoContent) // GitHub: 204 on success
	}))
	defer srv.Close()

	e, err := NewGitHubExecutor(srv.URL, "acme/widgets", "ghp_secret")
	if err != nil {
		t.Fatal(err)
	}
	if err := e.Promote(context.Background(), "dep-7", canary.Stage50pct); err != nil {
		t.Fatal(err)
	}
	if gotMethod != http.MethodPost {
		t.Fatalf("method = %s", gotMethod)
	}
	if gotPath != "/repos/acme/widgets/dispatches" {
		t.Fatalf("path = %s", gotPath)
	}
	if gotAuth != "Bearer ghp_secret" {
		t.Fatalf("auth header = %q", gotAuth)
	}
	if !strings.Contains(gotAccept, "github") {
		t.Fatalf("accept header = %q", gotAccept)
	}
	if body.EventType != "canary-promote" {
		t.Fatalf("event_type = %s", body.EventType)
	}
	if body.ClientPayload["deploy_id"] != "dep-7" {
		t.Fatalf("payload deploy_id = %v", body.ClientPayload["deploy_id"])
	}
	// JSON numbers decode to float64.
	if body.ClientPayload["stage"] != float64(int(canary.Stage50pct)) {
		t.Fatalf("payload stage = %v", body.ClientPayload["stage"])
	}
}

func TestRollbackRequestShapeAndError(t *testing.T) {
	var body dispatchBody
	status := http.StatusNoContent
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &body)
		w.WriteHeader(status)
	}))
	defer srv.Close()

	e, _ := NewGitHubExecutor(srv.URL, "acme/widgets", "tok")
	if err := e.Rollback(context.Background(), "dep-8", "burn breach"); err != nil {
		t.Fatal(err)
	}
	if body.EventType != "canary-rollback" || body.ClientPayload["reason"] != "burn breach" {
		t.Fatalf("rollback body wrong: %+v", body)
	}
	// Non-204 must surface as an error (a failed traffic shift must not look ok).
	status = http.StatusUnprocessableEntity
	if err := e.Rollback(context.Background(), "dep-8", "x"); err == nil {
		t.Fatal("422 must error")
	}
}
