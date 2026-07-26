package api

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// Input-guard tests (no DB, no grant stub) — the DB rename behavior (dedup collision,
// revision event) rides on setEntityAttributes' own core tests, since rename delegates
// to that exact core. These assert the wrapper's own validation before any DB touch.

func TestEntityRename_MissingIdentity(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolEntityRename(context.Background(), nil, entityRenameToolIn{
		BookID: uuid.NewString(), EntityID: uuid.NewString(), Name: "New Name",
	})
	if err == nil || !strings.Contains(err.Error(), "identity") {
		t.Fatalf("want missing-identity error, got %v", err)
	}
}

func TestEntityRename_BadBookID(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolEntityRename(ctxWithUser(uuid.New()), nil, entityRenameToolIn{
		BookID: "nope", EntityID: uuid.NewString(), Name: "New Name",
	})
	if err == nil || !strings.Contains(err.Error(), "book_id must be a UUID") {
		t.Fatalf("want book_id error, got %v", err)
	}
}

func TestEntityRename_BadEntityID(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolEntityRename(ctxWithUser(uuid.New()), nil, entityRenameToolIn{
		BookID: uuid.NewString(), EntityID: "nope", Name: "New Name",
	})
	if err == nil || !strings.Contains(err.Error(), "entity_id must be a UUID") {
		t.Fatalf("want entity_id error, got %v", err)
	}
}

func TestEntityRename_EmptyName(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolEntityRename(ctxWithUser(uuid.New()), nil, entityRenameToolIn{
		BookID: uuid.NewString(), EntityID: uuid.NewString(), Name: "   ",
	})
	if err == nil || !strings.Contains(err.Error(), "name is required") {
		t.Fatalf("want empty-name error, got %v", err)
	}
}
