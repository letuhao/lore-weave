package api

// G3b — book-tier ontology CRUD (genre·kind·attribute re-architecture, 2026-06-19).
// Spec docs/specs/2026-06-19-genre-kind-attribute-tiering.md; plan
// docs/plans/2026-06-19-genre-kind-attribute-build.md (D-GKA-BOOK-CRUD).
//
// Once a book has adopted its standards (book_adopt_handler.go, G3a), this is the
// surface the Manage workspace uses to reshape the book's SOVEREIGN ontology:
// create book-native genres/kinds/attributes, edit any of them, set the active
// genres (the kind×genre matrix columns), and wire the per-kind genre links (the
// matrix cells). Every row lives in the book tier; reads/writes touch only book_*
// tables (the spike's book-local invariant) — never System/User.
//
// Tenancy: all writes are Manage-gated (book owner + manage-grantees reshape the
// ontology; a View/Edit collaborator cannot — same gate as adopt). Every query is
// scoped by book_id, and genre/kind ids supplied in a body are validated to belong
// to THIS book (book-local FK — a book_kinds row from another book would satisfy the
// raw FK but must be rejected). DELETE is a soft DEPRECATE (deprecated_at) for
// boundary independence + Sync (G5), never a hard row drop.

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/loreweave/grantclient"
)

// ── single-row loaders (book-local, live only) ────────────────────────────────

// loadBookGenreOne fetches one live book genre with its active flag. pgx.ErrNoRows if absent.
func (s *Server) loadBookGenreOne(ctx context.Context, bookID, genreID uuid.UUID) (*bookGenreResp, error) {
	var g bookGenreResp
	var updatedAt time.Time
	err := s.pool.QueryRow(ctx, `
		SELECT bg.genre_id::text, bg.code, bg.name, bg.icon, bg.color, bg.sort_order,
		       (bag.genre_id IS NOT NULL) AS active, bg.source_ref, bg.updated_at
		FROM book_genres bg
		LEFT JOIN book_active_genres bag ON bag.book_id = bg.book_id AND bag.genre_id = bg.genre_id
		WHERE bg.book_id = $1 AND bg.genre_id = $2 AND bg.deprecated_at IS NULL`,
		bookID, genreID,
	).Scan(&g.GenreID, &g.Code, &g.Name, &g.Icon, &g.Color, &g.SortOrder, &g.Active, &g.SourceRef, &updatedAt)
	if err != nil {
		return nil, err
	}
	g.BaseVersion = formatBaseVersion(updatedAt)
	return &g, nil
}

func (s *Server) loadBookKindOne(ctx context.Context, bookID, kindID uuid.UUID) (*bookKindResp, error) {
	var k bookKindResp
	var updatedAt time.Time
	err := s.pool.QueryRow(ctx, `
		SELECT book_kind_id::text, code, name, description, icon, color, sort_order, is_hidden, is_person, source_ref, updated_at
		FROM book_kinds WHERE book_id = $1 AND book_kind_id = $2 AND deprecated_at IS NULL`,
		bookID, kindID,
	).Scan(&k.BookKindID, &k.Code, &k.Name, &k.Description, &k.Icon, &k.Color, &k.SortOrder, &k.IsHidden, &k.IsPerson, &k.SourceRef, &updatedAt)
	if err != nil {
		return nil, err
	}
	k.BaseVersion = formatBaseVersion(updatedAt)
	return &k, nil
}

func (s *Server) loadBookAttrOne(ctx context.Context, bookID, attrID uuid.UUID) (*bookAttrResp, error) {
	var a bookAttrResp
	var updatedAt time.Time
	err := s.pool.QueryRow(ctx, `
		SELECT attr_id::text, kind_id::text, genre_id::text, code, name, description,
		       field_type, is_required, sort_order, options, auto_fill_prompt, translation_hint, source_ref, merge_strategy, updated_at
		FROM book_attributes WHERE book_id = $1 AND attr_id = $2 AND deprecated_at IS NULL`,
		bookID, attrID,
	).Scan(&a.AttrID, &a.KindID, &a.GenreID, &a.Code, &a.Name, &a.Description,
		&a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options, &a.AutoFillPrompt, &a.TranslationHint, &a.SourceRef, &a.MergeStrategy, &updatedAt)
	if err != nil {
		return nil, err
	}
	a.BaseVersion = formatBaseVersion(updatedAt)
	if a.Options == nil {
		a.Options = []string{}
	}
	return &a, nil
}

// bookGenreLive / bookKindLive report whether the id is a live (non-deprecated)
// genre/kind of THIS book — the book-local FK guard for body-supplied ids.
func (s *Server) bookGenreLive(ctx context.Context, bookID, genreID uuid.UUID) (bool, error) {
	var ok bool
	err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM book_genres WHERE book_id=$1 AND genre_id=$2 AND deprecated_at IS NULL)`,
		bookID, genreID).Scan(&ok)
	return ok, err
}

func (s *Server) bookKindLive(ctx context.Context, bookID, kindID uuid.UUID) (bool, error) {
	var ok bool
	err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM book_kinds WHERE book_id=$1 AND book_kind_id=$2 AND deprecated_at IS NULL)`,
		bookID, kindID).Scan(&ok)
	return ok, err
}

// ── genres ─────────────────────────────────────────────────────────────────────

func (s *Server) createBookGenre(w http.ResponseWriter, r *http.Request) {
	bookID, ok := s.requireBookManage(w, r)
	if !ok {
		return
	}

	var in struct {
		Code      string `json:"code"`
		Name      string `json:"name"`
		Icon      string `json:"icon"`
		Color     string `json:"color"`
		SortOrder int    `json:"sort_order"`
		Active    *bool  `json:"active"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	detail, err := s.createBookGenreCore(r.Context(), bookID, bookGenreCreateParams{
		Code: in.Code, Name: in.Name, Icon: in.Icon, Color: in.Color, SortOrder: in.SortOrder, Active: in.Active,
	})
	if err != nil {
		writeBookCreateErr(w, err, "book genre")
		return
	}
	writeJSON(w, http.StatusCreated, detail)
}

// writeBookCreateErr maps the shared create-core sentinels to HTTP responses.
func writeBookCreateErr(w http.ResponseWriter, err error, what string) {
	switch {
	case errors.Is(err, errDuplicateBookCode):
		writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_CODE", "a "+what+" with this code already exists")
	case errors.Is(err, errBookFKNotLive):
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "kind_id or genre_id is not a live row of this book")
	case errors.Is(err, errInvalidFieldType):
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", err.Error())
	case err.Error() == "name is required" || err.Error() == "code could not be derived from name":
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", err.Error())
	default:
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "create failed")
	}
}

func (s *Server) patchBookGenre(w http.ResponseWriter, r *http.Request) {
	bookID, genreID, ok := s.bookOntologyTarget(w, r, "genre_id")
	if !ok {
		return
	}
	if _, err := s.loadBookGenreOne(r.Context(), bookID, genreID); err != nil {
		s.writeLoadErr(w, err, "book genre")
		return
	}
	fields, ok := scanStringIntFields(w, r, []string{"name", "icon", "color"}, []string{"sort_order"})
	if !ok {
		return
	}
	if err := s.applyBookUpdate(r.Context(), "book_genres", "genre_id", bookID, genreID, fields); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
		return
	}
	detail, err := s.loadBookGenreOne(r.Context(), bookID, genreID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

// deleteBookGenre soft-deprecates a book genre and cascades (see cascadeDeleteBookGenre).
func (s *Server) deleteBookGenre(w http.ResponseWriter, r *http.Request) {
	bookID, genreID, ok := s.bookOntologyTarget(w, r, "genre_id")
	if !ok {
		return
	}
	found, err := s.cascadeDeleteBookGenre(r.Context(), bookID, genreID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if !found {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "book genre not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// cascadeDeleteBookGenre soft-deprecates a book genre and cascades in one tx:
// deprecate its attributes, drop its active/link/per-entity rows (boundary
// independence — the genre vanishes from the ontology read but the row survives
// for Sync history). The single source of truth shared by the HTTP delete handler
// and the MCP book_delete confirm path. Returns found=false when no live genre matched.
func (s *Server) cascadeDeleteBookGenre(ctx context.Context, bookID, genreID uuid.UUID) (bool, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return false, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	tag, err := tx.Exec(ctx, `
		UPDATE book_genres SET deprecated_at = now(), updated_at = now()
		WHERE book_id = $1 AND genre_id = $2 AND deprecated_at IS NULL`, bookID, genreID)
	if err != nil {
		return false, err
	}
	if tag.RowsAffected() == 0 {
		return false, nil
	}
	if _, err := tx.Exec(ctx,
		`UPDATE book_attributes SET deprecated_at = now(), updated_at = now()
		 WHERE book_id = $1 AND genre_id = $2 AND deprecated_at IS NULL`, bookID, genreID); err != nil {
		return false, err
	}
	for _, q := range []string{
		`DELETE FROM book_active_genres WHERE book_id = $1 AND genre_id = $2`,
		`DELETE FROM book_kind_genres   WHERE book_id = $1 AND genre_id = $2`,
	} {
		if _, err := tx.Exec(ctx, q, bookID, genreID); err != nil {
			return false, err
		}
	}
	// entity_genres is keyed by genre_id alone (book scope is implied by the genre).
	if _, err := tx.Exec(ctx, `DELETE FROM entity_genres WHERE genre_id = $1`, genreID); err != nil {
		return false, err
	}
	if err := tx.Commit(ctx); err != nil {
		return false, err
	}
	return true, nil
}

// setBookActiveGenres replaces the book's active-genre set (matrix columns).
func (s *Server) setBookActiveGenres(w http.ResponseWriter, r *http.Request) {
	bookID, ok := s.requireBookManage(w, r)
	if !ok {
		return
	}
	genreIDs, ok := s.decodeBookGenreIDSet(w, r, bookID)
	if !ok {
		return
	}

	ctx := r.Context()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx failed")
		return
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	if _, err := tx.Exec(ctx, `DELETE FROM book_active_genres WHERE book_id = $1`, bookID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "clear active failed")
		return
	}
	for _, gid := range genreIDs {
		if _, err := tx.Exec(ctx,
			`INSERT INTO book_active_genres (book_id, genre_id) VALUES ($1,$2) ON CONFLICT DO NOTHING`,
			bookID, gid); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "activate failed")
			return
		}
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}
	s.respondOntology(w, ctx, bookID)
}

// ── kinds ────────────────────────────────────────────────────────────────────

func (s *Server) createBookKind(w http.ResponseWriter, r *http.Request) {
	bookID, ok := s.requireBookManage(w, r)
	if !ok {
		return
	}

	var in struct {
		Code        string  `json:"code"`
		Name        string  `json:"name"`
		Description *string `json:"description"`
		Icon        string  `json:"icon"`
		Color       string  `json:"color"`
		SortOrder   int     `json:"sort_order"`
		IsHidden    bool    `json:"is_hidden"`
		IsPerson    bool    `json:"is_person"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	detail, err := s.createBookKindCore(r.Context(), bookID, bookKindCreateParams{
		Code: in.Code, Name: in.Name, Description: in.Description, Icon: in.Icon,
		Color: in.Color, SortOrder: in.SortOrder, IsHidden: in.IsHidden, IsPerson: in.IsPerson,
	})
	if err != nil {
		writeBookCreateErr(w, err, "book kind")
		return
	}
	writeJSON(w, http.StatusCreated, detail)
}

func (s *Server) patchBookKind(w http.ResponseWriter, r *http.Request) {
	bookID, kindID, ok := s.bookOntologyTarget(w, r, "book_kind_id")
	if !ok {
		return
	}
	if _, err := s.loadBookKindOne(r.Context(), bookID, kindID); err != nil {
		s.writeLoadErr(w, err, "book kind")
		return
	}
	fields, ok := scanBookKindFields(w, r)
	if !ok {
		return
	}
	if err := s.applyBookUpdate(r.Context(), "book_kinds", "book_kind_id", bookID, kindID, fields); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
		return
	}
	detail, err := s.loadBookKindOne(r.Context(), bookID, kindID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

// deleteBookKind soft-deprecates a kind + its attributes and drops its genre links.
func (s *Server) deleteBookKind(w http.ResponseWriter, r *http.Request) {
	bookID, kindID, ok := s.bookOntologyTarget(w, r, "book_kind_id")
	if !ok {
		return
	}
	found, err := s.cascadeDeleteBookKind(r.Context(), bookID, kindID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if !found {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "book kind not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// cascadeDeleteBookKind soft-deprecates a book kind and cascades its attributes +
// genre links in one tx. Shared by the HTTP handler and the MCP book_delete path.
// Returns found=false when no live kind matched.
func (s *Server) cascadeDeleteBookKind(ctx context.Context, bookID, kindID uuid.UUID) (bool, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return false, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	tag, err := tx.Exec(ctx, `
		UPDATE book_kinds SET deprecated_at = now(), updated_at = now()
		WHERE book_id = $1 AND book_kind_id = $2 AND deprecated_at IS NULL`, bookID, kindID)
	if err != nil {
		return false, err
	}
	if tag.RowsAffected() == 0 {
		return false, nil
	}
	if _, err := tx.Exec(ctx,
		`UPDATE book_attributes SET deprecated_at = now(), updated_at = now()
		 WHERE book_id = $1 AND kind_id = $2 AND deprecated_at IS NULL`, bookID, kindID); err != nil {
		return false, err
	}
	if _, err := tx.Exec(ctx,
		`DELETE FROM book_kind_genres WHERE book_id = $1 AND kind_id = $2`, bookID, kindID); err != nil {
		return false, err
	}
	if err := tx.Commit(ctx); err != nil {
		return false, err
	}
	return true, nil
}

// setBookKindGenres replaces a kind's genre links (one matrix row).
func (s *Server) setBookKindGenres(w http.ResponseWriter, r *http.Request) {
	bookID, kindID, ok := s.bookOntologyTarget(w, r, "book_kind_id")
	if !ok {
		return
	}
	if live, err := s.bookKindLive(r.Context(), bookID, kindID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "kind check failed")
		return
	} else if !live {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "book kind not found")
		return
	}
	genreIDs, ok := s.decodeBookGenreIDSet(w, r, bookID)
	if !ok {
		return
	}
	// A book kind must stay linked to ≥1 genre: the ontology is genre-first, so a
	// zero-link kind is unreachable in the Manage drilldown and can hold no attributes
	// (attributes are keyed per kind×genre). This is the load-bearing form of the FE
	// modal's invariant (#25). (User-tier kinds are listed flat, so they allow zero.)
	if len(genreIDs) == 0 {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
			"a kind must stay linked to at least one genre")
		return
	}

	ctx := r.Context()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx failed")
		return
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	if _, err := tx.Exec(ctx, `DELETE FROM book_kind_genres WHERE book_id = $1 AND kind_id = $2`, bookID, kindID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "clear links failed")
		return
	}
	for _, gid := range genreIDs {
		if _, err := tx.Exec(ctx,
			`INSERT INTO book_kind_genres (book_id, kind_id, genre_id) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING`,
			bookID, kindID, gid); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "link failed")
			return
		}
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}
	s.respondOntology(w, ctx, bookID)
}

// ── attributes ─────────────────────────────────────────────────────────────────

func (s *Server) createBookAttribute(w http.ResponseWriter, r *http.Request) {
	bookID, ok := s.requireBookManage(w, r)
	if !ok {
		return
	}

	var in struct {
		KindID          string   `json:"kind_id"`
		GenreID         string   `json:"genre_id"`
		Code            string   `json:"code"`
		Name            string   `json:"name"`
		Description     *string  `json:"description"`
		FieldType       string   `json:"field_type"`
		IsRequired      bool     `json:"is_required"`
		SortOrder       int      `json:"sort_order"`
		Options         []string `json:"options"`
		AutoFillPrompt  *string  `json:"auto_fill_prompt"`
		TranslationHint *string  `json:"translation_hint"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	kindID, err := uuid.Parse(in.KindID)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid kind_id")
		return
	}
	genreID, err := uuid.Parse(in.GenreID)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid genre_id")
		return
	}
	detail, err := s.createBookAttributeCore(r.Context(), bookID, bookAttrCreateParams{
		KindID: kindID, GenreID: genreID, Code: in.Code, Name: in.Name, Description: in.Description,
		FieldType: in.FieldType, IsRequired: in.IsRequired, SortOrder: in.SortOrder, Options: in.Options,
		AutoFillPrompt: in.AutoFillPrompt, TranslationHint: in.TranslationHint,
	})
	if err != nil {
		writeBookCreateErr(w, err, "book attribute")
		return
	}
	writeJSON(w, http.StatusCreated, detail)
}

func (s *Server) patchBookAttribute(w http.ResponseWriter, r *http.Request) {
	bookID, attrID, ok := s.bookOntologyTarget(w, r, "attr_id")
	if !ok {
		return
	}
	if _, err := s.loadBookAttrOne(r.Context(), bookID, attrID); err != nil {
		s.writeLoadErr(w, err, "book attribute")
		return
	}
	fields, ok := scanBookAttrFields(w, r)
	if !ok {
		return
	}
	if err := s.applyBookUpdate(r.Context(), "book_attributes", "attr_id", bookID, attrID, fields); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
		return
	}
	detail, err := s.loadBookAttrOne(r.Context(), bookID, attrID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

func (s *Server) deleteBookAttribute(w http.ResponseWriter, r *http.Request) {
	bookID, attrID, ok := s.bookOntologyTarget(w, r, "attr_id")
	if !ok {
		return
	}
	found, err := s.softDeleteBookAttribute(r.Context(), bookID, attrID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if !found {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "book attribute not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// softDeleteBookAttribute soft-deprecates one book attribute (no children to
// cascade). Shared by the HTTP handler and the MCP book_delete path. found=false
// when no live attribute matched.
func (s *Server) softDeleteBookAttribute(ctx context.Context, bookID, attrID uuid.UUID) (bool, error) {
	tag, err := s.pool.Exec(ctx, `
		UPDATE book_attributes SET deprecated_at = now(), updated_at = now()
		WHERE book_id = $1 AND attr_id = $2 AND deprecated_at IS NULL`, bookID, attrID)
	if err != nil {
		return false, err
	}
	return tag.RowsAffected() > 0, nil
}

// ── shared helpers ─────────────────────────────────────────────────────────────

// requireBookManage resolves book_id and enforces the Manage gate — the common
// preamble for every book-tier ontology write (a View/Edit collaborator cannot
// reshape the ontology; only the owner + manage-grantees).
func (s *Server) requireBookManage(w http.ResponseWriter, r *http.Request) (uuid.UUID, bool) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return uuid.Nil, false
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return uuid.Nil, false
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantManage) {
		return uuid.Nil, false
	}
	return bookID, true
}

// bookOntologyTarget = requireBookManage + a target path id, for the per-row handlers.
func (s *Server) bookOntologyTarget(w http.ResponseWriter, r *http.Request, idParam string) (uuid.UUID, uuid.UUID, bool) {
	bookID, ok := s.requireBookManage(w, r)
	if !ok {
		return uuid.Nil, uuid.Nil, false
	}
	targetID, ok := parsePathUUID(w, r, idParam)
	if !ok {
		return uuid.Nil, uuid.Nil, false
	}
	return bookID, targetID, true
}

// decodeBookGenreIDSet parses {genre_ids:[...]}, validating each id is a live book
// genre of bookID and de-duplicating. Writes 4xx itself on failure.
func (s *Server) decodeBookGenreIDSet(w http.ResponseWriter, r *http.Request, bookID uuid.UUID) ([]uuid.UUID, bool) {
	var in struct {
		GenreIDs []string `json:"genre_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return nil, false
	}
	seen := map[uuid.UUID]struct{}{}
	out := make([]uuid.UUID, 0, len(in.GenreIDs))
	for _, raw := range in.GenreIDs {
		gid, err := uuid.Parse(raw)
		if err != nil {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid genre id: "+raw)
			return nil, false
		}
		if _, dup := seen[gid]; dup {
			continue
		}
		if live, err := s.bookGenreLive(r.Context(), bookID, gid); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "genre check failed")
			return nil, false
		} else if !live {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
				"genre "+raw+" is not a live genre of this book")
			return nil, false
		}
		seen[gid] = struct{}{}
		out = append(out, gid)
	}
	return out, true
}

// respondOntology reloads + writes the book's full ontology (200).
func (s *Server) respondOntology(w http.ResponseWriter, ctx context.Context, bookID uuid.UUID) {
	ont, err := s.loadBookOntology(ctx, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load ontology failed")
		return
	}
	writeJSON(w, http.StatusOK, ont)
}

func (s *Server) writeLoadErr(w http.ResponseWriter, err error, what string) {
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", what+" not found")
		return
	}
	writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
}
