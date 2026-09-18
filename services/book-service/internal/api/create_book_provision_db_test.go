package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

// T7 (plan 2026-09-18, L4) — a book created through REST asks composition for its Work right after
// commit, with the author's own bearer, so its knowledge project exists without anyone opening it.

func createBookViaREST(t *testing.T, s *Server, caller uuid.UUID) (*httptest.ResponseRecorder, string, time.Duration) {
	t.Helper()
	bearer := "Bearer " + mcpJWT(t, caller)
	req := httptest.NewRequest(http.MethodPost, "/v1/books", strings.NewReader(`{"title":"T7 provision","original_language":"en"}`))
	req.Header.Set("Authorization", bearer)
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	start := time.Now()
	s.Router().ServeHTTP(rr, req)
	return rr, bearer, time.Since(start)
}

type workCall struct{ path, auth string }

func TestCreateBook_AsksCompositionForTheWork_WithTheCallersBearer_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	owner := uuid.New()
	t.Cleanup(func() { _, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE owner_user_id=$1`, owner) })

	calls := make(chan workCall, 4)
	comp := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls <- workCall{r.Method + " " + r.URL.Path, r.Header.Get("Authorization")}
		w.WriteHeader(http.StatusCreated)
	}))
	defer comp.Close()
	cfg := *s.cfg
	cfg.CompositionServiceURL = comp.URL
	s.cfg = &cfg

	rr, bearer, _ := createBookViaREST(t, s, owner)
	if rr.Code != http.StatusCreated {
		t.Fatalf("create = %d, want 201. body=%s", rr.Code, rr.Body.String())
	}
	var out struct {
		BookID string `json:"book_id"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &out)

	select {
	case c := <-calls:
		if c.path != "POST /v1/composition/books/"+out.BookID+"/work" {
			t.Fatalf("composition got %q, want POST /v1/composition/books/%s/work", c.path, out.BookID)
		}
		if c.auth != bearer {
			t.Fatal("composition did not receive the creator's own bearer — OQ-1 allows no other identity")
		}
	case <-time.After(5 * time.Second):
		t.Fatal("no POST /work within 5s of creating the book — its knowledge project waits for someone to open it")
	}
	select {
	case c := <-calls:
		t.Fatalf("a second provisioning call went out: %+v", c)
	case <-time.After(200 * time.Millisecond):
	}
}

func TestCreateBook_AFailingOrHungComposition_NeverFailsOrSlowsTheCreate_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	owner := uuid.New()
	t.Cleanup(func() { _, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE owner_user_id=$1`, owner) })

	release := make(chan struct{})
	comp := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		select { // hang, as a stalled knowledge service would
		case <-release:
		case <-r.Context().Done():
		}
		w.WriteHeader(http.StatusBadGateway)
	}))
	defer comp.Close()
	defer close(release)
	cfg := *s.cfg
	cfg.CompositionServiceURL = comp.URL
	s.cfg = &cfg

	rr, _, took := createBookViaREST(t, s, owner)
	if rr.Code != http.StatusCreated {
		t.Fatalf("create = %d with composition down, want 201 — provisioning is best-effort", rr.Code)
	}
	if took > 2*time.Second {
		t.Fatalf("create took %s while composition hung — provisioning must stay off the request path", took)
	}
}
