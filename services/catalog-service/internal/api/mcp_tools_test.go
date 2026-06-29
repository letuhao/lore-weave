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

	"github.com/loreweave/catalog-service/internal/config"
)

// newMCPServer runs MustValidateToolMeta on every tool at registration — a missing or
// invalid tier/scope panics here. A clean construction proves the _meta is valid.
func TestNewMCPServer_BuildsWithoutPanic(t *testing.T) {
	srv := &Server{cfg: &config.Config{InternalServiceToken: "tok"}}
	if srv.newMCPServer() == nil {
		t.Fatal("nil MCP server")
	}
}

// The list tool shares the HTTP core, so it returns only public+active books — and it
// needs NO caller identity (owner-agnostic, OD-7): a bare context resolves the catalog.
func TestToolCatalogListPublicBooks_PublicActiveOnly(t *testing.T) {
	activeID := uuid.New()
	trashedID := uuid.New()

	sharing := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_ids": []string{activeID.String(), trashedID.String()},
			"total":    2,
		})
	}))
	defer sharing.Close()
	book := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := strings.TrimSuffix(strings.TrimPrefix(r.URL.Path, "/internal/books/"), "/projection")
		state := "active"
		if id == trashedID.String() {
			state = "trashed"
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_id": id, "title": "Book", "lifecycle_state": state,
			"chapter_count": 1, "original_language": "en", "created_at": time.Now().UTC(),
		})
	}))
	defer book.Close()

	srv := &Server{cfg: &config.Config{SharingServiceInternalURL: sharing.URL, BookServiceInternalURL: book.URL}}
	// context.Background() — NO identity envelope; the tool must still resolve (public).
	_, out, err := srv.toolCatalogListPublicBooks(context.Background(), nil, catalogListIn{})
	if err != nil {
		t.Fatalf("tool error: %v", err)
	}
	if len(out.Items) != 1 || out.Total != 1 {
		t.Fatalf("expected only the active public book, got items=%d total=%d", len(out.Items), out.Total)
	}
	if out.Items[0]["book_id"] != activeID { // in-memory map holds uuid.UUID (JSON stringifies on the wire)
		t.Errorf("returned the wrong book: %v", out.Items[0]["book_id"])
	}
}

func TestToolCatalogListPublicBooks_BadAuthor(t *testing.T) {
	srv := &Server{cfg: &config.Config{}}
	_, _, err := srv.toolCatalogListPublicBooks(context.Background(), nil, catalogListIn{Author: "not-a-uuid"})
	if err == nil {
		t.Fatal("expected an error for an invalid author id")
	}
}

func TestToolCatalogGetBook_InvalidUUID(t *testing.T) {
	srv := &Server{cfg: &config.Config{}}
	_, _, err := srv.toolCatalogGetBook(context.Background(), nil, catalogGetIn{BookID: "bad"})
	if err == nil {
		t.Fatal("expected an error for an invalid book id")
	}
}

// A non-public book (sharing returns 404) → not found (no leak of a private book).
func TestToolCatalogGetBook_NotFoundForNonPublic(t *testing.T) {
	sharing := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer sharing.Close()
	srv := &Server{cfg: &config.Config{SharingServiceInternalURL: sharing.URL}}
	_, _, err := srv.toolCatalogGetBook(context.Background(), nil, catalogGetIn{BookID: uuid.New().String()})
	if err == nil {
		t.Fatal("expected not-found for a non-public book")
	}
}
