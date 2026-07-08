package api

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

// ── non-DB: tool wrapper validation + ownership (always run) ──────────────────

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
		{"empty attributes", entitySetAttributesToolIn{BookID: uuid.NewString(), EntityID: uuid.NewString(), Attributes: map[string]string{}}},
	}
	for _, c := range cases {
		if _, _, err := s.toolSetEntityAttributes(ctxWithUser(u), nil, c.in); err == nil {
			t.Errorf("%s: want validation error, got nil", c.name)
		}
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
	out, err := s.setEntityAttributes(ctx, book, entityID, userID, map[string]string{"description": "A newly added description"})
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
	_, err = s.setEntityAttributes(ctx, book, entityID, userID, map[string]string{"name": "Corrected Name"})
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
	_, err = s.setEntityAttributes(ctx, book, entityID, userID, map[string]string{"description": ""})
	if err != nil {
		t.Fatalf("clear: %v", err)
	}
	pool.QueryRow(ctx, `SELECT original_value FROM entity_attribute_values WHERE entity_id=$1 AND attr_def_id=$2`, entityID, descAttrID).Scan(&got)
	if got != "" {
		t.Errorf("want cleared (empty), got %q", got)
	}

	// 4. An unknown attr code for this kind is reported skipped, not an error.
	out4, err := s.setEntityAttributes(ctx, book, entityID, userID, map[string]string{"name": "Still Valid", "no_such_code": "x"})
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

	_, err := s.setEntityAttributes(ctx, book, uuid.New(), uuid.New(), map[string]string{"name": "X"})
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

	_, err := s.setEntityAttributes(ctx, book, entityID, uuid.New(), map[string]string{"no_such_code": "x"})
	if err == nil {
		t.Fatal("want an error when every attr code is unknown for the kind")
	}
}
