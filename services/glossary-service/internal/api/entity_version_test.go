package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/config"
	"github.com/loreweave/glossary-service/internal/migrate"
)

// H5 optimistic concurrency (If-Match → 412) for the assistant-edit Apply path.
// DB-backed + full HTTP path (auth + verifyBookOwner mock), so it proves the
// header→guarded-UPDATE→412 mapping end to end, not just the SQL.

const versionTestSecret = "test_jwt_secret_at_least_32_characters_long"

// versionFixture seeds an owned entity with a name attribute and returns the
// wired server, a valid bearer token, and the ids needed to drive PATCH.
type versionFixture struct {
	srv         *Server
	token       string
	bookID      uuid.UUID
	entityID    uuid.UUID
	nameAttrVal uuid.UUID
}

func newVersionFixture(t *testing.T, pool *pgxpool.Pool) *versionFixture {
	t.Helper()
	ctx := context.Background()
	runK2aMigrations(t, pool)
	// patchEntity's success path emits a transactional outbox event — the table
	// is created by UpOutbox (not part of runK2aMigrations).
	if err := migrate.UpOutbox(ctx, pool); err != nil {
		t.Fatalf("UpOutbox: %v", err)
	}
	// short_description_auto column (entity-level writes set it false).
	if err := migrate.UpShortDescAuto(ctx, pool); err != nil {
		t.Fatalf("UpShortDescAuto: %v", err)
	}

	owner, book := uuid.New(), uuid.New()
	// book-service projection mock → owner owns book (verifyBookOwner passes).
	ts := httptest.NewServer(projection(book, owner))
	t.Cleanup(ts.Close)

	srv := NewServer(pool, &config.Config{
		JWTSecret:            versionTestSecret,
		BookServiceURL:       ts.URL,
		InternalServiceToken: "tok",
	})

	// G4: entities reference the BOOK tier (book_kinds/book_attributes). Adopt the
	// book's ontology from the System standards (idempotent SQL copy-down), then
	// resolve the 'character' kind + its universal-genre 'name' attribute id. The
	// seed guarantees 'character' exists system-side, so adopt always produces it.
	adoptTestBook(t, pool, book)
	kindID := bookKindID(t, pool, book, "character")
	nameAttrDef := bookAttrID(t, pool, book, kindID, "name")

	var entityID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		book, kindID).Scan(&entityID); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	var nameAttrVal uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'en','Nezha') RETURNING attr_value_id`,
		entityID, nameAttrDef).Scan(&nameAttrVal); err != nil {
		t.Fatalf("seed name attr: %v", err)
	}
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, book)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book)
	})

	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject:   owner.String(),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	signed, err := tok.SignedString([]byte(versionTestSecret))
	if err != nil {
		t.Fatalf("sign token: %v", err)
	}

	return &versionFixture{srv: srv, token: signed, bookID: book, entityID: entityID, nameAttrVal: nameAttrVal}
}

// currentVersion returns the entity's updated_at formatted exactly as the JSON
// API emits it (RFC3339Nano) — i.e. the value the assistant would read from
// glossary_get_entity and echo back as If-Match.
func (f *versionFixture) currentVersion(t *testing.T, pool *pgxpool.Pool) string {
	t.Helper()
	var ts time.Time
	if err := pool.QueryRow(context.Background(),
		`SELECT updated_at FROM glossary_entities WHERE entity_id=$1`, f.entityID).Scan(&ts); err != nil {
		t.Fatalf("read version: %v", err)
	}
	return ts.UTC().Format(time.RFC3339Nano)
}

func (f *versionFixture) patch(t *testing.T, path, body, ifMatch string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPatch, path, bytes.NewBufferString(body))
	req.Header.Set("Authorization", "Bearer "+f.token)
	req.Header.Set("Content-Type", "application/json")
	if ifMatch != "" {
		req.Header.Set("If-Match", ifMatch)
	}
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

func TestPatchEntity_IfMatch(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	base := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String()

	// Entity-level field (`status`) is enough to exercise the version guard —
	// the If-Match WHERE clause is field-agnostic.
	// Stale version → 412 (no write).
	w := f.patch(t, base, `{"status":"inactive"}`, "2000-01-01T00:00:00Z")
	if w.Code != http.StatusPreconditionFailed {
		t.Fatalf("stale If-Match: want 412, got %d (%s)", w.Code, w.Body.String())
	}

	// Matching version → 200 and the version advances.
	v := f.currentVersion(t, pool)
	w = f.patch(t, base, `{"status":"inactive"}`, v)
	if w.Code != http.StatusOK {
		t.Fatalf("matching If-Match: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if f.currentVersion(t, pool) == v {
		t.Error("matching PATCH must bump updated_at (the version is now stale for a replay)")
	}

	// Replaying the now-stale version → 412 (lost-update prevented).
	w = f.patch(t, base, `{"status":"active"}`, v)
	if w.Code != http.StatusPreconditionFailed {
		t.Fatalf("replayed stale version: want 412, got %d", w.Code)
	}

	// No If-Match → unchanged behavior (200), so the /v1 UI path is unaffected.
	w = f.patch(t, base, `{"status":"draft"}`, "")
	if w.Code != http.StatusOK {
		t.Fatalf("no If-Match: want 200, got %d (%s)", w.Code, w.Body.String())
	}
}

// TestPatchEntity_StatusValidation exercises the PATCH single-entity handler's
// status guard (entity_handler.go, consolidated onto validEntityStatus): the new
// "rejected" value must be accepted and persisted, and a still-invalid value must
// keep failing with the same 422/GLOSS_INVALID_STATUS shape as before.
func TestPatchEntity_StatusValidation(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	base := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String()

	w := f.patch(t, base, `{"status":"rejected"}`, "")
	if w.Code != http.StatusOK {
		t.Fatalf("rejected: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if statusOf(t, pool, f.entityID) != "rejected" {
		t.Errorf("entity must be rejected, got %s", statusOf(t, pool, f.entityID))
	}

	w = f.patch(t, base, `{"status":"bogus"}`, "")
	if w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("bad status: want 422, got %d (%s)", w.Code, w.Body.String())
	}
	var body struct {
		Code string `json:"code"`
	}
	json.Unmarshal(w.Body.Bytes(), &body) //nolint:errcheck
	if body.Code != "GLOSS_INVALID_STATUS" {
		t.Errorf("want GLOSS_INVALID_STATUS, got %q", body.Code)
	}
}

// D-GLOSSARY-ENTITY-SCOPE — the manual-edit REST PATCH path (EntityEditorModal's
// only write path today) can set/clear scope_label, and a change that would
// collide with another entity's (name, kind, scope_label) is rejected with a
// specific, user-actionable code rather than a raw 500.
func TestPatchEntity_ScopeLabel(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	base := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String()
	ctx := context.Background()

	w := f.patch(t, base, `{"scope_label":"World A"}`, "")
	if w.Code != http.StatusOK {
		t.Fatalf("set scope_label: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var got string
	pool.QueryRow(ctx, `SELECT scope_label FROM glossary_entities WHERE entity_id=$1`, f.entityID).Scan(&got)
	if got != "World A" {
		t.Errorf("want scope_label=World A, got %q", got)
	}
	var resp struct {
		ScopeLabel string `json:"scope_label"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp) //nolint:errcheck
	if resp.ScopeLabel != "World A" {
		t.Errorf("PATCH response must echo scope_label, got %q", resp.ScopeLabel)
	}

	w = f.patch(t, base, `{"scope_label":""}`, "")
	if w.Code != http.StatusOK {
		t.Fatalf("clear scope_label: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	pool.QueryRow(ctx, `SELECT scope_label FROM glossary_entities WHERE entity_id=$1`, f.entityID).Scan(&got)
	if got != "" {
		t.Errorf("want cleared scope_label, got %q", got)
	}

	// Seed a second, same-name-same-kind entity already scoped to "World B", then
	// try to collide f's entity onto it.
	var kindID uuid.UUID
	pool.QueryRow(ctx, `SELECT kind_id FROM glossary_entities WHERE entity_id=$1`, f.entityID).Scan(&kindID)
	nameAttrDef := bookAttrID(t, pool, f.bookID, kindID, "name")
	var other uuid.UUID
	pool.QueryRow(ctx, `INSERT INTO glossary_entities(book_id,kind_id,status,tags,scope_label) VALUES($1,$2,'active','{}','World B') RETURNING entity_id`,
		f.bookID, kindID).Scan(&other)
	pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'en','Nezha')`, other, nameAttrDef)
	if err := refreshEntityDedupKey(ctx, pool, f.entityID); err != nil {
		t.Fatalf("refresh dedup key f: %v", err)
	}
	if err := refreshEntityDedupKey(ctx, pool, other); err != nil {
		t.Fatalf("refresh dedup key other: %v", err)
	}

	w = f.patch(t, base, `{"scope_label":"World B"}`, "")
	if w.Code != http.StatusConflict {
		t.Fatalf("colliding scope_label: want 409, got %d (%s)", w.Code, w.Body.String())
	}
	var conflictBody struct {
		Code string `json:"code"`
	}
	json.Unmarshal(w.Body.Bytes(), &conflictBody) //nolint:errcheck
	if conflictBody.Code != "GLOSS_DUPLICATE_NAME" {
		t.Errorf("want GLOSS_DUPLICATE_NAME, got %q", conflictBody.Code)
	}
}

func TestPatchAttributeValue_IfMatch(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	path := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String() +
		"/attributes/" + f.nameAttrVal.String()

	// Stale version → 412, value untouched.
	w := f.patch(t, path, `{"original_value":"Nezha III"}`, "2000-01-01T00:00:00Z")
	if w.Code != http.StatusPreconditionFailed {
		t.Fatalf("stale If-Match on attr: want 412, got %d (%s)", w.Code, w.Body.String())
	}
	var val string
	pool.QueryRow(context.Background(), `SELECT original_value FROM entity_attribute_values WHERE attr_value_id=$1`, f.nameAttrVal).Scan(&val)
	if val != "Nezha" {
		t.Errorf("412 must not write: want original 'Nezha', got %q", val)
	}

	// Matching version → 200, value applied + entity version bumped.
	v := f.currentVersion(t, pool)
	w = f.patch(t, path, `{"original_value":"Nezha III"}`, v)
	if w.Code != http.StatusOK {
		t.Fatalf("matching If-Match on attr: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	pool.QueryRow(context.Background(), `SELECT original_value FROM entity_attribute_values WHERE attr_value_id=$1`, f.nameAttrVal).Scan(&val)
	if val != "Nezha III" {
		t.Errorf("matching attr PATCH must write: want 'Nezha III', got %q", val)
	}
	if f.currentVersion(t, pool) == v {
		t.Error("attr PATCH must bump the entity version (the single H5 token covers attr edits)")
	}
}
