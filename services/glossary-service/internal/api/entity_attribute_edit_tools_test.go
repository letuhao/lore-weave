package api

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// ── non-DB: tool wrapper validation + ownership (always run) ──────────────────

// /review-impl MED fix (2026-07-09): validateScopeLabel is the ONE shared trim +
// length check every write path (this tool, proposeNewEntity, proposeOneEntity,
// patchEntity) now routes through — previously only patchEntity trimmed, and
// NONE of the four bounded length, risking whitespace-variant "different" scopes
// and a raw-ish Postgres error on an oversized value instead of a clean rejection.
func TestValidateScopeLabel(t *testing.T) {
	trimmed, err := validateScopeLabel("  World A  ")
	if err != nil || trimmed != "World A" {
		t.Errorf("want trimmed %q, nil err; got %q, %v", "World A", trimmed, err)
	}
	empty, err := validateScopeLabel("   ")
	if err != nil || empty != "" {
		t.Errorf("want whitespace-only to trim to empty with no error; got %q, %v", empty, err)
	}
	oversized := strings.Repeat("a", scopeLabelMaxLen+1)
	if _, err := validateScopeLabel(oversized); err == nil {
		t.Error("want an error for a scope_label over the length cap")
	}
	atCap := strings.Repeat("a", scopeLabelMaxLen)
	if _, err := validateScopeLabel(atCap); err != nil {
		t.Errorf("want exactly-at-cap to be accepted, got %v", err)
	}
}

func TestToolSetEntityAttributes_MissingIdentity(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolSetEntityAttributes(context.Background(), nil,
		entitySetAttributesToolIn{BookID: uuid.NewString(), EntityID: uuid.NewString(), Attributes: map[string]string{"name": "X"}})
	if err == nil || err.Error() != "missing caller identity" {
		t.Fatalf("want missing-identity error, got %v", err)
	}
}

func TestToolSetEntityAttributes_RejectsBadInput(t *testing.T) {
	s := &Server{}
	u := uuid.New()
	cases := []struct {
		name string
		in   entitySetAttributesToolIn
	}{
		{"bad book_id", entitySetAttributesToolIn{BookID: "nope", EntityID: uuid.NewString(), Attributes: map[string]string{"name": "X"}}},
		{"bad entity_id", entitySetAttributesToolIn{BookID: uuid.NewString(), EntityID: "nope", Attributes: map[string]string{"name": "X"}}},
		{"empty attributes and no scope_label", entitySetAttributesToolIn{BookID: uuid.NewString(), EntityID: uuid.NewString(), Attributes: map[string]string{}}},
	}
	for _, c := range cases {
		if _, _, err := s.toolSetEntityAttributes(ctxWithUser(u), nil, c.in); err == nil {
			t.Errorf("%s: want validation error, got nil", c.name)
		}
	}
}

func TestToolSetEntityAttributes_RejectsOversizedScopeLabel(t *testing.T) {
	s := &Server{}
	oversized := strings.Repeat("a", scopeLabelMaxLen+1)
	_, _, err := s.toolSetEntityAttributes(ctxWithUser(uuid.New()), nil, entitySetAttributesToolIn{
		BookID: uuid.NewString(), EntityID: uuid.NewString(), ScopeLabel: &oversized,
	})
	if err == nil {
		t.Fatal("want a validation error for an oversized scope_label")
	}
}

func TestToolSetEntityAttributes_ScopeLabelAloneIsValid(t *testing.T) {
	// A nonexistent book_id/entity_id still fails downstream (grant/lookup), but
	// this confirms the wrapper's "must provide something" gate accepts a
	// scope_label-only call (empty Attributes is fine when ScopeLabel is set).
	s := &Server{}
	scope := "Some World"
	_, _, err := s.toolSetEntityAttributes(ctxWithUser(uuid.New()), nil, entitySetAttributesToolIn{
		BookID: uuid.NewString(), EntityID: uuid.NewString(), ScopeLabel: &scope,
	})
	if err != nil && err.Error() == "attributes or scope_label must be provided" {
		t.Fatalf("scope_label-only call must not fail the presence gate, got %v", err)
	}
}

// ── DB-backed: setEntityAttributes core (skips without GLOSSARY_TEST_DB_URL) ─────

func TestSetEntityAttributes_AddsEditsAndClears(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	book := uuid.New()
	adoptTestBook(t, pool, book)
	kindID := bookKindID(t, pool, book, "character")
	nameAttrID := bookAttrID(t, pool, book, kindID, "name")
	descAttrID := bookAttrID(t, pool, book, kindID, "description")
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, book)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book)
	})

	// Entity created with ONLY "name" set — mirrors an MCP-created entity, which
	// (unlike the REST manual-create path) does NOT pre-seed every kind attribute.
	var entityID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'draft','{}') RETURNING entity_id`,
		book, kindID).Scan(&entityID); err != nil {
		t.Fatal(err)
	}
	pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','Original Name')`, entityID, nameAttrID)

	s := &Server{pool: pool}
	userID := uuid.New()

	// 1. ADD a value for an attribute the entity has no row for at all yet.
	out, err := s.setEntityAttributes(ctx, book, entityID, userID, map[string]string{"description": "A newly added description"}, nil)
	if err != nil {
		t.Fatalf("add: %v", err)
	}
	if len(out.Updated) != 1 || out.Updated[0] != "description" {
		t.Errorf("want updated=[description], got %v (skipped=%v)", out.Updated, out.Skipped)
	}
	var got string
	pool.QueryRow(ctx, `SELECT original_value FROM entity_attribute_values WHERE entity_id=$1 AND attr_def_id=$2`, entityID, descAttrID).Scan(&got)
	if got != "A newly added description" {
		t.Errorf("description not added, got %q", got)
	}

	// 2. EDIT an attribute that already has a value.
	_, err = s.setEntityAttributes(ctx, book, entityID, userID, map[string]string{"name": "Corrected Name"}, nil)
	if err != nil {
		t.Fatalf("edit: %v", err)
	}
	pool.QueryRow(ctx, `SELECT original_value FROM entity_attribute_values WHERE entity_id=$1 AND attr_def_id=$2`, entityID, nameAttrID).Scan(&got)
	if got != "Corrected Name" {
		t.Errorf("name not edited, got %q", got)
	}
	var confidence string
	pool.QueryRow(ctx, `SELECT confidence FROM entity_attribute_values WHERE entity_id=$1 AND attr_def_id=$2`, entityID, nameAttrID).Scan(&confidence)
	if confidence != "verified" {
		t.Errorf("edited value should be marked verified (INV-8), got %q", confidence)
	}

	// 3. CLEAR via empty string.
	_, err = s.setEntityAttributes(ctx, book, entityID, userID, map[string]string{"description": ""}, nil)
	if err != nil {
		t.Fatalf("clear: %v", err)
	}
	pool.QueryRow(ctx, `SELECT original_value FROM entity_attribute_values WHERE entity_id=$1 AND attr_def_id=$2`, entityID, descAttrID).Scan(&got)
	if got != "" {
		t.Errorf("want cleared (empty), got %q", got)
	}

	// 4. An unknown attr code for this kind is reported skipped, not an error.
	out4, err := s.setEntityAttributes(ctx, book, entityID, userID, map[string]string{"name": "Still Valid", "no_such_code": "x"}, nil)
	if err != nil {
		t.Fatalf("mixed valid/invalid: %v", err)
	}
	if len(out4.Skipped) != 1 || out4.Skipped[0] != "no_such_code" {
		t.Errorf("want skipped=[no_such_code], got %v", out4.Skipped)
	}
	if len(out4.Updated) != 1 || out4.Updated[0] != "name" {
		t.Errorf("want updated=[name] alongside the skip, got %v", out4.Updated)
	}
}

func TestSetEntityAttributes_EntityNotFound(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	book := uuid.New()
	adoptTestBook(t, pool, book)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book)
	})
	s := &Server{pool: pool}

	_, err := s.setEntityAttributes(ctx, book, uuid.New(), uuid.New(), map[string]string{"name": "X"}, nil)
	if err == nil {
		t.Fatal("want not-found error for a nonexistent entity_id")
	}
}

func TestSetEntityAttributes_AllCodesUnknown(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	book := uuid.New()
	adoptTestBook(t, pool, book)
	kindID := bookKindID(t, pool, book, "character")
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, book)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book)
	})
	var entityID uuid.UUID
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'draft','{}') RETURNING entity_id`,
		book, kindID).Scan(&entityID)
	s := &Server{pool: pool}

	_, err := s.setEntityAttributes(ctx, book, entityID, uuid.New(), map[string]string{"no_such_code": "x"}, nil)
	if err == nil {
		t.Fatal("want an error when every attr code is unknown for the kind")
	}
}

// ── D-GLOSSARY-ENTITY-SCOPE: scope_label set/clear + dedup interaction ──────────

func TestSetEntityAttributes_SetsScopeLabelAlone(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	book := uuid.New()
	adoptTestBook(t, pool, book)
	kindID := bookKindID(t, pool, book, "character")
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book)
	})
	var entityID uuid.UUID
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'draft','{}') RETURNING entity_id`,
		book, kindID).Scan(&entityID)
	s := &Server{pool: pool}

	scope := "Linh Quy Tinh He"
	_, err := s.setEntityAttributes(ctx, book, entityID, uuid.New(), nil, &scope)
	if err != nil {
		t.Fatalf("scope-only call: %v", err)
	}
	var got string
	pool.QueryRow(ctx, `SELECT scope_label FROM glossary_entities WHERE entity_id=$1`, entityID).Scan(&got)
	if got != scope {
		t.Errorf("want scope_label=%q, got %q", scope, got)
	}

	// Clear it back to empty.
	empty := ""
	_, err = s.setEntityAttributes(ctx, book, entityID, uuid.New(), nil, &empty)
	if err != nil {
		t.Fatalf("clear scope: %v", err)
	}
	pool.QueryRow(ctx, `SELECT scope_label FROM glossary_entities WHERE entity_id=$1`, entityID).Scan(&got)
	if got != "" {
		t.Errorf("want cleared scope_label, got %q", got)
	}
}

func TestSetEntityAttributes_ScopeLabelDedupCollisionRejected(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	book := uuid.New()
	adoptTestBook(t, pool, book)
	kindID := bookKindID(t, pool, book, "character")
	nameAttrID := bookAttrID(t, pool, book, kindID, "name")
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, book)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book)
	})

	// Two entities, SAME name+kind, already disambiguated by DIFFERENT scope_label.
	var a, b uuid.UUID
	pool.QueryRow(ctx, `INSERT INTO glossary_entities(book_id,kind_id,status,tags,scope_label) VALUES($1,$2,'draft','{}','World A') RETURNING entity_id`, book, kindID).Scan(&a)
	pool.QueryRow(ctx, `INSERT INTO glossary_entities(book_id,kind_id,status,tags,scope_label) VALUES($1,$2,'draft','{}','World B') RETURNING entity_id`, book, kindID).Scan(&b)
	pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','Lam Gia')`, a, nameAttrID)
	pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','Lam Gia')`, b, nameAttrID)
	pool.Exec(ctx, `SELECT recalculate_entity_snapshot($1)`, a)
	pool.Exec(ctx, `SELECT recalculate_entity_snapshot($1)`, b)
	// normalized_name is APP-maintained (D-GLOSSARY-ST-DEDUP), not trigger-derived —
	// the partial unique index excludes rows where it's still '' (the DEFAULT).
	if err := refreshEntityDedupKey(ctx, pool, a); err != nil {
		t.Fatalf("refresh dedup key a: %v", err)
	}
	if err := refreshEntityDedupKey(ctx, pool, b); err != nil {
		t.Fatalf("refresh dedup key b: %v", err)
	}

	s := &Server{pool: pool}
	// Changing b's scope to match a's would collide on (book,kind,name,scope).
	worldA := "World A"
	_, err := s.setEntityAttributes(ctx, book, b, uuid.New(), nil, &worldA)
	// /review-impl LOW fix (2026-07-09): assert the SPECIFIC friendly message, not
	// just "some error" — otherwise a regression in isUniqueViolation's detection
	// (e.g. a pgx error-wrapping change) would silently fall through to the generic
	// "set scope_label failed" branch and this test would still pass.
	if err == nil || err.Error() != "an entity with this name, kind, and scope already exists in this book" {
		t.Fatalf("want the specific duplicate-collision message, got %v", err)
	}
}
