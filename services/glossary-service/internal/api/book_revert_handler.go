package api

// G-U1 — revert a Book override back to its parent tier (System/User).
//
// At adopt, each book row captured source_ref ('system:<id>' | 'user:<id>') + a frozen
// source_hash. The book row is an editable COPY. "Revert" drops the local edits and
// re-pulls the parent's CURRENT values — a forced single-row take_theirs. It reuses the
// exact Sync write path (applySyncRow take=true), so it inherits the deprecated-source
// guard (G-C8) and the user-tier caller-scoping (D-GKA-SYNC-USER-SOURCE-VISIBILITY).
//
// Distinct from delete: delete deprecates the row (it vanishes, leaving a gap — the
// single-tier read has no fallback); revert mutates the row in place to the parent value,
// keeping the same id/code so entity data referencing it is unaffected. A book-native row
// (source_ref NULL) has no parent, so revert is a no-op there and reports "not revertable".

import (
	"context"
	"fmt"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// revertBookRow re-pulls a single book row's parent values (forced take_theirs), under the
// same per-book advisory lock adopt/sync use. reverted=false ⇒ book-native row OR a
// source that is retired/deprecated (nothing to revert to).
func (s *Server) revertBookRow(ctx context.Context, bookID, userID uuid.UUID, entity string, id uuid.UUID) (bool, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return false, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext('gloss-adopt:' || $1::text))`, bookID); err != nil {
		return false, err
	}
	reverted, err := s.applySyncRow(ctx, tx, bookID, userID, entity, id, true)
	if err != nil {
		return false, err
	}
	if err := tx.Commit(ctx); err != nil {
		return false, err
	}
	return reverted, nil
}

// bookRowSourceRef returns a book row's source_ref ("" = book-native / not found). The
// table/id-column are internal constants keyed by level (no request data → no injection).
func (s *Server) bookRowSourceRef(ctx context.Context, bookID uuid.UUID, level string, id uuid.UUID) (string, error) {
	var table, idCol string
	switch level {
	case deleteLevelGenre:
		table, idCol = "book_genres", "genre_id"
	case deleteLevelKind:
		table, idCol = "book_kinds", "book_kind_id"
	case deleteLevelAttr:
		table, idCol = "book_attributes", "attr_id"
	default:
		return "", fmt.Errorf("unknown level %q", level)
	}
	var ref *string
	err := s.pool.QueryRow(ctx,
		`SELECT source_ref FROM `+table+` WHERE book_id=$1 AND `+idCol+`=$2 AND deprecated_at IS NULL`,
		bookID, id).Scan(&ref)
	if err != nil {
		return "", err
	}
	if ref == nil {
		return "", nil
	}
	return *ref, nil
}

// tierLabel renders a source_ref's parent tier for a human-facing preview.
func tierLabel(sourceRef string) string {
	switch {
	case strings.HasPrefix(sourceRef, "system:"):
		return "System"
	case strings.HasPrefix(sourceRef, "user:"):
		return "User"
	default:
		return "parent"
	}
}

// ── HTTP: POST /v1/glossary/books/{book_id}/ontology/{genres|kinds|attributes}/{id}/revert ──
// Manage-gated (bookOntologyTarget). The human-FE path; the agent path is the class-C
// glossary_book_revert MCP tool. Both call revertBookRow.

func (s *Server) revertBookGenre(w http.ResponseWriter, r *http.Request) {
	s.handleBookRevert(w, r, "genre_id", deleteLevelGenre, func(ctx context.Context, bookID, id uuid.UUID) (any, error) {
		return s.loadBookGenreOne(ctx, bookID, id)
	})
}

func (s *Server) revertBookKind(w http.ResponseWriter, r *http.Request) {
	s.handleBookRevert(w, r, "book_kind_id", deleteLevelKind, func(ctx context.Context, bookID, id uuid.UUID) (any, error) {
		return s.loadBookKindOne(ctx, bookID, id)
	})
}

func (s *Server) revertBookAttribute(w http.ResponseWriter, r *http.Request) {
	s.handleBookRevert(w, r, "attr_id", deleteLevelAttr, func(ctx context.Context, bookID, id uuid.UUID) (any, error) {
		return s.loadBookAttrOne(ctx, bookID, id)
	})
}

func (s *Server) handleBookRevert(w http.ResponseWriter, r *http.Request, idParam, level string, load func(context.Context, uuid.UUID, uuid.UUID) (any, error)) {
	bookID, targetID, ok := s.bookOntologyTarget(w, r, idParam)
	if !ok {
		return
	}
	userID, ok := s.requireUserID(r) // already validated by the Manage gate above
	if !ok {
		return
	}
	reverted, err := s.revertBookRow(r.Context(), bookID, userID, level, targetID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "revert failed")
		return
	}
	if !reverted {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_REVERTABLE",
			"this row is book-native or its parent standard is no longer available")
		return
	}
	detail, err := load(r.Context(), bookID, targetID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

// ── MCP: glossary_book_revert (class C) ──────────────────────────────────────────

type bookRevertToolIn struct {
	BookID    string `json:"book_id" jsonschema:"the book whose row to revert (UUID)"`
	Level     string `json:"level" jsonschema:"what to revert: genre | kind | attribute"`
	Code      string `json:"code" jsonschema:"the code of the genre/kind, or (for level=attribute) the attribute's own code"`
	KindCode  string `json:"kind_code,omitempty" jsonschema:"for level=attribute: the kind code the attribute belongs to"`
	GenreCode string `json:"genre_code,omitempty" jsonschema:"for level=attribute: the genre code the attribute belongs to"`
}

func (s *Server) toolBookRevert(ctx context.Context, req *mcp.CallToolRequest, in bookRevertToolIn) (*mcp.CallToolResult, any, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, confirmCardOut{}, fmt.Errorf("missing caller identity")
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, confirmCardOut{}, fmt.Errorf("book_id must be a UUID")
	}
	level := strings.TrimSpace(in.Level)
	code := strings.TrimSpace(in.Code)
	if code == "" {
		return nil, confirmCardOut{}, fmt.Errorf("code is required")
	}
	p := bookDeleteParams{Level: level, Code: code,
		KindCode: strings.TrimSpace(in.KindCode), GenreCode: strings.TrimSpace(in.GenreCode)}
	switch level {
	case deleteLevelGenre, deleteLevelKind:
	case deleteLevelAttr:
		if p.KindCode == "" || p.GenreCode == "" {
			return nil, confirmCardOut{}, fmt.Errorf("kind_code and genre_code are required to revert an attribute")
		}
	default:
		return nil, confirmCardOut{}, fmt.Errorf("level must be genre, kind, or attribute")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantManage); err != nil {
		return nil, confirmCardOut{}, uniformOwnershipError(err)
	}
	// Mint-time validation: the row must exist AND be an adopted (sourced) row.
	targetID, err := s.resolveDeleteTarget(ctx, bookID, p)
	if isNoRows(err) {
		return nil, confirmCardOut{}, fmt.Errorf("no live %s with that code in this book", level)
	}
	if err != nil {
		return nil, confirmCardOut{}, fmt.Errorf("failed to resolve the target")
	}
	ref, err := s.bookRowSourceRef(ctx, bookID, level, targetID)
	if err != nil {
		return nil, confirmCardOut{}, fmt.Errorf("failed to resolve the target")
	}
	if ref == "" {
		return nil, confirmCardOut{}, fmt.Errorf("this %s is book-native — it has no parent standard to revert to", level)
	}
	tier := tierLabel(ref)
	rows := []previewRow{
		{Label: "level", Value: level},
		{Label: "code", Value: code},
		{Label: "reverts to", Value: tier + " default", Note: "discards this book's local edits to this row"},
	}
	title := fmt.Sprintf("Revert %s %q to its %s default", level, code, tier)
	_, card, cerr := s.mintGrantActionCard(userID, bookID, descBookRevert, title, p, rows, false)
	return s.gateOrCard(ctx, req, descBookRevert, bookID, userID, p, card, cerr)
}
