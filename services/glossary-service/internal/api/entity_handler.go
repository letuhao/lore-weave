package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/loreweave/grantclient"
)

// ── response types ────────────────────────────────────────────────────────────

type kindSummary struct {
	KindID string `json:"kind_id"`
	Code   string `json:"code"`
	Name   string `json:"name"`
	Icon   string `json:"icon"`
	Color  string `json:"color"`
}

type chapterLinkResp struct {
	LinkID       string    `json:"link_id"`
	EntityID     string    `json:"entity_id"`
	ChapterID    string    `json:"chapter_id"`
	ChapterTitle *string   `json:"chapter_title"`
	ChapterIndex *int      `json:"chapter_index"`
	Relevance    string    `json:"relevance"`
	Note         *string   `json:"note"`
	AddedAt      time.Time `json:"added_at"`
	// MentionCount (M7) — per-chapter mention frequency, surfaced so the FE heatmap
	// reads per-chapter counts instead of a whole-book scalar. 0 for un-recounted rows.
	MentionCount int `json:"mention_count"`
}

type attrDefResp struct {
	AttrDefID  string   `json:"attr_def_id"`
	Code       string   `json:"code"`
	Name       string   `json:"name"`
	FieldType  string   `json:"field_type"`
	IsRequired bool     `json:"is_required"`
	IsSystem   bool     `json:"is_system"`
	SortOrder  int      `json:"sort_order"`
	Options    []string `json:"options,omitempty"`
	// #26/#7 — the authored merge_strategy. The FE branches on 'summarize' to render the
	// synthesized canonical_value as the headline + the raw items under "sources/history".
	MergeStrategy string `json:"merge_strategy,omitempty"`
}

type translationResp struct {
	TranslationID string    `json:"translation_id"`
	AttrValueID   string    `json:"attr_value_id"`
	LanguageCode  string    `json:"language_code"`
	Value         string    `json:"value"`
	Confidence    string    `json:"confidence"`
	Translator    *string   `json:"translator,omitempty"`
	UpdatedAt     time.Time `json:"updated_at"`
}

type evidenceTranslationResp struct {
	ID           string `json:"id"`
	EvidenceID   string `json:"evidence_id"`
	LanguageCode string `json:"language_code"`
	Value        string `json:"value"`
	Confidence   string `json:"confidence"`
}

type evidenceResp struct {
	EvidenceID       string                    `json:"evidence_id"`
	AttrValueID      string                    `json:"attr_value_id"`
	ChapterID        *string                   `json:"chapter_id"`
	ChapterTitle     *string                   `json:"chapter_title"`
	BlockOrLine      string                    `json:"block_or_line"`
	EvidenceType     string                    `json:"evidence_type"`
	OriginalLanguage string                    `json:"original_language"`
	OriginalText     string                    `json:"original_text"`
	Note             *string                   `json:"note"`
	CreatedAt        time.Time                 `json:"created_at"`
	Translations     []evidenceTranslationResp `json:"translations"`
}

type attrValueResp struct {
	AttrValueID      string            `json:"attr_value_id"`
	EntityID         string            `json:"entity_id"`
	AttrDefID        string            `json:"attr_def_id"`
	AttributeDef     attrDefResp       `json:"attribute_def"`
	OriginalLanguage string            `json:"original_language"`
	OriginalValue    string            `json:"original_value"`
	Translations     []translationResp `json:"translations"`
	Evidences        []evidenceResp    `json:"evidences"`
	// #26/#7 summarize mode — the LLM-synthesized canonical value (null until the first
	// end-of-job resynthesis) + whether a re-synthesis is pending (the raw set changed since).
	CanonicalValue *string `json:"canonical_value,omitempty"`
	CanonicalDirty bool    `json:"canonical_dirty,omitempty"`
}

type entityListItem struct {
	EntityID               string       `json:"entity_id"`
	BookID                 string       `json:"book_id"`
	KindID                 string       `json:"kind_id"`
	Kind                   kindSummary  `json:"kind"`
	DisplayName            string       `json:"display_name"`
	DisplayNameTranslation *string      `json:"display_name_translation"`
	Status                 string       `json:"status"`
	Tags                   []string     `json:"tags"`
	ShortDescription       *string      `json:"short_description"`
	// ScopeLabel (D-GLOSSARY-ENTITY-SCOPE) — an optional author-set disambiguator
	// (e.g. a world/realm name); "" when unset (the common case). Surfaced so an
	// agent/human can see whether a name collision already carries a scope before
	// deciding whether a NEW entity of the same name needs a different one.
	ScopeLabel             string       `json:"scope_label,omitempty"`
	IsPinnedForContext     bool         `json:"is_pinned_for_context"`
	ChapterLinkCount       int          `json:"chapter_link_count"`
	TranslationCount       int          `json:"translation_count"`
	EvidenceCount          int          `json:"evidence_count"`
	CreatedAt              time.Time    `json:"created_at"`
	UpdatedAt              time.Time    `json:"updated_at"`
	Match                  *entityMatch `json:"match,omitempty"` // raw-search only: why this entity matched
}

type entityListResp struct {
	Items  []entityListItem `json:"items"`
	Total  int              `json:"total"`
	Limit  int              `json:"limit"`
	Offset int              `json:"offset"`
}

type entityDetailResp struct {
	entityListItem
	ChapterLinks    []chapterLinkResp `json:"chapter_links"`
	AttributeValues []attrValueResp   `json:"attribute_values"`
}

// ── small helpers ─────────────────────────────────────────────────────────────

func splitNonEmpty(s, sep string) []string {
	out := []string{}
	for _, p := range strings.Split(s, sep) {
		if t := strings.TrimSpace(p); t != "" {
			out = append(out, t)
		}
	}
	return out
}

// ── loadEntityDetail ──────────────────────────────────────────────────────────

func (s *Server) loadEntityDetail(ctx context.Context, bookID, entityID uuid.UUID) (*entityDetailResp, error) {
	var d entityDetailResp

	// Query 1: entity + kind + aggregate counts + display_name
	err := s.pool.QueryRow(ctx, `
		SELECT
			e.entity_id, e.book_id, e.kind_id, e.status, e.tags, e.created_at, e.updated_at,
			ek.book_kind_id, ek.code, ek.name, ek.icon, ek.color,
			COALESCE((
				SELECT eav.original_value FROM entity_attribute_values eav
				JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
				WHERE eav.entity_id = e.entity_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			), '') AS display_name,
			e.short_description, e.scope_label, e.is_pinned_for_context,
			(SELECT COUNT(*) FROM chapter_entity_links WHERE entity_id = e.entity_id) AS chapter_link_count,
			(SELECT COUNT(*) FROM attribute_translations tr
				JOIN entity_attribute_values eav2 ON eav2.attr_value_id = tr.attr_value_id
				WHERE eav2.entity_id = e.entity_id) AS translation_count,
			(SELECT COUNT(*) FROM evidences ev
				JOIN entity_attribute_values eav3 ON eav3.attr_value_id = ev.attr_value_id
				WHERE eav3.entity_id = e.entity_id) AS evidence_count
		FROM glossary_entities e
		JOIN book_kinds ek ON ek.book_kind_id = e.kind_id
		WHERE e.entity_id = $1 AND e.book_id = $2 AND e.deleted_at IS NULL`,
		entityID, bookID,
	).Scan(
		&d.EntityID, &d.BookID, &d.KindID, &d.Status, &d.Tags, &d.CreatedAt, &d.UpdatedAt,
		&d.Kind.KindID, &d.Kind.Code, &d.Kind.Name, &d.Kind.Icon, &d.Kind.Color,
		&d.DisplayName,
		&d.ShortDescription, &d.ScopeLabel, &d.IsPinnedForContext,
		&d.ChapterLinkCount, &d.TranslationCount, &d.EvidenceCount,
	)
	if err == pgx.ErrNoRows {
		return nil, pgx.ErrNoRows
	}
	if err != nil {
		return nil, err
	}
	if d.Tags == nil {
		d.Tags = []string{}
	}

	// Query 2: chapter links
	clRows, err := s.pool.Query(ctx, `
		SELECT link_id, entity_id, chapter_id, chapter_title, chapter_index, relevance, note, added_at, mention_count
		FROM chapter_entity_links
		WHERE entity_id = $1
		ORDER BY chapter_index NULLS LAST, added_at`, entityID)
	if err != nil {
		return nil, err
	}
	defer clRows.Close()

	d.ChapterLinks = []chapterLinkResp{}
	for clRows.Next() {
		var cl chapterLinkResp
		if err := clRows.Scan(
			&cl.LinkID, &cl.EntityID, &cl.ChapterID,
			&cl.ChapterTitle, &cl.ChapterIndex, &cl.Relevance, &cl.Note, &cl.AddedAt, &cl.MentionCount,
		); err != nil {
			return nil, err
		}
		d.ChapterLinks = append(d.ChapterLinks, cl)
	}
	if err := clRows.Err(); err != nil {
		return nil, err
	}

	// Query 3: attribute values + embedded attr defs
	avRows, err := s.pool.Query(ctx, `
		SELECT eav.attr_value_id, eav.entity_id, eav.attr_def_id,
		       eav.original_language, eav.original_value, eav.canonical_value, eav.canonical_dirty,
		       ad.attr_id, ad.code, ad.name, ad.field_type, ad.is_required, false AS is_system, ad.sort_order, ad.options, ad.merge_strategy
		FROM entity_attribute_values eav
		JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
		WHERE eav.entity_id = $1
		ORDER BY ad.sort_order`, entityID)
	if err != nil {
		return nil, err
	}
	defer avRows.Close()

	attrValsByID := map[string]*attrValueResp{}
	var attrValsOrdered []string
	for avRows.Next() {
		var av attrValueResp
		if err := avRows.Scan(
			&av.AttrValueID, &av.EntityID, &av.AttrDefID,
			&av.OriginalLanguage, &av.OriginalValue, &av.CanonicalValue, &av.CanonicalDirty,
			&av.AttributeDef.AttrDefID, &av.AttributeDef.Code, &av.AttributeDef.Name,
			&av.AttributeDef.FieldType, &av.AttributeDef.IsRequired, &av.AttributeDef.IsSystem, &av.AttributeDef.SortOrder, &av.AttributeDef.Options, &av.AttributeDef.MergeStrategy,
		); err != nil {
			return nil, err
		}
		av.Translations = []translationResp{}
		av.Evidences = []evidenceResp{}
		attrValsByID[av.AttrValueID] = &av
		attrValsOrdered = append(attrValsOrdered, av.AttrValueID)
	}
	if err := avRows.Err(); err != nil {
		return nil, err
	}

	// Query 4: all translations for this entity, grouped by attr_value_id
	trRows, err := s.pool.Query(ctx, `
		SELECT tr.translation_id, tr.attr_value_id, tr.language_code,
		       tr.value, tr.confidence, tr.translator, tr.updated_at
		FROM attribute_translations tr
		JOIN entity_attribute_values eav ON eav.attr_value_id = tr.attr_value_id
		WHERE eav.entity_id = $1`, entityID)
	if err != nil {
		return nil, err
	}
	defer trRows.Close()

	for trRows.Next() {
		var tr translationResp
		if err := trRows.Scan(
			&tr.TranslationID, &tr.AttrValueID, &tr.LanguageCode,
			&tr.Value, &tr.Confidence, &tr.Translator, &tr.UpdatedAt,
		); err != nil {
			return nil, err
		}
		if av, ok := attrValsByID[tr.AttrValueID]; ok {
			av.Translations = append(av.Translations, tr)
		}
	}
	if err := trRows.Err(); err != nil {
		return nil, err
	}

	// Query 5: all evidences for this entity, grouped by attr_value_id
	evRows, err := s.pool.Query(ctx, `
		SELECT ev.evidence_id, ev.attr_value_id, ev.chapter_id, ev.chapter_title,
		       ev.block_or_line, ev.evidence_type, ev.original_language,
		       ev.original_text, ev.note, ev.created_at
		FROM evidences ev
		JOIN entity_attribute_values eav ON eav.attr_value_id = ev.attr_value_id
		WHERE eav.entity_id = $1`, entityID)
	if err != nil {
		return nil, err
	}
	defer evRows.Close()

	for evRows.Next() {
		var ev evidenceResp
		ev.Translations = []evidenceTranslationResp{}
		if err := evRows.Scan(
			&ev.EvidenceID, &ev.AttrValueID, &ev.ChapterID, &ev.ChapterTitle,
			&ev.BlockOrLine, &ev.EvidenceType, &ev.OriginalLanguage,
			&ev.OriginalText, &ev.Note, &ev.CreatedAt,
		); err != nil {
			return nil, err
		}
		if av, ok := attrValsByID[ev.AttrValueID]; ok {
			av.Evidences = append(av.Evidences, ev)
		}
	}
	if err := evRows.Err(); err != nil {
		return nil, err
	}

	// Assemble attribute values in sort_order
	d.AttributeValues = make([]attrValueResp, 0, len(attrValsOrdered))
	for _, id := range attrValsOrdered {
		d.AttributeValues = append(d.AttributeValues, *attrValsByID[id])
	}

	return &d, nil
}

// ── POST /v1/glossary/books/{book_id}/entities ────────────────────────────────

func (s *Server) createEntity(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
		return
	}

	var in struct {
		KindID string `json:"kind_id"`
		// Optional per-entity genre override (D2). Non-empty ⇒ the entity's genres are
		// exactly these (+ universal); empty/omitted ⇒ the entity follows the book's
		// active genres. The set also decides which (kind × genre) attribute value rows
		// are seeded (D-GKA-ENTITY-MULTIGENRE-VALUES — one per (genre, code)).
		GenreIDs []string `json:"genre_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.KindID == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "kind_id is required")
		return
	}
	kindID, err := uuid.Parse(in.KindID)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "kind_id must be a UUID")
		return
	}

	ctx := r.Context()

	// Validate the kind is a live, visible BOOK kind of THIS book (G4: kind_id is a
	// book_kind_id — the entity FK now targets book_kinds). A system_kind id would
	// pass an old system check but then violate the book_kinds FK on insert; and a
	// book_kind from another book must not be accepted (tenant boundary).
	var kindExists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM book_kinds
		               WHERE book_kind_id=$1 AND book_id=$2 AND deprecated_at IS NULL AND is_hidden=false)`,
		kindID, bookID,
	).Scan(&kindExists); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "db error")
		return
	}
	if !kindExists {
		writeError(w, http.StatusNotFound, "GLOSS_KIND_NOT_FOUND", "kind not found in this book's ontology (adopt it first)")
		return
	}

	// Validate the per-entity genre override (if any) BEFORE the tx, so a bad id 422s
	// without leaving a half-created entity. universal is auto-included (O4); every id
	// must be a live book genre of THIS book (tenant boundary).
	override := len(in.GenreIDs) > 0
	var overrideSet []uuid.UUID
	if override {
		want := make([]uuid.UUID, 0, len(in.GenreIDs)+1)
		for _, g := range in.GenreIDs {
			id, perr := uuid.Parse(g)
			if perr != nil {
				writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "genre_ids must be UUIDs")
				return
			}
			want = append(want, id)
		}
		var universalID uuid.UUID
		if err := s.pool.QueryRow(ctx,
			`SELECT genre_id FROM book_genres WHERE book_id=$1 AND code='universal' AND deprecated_at IS NULL`,
			bookID).Scan(&universalID); err != nil {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "book has no universal genre (adopt it first)")
			return
		}
		want = append(want, universalID)
		var validCount int
		if err := s.pool.QueryRow(ctx,
			`SELECT count(DISTINCT genre_id) FROM book_genres
			 WHERE book_id=$1 AND deprecated_at IS NULL AND genre_id = ANY($2)`,
			bookID, want).Scan(&validCount); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "validate genres failed")
			return
		}
		if validCount != distinctCount(want) {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "every genre_id must be a live genre of this book")
			return
		}
		overrideSet = want
	}

	// Create entity + attribute value rows in one transaction
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx error")
		return
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	var entityIDStr string
	if err := tx.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, status, tags)
		 VALUES($1,$2,'draft','{}') RETURNING entity_id`,
		bookID, kindID,
	).Scan(&entityIDStr); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert entity failed")
		return
	}
	entityUUID, _ := uuid.Parse(entityIDStr)

	// Resolve the entity's effective genre set: the validated override (persisted as
	// entity_genres rows), or the book's active genres (no override rows — follows the
	// book). The set bounds which attribute value rows we seed.
	var seedGenres []uuid.UUID
	if override {
		if _, err := tx.Exec(ctx,
			`INSERT INTO entity_genres(entity_id, genre_id)
			 SELECT $1, g FROM unnest($2::uuid[]) AS g ON CONFLICT DO NOTHING`,
			entityUUID, overrideSet); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert entity genres failed")
			return
		}
		seedGenres = overrideSet
	} else {
		grows, gerr := tx.Query(ctx, `SELECT genre_id FROM book_active_genres WHERE book_id=$1`, bookID)
		if gerr != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load active genres failed")
			return
		}
		for grows.Next() {
			var gid uuid.UUID
			if err := grows.Scan(&gid); err != nil {
				grows.Close()
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan active genre failed")
				return
			}
			seedGenres = append(seedGenres, gid)
		}
		grows.Close()
	}

	// Seed one attribute_value row per (genre, code) of the kind RESTRICTED to the
	// entity's genres — NOT DISTINCT ON code, so a keep-both conflict (same code in two
	// genres) gets a row per genre and both values persist (D-GKA-ENTITY-MULTIGENRE-VALUES).
	attrRows, err := tx.Query(ctx, `
		SELECT ba.attr_id
		FROM book_attributes ba
		WHERE ba.kind_id=$1 AND ba.deprecated_at IS NULL AND ba.genre_id = ANY($2::uuid[])
		ORDER BY ba.sort_order`, kindID, seedGenres)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load attrs failed")
		return
	}
	var attrDefIDs []string
	for attrRows.Next() {
		var id string
		if err := attrRows.Scan(&id); err != nil {
			attrRows.Close()
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan attr failed")
			return
		}
		attrDefIDs = append(attrDefIDs, id)
	}
	attrRows.Close()

	// Bulk insert one attribute value row per definition
	for _, defID := range attrDefIDs {
		if _, err := tx.Exec(ctx,
			`INSERT INTO entity_attribute_values(entity_id, attr_def_id) VALUES($1,$2)`,
			entityIDStr, defID,
		); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert attr value failed")
			return
		}
	}

	// C4 (K14) — emit glossary.entity_updated inside the SAME tx as the
	// entity insert (true transactional outbox: the event row commits
	// atomically with the entity, or not at all). A fresh draft has no
	// name yet; the payload carries kind + book_id, and the later PATCH
	// that fills the name re-emits — knowledge-service's glossary_sync
	// MERGE (keyed on glossary_entity_id) makes both events idempotent.
	createEntityUUID, _ := uuid.Parse(entityIDStr)
	{
		name, kind, aliases, shortDesc, ok := loadEntityEventFields(ctx, tx, createEntityUUID)
		if !ok {
			name, kind, aliases, shortDesc = "", "", []string{}, ""
		}
		// Phase B: a user-created entity is a "missing-add" correction
		// (before=nil). The creator holds an edit grant (requireGrant above —
		// owner or collaborator), so actor_id = userID.
		payload := buildEntityEventPayload(
			bookID.String(), entityIDStr, name, kind, aliases, shortDesc, "created",
			"user", userID.String(), nil,
		)
		if err := emitEntityUpdatedTx(ctx, tx, createEntityUUID, payload); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "outbox emit failed")
			return
		}
	}

	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}

	entityID, _ := uuid.Parse(entityIDStr)
	detail, err := s.loadEntityDetail(ctx, bookID, entityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load detail failed")
		return
	}
	writeJSON(w, http.StatusCreated, detail)
}

// ── GET /v1/glossary/books/{book_id}/entities ─────────────────────────────────

func (s *Server) listEntities(w http.ResponseWriter, r *http.Request) {
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

	ctx := r.Context()
	q := r.URL.Query()
	displayLang := strings.TrimSpace(q.Get("display_language"))

	// Build dynamic WHERE clause
	args := []any{bookID}
	n := 1
	where := []string{"e.book_id = $1", "e.deleted_at IS NULL"}

	var displayLangArg int
	displayLangInArgs := false
	bindDisplayLang := func() {
		if displayLang == "" || displayLangInArgs {
			return
		}
		n++
		displayLangArg = n
		args = append(args, displayLang)
		displayLangInArgs = true
	}

	// Filter: kind_codes
	if kc := q.Get("kind_codes"); kc != "" {
		codes := splitNonEmpty(kc, ",")
		if len(codes) > 0 {
			n++
			where = append(where, fmt.Sprintf("ek.code = ANY($%d)", n))
			args = append(args, codes)
		}
	}

	// Filter: status
	if st := q.Get("status"); st != "" && st != "all" {
		n++
		where = append(where, fmt.Sprintf("e.status = $%d", n))
		args = append(args, st)
	}

	// Filter: chapter_ids or "unlinked"
	if ci := q.Get("chapter_ids"); ci != "" {
		if ci == "unlinked" {
			where = append(where, "NOT EXISTS (SELECT 1 FROM chapter_entity_links WHERE entity_id = e.entity_id)")
		} else {
			ids := splitNonEmpty(ci, ",")
			validIDs := make([]string, 0, len(ids))
			for _, id := range ids {
				if uid, err := uuid.Parse(id); err == nil {
					validIDs = append(validIDs, uid.String())
				}
			}
			if len(validIDs) > 0 {
				n++
				where = append(where, fmt.Sprintf(
					"EXISTS (SELECT 1 FROM chapter_entity_links WHERE entity_id = e.entity_id AND chapter_id::text = ANY($%d))", n))
				args = append(args, validIDs)
			}
		}
	}

	// Filter: search. Two modes:
	//   simple (default)        — ILIKE '%q%' on the name/term original_value
	//                             (+ the display-language translation when set).
	//   raw (search_mode=raw)   — the entity-side mirror of the chapter raw
	//                             search: ILIKE exact-substring PRIMARY + pg_trgm
	//                             similarity ranking over the denormalised
	//                             cached_name / cached_aliases (+ display-language
	//                             translated name), accelerated by the GIN trigram
	//                             indexes. CJK-safe (search_vector's 'simple' FTS
	//                             config can't segment CJK — see migrate notes).
	searchVal := strings.TrimSpace(q.Get("search"))
	rawMode := q.Get("search_mode") == "raw"
	var rawQArg, rawPatArg int // bound positions of the raw query + escaped pattern (0 = unbound)
	if searchVal != "" {
		if utf8.RuneCountInString(searchVal) > maxEntitySearchRunes {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_QUERY", "search query too long")
			return
		}
	}
	if searchVal != "" && rawMode {
		n++
		rawQArg = n
		args = append(args, searchVal)
		n++
		rawPatArg = n
		args = append(args, escapeLikePattern(searchVal))
		leg := fmt.Sprintf(
			"(e.cached_name ILIKE $%d OR glossary_aliases_text(e.cached_aliases) ILIKE $%d "+
				"OR e.cached_name %% $%d OR glossary_aliases_text(e.cached_aliases) %% $%d)",
			rawPatArg, rawPatArg, rawQArg, rawQArg)
		if displayLang != "" {
			bindDisplayLang()
			leg = "(" + leg + fmt.Sprintf(` OR EXISTS (
				SELECT 1 FROM entity_attribute_values eav
				JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
				JOIN attribute_translations at ON at.attr_value_id = eav.attr_value_id
				WHERE eav.entity_id = e.entity_id
				  AND ad.code IN ('name','term')
				  AND at.language_code = $%d
				  AND at.value ILIKE $%d))`, displayLangArg, rawPatArg)
		}
		where = append(where, leg)
	} else if searchVal != "" {
		n++
		searchArg := n
		args = append(args, "%"+searchVal+"%")
		if displayLang != "" {
			bindDisplayLang()
			where = append(where, fmt.Sprintf(`EXISTS (
			SELECT 1 FROM entity_attribute_values eav
			JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
			WHERE eav.entity_id = e.entity_id
			  AND ad.code IN ('name','term')
			  AND (
			    eav.original_value ILIKE $%d
			    OR EXISTS (
			      SELECT 1 FROM attribute_translations at
			      WHERE at.attr_value_id = eav.attr_value_id
			        AND at.language_code = $%d
			        AND at.value ILIKE $%d
			    )
			  ))`, searchArg, displayLangArg, searchArg))
		} else {
			where = append(where, fmt.Sprintf(`EXISTS (
			SELECT 1 FROM entity_attribute_values eav
			JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
			WHERE eav.entity_id = e.entity_id
			  AND ad.code IN ('name','term')
			  AND eav.original_value ILIKE $%d)`, searchArg))
		}
	}

	// Filter: tags (AND containment)
	if tg := q.Get("tags"); tg != "" {
		tagList := splitNonEmpty(tg, ",")
		if len(tagList) > 0 {
			n++
			where = append(where, fmt.Sprintf("e.tags @> $%d", n))
			args = append(args, tagList)
		}
	}

	whereClause := "WHERE " + strings.Join(where, " AND ")

	// Total count (reuse args without limit/offset)
	countSQL := fmt.Sprintf(`
		SELECT COUNT(*) FROM glossary_entities e
		JOIN book_kinds ek ON ek.book_kind_id = e.kind_id
		%s`, whereClause)
	var total int
	if err := s.pool.QueryRow(ctx, countSQL, args...).Scan(&total); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count query failed")
		return
	}

	// Sort — whitelist-mapped to fixed ORDER BY clauses (no user input is ever
	// interpolated). Raw mode defaults to relevance (exact-first, then trigram
	// similarity). When raw-searching with a display language, an exact match in
	// the translated name joins the top "exact" tier (else a pure translation hit
	// ranks by name/alias similarity ≈0 and sinks).
	transExactExpr := ""
	if rawMode && displayLang != "" && rawPatArg > 0 {
		bindDisplayLang()
		transExactExpr = fmt.Sprintf(`EXISTS (
			SELECT 1 FROM entity_attribute_values eav
			JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
			JOIN attribute_translations at ON at.attr_value_id = eav.attr_value_id
			WHERE eav.entity_id = e.entity_id
			  AND ad.code IN ('name','term')
			  AND at.language_code = $%d
			  AND at.value ILIKE $%d)`, displayLangArg, rawPatArg)
	}
	sortClause := entityOrderBy(q.Get("sort"), rawMode, rawQArg, rawPatArg, transExactExpr)

	// Pagination
	limit := 50
	offset := 0
	// bug #6: allow up to 1000 per page so a large glossary (15000+ entities) can be paged
	// in bulk for activation. A value above the cap (or unparseable) keeps the default 50.
	if v, err := strconv.Atoi(q.Get("limit")); err == nil && v > 0 && v <= 1000 {
		limit = v
	}
	if v, err := strconv.Atoi(q.Get("offset")); err == nil && v >= 0 {
		offset = v
	}
	n++
	limitArg := n
	n++
	offsetArg := n
	args = append(args, limit, offset)

	displayNameSQL := `COALESCE((
				SELECT eav.original_value FROM entity_attribute_values eav
				JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
				WHERE eav.entity_id = e.entity_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			), '')`
	displayNameTranslationSQL := `NULL::text`
	if displayLang != "" {
		bindDisplayLang()
		displayNameSQL = fmt.Sprintf(`COALESCE((
				SELECT COALESCE(NULLIF(at.value, ''), eav.original_value)
				FROM entity_attribute_values eav
				JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
				LEFT JOIN attribute_translations at ON at.attr_value_id = eav.attr_value_id
					AND at.language_code = $%d
				WHERE eav.entity_id = e.entity_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			), '')`, displayLangArg)
		displayNameTranslationSQL = fmt.Sprintf(`(
				SELECT NULLIF(at.value, '')
				FROM entity_attribute_values eav
				JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
				LEFT JOIN attribute_translations at ON at.attr_value_id = eav.attr_value_id
					AND at.language_code = $%d
				WHERE eav.entity_id = e.entity_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			)`, displayLangArg)
	}

	mainSQL := fmt.Sprintf(`
		SELECT
			e.entity_id, e.book_id, e.kind_id, e.status, e.tags, e.created_at, e.updated_at,
			ek.book_kind_id, ek.code, ek.name, ek.icon, ek.color,
			%s AS display_name,
			%s AS display_name_translation,
			e.short_description, e.scope_label, e.is_pinned_for_context,
			(SELECT COUNT(*) FROM chapter_entity_links WHERE entity_id = e.entity_id) AS chapter_link_count,
			(SELECT COUNT(*) FROM attribute_translations tr
				JOIN entity_attribute_values eav2 ON eav2.attr_value_id = tr.attr_value_id
				WHERE eav2.entity_id = e.entity_id) AS translation_count,
			(SELECT COUNT(*) FROM evidences ev
				JOIN entity_attribute_values eav3 ON eav3.attr_value_id = ev.attr_value_id
				WHERE eav3.entity_id = e.entity_id) AS evidence_count,
			e.cached_name, e.cached_aliases
		FROM glossary_entities e
		JOIN book_kinds ek ON ek.book_kind_id = e.kind_id
		%s
		%s
		LIMIT $%d OFFSET $%d`,
		displayNameSQL, displayNameTranslationSQL, whereClause, sortClause, limitArg, offsetArg)

	rows, err := s.pool.Query(ctx, mainSQL, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "list query failed")
		return
	}
	defer rows.Close()

	items := []entityListItem{}
	for rows.Next() {
		var item entityListItem
		var cachedName *string
		var cachedAliases []string
		if err := rows.Scan(
			&item.EntityID, &item.BookID, &item.KindID, &item.Status, &item.Tags,
			&item.CreatedAt, &item.UpdatedAt,
			&item.Kind.KindID, &item.Kind.Code, &item.Kind.Name, &item.Kind.Icon, &item.Kind.Color,
			&item.DisplayName,
			&item.DisplayNameTranslation,
			&item.ShortDescription, &item.ScopeLabel, &item.IsPinnedForContext,
			&item.ChapterLinkCount, &item.TranslationCount, &item.EvidenceCount,
			&cachedName, &cachedAliases,
		); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		if item.Tags == nil {
			item.Tags = []string{}
		}
		// Raw mode: attach the per-row "why it matched" payload (field + verbatim
		// snippet + rune offsets) so the UI can show the match at 20K scale.
		if rawMode && searchVal != "" {
			name := ""
			if cachedName != nil {
				name = *cachedName
			}
			m := buildEntityMatch(name, cachedAliases, item.DisplayNameTranslation, searchVal)
			item.Match = &m
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return
	}

	writeJSON(w, http.StatusOK, entityListResp{
		Items:  items,
		Total:  total,
		Limit:  limit,
		Offset: offset,
	})
}

// ── GET /v1/glossary/books/{book_id}/translation-languages ────────────────────

type bookTranslationLanguagesResp struct {
	Languages []string `json:"languages"`
}

func (s *Server) listBookTranslationLanguages(w http.ResponseWriter, r *http.Request) {
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

	rows, err := s.pool.Query(r.Context(), `
		SELECT DISTINCT at.language_code
		FROM attribute_translations at
		JOIN entity_attribute_values eav ON eav.attr_value_id = at.attr_value_id
		JOIN glossary_entities e ON e.entity_id = eav.entity_id
		WHERE e.book_id = $1 AND e.deleted_at IS NULL
		  AND at.value IS NOT NULL AND trim(at.value) <> ''
		ORDER BY at.language_code`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()

	langs := []string{}
	for rows.Next() {
		var code string
		if err := rows.Scan(&code); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		langs = append(langs, code)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return
	}
	if langs == nil {
		langs = []string{}
	}

	writeJSON(w, http.StatusOK, bookTranslationLanguagesResp{Languages: langs})
}

// ── GET /v1/glossary/books/{book_id}/entities/{entity_id} ─────────────────────

func (s *Server) getEntityDetail(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
		return
	}

	ctx := r.Context()
	detail, err := s.loadEntityDetail(ctx, bookID, entityID)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

// ── PATCH /v1/glossary/books/{book_id}/entities/{entity_id} ──────────────────

func (s *Server) patchEntity(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
		return
	}

	var in map[string]json.RawMessage
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}

	// H5 optimistic concurrency (opt-in): the assistant-edit Apply path sends
	// If-Match carrying the entity's `updated_at` captured when it was read
	// (glossary_get_entity). When present, the UPDATE is gated on that version
	// so a concurrent edit (e.g. the background pipeline) since the read yields
	// 412 instead of a silent lost update. Absent header ⇒ unchanged behavior
	// (the /v1 glossary UI does not send it).
	ifMatch := strings.TrimSpace(r.Header.Get("If-Match"))

	setClauses := []string{}
	args := []any{}
	argN := 1

	if raw, ok := in["status"]; ok {
		var status string
		if err := json.Unmarshal(raw, &status); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid status")
			return
		}
		if !validEntityStatus(status) {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_STATUS",
				"status must be active, inactive, draft, or rejected")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("status = $%d", argN))
		args = append(args, status)
		argN++
	}

	if raw, ok := in["alive"]; ok {
		var alive bool
		if err := json.Unmarshal(raw, &alive); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "alive must be boolean")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("alive = $%d", argN))
		args = append(args, alive)
		argN++
	}

	if raw, ok := in["tags"]; ok {
		var tags []string
		if err := json.Unmarshal(raw, &tags); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid tags")
			return
		}
		if tags == nil {
			tags = []string{}
		}
		setClauses = append(setClauses, fmt.Sprintf("tags = $%d", argN))
		args = append(args, tags)
		argN++
	}

	// short_description is nullable. An explicit null OR a trimmed-empty
	// string both clear the field so the response shape stays consistent.
	// Length cap is measured in runes (characters), not bytes, so CJK
	// content gets the same 500-character budget as Latin.
	//
	// User writes to short_description also flip short_description_auto
	// to false so the backfill/auto-regen hooks never overwrite a user
	// choice (K3.3a sticky-override rule).
	if raw, ok := in["short_description"]; ok {
		var sdPtr *string
		if string(raw) != "null" {
			var sd string
			if err := json.Unmarshal(raw, &sd); err != nil {
				writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY",
					"short_description must be string or null")
				return
			}
			sd = strings.TrimSpace(sd)
			if utf8.RuneCountInString(sd) > 500 {
				writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_SHORT_DESCRIPTION",
					"short_description must be at most 500 characters")
				return
			}
			if sd != "" {
				sdPtr = &sd
			}
		}
		setClauses = append(setClauses, fmt.Sprintf("short_description = $%d", argN))
		args = append(args, sdPtr)
		argN++
		// Mark as user-authored so backfill / auto-regen never overwrite.
		setClauses = append(setClauses, fmt.Sprintf("short_description_auto = $%d", argN))
		args = append(args, false)
		argN++
	}

	// scope_label (D-GLOSSARY-ENTITY-SCOPE) — an optional author-set disambiguator
	// (e.g. a world/realm name) for a name that legitimately recurs across
	// different in-story contexts. Plain string, no nullability tri-state (unlike
	// short_description): an explicit "" clears it, same as any other value sets it.
	if raw, ok := in["scope_label"]; ok {
		var scope string
		if err := json.Unmarshal(raw, &scope); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "scope_label must be a string")
			return
		}
		// /review-impl MED fix (2026-07-09): same bound + message as every other
		// scope_label write path (validateScopeLabel, entity_attribute_edit_tools.go)
		// — an oversized value used to have no path-specific check, risking a raw
		// Postgres "index row size exceeds maximum" error from the uq_entity_dedup
		// btree entry instead of a clean 422.
		validated, verr := validateScopeLabel(scope)
		if verr != nil {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_SCOPE_LABEL", verr.Error())
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("scope_label = $%d", argN))
		args = append(args, validated)
		argN++
	}

	if raw, ok := in["is_pinned_for_context"]; ok {
		var pinned bool
		if err := json.Unmarshal(raw, &pinned); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY",
				"is_pinned_for_context must be boolean")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("is_pinned_for_context = $%d", argN))
		args = append(args, pinned)
		argN++
	}

	ctx := r.Context()

	if len(setClauses) > 0 {
		setClauses = append(setClauses, "updated_at = now()")
		args = append(args, entityID, bookID)
		whereClause := fmt.Sprintf("entity_id = $%d AND book_id = $%d", argN, argN+1)
		if ifMatch != "" {
			args = append(args, ifMatch)
			whereClause += fmt.Sprintf(" AND updated_at = $%d::timestamptz", argN+2)
		}
		updateSQL := fmt.Sprintf(
			"UPDATE glossary_entities SET %s WHERE %s",
			strings.Join(setClauses, ", "), whereClause)

		// Phase B: PATCH is now transactional so the before/after snapshot is
		// captured consistently with the UPDATE (no TOCTOU — design §5 /
		// review-impl MED-3). The glossary.entity_updated event commits
		// atomically with the edit (transactional outbox, like createEntity).
		tx, err := s.pool.Begin(ctx)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "begin tx failed")
			return
		}
		defer tx.Rollback(ctx)

		// Capture BEFORE in-tx (FOR-UPDATE-equivalent: the subsequent UPDATE
		// locks the row, so no concurrent writer can interleave).
		beforeName, beforeKind, beforeAliases, beforeShortDesc, beforeOK :=
			loadEntityEventFields(ctx, tx, entityID)

		tag, err := tx.Exec(ctx, updateSQL, args...)
		if err != nil {
			// A scope_label change can collide with uq_entity_dedup(book_id, kind_id,
			// normalized_name, scope_label) if another entity already holds this exact
			// name+kind+scope — a real, user-actionable conflict, not an infra fault.
			if isUniqueViolation(err) {
				writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_NAME",
					"an entity with this name, kind, and scope already exists in this book")
				return
			}
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
			return
		}
		if tag.RowsAffected() == 0 {
			// With If-Match, 0 rows can mean the version drifted (entity still
			// exists) OR the entity is gone — distinguish so the assistant gets a
			// truthful conflict vs not-found (H5/H6). Without If-Match it can only
			// be not-found (the WHERE was entity_id + book_id only).
			if ifMatch != "" {
				var exists bool
				// EDIT-LOW3: don't swallow a DB error here — a failed existence
				// check is an INFRA fault, not "entity not found". Surface 500 so
				// it isn't mislabelled 404.
				if err := tx.QueryRow(ctx,
					`SELECT EXISTS(SELECT 1 FROM glossary_entities WHERE entity_id=$1 AND book_id=$2)`,
					entityID, bookID).Scan(&exists); err != nil {
					writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "existence check failed")
					return
				}
				if exists {
					writeError(w, http.StatusPreconditionFailed, "GLOSS_VERSION_CONFLICT",
						"entity changed since it was read; re-open and try again")
					return
				}
			}
			writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found")
			return
		}

		// Capture AFTER in-tx and emit transactionally. A user PATCH is a
		// correction by construction (requireGrant edit above → actor = userID).
		afterName, afterKind, afterAliases, afterShortDesc, _ :=
			loadEntityEventFields(ctx, tx, entityID)
		var before *EntitySnapshot
		if beforeOK {
			before = &EntitySnapshot{
				Name:             beforeName,
				Kind:             beforeKind,
				Aliases:          beforeAliases,
				ShortDescription: beforeShortDesc,
			}
		}
		payload := buildEntityEventPayload(
			bookID.String(), entityID.String(),
			afterName, afterKind, afterAliases, afterShortDesc, "updated",
			"user", userID.String(), before,
		)
		if err := emitEntityUpdatedTx(ctx, tx, entityID, payload); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "outbox emit failed")
			return
		}
		if err := tx.Commit(ctx); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
			return
		}
	}

	detail, err := s.loadEntityDetail(ctx, bookID, entityID)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

// ── POST /v1/glossary/books/{book_id}/entities/bulk-status ───────────────────

// bulkSetEntityStatus flips status (active|inactive|draft|rejected) for many entities in
// one transaction-free UPDATE. Primary use: bulk-activate freshly-extracted draft
// entities so they feed the translation glossary (the translation-glossary query
// only returns status='active'). Book-scoped + edit-grant gated.
//
// No outbox event is emitted: the glossary.entity_updated payload carries
// name/kind/aliases/short_description (the wiki-staleness inputs), none of which a
// status flip changes — emitting "updated" here would mark wikis stale for nothing.
func (s *Server) bulkSetEntityStatus(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
		return
	}

	var in struct {
		Status    string   `json:"status"`
		EntityIDs []string `json:"entity_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	if !validEntityStatus(in.Status) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_STATUS",
			"status must be active, inactive, draft, or rejected")
		return
	}
	if len(in.EntityIDs) == 0 {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "entity_ids must not be empty")
		return
	}
	if len(in.EntityIDs) > 1000 {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_TOO_MANY",
			"entity_ids must be at most 1000")
		return
	}
	// Drop malformed ids (mirrors entities/by-ids) — a bad id never matches the
	// book-scoped WHERE anyway, so coerce to a clean uuid slice.
	ids := make([]uuid.UUID, 0, len(in.EntityIDs))
	for _, raw := range in.EntityIDs {
		if id, err := uuid.Parse(strings.TrimSpace(raw)); err == nil {
			ids = append(ids, id)
		}
	}
	if len(ids) == 0 {
		writeJSON(w, http.StatusOK, map[string]int{"updated": 0})
		return
	}

	updated, err := s.bulkSetEntityStatusCore(r.Context(), bookID, in.Status, ids)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bulk status update failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]int{"updated": updated})
}

// bulkSetEntityStatusCore sets `status` on the live, book-scoped entities in `ids`
// and returns the count actually updated. Status validity + grant are the CALLER's
// concern; book-scoping (book_id = $2) is enforced here so a confirm-token effect can
// never touch another book's rows. Single source of truth for the HTTP bulk handler
// and the glossary_propose_status_change confirm effect.
func (s *Server) bulkSetEntityStatusCore(ctx context.Context, bookID uuid.UUID, status string, ids []uuid.UUID) (int, error) {
	if len(ids) == 0 {
		return 0, nil
	}
	tag, err := s.pool.Exec(ctx,
		`UPDATE glossary_entities SET status = $1, updated_at = now()
		 WHERE book_id = $2 AND entity_id = ANY($3::uuid[]) AND deleted_at IS NULL`,
		status, bookID, ids)
	if err != nil {
		return 0, err
	}
	return int(tag.RowsAffected()), nil
}

// countLiveEntitiesInBook returns how many of `ids` are live entities in the book — used
// to render the status-change confirm preview from current state.
func (s *Server) countLiveEntitiesInBook(ctx context.Context, bookID uuid.UUID, ids []uuid.UUID) (int, error) {
	if len(ids) == 0 {
		return 0, nil
	}
	var n int
	err := s.pool.QueryRow(ctx,
		`SELECT count(*) FROM glossary_entities
		 WHERE book_id = $1 AND entity_id = ANY($2::uuid[]) AND deleted_at IS NULL`,
		bookID, ids).Scan(&n)
	return n, err
}

// countEntitiesNeedingStatusChange returns how many of `ids` are live entities in the
// book whose CURRENT status differs from `status` — i.e. how many would actually change.
// effectStatusChange's UPDATE has no `status <> $1` guard, so it reports every live id as
// "updated" even when every one of them already has the target status (external MCP
// discoverability audit #11: used by toolProposeStatusChange to warn on that no-op case).
func (s *Server) countEntitiesNeedingStatusChange(ctx context.Context, bookID uuid.UUID, ids []uuid.UUID, status string) (int, error) {
	if len(ids) == 0 {
		return 0, nil
	}
	var n int
	err := s.pool.QueryRow(ctx,
		`SELECT count(*) FROM glossary_entities
		 WHERE book_id = $1 AND entity_id = ANY($2::uuid[]) AND deleted_at IS NULL AND status <> $3`,
		bookID, ids, status).Scan(&n)
	return n, err
}

// ── POST/DELETE /v1/glossary/books/{book_id}/entities/{entity_id}/pin ────────
//
// Idempotent toggle of the is_pinned_for_context flag used by the
// knowledge-service glossary-fallback selector. POST sets to true,
// DELETE sets to false. Returns 204 on success. Book ownership is
// verified the same way as patchEntity.

func (s *Server) setEntityPinned(w http.ResponseWriter, r *http.Request, pinned bool) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
		return
	}

	// T2-close-7 / P-K2a-02: pin toggle no longer bumps updated_at.
	// Pinning is a UX-only bit, not a semantic edit, and bumping
	// updated_at used to fire the full entity_snapshot rebuild
	// (recalculate_entity_snapshot) for no material change. The
	// self-trigger's watch list dropped `updated_at` in the same
	// cycle as defence-in-depth so even if a future callsite does
	// bump `updated_at` alone, nothing recalcs.
	tag, err := s.pool.Exec(r.Context(),
		`UPDATE glossary_entities
		 SET is_pinned_for_context = $1
		 WHERE entity_id = $2 AND book_id = $3 AND deleted_at IS NULL`,
		pinned, entityID, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "pin update failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) pinEntity(w http.ResponseWriter, r *http.Request) {
	s.setEntityPinned(w, r, true)
}

func (s *Server) unpinEntity(w http.ResponseWriter, r *http.Request) {
	s.setEntityPinned(w, r, false)
}

// ── DELETE /v1/glossary/books/{book_id}/entities/{entity_id} ─────────────────

func (s *Server) deleteEntity(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantManage) {
		return
	}

	found, err := s.softDeleteEntityCore(r.Context(), bookID, entityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if !found {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// softDeleteEntityCore soft-deletes ONE entity (deleted_at=now()). The single
// source of truth for the REST DELETE route above AND the glossary_entity_delete
// Tier-W confirm effect (entity_delete_tools.go) — found=false means the entity
// doesn't exist in this book, or is already deleted (idempotent no-op at the
// caller's discretion).
func (s *Server) softDeleteEntityCore(ctx context.Context, bookID, entityID uuid.UUID) (found bool, err error) {
	tag, err := s.pool.Exec(ctx,
		`UPDATE glossary_entities
		 SET deleted_at = now(), updated_at = now()
		 WHERE entity_id = $1 AND book_id = $2 AND deleted_at IS NULL`,
		entityID, bookID)
	if err != nil {
		return false, err
	}
	return tag.RowsAffected() > 0, nil
}

// ── POST /v1/glossary/books/{book_id}/entities/bulk-delete ───────────────────

// bulkDeleteEntities soft-deletes many book-scoped entities in one UPDATE — the
// bulk sibling of deleteEntity, for cleaning up duplicate/unwanted entities (e.g.
// the cross-kind duplicates extraction can produce, #38/#39). Book-scoped +
// Manage-grant gated — delete is a destructive, manage-level op, matching the
// single-entity DELETE. Soft-delete (deleted_at) so the row + its history survive;
// returns the count actually deleted — ids that don't match a live book entity
// simply don't count (the implicit partial-success report).
//
// No outbox event is emitted — mirrors the single-entity deleteEntity (the
// glossary.entity_* events carry no "deleted" variant today; adding one is a
// separate cross-cutting change).
func (s *Server) bulkDeleteEntities(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantManage) {
		return
	}

	var in struct {
		EntityIDs []string `json:"entity_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	if len(in.EntityIDs) == 0 {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "entity_ids must not be empty")
		return
	}
	if len(in.EntityIDs) > 1000 {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_TOO_MANY",
			"entity_ids must be at most 1000")
		return
	}
	// Drop malformed ids (mirrors bulk-status) — a bad id never matches the
	// book-scoped WHERE anyway, so coerce to a clean uuid slice.
	ids := make([]uuid.UUID, 0, len(in.EntityIDs))
	for _, raw := range in.EntityIDs {
		if id, err := uuid.Parse(strings.TrimSpace(raw)); err == nil {
			ids = append(ids, id)
		}
	}
	if len(ids) == 0 {
		writeJSON(w, http.StatusOK, map[string]int{"deleted": 0})
		return
	}

	tag, err := s.pool.Exec(r.Context(),
		`UPDATE glossary_entities SET deleted_at = now(), updated_at = now()
		 WHERE book_id = $1 AND entity_id = ANY($2::uuid[]) AND deleted_at IS NULL`,
		bookID, ids)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bulk delete failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]int{"deleted": int(tag.RowsAffected())})
}

// ── GET /v1/glossary/books/{book_id}/entity-names ───────────────────────────
// Lightweight names-only surface for editor decoration scanning AND the Plan Hub
// badge name map (F-H9/PH26). Returns entity_id, display_name + kind metadata.
//
// Widened (F-H9/PH26) from the old hard `LIMIT 500` bare-array to KEYSET
// pagination over entity_id ASC (reuses internalListEntities' opaque base64
// cursor codec — encode/decodeEntitiesCursor). Every page carries `truncated`
// (more pages remain) + `next_cursor`, so a large glossary (15000+ entities)
// pages fully instead of being silently capped at 500. The status filter is
// widened to ALL non-deleted entities (deleted_at IS NULL) — the Hub needs the
// full name map across draft/inactive/active, not just active. Book-scoped +
// View-grant gated, exactly as before.

type entityNameItem struct {
	EntityID    string  `json:"entity_id"`
	DisplayName string  `json:"display_name"`
	KindCode    *string `json:"kind_code,omitempty"`
	KindColor   *string `json:"kind_color,omitempty"`
	KindIcon    *string `json:"kind_icon,omitempty"`
	KindName    *string `json:"kind_name,omitempty"`
}

type entityNamesPageResp struct {
	Items      []entityNameItem `json:"items"`
	Truncated  bool             `json:"truncated"`
	NextCursor *string          `json:"next_cursor"`
}

func (s *Server) listEntityNames(w http.ResponseWriter, r *http.Request) {
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

	q := r.URL.Query()
	// Page size: default 200, clamped to [1, 500] (the old hard cap becomes the
	// per-page ceiling; the caller pages past it via next_cursor).
	limit := queryInt(q.Get("limit"), 200)
	if limit < 1 {
		limit = 1
	}
	if limit > 500 {
		limit = 500
	}

	// Opaque keyset cursor over entity_id (reuses the internalListEntities codec).
	// null/missing starts from the first entity; a malformed cursor is a 400.
	var afterArg any
	if raw := q.Get("cursor"); raw != "" {
		id, err := decodeEntitiesCursor(raw)
		if err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_BAD_CURSOR", "invalid cursor: "+err.Error())
			return
		}
		afterArg = id
	} else {
		afterArg = nil
	}

	// Peek-ahead: fetch limit+1 rows; the (limit+1)-th row (if present) confirms a
	// further page and sets truncated + next_cursor without being emitted.
	// display_name resolution MUST mirror the canonical label lookup used everywhere else in this
	// file (loadEntityDetail Q1 + the list queries): the label attribute is keyed under EITHER
	// 'name' OR 'term' (kinds differ — e.g. a glossary term entry labels under 'term'), so a
	// `code = 'name'`-only filter silently drops every term-keyed entity from the name map
	// (glossary-unmatched-attr-fallback bug class). Use the same correlated subquery + IN clause.
	rows, err := s.pool.Query(r.Context(), `
		SELECT e.entity_id,
			COALESCE((
				SELECT eav.original_value FROM entity_attribute_values eav
				JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
				WHERE eav.entity_id = e.entity_id AND ad.code IN ('name','term')
				ORDER BY (ad.code = 'name') DESC, ad.sort_order LIMIT 1
			), '') AS display_name,
			ek.code AS kind_code, ek.color AS kind_color, ek.icon AS kind_icon, ek.name AS kind_name
		FROM glossary_entities e
		JOIN book_kinds ek ON ek.book_kind_id = e.kind_id
		WHERE e.book_id = $1 AND e.deleted_at IS NULL
		  AND ($2::uuid IS NULL OR e.entity_id > $2::uuid)
		ORDER BY e.entity_id ASC
		LIMIT $3`, bookID, afterArg, limit+1)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()

	items := make([]entityNameItem, 0, limit)
	var pageLastID uuid.UUID // entity_id of the last row AT-OR-BEFORE position `limit`
	havePageLast := false
	rowsScanned := 0
	for rows.Next() {
		var entityID uuid.UUID
		var displayName, kindCode, kindColor, kindIcon, kindName *string
		if err := rows.Scan(&entityID, &displayName, &kindCode, &kindColor, &kindIcon, &kindName); err != nil {
			continue
		}
		rowsScanned++
		// The (limit+1)-th row is the peek-ahead: it signals truncation but is
		// neither emitted nor used as the cursor boundary.
		if rowsScanned > limit {
			break
		}
		// Track the last DB row of the page as the cursor boundary REGARDLESS of the
		// name filter below — so a name-filtered row at the page boundary can't strand
		// pagination (mirrors internalListEntities' peek-ahead correctness fix).
		pageLastID = entityID
		havePageLast = true

		dn := ""
		if displayName != nil {
			dn = *displayName
		}
		if dn == "" {
			continue // skip nameless entities (still counted so pagination advances past them)
		}
		items = append(items, entityNameItem{
			EntityID:    entityID.String(),
			DisplayName: dn,
			KindCode:    kindCode,
			KindColor:   kindColor,
			KindIcon:    kindIcon,
			KindName:    kindName,
		})
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "row iteration failed")
		return
	}

	// truncated when a peek-ahead row was observed. next_cursor = the entity_id of the
	// last page row (position `limit`), so the next page resumes at entity_id > it.
	truncated := rowsScanned > limit
	var nextCursor *string
	if truncated && havePageLast {
		c := encodeEntitiesCursor(pageLastID)
		nextCursor = &c
	}

	writeJSON(w, http.StatusOK, entityNamesPageResp{
		Items:      items,
		Truncated:  truncated,
		NextCursor: nextCursor,
	})
}

// parsePathUUID extracts and parses a UUID path parameter, writing a 400 on failure.
func parsePathUUID(w http.ResponseWriter, r *http.Request, param string) (uuid.UUID, bool) {
	id, err := uuid.Parse(chi.URLParam(r, param))
	if err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_ID", "invalid "+param)
		return uuid.Nil, false
	}
	return id, true
}
