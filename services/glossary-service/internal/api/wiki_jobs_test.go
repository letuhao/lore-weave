package api

// wiki-llm M7b — tests for the wiki-gen job-proxy CLIENT calls (the glossary→
// knowledge hop). These need no DB: they pin URL construction, the internal
// token header, request body, and status/body PROPAGATION against an httptest
// knowledge stub. The owner-gated HTTP handlers wrapping these are exercised by
// the cross-service live-smoke (they additionally need GLOSSARY_TEST_DB_URL for
// verifyBookOwner).

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/config"
)

func newJobProxyServer(knowledgeURL string) *Server {
	return NewServer(nil, &config.Config{
		JWTSecret:            "test_jwt_secret_at_least_32_characters_long",
		KnowledgeServiceURL:  knowledgeURL,
		InternalServiceToken: "tok-internal",
	})
}

func TestGetWikiGenJob_PropagatesStatusAndBuildsURL(t *testing.T) {
	book, user := uuid.New(), uuid.New()
	var gotPath, gotQuery, gotToken, gotMethod string
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath, gotQuery, gotToken, gotMethod = r.URL.Path, r.URL.Query().Get("user_id"), r.Header.Get("X-Internal-Token"), r.Method
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"running","items_processed":2}`))
	}))
	defer stub.Close()

	srv := newJobProxyServer(stub.URL)
	status, body, err := srv.getWikiGenJob(context.Background(), book, user)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if status != http.StatusOK {
		t.Fatalf("status: want 200, got %d", status)
	}
	if gotMethod != http.MethodGet {
		t.Fatalf("method: want GET, got %s", gotMethod)
	}
	if want := "/internal/knowledge/books/" + book.String() + "/wiki/job"; gotPath != want {
		t.Fatalf("path: want %s, got %s", want, gotPath)
	}
	if gotQuery != user.String() {
		t.Fatalf("user_id query: want %s, got %s", user, gotQuery)
	}
	if gotToken != "tok-internal" {
		t.Fatalf("internal token: want tok-internal, got %q", gotToken)
	}
	var parsed map[string]any
	if err := json.Unmarshal(body, &parsed); err != nil || parsed["status"] != "running" {
		t.Fatalf("body not propagated verbatim: %s", body)
	}
}

func TestGetWikiGenJob_Propagates404(t *testing.T) {
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"detail":"no_job"}`))
	}))
	defer stub.Close()
	srv := newJobProxyServer(stub.URL)
	status, _, err := srv.getWikiGenJob(context.Background(), uuid.New(), uuid.New())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if status != http.StatusNotFound {
		t.Fatalf("status: want 404 (no-job forwarded verbatim), got %d", status)
	}
}

func TestWikiGenJobAction_ResumeBuildsURLAndBody(t *testing.T) {
	book, user, job := uuid.New(), uuid.New(), uuid.New()
	var gotPath, gotUserID string
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		raw, _ := io.ReadAll(r.Body)
		var b map[string]any
		_ = json.Unmarshal(raw, &b)
		gotUserID, _ = b["user_id"].(string)
		w.WriteHeader(http.StatusAccepted)
		_, _ = w.Write([]byte(`{"status":"pending"}`))
	}))
	defer stub.Close()

	srv := newJobProxyServer(stub.URL)
	status, _, err := srv.wikiGenJobAction(context.Background(), book, user, job, "resume")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if status != http.StatusAccepted {
		t.Fatalf("status: want 202, got %d", status)
	}
	if want := "/internal/knowledge/books/" + book.String() + "/wiki/job/" + job.String() + "/resume"; gotPath != want {
		t.Fatalf("path: want %s, got %s", want, gotPath)
	}
	if gotUserID != user.String() {
		t.Fatalf("body user_id: want %s, got %s", user, gotUserID)
	}
}

func TestWikiGenJobAction_CancelPropagates409(t *testing.T) {
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if want := "/cancel"; r.URL.Path[len(r.URL.Path)-len(want):] != want {
			t.Errorf("expected a /cancel path, got %s", r.URL.Path)
		}
		w.WriteHeader(http.StatusConflict)
		_, _ = w.Write([]byte(`{"detail":"not_cancellable"}`))
	}))
	defer stub.Close()
	srv := newJobProxyServer(stub.URL)
	status, _, err := srv.wikiGenJobAction(context.Background(), uuid.New(), uuid.New(), uuid.New(), "cancel")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if status != http.StatusConflict {
		t.Fatalf("status: want 409 forwarded, got %d", status)
	}
}

// Route wiring + auth gate (no DB): an unauthenticated request reaches
// requireUserID (which runs before verifyBookOwner touches the pool) → 401,
// proving the three /wiki/job routes are registered and gated.
func TestWikiGenJobRoutes_RequireAuth(t *testing.T) {
	srv := newJobProxyServer("http://unused")
	book, job := uuid.New().String(), uuid.New().String()
	cases := []struct {
		method, path string
	}{
		{http.MethodGet, "/v1/glossary/books/" + book + "/wiki/job"},
		{http.MethodPost, "/v1/glossary/books/" + book + "/wiki/job/" + job + "/resume"},
		{http.MethodPost, "/v1/glossary/books/" + book + "/wiki/job/" + job + "/cancel"},
	}
	for _, c := range cases {
		req := httptest.NewRequest(c.method, c.path, nil)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusUnauthorized {
			t.Fatalf("%s %s: want 401 (registered+gated), got %d", c.method, c.path, w.Code)
		}
	}
}

func TestWikiGenJob_NotConfiguredErrors(t *testing.T) {
	srv := newJobProxyServer("") // knowledge-service URL unset
	if _, _, err := srv.getWikiGenJob(context.Background(), uuid.New(), uuid.New()); err == nil {
		t.Fatal("getWikiGenJob: expected error when knowledge-service unconfigured")
	}
	if _, _, err := srv.wikiGenJobAction(context.Background(), uuid.New(), uuid.New(), uuid.New(), "resume"); err == nil {
		t.Fatal("wikiGenJobAction: expected error when knowledge-service unconfigured")
	}
}
