package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/google/uuid"
)

// T10 (plan 2026-09-18, Q4) — the sign-in backfill provisions every book the CALLER owns that lacks
// a ready Work, with the caller's own bearer, and touches nobody else's book (OQ-1).

type fakeComposition struct {
	mu       sync.Mutex
	ready    map[string]bool // book id -> GET /work returns a project-backed Work
	failPost map[string]bool // book id -> POST /work fails
	gets     []string
	posts    []string
	auths    map[string]bool
}

func (f *fakeComposition) handler(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	parts := strings.Split(r.URL.Path, "/") // /v1/composition/books/{id}/work
	id := parts[4]
	f.auths[r.Header.Get("Authorization")] = true
	switch r.Method {
	case http.MethodGet:
		f.gets = append(f.gets, id)
		if f.ready[id] {
			_ = json.NewEncoder(w).Encode(map[string]any{"work": map[string]any{"project_id": "p-" + id}})
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"work": nil})
	case http.MethodPost:
		f.posts = append(f.posts, id)
		if f.failPost[id] {
			w.WriteHeader(http.StatusBadGateway)
			return
		}
		w.WriteHeader(http.StatusCreated)
	}
}

func seedOwnedBook(t *testing.T, s *Server, owner uuid.UUID, kind string, active bool) string {
	t.Helper()
	state := "active"
	if !active {
		state = "trashed"
	}
	var id uuid.UUID
	if err := s.pool.QueryRow(context.Background(),
		`INSERT INTO books(owner_user_id,title,kind,lifecycle_state) VALUES($1,'pm',$2,$3) RETURNING id`,
		owner, kind, state).Scan(&id); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	return id.String()
}

func TestProvisionMissing_OnlyTheCallersBooks_OnlyTheCallersBearer_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	owner, other := uuid.New(), uuid.New()
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE owner_user_id = ANY($1)`, []uuid.UUID{owner, other})
	})
	readyBook := seedOwnedBook(t, s, owner, "novel", true)
	missing1 := seedOwnedBook(t, s, owner, "novel", true)
	missing2 := seedOwnedBook(t, s, owner, "document", true)
	failing := seedOwnedBook(t, s, owner, "novel", true)
	diary := seedOwnedBook(t, s, owner, "diary", true)
	trashed := seedOwnedBook(t, s, owner, "novel", false)
	othersBook := seedOwnedBook(t, s, other, "novel", true)

	f := &fakeComposition{ready: map[string]bool{readyBook: true}, failPost: map[string]bool{failing: true},
		auths: map[string]bool{}}
	comp := httptest.NewServer(http.HandlerFunc(f.handler))
	defer comp.Close()
	cfg := *s.cfg
	cfg.CompositionServiceURL = comp.URL
	s.cfg = &cfg

	bearer := "Bearer " + mcpJWT(t, owner)
	req := httptest.NewRequest(http.MethodPost, "/v1/books/provision-missing", nil)
	req.Header.Set("Authorization", bearer)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("provision-missing = %d, want 200. body=%s", rr.Code, rr.Body.String())
	}
	var out provisionMissingResult
	_ = json.Unmarshal(rr.Body.Bytes(), &out)
	want := provisionMissingResult{Checked: 4, Ready: 1, Provisioned: 2, Failed: 1}
	if out != want {
		t.Fatalf("result %+v, want %+v", out, want)
	}

	f.mu.Lock()
	defer f.mu.Unlock()
	touched := map[string]bool{}
	for _, id := range append(append([]string{}, f.gets...), f.posts...) {
		touched[id] = true
	}
	for name, id := range map[string]string{"another user's book": othersBook, "a diary": diary, "a trashed book": trashed} {
		if touched[id] {
			t.Fatalf("%s was sent to composition — the backfill is the caller's own active books only", name)
		}
	}
	for _, id := range f.posts {
		if id == readyBook {
			t.Fatal("a book whose Work is already project-backed was provisioned again")
		}
	}
	if len(f.auths) != 1 || !f.auths[bearer] {
		t.Fatalf("composition saw identities %v — only the caller's own bearer may be forwarded", f.auths)
	}
	_ = missing1
	_ = missing2
}

func TestProvisionMissing_RequiresASignedInCaller_DB(t *testing.T) {
	s, _ := dbTestServer(t)
	req := httptest.NewRequest(http.MethodPost, "/v1/books/provision-missing", nil)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous provision-missing = %d, want 401", rr.Code)
	}
}

func TestProvisionMissing_KeepsGoingWhenTheClientHangsUp_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	owner := uuid.New()
	t.Cleanup(func() { _, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE owner_user_id=$1`, owner) })
	book := seedOwnedBook(t, s, owner, "novel", true)

	f := &fakeComposition{ready: map[string]bool{}, failPost: map[string]bool{}, auths: map[string]bool{}}
	comp := httptest.NewServer(http.HandlerFunc(f.handler))
	defer comp.Close()
	cfg := *s.cfg
	cfg.CompositionServiceURL = comp.URL
	s.cfg = &cfg

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // the browser fired and left: the request context is already cancelled
	req := httptest.NewRequest(http.MethodPost, "/v1/books/provision-missing", nil).WithContext(ctx)
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, owner))
	s.Router().ServeHTTP(httptest.NewRecorder(), req)

	f.mu.Lock()
	defer f.mu.Unlock()
	if len(f.posts) != 1 || f.posts[0] != book {
		t.Fatalf("posts %v — a fire-and-forget caller hanging up must not stop the sweep", f.posts)
	}
}
