package api

// RAID C1 — steering store DB-gated tests. Real Postgres because they exercise
// the UNIQUE(book_id, name) → 409 mapping, the 20-row cap, the id+book_id
// tenancy scoping, and the internal enabled-only projection. Gated on
// BOOK_TEST_DATABASE_URL like publish_guard_db_test.go (skipped when unset).

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// seedSteeringBook inserts an active book owned by ownerID.
func seedSteeringBook(t *testing.T, ctx context.Context, pool *pgxpool.Pool, ownerID uuid.UUID) uuid.UUID {
	t.Helper()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'steer') RETURNING id`, ownerID).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	return bookID
}

func steeringHTTP(t *testing.T, s *Server, caller uuid.UUID, method, path, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, caller))
	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func decodeSteeringItem(t *testing.T, raw []byte) map[string]any {
	t.Helper()
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatalf("decode steering item: %v — raw %s", err, raw)
	}
	return out
}

// Full CRUD round-trip as the book owner.
func TestSteering_CRUD_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID := seedSteeringBook(t, ctx, pool, owner)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	base := "/v1/books/" + bookID.String() + "/steering"

	// create
	rr := steeringHTTP(t, s, owner, http.MethodPost, base,
		`{"name":"tone","body":"Keep the prose wry.","inclusion_mode":"manual"}`)
	if rr.Code != http.StatusCreated {
		t.Fatalf("create = %d, want 201\n%s", rr.Code, rr.Body.String())
	}
	created := decodeSteeringItem(t, rr.Body.Bytes())
	if created["name"] != "tone" || created["inclusion_mode"] != "manual" || created["enabled"] != true {
		t.Fatalf("created row wrong: %v", created)
	}
	if created["author_user_id"] != owner.String() {
		t.Fatalf("author_user_id = %v, want the caller %s (audit)", created["author_user_id"], owner)
	}
	id := created["id"].(string)

	// list
	rr = steeringHTTP(t, s, owner, http.MethodGet, base, "")
	if rr.Code != http.StatusOK {
		t.Fatalf("list = %d, want 200\n%s", rr.Code, rr.Body.String())
	}
	var listed struct {
		Items []map[string]any `json:"items"`
		Total int              `json:"total"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &listed)
	if listed.Total != 1 || len(listed.Items) != 1 || listed.Items[0]["id"] != id {
		t.Fatalf("list wrong: %+v", listed)
	}

	// update (full replace; flips mode + disables)
	rr = steeringHTTP(t, s, owner, http.MethodPut, base+"/"+id,
		`{"name":"tone","body":"Wry, but never glib.","inclusion_mode":"scene_match","match_pattern":"tavern","enabled":false}`)
	if rr.Code != http.StatusOK {
		t.Fatalf("update = %d, want 200\n%s", rr.Code, rr.Body.String())
	}
	updated := decodeSteeringItem(t, rr.Body.Bytes())
	if updated["body"] != "Wry, but never glib." || updated["inclusion_mode"] != "scene_match" ||
		updated["match_pattern"] != "tavern" || updated["enabled"] != false {
		t.Fatalf("updated row wrong: %v", updated)
	}

	// delete
	rr = steeringHTTP(t, s, owner, http.MethodDelete, base+"/"+id, "")
	if rr.Code != http.StatusNoContent {
		t.Fatalf("delete = %d, want 204\n%s", rr.Code, rr.Body.String())
	}
	rr = steeringHTTP(t, s, owner, http.MethodDelete, base+"/"+id, "")
	if rr.Code != http.StatusNotFound {
		t.Fatalf("re-delete = %d, want 404", rr.Code)
	}
}

// UNIQUE(book_id, name) → 409, on create AND on a rename collision; the SAME
// name on a DIFFERENT book is fine (the unique is scoped — tenancy lock).
func TestSteering_DuplicateName409_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookA := seedSteeringBook(t, ctx, pool, owner)
	bookB := seedSteeringBook(t, ctx, pool, owner)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	baseA := "/v1/books/" + bookA.String() + "/steering"

	if rr := steeringHTTP(t, s, owner, http.MethodPost, baseA, `{"name":"tone","body":"a"}`); rr.Code != http.StatusCreated {
		t.Fatalf("create #1 = %d\n%s", rr.Code, rr.Body.String())
	}
	if rr := steeringHTTP(t, s, owner, http.MethodPost, baseA, `{"name":"tone","body":"b"}`); rr.Code != http.StatusConflict {
		t.Fatalf("duplicate create = %d, want 409\n%s", rr.Code, rr.Body.String())
	}
	// rename collision: second entry renamed onto the first → 409
	rr := steeringHTTP(t, s, owner, http.MethodPost, baseA, `{"name":"pov","body":"c"}`)
	if rr.Code != http.StatusCreated {
		t.Fatalf("create #2 = %d\n%s", rr.Code, rr.Body.String())
	}
	povID := decodeSteeringItem(t, rr.Body.Bytes())["id"].(string)
	if rr := steeringHTTP(t, s, owner, http.MethodPut, baseA+"/"+povID, `{"name":"tone","body":"c"}`); rr.Code != http.StatusConflict {
		t.Fatalf("rename collision = %d, want 409\n%s", rr.Code, rr.Body.String())
	}
	// same name on another book — scoped unique allows it
	baseB := "/v1/books/" + bookB.String() + "/steering"
	if rr := steeringHTTP(t, s, owner, http.MethodPost, baseB, `{"name":"tone","body":"d"}`); rr.Code != http.StatusCreated {
		t.Fatalf("same name on other book = %d, want 201 (unique must be book-scoped)\n%s", rr.Code, rr.Body.String())
	}
}

// Row cap: the 21st entry is refused 422. (The 8001-char body 422 is covered
// by the pure-validation unit tests; the DB CHECK is belt-and-braces.)
func TestSteering_RowCap422_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID := seedSteeringBook(t, ctx, pool, owner)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	for i := 0; i < maxSteeringRowsPerBook; i++ {
		if _, err := pool.Exec(ctx, `
INSERT INTO book_steering(book_id, name, body, author_user_id) VALUES($1,$2,'b',$3)`,
			bookID, fmt.Sprintf("rule-%02d", i), owner); err != nil {
			t.Fatalf("seed row %d: %v", i, err)
		}
	}
	rr := steeringHTTP(t, s, owner, http.MethodPost, "/v1/books/"+bookID.String()+"/steering",
		`{"name":"one-too-many","body":"x"}`)
	if rr.Code != http.StatusUnprocessableEntity {
		t.Fatalf("21st entry = %d, want 422\n%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "STEERING_LIMIT_REACHED") {
		t.Fatalf("cap error code missing: %s", rr.Body.String())
	}
}

// A VIEW grantee can list but not write — enforced against the real routes +
// real rows (the grant_mapping unit test proves the mapping; this proves no
// write landed).
func TestSteering_ViewCanReadNotWrite_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	viewer := uuid.New()
	bookID := seedSteeringBook(t, ctx, pool, owner)
	if _, err := pool.Exec(ctx, `
INSERT INTO book_steering(book_id, name, body, author_user_id) VALUES($1,'tone','b',$2)`, bookID, owner); err != nil {
		t.Fatalf("seed steering: %v", err)
	}
	s.resolveBook = func(_ context.Context, _, userID uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		if userID == viewer {
			return GrantView, owner, "active", nil
		}
		return GrantOwner, owner, "active", nil
	}
	base := "/v1/books/" + bookID.String() + "/steering"

	if rr := steeringHTTP(t, s, viewer, http.MethodGet, base, ""); rr.Code != http.StatusOK {
		t.Fatalf("viewer list = %d, want 200\n%s", rr.Code, rr.Body.String())
	}
	if rr := steeringHTTP(t, s, viewer, http.MethodPost, base, `{"name":"x","body":"y"}`); rr.Code != http.StatusForbidden {
		t.Fatalf("viewer create = %d, want 403\n%s", rr.Code, rr.Body.String())
	}
	var n int
	_ = pool.QueryRow(ctx, `SELECT COUNT(*) FROM book_steering WHERE book_id=$1`, bookID).Scan(&n)
	if n != 1 {
		t.Fatalf("viewer write landed: %d rows, want 1", n)
	}
}

// Tenancy: an id from book A reached via book B's path uniformly 404s even
// when the caller holds grants on BOTH books (the query is id+book_id scoped).
func TestSteering_CrossBookIDScoping_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookA := seedSteeringBook(t, ctx, pool, owner)
	bookB := seedSteeringBook(t, ctx, pool, owner)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	rr := steeringHTTP(t, s, owner, http.MethodPost, "/v1/books/"+bookA.String()+"/steering", `{"name":"tone","body":"a"}`)
	if rr.Code != http.StatusCreated {
		t.Fatalf("create = %d\n%s", rr.Code, rr.Body.String())
	}
	id := decodeSteeringItem(t, rr.Body.Bytes())["id"].(string)

	baseB := "/v1/books/" + bookB.String() + "/steering/" + id
	if rr := steeringHTTP(t, s, owner, http.MethodPut, baseB, `{"name":"tone","body":"hijack"}`); rr.Code != http.StatusNotFound {
		t.Fatalf("cross-book update = %d, want 404\n%s", rr.Code, rr.Body.String())
	}
	if rr := steeringHTTP(t, s, owner, http.MethodDelete, baseB, ""); rr.Code != http.StatusNotFound {
		t.Fatalf("cross-book delete = %d, want 404\n%s", rr.Code, rr.Body.String())
	}
}

// Internal route: enabled-only projection with exactly the render fields, and
// the internal-token gate holds.
func TestSteering_InternalEnabledOnly_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID := seedSteeringBook(t, ctx, pool, owner)
	if _, err := pool.Exec(ctx, `
INSERT INTO book_steering(book_id, name, body, inclusion_mode, match_pattern, enabled, author_user_id) VALUES
  ($1,'tone','Keep it wry.','always',NULL,true,$2),
  ($1,'combat','Fast cuts.','scene_match','battle',true,$2),
  ($1,'retired','Old rule.','manual',NULL,false,$2)`, bookID, owner); err != nil {
		t.Fatalf("seed steering: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/internal/books/"+bookID.String()+"/steering", nil)
	req.Header.Set("X-Internal-Token", mcpTestToken)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("internal steering = %d, want 200\n%s", rr.Code, rr.Body.String())
	}
	var out struct {
		Items []map[string]any `json:"items"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &out)
	if len(out.Items) != 2 {
		t.Fatalf("internal returned %d items, want 2 (enabled-only)", len(out.Items))
	}
	for _, it := range out.Items {
		if it["name"] == "retired" {
			t.Fatal("disabled entry leaked through the internal route")
		}
		for _, k := range []string{"id", "name", "body", "inclusion_mode", "match_pattern"} {
			if _, ok := it[k]; !ok {
				t.Fatalf("internal item missing render field %q: %v", k, it)
			}
		}
	}

	// token gate
	req = httptest.NewRequest(http.MethodGet, "/internal/books/"+bookID.String()+"/steering", nil)
	req.Header.Set("X-Internal-Token", "wrong")
	rr = httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("internal steering with bad token = %d, want 401", rr.Code)
	}
}
