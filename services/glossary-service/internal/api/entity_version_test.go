package api

import (
	"bytes"
	"context"
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

	owner, book := uuid.New(), uuid.New()
	// book-service projection mock → owner owns book (verifyBookOwner passes).
	ts := httptest.NewServer(projection(book, owner))
	t.Cleanup(ts.Close)

	srv := NewServer(pool, &config.Config{
		JWTSecret:            versionTestSecret,
		BookServiceURL:       ts.URL,
		InternalServiceToken: "tok",
	})

	// Self-seed a 'character' kind + name attr if absent. migrate.Seed skips the
	// default kinds when entity_kinds already holds the Up()-inserted 'unknown'
	// kind (D-WIKI-SEED-ROBUSTNESS), so on a fresh local DB 'character' is missing.
	// Seeding it here keeps this test self-sufficient (green locally and in CI).
	var kindID, nameAttrDef uuid.UUID
	if err := pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID); err != nil {
		if err := pool.QueryRow(ctx,
			`INSERT INTO entity_kinds(code,name,icon,color,is_default,is_hidden,sort_order,genre_tags)
			 VALUES('character','Character','👤','#000',true,false,1,'{universal}') RETURNING kind_id`,
		).Scan(&kindID); err != nil {
			t.Fatalf("seed character kind: %v", err)
		}
	}
	if err := pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`,
		kindID).Scan(&nameAttrDef); err != nil {
		if err := pool.QueryRow(ctx,
			`INSERT INTO attribute_definitions(kind_id,code,name,field_type,is_required,is_system,sort_order)
			 VALUES($1,'name','Name','text',true,true,1) RETURNING attr_def_id`,
			kindID).Scan(&nameAttrDef); err != nil {
			t.Fatalf("seed name attr def: %v", err)
		}
	}

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
