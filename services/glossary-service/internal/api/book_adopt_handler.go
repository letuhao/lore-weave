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
// SCOPE: the copy-down merges System (defaults) → the adopting CALLER's User tier
// (D-GKA-ADOPT-USER-TIER, caller-scoped per the owner≈caller-under-Manage decision):
// for each picked code, the caller's user-tier row shadows the System one. This is
// done by inserting the user-tier rows FIRST, then System with ON CONFLICT (book_id,
// code) DO NOTHING — so a code the caller customized resolves to their version, and
// System fills only the codes they didn't. Resolution precedence System→User matches
// CLAUDE.md › User Boundaries. (Book-tier CRUD layers on after: book_ontology_handler.go.)

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

// formatBaseVersion renders a row's updated_at as the base_version token —
// EXACTLY the format compareBaseVersion / bookRowVersion compare against
// (UTC RFC3339Nano). Every read that emits base_version and every OCC check
// must go through this shared formatter so they can never drift.
func formatBaseVersion(t time.Time) string { return t.UTC().Format(time.RFC3339Nano) }

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
	// BaseVersion is the row's updated_at in RFC3339Nano — the optimistic-
	// concurrency token a patch passes back (W0 HIGH: reads must emit it, or the
	// OCC loop is un-completable and every patch degrades to last-writer-wins).
	BaseVersion string `json:"base_version"`
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
	IsPerson    bool    `json:"is_person"` // C4/SD-C4 — a REAL-person kind; excluded from AI wiki-gen/enrichment
	SourceRef   *string `json:"source_ref,omitempty"`
	BaseVersion string  `json:"base_version"`
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
	Options         []string `json:"options"`
	AutoFillPrompt  *string  `json:"auto_fill_prompt,omitempty"`  // G-U2
	TranslationHint *string  `json:"translation_hint,omitempty"`
	SourceRef       *string  `json:"source_ref,omitempty"`
	MergeStrategy   string   `json:"merge_strategy"`
	BaseVersion     string   `json:"base_version"`
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
	ctx := r.Context()
	if err := s.adoptBookOntologyCore(ctx, bookID, userID, in.Genres, in.Kinds); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "adopt failed")
		return
	}
	ont, err := s.loadBookOntology(ctx, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load ontology failed")
		return
	}
	writeJSON(w, http.StatusOK, ont)
}

// internalAdoptBookKinds — POST /internal/books/{book_id}/ontology/adopt-kinds?user_id=
// (internal-token). Idempotently copies the given System kind codes into the book tier
// for user_id, reusing adoptBookOntologyCore — the SAME copy-down the HTTP adopt + MCP
// effect use. knowledge-service's KG graph-schema adopt calls this to auto-seed the
// node-kinds a schema REQUIRES, so adopting a schema no longer 422s NEEDS_GLOSSARY and
// silently fails. No grant check here: the caller (knowledge) already verified the
// user's MANAGE grant on the project's book (the same grant adopt itself requires).
func (s *Server) internalAdoptBookKinds(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	userID, err := uuid.Parse(r.URL.Query().Get("user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "invalid or missing user_id")
		return
	}
	var in struct {
		Kinds []string `json:"kinds"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	// 1) Copy-down from the System/User catalogue (inherits name/icon/label) for any
	//    requested code that IS a catalogue kind.
	if err := s.adoptBookOntologyCore(r.Context(), bookID, userID, nil, in.Kinds); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "adopt kinds failed")
		return
	}
	// 2) A KG schema is authoritative about the node-kinds it needs, and a template
	//    can require kinds that are NOT in the System/User catalogue (so the copy-down
	//    above can't create them). Directly create any such residual code as a minimal
	//    book-tier kind (name = code; the user can rename in glossary). ON CONFLICT skips
	//    codes the copy-down already created, so this is additive + idempotent.
	if len(in.Kinds) > 0 {
		if _, err := s.pool.Exec(r.Context(), `
			INSERT INTO book_kinds (book_id, code, name, source_ref)
			SELECT $1, code, code, 'kg-adopt'
			FROM unnest($2::text[]) AS code
			ON CONFLICT (book_id, code) DO NOTHING`, bookID, in.Kinds); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "create kinds failed")
			return
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"book_id": bookID.String(), "adopted": in.Kinds})
}

// adoptBookOntologyCore copies the picked System standards (shadowed by the caller's
// User tier) into the book tier — the single source of truth shared by the HTTP adopt
// handler and the MCP adopt confirm effect. `universal` genre + `unknown` kind are
// always included (O4/E6). Idempotent (per-book advisory lock + ON CONFLICT DO NOTHING).
func (s *Server) adoptBookOntologyCore(ctx context.Context, bookID, userID uuid.UUID, genresIn, kindsIn []string) error {
	genres := dedupAppend(genresIn, "universal")
	kinds := dedupAppend(kindsIn, "unknown")

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	// Per-book advisory lock: serialize concurrent / double-submit adopts so the
	// multi-statement copy can't interleave. Released on commit/rollback.
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext('gloss-adopt:' || $1::text))`, bookID); err != nil {
		return err
	}

	// 1) genres — caller's User tier FIRST (shadows System by code), then System.
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_genres (book_id, code, name, icon, color, sort_order, source_ref, source_hash)
		SELECT $1, ug.code, ug.name, ug.icon, ug.color, ug.sort_order, 'user:'||ug.genre_id::text, ug.content_hash
		FROM user_genres ug
		WHERE ug.owner_user_id = $3 AND ug.code = ANY($2)
		  AND ug.deleted_at IS NULL AND ug.permanently_deleted_at IS NULL
		ON CONFLICT (book_id, code) DO NOTHING`, bookID, genres, userID); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_genres (book_id, code, name, icon, color, sort_order, source_ref, source_hash)
		SELECT $1, sg.code, sg.name, sg.icon, sg.color, sg.sort_order, 'system:'||sg.genre_id::text, sg.content_hash
		FROM system_genres sg WHERE sg.code = ANY($2) AND sg.deprecated_at IS NULL
		ON CONFLICT (book_id, code) DO NOTHING`, bookID, genres); err != nil {
		return err
	}
	// 2) activate the adopted genres
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_active_genres (book_id, genre_id)
		SELECT $1, bg.genre_id FROM book_genres bg WHERE bg.book_id=$1 AND bg.code = ANY($2)
		ON CONFLICT DO NOTHING`, bookID, genres); err != nil {
		return err
	}
	// 3) kinds — caller's User tier FIRST (shadows System by code), then System.
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_kinds (book_id, code, name, description, icon, color, sort_order, is_hidden, is_person, source_ref, source_hash)
		SELECT $1, uk.code, uk.name, uk.description, uk.icon, uk.color, 0, NOT uk.is_active, uk.is_person,
		       'user:'||uk.user_kind_id::text, md5(uk.code||'|'||uk.name||'|'||coalesce(uk.description,''))
		FROM user_kinds uk
		WHERE uk.owner_user_id = $3 AND uk.code = ANY($2)
		  AND uk.deleted_at IS NULL AND uk.permanently_deleted_at IS NULL
		ON CONFLICT (book_id, code) DO NOTHING`, bookID, kinds, userID); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_kinds (book_id, code, name, description, icon, color, sort_order, is_hidden, is_person, source_ref, source_hash)
		SELECT $1, sk.code, sk.name, sk.description, sk.icon, sk.color, sk.sort_order, sk.is_hidden, sk.is_person,
		       'system:'||sk.kind_id::text, md5(sk.code||'|'||sk.name||'|'||coalesce(sk.description,''))
		FROM system_kinds sk WHERE sk.code = ANY($2) AND sk.deprecated_at IS NULL
		ON CONFLICT (book_id, code) DO NOTHING`, bookID, kinds); err != nil {
		return err
	}
	// 4) kind↔genre links (picked kinds × picked genres), remapped to book ids by code
	//    (union both tiers; adopt can add links, never suppress one).
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_kind_genres (book_id, kind_id, genre_id)
		SELECT $1, bk.book_kind_id, bg.genre_id
		FROM user_kind_genres ukg
		JOIN user_kinds  uk ON uk.user_kind_id = ukg.kind_id  AND uk.owner_user_id = $4
		JOIN user_genres ug ON ug.genre_id      = ukg.genre_id AND ug.owner_user_id = $4
		JOIN book_kinds  bk ON bk.book_id=$1 AND bk.code = uk.code
		JOIN book_genres bg ON bg.book_id=$1 AND bg.code = ug.code
		WHERE uk.code = ANY($2) AND ug.code = ANY($3)
		  AND uk.deleted_at IS NULL AND uk.permanently_deleted_at IS NULL
		  AND ug.deleted_at IS NULL AND ug.permanently_deleted_at IS NULL
		ON CONFLICT DO NOTHING`, bookID, kinds, genres, userID); err != nil {
		return err
	}
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
		return err
	}
	// 5) attributes for the picked (kind × genre) cells, remapped to book ids.
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_attributes
		  (book_id, kind_id, genre_id, code, name, description, field_type, is_required,
		   sort_order, options, auto_fill_prompt, translation_hint, source_ref, source_hash, merge_strategy)
		SELECT $1, bk.book_kind_id, bg.genre_id, ua.code, ua.name, ua.description, ua.field_type, ua.is_required,
		       ua.sort_order, ua.options, ua.auto_fill_prompt, ua.translation_hint,
		       'user:'||ua.attr_id::text, ua.content_hash, ua.merge_strategy
		FROM user_attributes ua
		JOIN user_kinds  uk ON uk.user_kind_id = ua.kind_id  AND uk.owner_user_id = $4
		JOIN user_genres ug ON ug.genre_id      = ua.genre_id AND ug.owner_user_id = $4
		JOIN book_kinds  bk ON bk.book_id=$1 AND bk.code = uk.code
		JOIN book_genres bg ON bg.book_id=$1 AND bg.code = ug.code
		WHERE uk.code = ANY($2) AND ug.code = ANY($3)
		  AND ua.deleted_at IS NULL
		  AND uk.deleted_at IS NULL AND uk.permanently_deleted_at IS NULL
		  AND ug.deleted_at IS NULL AND ug.permanently_deleted_at IS NULL
		ON CONFLICT (book_id, kind_id, genre_id, code) DO NOTHING`, bookID, kinds, genres, userID); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_attributes
		  (book_id, kind_id, genre_id, code, name, description, field_type, is_required,
		   sort_order, options, auto_fill_prompt, translation_hint, source_ref, source_hash, merge_strategy)
		SELECT $1, bk.book_kind_id, bg.genre_id, sa.code, sa.name, sa.description, sa.field_type, sa.is_required,
		       sa.sort_order, sa.options, sa.auto_fill_prompt, sa.translation_hint,
		       'system:'||sa.attr_id::text, sa.content_hash, sa.merge_strategy
		FROM system_attributes sa
		JOIN system_kinds  sk ON sk.kind_id  = sa.kind_id
		JOIN system_genres sg ON sg.genre_id = sa.genre_id
		JOIN book_kinds  bk ON bk.book_id=$1 AND bk.code = sk.code
		JOIN book_genres bg ON bg.book_id=$1 AND bg.code = sg.code
		WHERE sk.code = ANY($2) AND sg.code = ANY($3) AND sa.deprecated_at IS NULL
		ON CONFLICT (book_id, kind_id, genre_id, code) DO NOTHING`, bookID, kinds, genres); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// adoptCounts reports, for the picked codes, how many would be NEWLY adopted vs are
// already present in the book — for the adopt confirm card preview (§12.7). Always
// counts the implicit universal/unknown too.
func (s *Server) adoptCounts(ctx context.Context, bookID uuid.UUID, genresIn, kindsIn []string) (newGenres, newKinds int, err error) {
	genres := dedupAppend(genresIn, "universal")
	kinds := dedupAppend(kindsIn, "unknown")
	// genres that exist as a System OR the caller-agnostic standard but are NOT yet a
	// live book row (a present-but-deprecated row still counts as present — adopt won't
	// resurrect it). Count picked codes absent from book_genres.
	if err = s.pool.QueryRow(ctx, `
		SELECT count(*) FROM unnest($2::text[]) AS c(code)
		WHERE NOT EXISTS (SELECT 1 FROM book_genres bg WHERE bg.book_id=$1 AND bg.code = c.code)`,
		bookID, genres).Scan(&newGenres); err != nil {
		return 0, 0, err
	}
	if err = s.pool.QueryRow(ctx, `
		SELECT count(*) FROM unnest($2::text[]) AS c(code)
		WHERE NOT EXISTS (SELECT 1 FROM book_kinds bk WHERE bk.book_id=$1 AND bk.code = c.code)`,
		bookID, kinds).Scan(&newKinds); err != nil {
		return 0, 0, err
	}
	return newGenres, newKinds, nil
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
		       (bag.genre_id IS NOT NULL) AS active, bg.source_ref, bg.updated_at
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
		var updatedAt time.Time
		if err := grows.Scan(&g.GenreID, &g.Code, &g.Name, &g.Icon, &g.Color, &g.SortOrder, &g.Active, &g.SourceRef, &updatedAt); err != nil {
			return nil, err
		}
		g.BaseVersion = formatBaseVersion(updatedAt)
		ont.Genres = append(ont.Genres, g)
	}
	if err := grows.Err(); err != nil {
		return nil, err
	}

	krows, err := s.pool.Query(ctx, `
		SELECT book_kind_id::text, code, name, description, icon, color, sort_order, is_hidden, is_person, source_ref, updated_at
		FROM book_kinds WHERE book_id = $1 AND deprecated_at IS NULL ORDER BY sort_order, code`, bookID)
	if err != nil {
		return nil, err
	}
	defer krows.Close()
	for krows.Next() {
		var k bookKindResp
		var updatedAt time.Time
		if err := krows.Scan(&k.BookKindID, &k.Code, &k.Name, &k.Description, &k.Icon, &k.Color, &k.SortOrder, &k.IsHidden, &k.IsPerson, &k.SourceRef, &updatedAt); err != nil {
			return nil, err
		}
		k.BaseVersion = formatBaseVersion(updatedAt)
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
		       field_type, is_required, sort_order, options, auto_fill_prompt, translation_hint, source_ref, merge_strategy, updated_at
		FROM book_attributes WHERE book_id = $1 AND deprecated_at IS NULL ORDER BY sort_order, code`, bookID)
	if err != nil {
		return nil, err
	}
	defer arows.Close()
	for arows.Next() {
		var a bookAttrResp
		var updatedAt time.Time
		if err := arows.Scan(&a.AttrID, &a.KindID, &a.GenreID, &a.Code, &a.Name, &a.Description,
			&a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options, &a.AutoFillPrompt, &a.TranslationHint, &a.SourceRef, &a.MergeStrategy, &updatedAt); err != nil {
			return nil, err
		}
		a.BaseVersion = formatBaseVersion(updatedAt)
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
