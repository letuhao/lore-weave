package api

import (
	"context"
	"net/http/httptest"
	"slices"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/config"
)

// ── non-DB: tool wrapper validation + ownership (always run) ──────────────────

func ctxWithUser(u uuid.UUID) context.Context {
	return context.WithValue(context.Background(), ctxKeyUserID, u.String())
}

func TestToolPropose_MissingIdentity(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolProposeNewEntity(context.Background(), nil,
		proposeEntityToolIn{BookID: uuid.NewString(), Kind: "character", Name: "X"})
	if err == nil || err.Error() != "missing caller identity" {
		t.Fatalf("want missing-identity error, got %v", err)
	}
}

func TestToolPropose_RejectsBadInput(t *testing.T) {
	s := &Server{}
	u := uuid.New()
	cases := []struct {
		name string
		in   proposeEntityToolIn
	}{
		{"bad book_id", proposeEntityToolIn{BookID: "nope", Kind: "character", Name: "X"}},
		{"empty name", proposeEntityToolIn{BookID: uuid.NewString(), Kind: "character", Name: "   "}},
		{"empty kind", proposeEntityToolIn{BookID: uuid.NewString(), Kind: "", Name: "X"}},
	}
	for _, c := range cases {
		if _, _, err := s.toolProposeNewEntity(ctxWithUser(u), nil, c.in); err == nil {
			t.Errorf("%s: want validation error, got nil", c.name)
		}
	}
}

func TestToolPropose_OwnershipDenied(t *testing.T) {
	// book-service returns a projection owned by someone else → not accessible.
	ts := httptest.NewServer(projection(uuid.New(), uuid.New()))
	defer ts.Close()
	s := &Server{cfg: &config.Config{BookServiceURL: ts.URL, InternalServiceToken: "t"}}
	_, _, err := s.toolProposeNewEntity(ctxWithUser(uuid.New()), nil,
		proposeEntityToolIn{BookID: uuid.NewString(), Kind: "character", Name: "X"})
	if err == nil || !strings.Contains(err.Error(), "not accessible") {
		t.Fatalf("non-owner must be denied with not-accessible, got %v", err)
	}
}

// ── DB-backed: proposeNewEntity core (skips without GLOSSARY_TEST_DB_URL) ─────

func TestProposeNewEntity_CreatesDraftThenDedups(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	book := uuid.New()
	var kindID uuid.UUID
	if err := pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID); err != nil {
		t.Fatalf("seed kind: %v", err)
	}
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, book)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book)
	})
	s := &Server{pool: pool}

	id, status, err := s.proposeNewEntity(ctx, book, kindID, "Nezha", nil)
	if err != nil || status != "created" {
		t.Fatalf("want created, got status=%q err=%v", status, err)
	}
	var st string
	var tags []string
	if err := pool.QueryRow(ctx, `SELECT status, tags FROM glossary_entities WHERE entity_id=$1`, id).Scan(&st, &tags); err != nil {
		t.Fatalf("query created: %v", err)
	}
	if st != "draft" {
		t.Errorf("want status=draft, got %q", st)
	}
	if !slices.Contains(tags, "ai-suggested") || !slices.Contains(tags, "assistant") {
		t.Errorf("want tags [ai-suggested assistant], got %v", tags)
	}

	// H9 dedup: a second propose of the same name does not create a duplicate.
	id2, status2, err := s.proposeNewEntity(ctx, book, kindID, "Nezha", nil)
	if err != nil {
		t.Fatal(err)
	}
	if status2 != "skipped_exists" || id2 != id {
		t.Errorf("want skipped_exists with same id, got status=%q id=%v", status2, id2)
	}
}

func TestProposeNewEntity_SkipsTombstoned(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	book := uuid.New()
	var kindID, nameAttrID uuid.UUID
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	pool.QueryRow(ctx, `SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`, kindID).Scan(&nameAttrID)

	// Seed a previously-rejected (tombstoned) entity named "Rejected".
	var rejectedID uuid.UUID
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'inactive','{ai-suggested,ai-rejected}') RETURNING entity_id`,
		book, kindID).Scan(&rejectedID)
	pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','Rejected')`,
		rejectedID, nameAttrID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, book)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book)
	})
	s := &Server{pool: pool}

	id, status, err := s.proposeNewEntity(ctx, book, kindID, "Rejected", nil)
	if err != nil {
		t.Fatal(err)
	}
	if status != "skipped_tombstoned" || id != rejectedID {
		t.Errorf("want skipped_tombstoned with the rejected id, got status=%q id=%v (rejected=%v)", status, id, rejectedID)
	}
}
