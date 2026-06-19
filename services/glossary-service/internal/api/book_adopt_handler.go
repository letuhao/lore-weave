package api

// G3 — book adopt (copy-down) + book-local ontology read. The heart of the
// standards→sovereign-instance model (spec 2026-06-19 §3; proven by the G0 spike).
//
// ADOPT (Moment A): a book is scaffolded from the System standards by copying the
// picked genres/kinds (+ their kind↔genre links + attributes) into the book tier,
// recording source_ref/source_hash for later Sync (G5). `universal` is always
// adopted (O4) and the `unknown` kind is always adopted (E6 — extraction parks
// unrecognized kinds there). Idempotent: ON CONFLICT DO NOTHING + a per-book
// advisory lock serializes concurrent/double-submit adopts.
//
// ONTOLOGY (Moment B): a book-LOCAL, single-tier read — touches only book_* tables,
// never system_*/user_* (the spike's EXPLAIN proof). This is the Manage workspace +
// entity-form source.
//
// SCOPE (G3a): the copy-down source is the SYSTEM tier. The User-tier union at adopt
// (D7 — book owner's user overrides shadow system by code) and book-tier CRUD are
// tracked follow-ups (D-GKA-ADOPT-USER-TIER, D-GKA-BOOK-CRUD). Adopt-from-system is
// the foundational path every book takes; user overrides layer on after.

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

// ── response types (book-local) ───────────────────────────────────────────────

type bookGenreResp struct {
	GenreID   string  `json:"genre_id"`
	Code      string  `json:"code"`
	Name      string  `json:"name"`
	Icon      string  `json:"icon"`
	Color     string  `json:"color"`
	SortOrder int     `json:"sort_order"`
	Active    bool    `json:"active"`
	SourceRef *string `json:"source_ref,omitempty"`
}

type bookKindResp struct {
	BookKindID  string  `json:"book_kind_id"`
	Code        string  `json:"code"`
	Name        string  `json:"name"`
	Description *string `json:"description,omitempty"`
	Icon        string  `json:"icon"`
	Color       string  `json:"color"`
	SortOrder   int     `json:"sort_order"`
	IsHidden    bool    `json:"is_hidden"`
	SourceRef   *string `json:"source_ref,omitempty"`
}

type bookKindGenreLink struct {
	KindID  string `json:"kind_id"`
	GenreID string `json:"genre_id"`
}

type bookAttrResp struct {
	AttrID      string   `json:"attr_id"`
	KindID      string   `json:"kind_id"`
	GenreID     string   `json:"genre_id"`
	Code        string   `json:"code"`
	Name        string   `json:"name"`
	Description *string  `json:"description,omitempty"`
	FieldType   string   `json:"field_type"`
	IsRequired  bool     `json:"is_required"`
	SortOrder   int      `json:"sort_order"`
	Options     []string `json:"options"`
	SourceRef   *string  `json:"source_ref,omitempty"`
}

type bookOntologyResp struct {
	BookID     string              `json:"book_id"`
	Genres     []bookGenreResp     `json:"genres"`
	Kinds      []bookKindResp      `json:"kinds"`
	KindGenres []bookKindGenreLink `json:"kind_genres"`
	Attributes []bookAttrResp      `json:"attributes"`
}

// ── POST /v1/glossary/books/{book_id}/adopt ────────────────────────────────────

func (s *Server) adoptBookOntology(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	// Structural scaffolding of the book's ontology → Manage (owner + manage-grantees);
	// a View/Edit collaborator must not reshape the book's kind/genre ontology.
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantManage) {
		return
	}

	var in struct {
		Genres []string `json:"genres"`
		Kinds  []string `json:"kinds"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	// `universal` is mandatory + always-active (O4); `unknown` always adopted (E6).
	genres := dedupAppend(in.Genres, "universal")
	kinds := dedupAppend(in.Kinds, "unknown")

	ctx := r.Context()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx failed")
		return
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	// Per-book advisory lock: serialize concurrent / double-submit adopts so the
	// multi-statement copy can't interleave. Released on commit/rollback.
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext('gloss-adopt:' || $1::text))`, bookID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "lock failed")
		return
	}

	// 1) genres
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_genres (book_id, code, name, icon, color, sort_order, source_ref, source_hash)
		SELECT $1, sg.code, sg.name, sg.icon, sg.color, sg.sort_order, 'system:'||sg.genre_id::text, sg.content_hash
		FROM system_genres sg WHERE sg.code = ANY($2)
		ON CONFLICT (book_id, code) DO NOTHING`, bookID, genres); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "adopt genres failed")
		return
	}
	// 2) activate the adopted genres
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_active_genres (book_id, genre_id)
		SELECT $1, bg.genre_id FROM book_genres bg WHERE bg.book_id=$1 AND bg.code = ANY($2)
		ON CONFLICT DO NOTHING`, bookID, genres); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "activate genres failed")
		return
	}
	// 3) kinds (source_hash computed inline — system_kinds has no content_hash column)
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_kinds (book_id, code, name, description, icon, color, sort_order, is_hidden, source_ref, source_hash)
		SELECT $1, sk.code, sk.name, sk.description, sk.icon, sk.color, sk.sort_order, sk.is_hidden,
		       'system:'||sk.kind_id::text, md5(sk.code||'|'||sk.name||'|'||coalesce(sk.description,''))
		FROM system_kinds sk WHERE sk.code = ANY($2)
		ON CONFLICT (book_id, code) DO NOTHING`, bookID, kinds); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "adopt kinds failed")
		return
	}
	// 4) kind↔genre links (picked kinds × picked genres the system kind supports), remapped to book ids
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_kind_genres (book_id, kind_id, genre_id)
		SELECT $1, bk.book_kind_id, bg.genre_id
		FROM system_kind_genres skg
		JOIN system_kinds  sk ON sk.kind_id  = skg.kind_id
		JOIN system_genres sg ON sg.genre_id = skg.genre_id
		JOIN book_kinds  bk ON bk.book_id=$1 AND bk.code = sk.code
		JOIN book_genres bg ON bg.book_id=$1 AND bg.code = sg.code
		WHERE sk.code = ANY($2) AND sg.code = ANY($3)
		ON CONFLICT DO NOTHING`, bookID, kinds, genres); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "adopt kind-genres failed")
		return
	}
	// 5) attributes for the picked (kind × genre) cells, remapped to book ids
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_attributes
		  (book_id, kind_id, genre_id, code, name, description, field_type, is_required,
		   sort_order, options, auto_fill_prompt, translation_hint, source_ref, source_hash)
		SELECT $1, bk.book_kind_id, bg.genre_id, sa.code, sa.name, sa.description, sa.field_type, sa.is_required,
		       sa.sort_order, sa.options, sa.auto_fill_prompt, sa.translation_hint,
		       'system:'||sa.attr_id::text, sa.content_hash
		FROM system_attributes sa
		JOIN system_kinds  sk ON sk.kind_id  = sa.kind_id
		JOIN system_genres sg ON sg.genre_id = sa.genre_id
		JOIN book_kinds  bk ON bk.book_id=$1 AND bk.code = sk.code
		JOIN book_genres bg ON bg.book_id=$1 AND bg.code = sg.code
		WHERE sk.code = ANY($2) AND sg.code = ANY($3)
		ON CONFLICT (book_id, kind_id, genre_id, code) DO NOTHING`, bookID, kinds, genres); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "adopt attributes failed")
		return
	}

	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}

	ont, err := s.loadBookOntology(ctx, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load ontology failed")
		return
	}
	writeJSON(w, http.StatusOK, ont)
}

// ── GET /v1/glossary/books/{book_id}/ontology ──────────────────────────────────

func (s *Server) getBookOntology(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
		return
	}
	ont, err := s.loadBookOntology(r.Context(), bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load ontology failed")
		return
	}
	writeJSON(w, http.StatusOK, ont)
}

// loadBookOntology reads the book's full ontology from book_* tables ONLY
// (single-tier; no system_*/user_* join — the spike's book-local read proof).
func (s *Server) loadBookOntology(ctx context.Context, bookID uuid.UUID) (*bookOntologyResp, error) {
	ont := &bookOntologyResp{
		BookID:     bookID.String(),
		Genres:     []bookGenreResp{},
		Kinds:      []bookKindResp{},
		KindGenres: []bookKindGenreLink{},
		Attributes: []bookAttrResp{},
	}

	grows, err := s.pool.Query(ctx, `
		SELECT bg.genre_id::text, bg.code, bg.name, bg.icon, bg.color, bg.sort_order,
		       (bag.genre_id IS NOT NULL) AS active, bg.source_ref
		FROM book_genres bg
		LEFT JOIN book_active_genres bag ON bag.book_id = bg.book_id AND bag.genre_id = bg.genre_id
		WHERE bg.book_id = $1 AND bg.deprecated_at IS NULL
		ORDER BY bg.sort_order, bg.code`, bookID)
	if err != nil {
		return nil, err
	}
	defer grows.Close()
	for grows.Next() {
		var g bookGenreResp
		if err := grows.Scan(&g.GenreID, &g.Code, &g.Name, &g.Icon, &g.Color, &g.SortOrder, &g.Active, &g.SourceRef); err != nil {
			return nil, err
		}
		ont.Genres = append(ont.Genres, g)
	}
	if err := grows.Err(); err != nil {
		return nil, err
	}

	krows, err := s.pool.Query(ctx, `
		SELECT book_kind_id::text, code, name, description, icon, color, sort_order, is_hidden, source_ref
		FROM book_kinds WHERE book_id = $1 AND deprecated_at IS NULL ORDER BY sort_order, code`, bookID)
	if err != nil {
		return nil, err
	}
	defer krows.Close()
	for krows.Next() {
		var k bookKindResp
		if err := krows.Scan(&k.BookKindID, &k.Code, &k.Name, &k.Description, &k.Icon, &k.Color, &k.SortOrder, &k.IsHidden, &k.SourceRef); err != nil {
			return nil, err
		}
		ont.Kinds = append(ont.Kinds, k)
	}
	if err := krows.Err(); err != nil {
		return nil, err
	}

	lrows, err := s.pool.Query(ctx, `
		SELECT kind_id::text, genre_id::text FROM book_kind_genres WHERE book_id = $1`, bookID)
	if err != nil {
		return nil, err
	}
	defer lrows.Close()
	for lrows.Next() {
		var l bookKindGenreLink
		if err := lrows.Scan(&l.KindID, &l.GenreID); err != nil {
			return nil, err
		}
		ont.KindGenres = append(ont.KindGenres, l)
	}
	if err := lrows.Err(); err != nil {
		return nil, err
	}

	arows, err := s.pool.Query(ctx, `
		SELECT attr_id::text, kind_id::text, genre_id::text, code, name, description,
		       field_type, is_required, sort_order, options, source_ref
		FROM book_attributes WHERE book_id = $1 AND deprecated_at IS NULL ORDER BY sort_order, code`, bookID)
	if err != nil {
		return nil, err
	}
	defer arows.Close()
	for arows.Next() {
		var a bookAttrResp
		if err := arows.Scan(&a.AttrID, &a.KindID, &a.GenreID, &a.Code, &a.Name, &a.Description,
			&a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options, &a.SourceRef); err != nil {
			return nil, err
		}
		if a.Options == nil {
			a.Options = []string{}
		}
		ont.Attributes = append(ont.Attributes, a)
	}
	if err := arows.Err(); err != nil {
		return nil, err
	}
	return ont, nil
}

// dedupAppend returns the input with `extra` guaranteed present, de-duplicated,
// dropping empties.
func dedupAppend(in []string, extra string) []string {
	seen := map[string]struct{}{}
	out := []string{}
	add := func(s string) {
		if s == "" {
			return
		}
		if _, ok := seen[s]; ok {
			return
		}
		seen[s] = struct{}{}
		out = append(out, s)
	}
	for _, s := range in {
		add(s)
	}
	add(extra)
	return out
}
