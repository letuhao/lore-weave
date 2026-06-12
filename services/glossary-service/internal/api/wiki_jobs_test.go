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

// M7b-2b — the explicit-entity-id path (single-article regenerate) validates the
// UUIDs (pure) then scopes them to the book via the pool (/review-impl F1); the
// book-scoping query is covered by the cross-service live-smoke. Here we pin the
// pure validation: well-formed ids canonicalize, a malformed one → 400.
func TestParseEntityUUIDs_CanonicalizesValid(t *testing.T) {
	a, b := uuid.New().String(), uuid.New().String()
	ids, err := parseEntityUUIDs([]string{a, b})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(ids) != 2 || ids[0] != a || ids[1] != b {
		t.Fatalf("want [%s %s], got %v", a, b, ids)
	}
}

func TestParseEntityUUIDs_RejectsBadUUID(t *testing.T) {
	_, err := parseEntityUUIDs([]string{uuid.New().String(), "not-a-uuid"})
	if err == nil {
		t.Fatal("expected a badEntityIDError for a malformed id")
	}
	if _, ok := err.(*badEntityIDError); !ok {
		t.Fatalf("want *badEntityIDError (→ 400), got %T", err)
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

// D-WIKI-P2B-COST-ESTIMATE — the cost-config client hop: GET the global knowledge
// endpoint with the internal token and propagate the body verbatim for the FE.
func TestGetWikiGenConfig_BuildsURLAndPropagates(t *testing.T) {
	var gotPath, gotToken, gotMethod string
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath, gotToken, gotMethod = r.URL.Path, r.Header.Get("X-Internal-Token"), r.Method
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"cost_per_article_usd":"0.05"}`))
	}))
	defer stub.Close()

	srv := newJobProxyServer(stub.URL)
	status, body, err := srv.getWikiGenConfig(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if status != http.StatusOK {
		t.Fatalf("status: want 200, got %d", status)
	}
	if gotMethod != http.MethodGet {
		t.Fatalf("method: want GET, got %s", gotMethod)
	}
	if gotPath != "/internal/knowledge/wiki/gen-config" {
		t.Fatalf("path: got %s", gotPath)
	}
	if gotToken != "tok-internal" {
		t.Fatalf("internal token: want tok-internal, got %q", gotToken)
	}
	var parsed map[string]any
	if err := json.Unmarshal(body, &parsed); err != nil || parsed["cost_per_article_usd"] != "0.05" {
		t.Fatalf("body not propagated verbatim: %s", body)
	}
}

func TestGetWikiGenConfig_NotConfiguredErrors(t *testing.T) {
	srv := newJobProxyServer("")
	if _, _, err := srv.getWikiGenConfig(context.Background()); err == nil {
		t.Fatal("getWikiGenConfig: expected error when knowledge-service unconfigured")
	}
}

// Route wiring + auth gate (no DB): unauthenticated → 401 (requireUserID runs
// before verifyBookOwner touches the pool), proving the route is registered+gated.
func TestWikiGenConfigRoute_RequiresAuth(t *testing.T) {
	srv := newJobProxyServer("http://unused")
	req := httptest.NewRequest(http.MethodGet,
		"/v1/glossary/books/"+uuid.New().String()+"/wiki/gen-config", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("want 401 (registered+gated), got %d", w.Code)
	}
}

// D-WIKI-P2-KG-SWEEP — the kg-hashes client hop: POST entity_ids with the owner
// user_id + internal token, parse the {hashes} map. Errors on non-200 (so the sweep
// degrades) and when unconfigured.
func TestFetchKgHashes_BuildsURLBodyAndParses(t *testing.T) {
	book, owner := uuid.New(), uuid.New()
	var gotPath, gotToken string
	var gotBody map[string]any
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath, gotToken = r.URL.Path, r.Header.Get("X-Internal-Token")
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
		_, _ = w.Write([]byte(`{"hashes":{"e1":"h1"}}`))
	}))
	defer stub.Close()

	srv := newJobProxyServer(stub.URL)
	hashes, err := srv.fetchKgHashes(context.Background(), book, owner, []string{"e1", "e2"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if want := "/internal/knowledge/books/" + book.String() + "/wiki/kg-hashes"; gotPath != want {
		t.Fatalf("path: want %s, got %s", want, gotPath)
	}
	if gotToken != "tok-internal" {
		t.Fatalf("internal token: want tok-internal, got %q", gotToken)
	}
	if gotBody["user_id"] != owner.String() {
		t.Fatalf("body user_id: want %s, got %v", owner, gotBody["user_id"])
	}
	if hashes["e1"] != "h1" {
		t.Fatalf("hashes not parsed: %v", hashes)
	}
}

func TestFetchKgHashes_ErrorsOnNon200(t *testing.T) {
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
	}))
	defer stub.Close()
	srv := newJobProxyServer(stub.URL)
	if _, err := srv.fetchKgHashes(context.Background(), uuid.New(), uuid.New(), []string{"e1"}); err == nil {
		t.Fatal("fetchKgHashes: expected error on non-200 (so the sweep degrades)")
	}
}

func TestFetchKgHashes_NotConfiguredErrors(t *testing.T) {
	srv := newJobProxyServer("")
	if _, err := srv.fetchKgHashes(context.Background(), uuid.New(), uuid.New(), []string{"e1"}); err == nil {
		t.Fatal("fetchKgHashes: expected error when knowledge-service unconfigured")
	}
}

// W5 (D-WIKI-PER-STEP-MODEL) — the trigger delegate forwards the optional
// revise-model override (both keys together) only when a revise ref is given.
func TestTriggerWikiGeneration_ForwardsReviseModel(t *testing.T) {
	book, user := uuid.New(), uuid.New()
	var gotBody map[string]any
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
		w.WriteHeader(http.StatusAccepted)
		_, _ = w.Write([]byte(`{"job_id":"j1","status":"pending"}`))
	}))
	defer stub.Close()

	srv := newJobProxyServer(stub.URL)
	st, _, err := srv.triggerWikiGeneration(
		context.Background(), book, user, "user_model", "m1", []string{"e1"}, nil,
		"user_model", "rm")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if st != http.StatusAccepted {
		t.Fatalf("want 202, got %d", st)
	}
	if gotBody["revise_model_ref"] != "rm" {
		t.Fatalf("revise_model_ref not forwarded: %v", gotBody["revise_model_ref"])
	}
	if gotBody["revise_model_source"] != "user_model" {
		t.Fatalf("revise_model_source not forwarded: %v", gotBody["revise_model_source"])
	}
}

func TestTriggerWikiGeneration_OmitsReviseModelWhenEmpty(t *testing.T) {
	var gotBody map[string]any
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
		w.WriteHeader(http.StatusAccepted)
	}))
	defer stub.Close()

	srv := newJobProxyServer(stub.URL)
	if _, _, err := srv.triggerWikiGeneration(
		context.Background(), uuid.New(), uuid.New(), "user_model", "m1", []string{"e1"}, nil,
		"", ""); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if _, present := gotBody["revise_model_ref"]; present {
		t.Fatal("revise_model_ref should be omitted when no override is given")
	}
	if _, present := gotBody["revise_model_source"]; present {
		t.Fatal("revise_model_source should be omitted when no override is given")
	}
}
