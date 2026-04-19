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
}

type entityListItem struct {
	EntityID               string      `json:"entity_id"`
	BookID                 string      `json:"book_id"`
	KindID                 string      `json:"kind_id"`
	Kind                   kindSummary `json:"kind"`
	DisplayName            string      `json:"display_name"`
	DisplayNameTranslation *string     `json:"display_name_translation"`
	Status                 string      `json:"status"`
	Tags                   []string    `json:"tags"`
	ShortDescription       *string     `json:"short_description"`
	IsPinnedForContext     bool        `json:"is_pinned_for_context"`
	ChapterLinkCount       int         `json:"chapter_link_count"`
	TranslationCount       int         `json:"translation_count"`
	EvidenceCount          int         `json:"evidence_count"`
	CreatedAt              time.Time   `json:"created_at"`
	UpdatedAt              time.Time   `json:"updated_at"`
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

// verifyBookOwner fetches the book projection and checks that userID is the owner.
// Returns false and writes an appropriate error response on failure.
func (s *Server) verifyBookOwner(w http.ResponseWriter, ctx context.Context, bookID, userID uuid.UUID) bool {
	proj, status := s.fetchBookProjection(ctx, bookID)
	switch {
	case status == http.StatusNotFound:
		writeError(w, http.StatusNotFound, "GLOSS_BOOK_NOT_FOUND", "book not found")
		return false
	case status != http.StatusOK:
		writeError(w, http.StatusServiceUnavailable, "GLOSS_UPSTREAM_UNAVAILABLE", "book service unavailable")
		return false
	case proj.OwnerUserID != userID:
		writeError(w, http.StatusForbidden, "GLOSS_FORBIDDEN", "forbidden")
		return false
	}
	return true
}

// ── loadEntityDetail ──────────────────────────────────────────────────────────

func (s *Server) loadEntityDetail(ctx context.Context, bookID, entityID uuid.UUID) (*entityDetailResp, error) {
	var d entityDetailResp

	// Query 1: entity + kind + aggregate counts + display_name
	err := s.pool.QueryRow(ctx, `
		SELECT
			e.entity_id, e.book_id, e.kind_id, e.status, e.tags, e.created_at, e.updated_at,
			ek.kind_id, ek.code, ek.name, ek.icon, ek.color,
			COALESCE((
				SELECT eav.original_value FROM entity_attribute_values eav
				JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
				WHERE eav.entity_id = e.entity_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			), '') AS display_name,
			e.short_description, e.is_pinned_for_context,
			(SELECT COUNT(*) FROM chapter_entity_links WHERE entity_id = e.entity_id) AS chapter_link_count,
			(SELECT COUNT(*) FROM attribute_translations tr
				JOIN entity_attribute_values eav2 ON eav2.attr_value_id = tr.attr_value_id
				WHERE eav2.entity_id = e.entity_id) AS translation_count,
			(SELECT COUNT(*) FROM evidences ev
				JOIN entity_attribute_values eav3 ON eav3.attr_value_id = ev.attr_value_id
				WHERE eav3.entity_id = e.entity_id) AS evidence_count
		FROM glossary_entities e
		JOIN entity_kinds ek ON ek.kind_id = e.kind_id
		WHERE e.entity_id = $1 AND e.book_id = $2 AND e.deleted_at IS NULL`,
		entityID, bookID,
	).Scan(
		&d.EntityID, &d.BookID, &d.KindID, &d.Status, &d.Tags, &d.CreatedAt, &d.UpdatedAt,
		&d.Kind.KindID, &d.Kind.Code, &d.Kind.Name, &d.Kind.Icon, &d.Kind.Color,
		&d.DisplayName,
		&d.ShortDescription, &d.IsPinnedForContext,
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
		SELECT link_id, entity_id, chapter_id, chapter_title, chapter_index, relevance, note, added_at
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
			&cl.ChapterTitle, &cl.ChapterIndex, &cl.Relevance, &cl.Note, &cl.AddedAt,
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
		       eav.original_language, eav.original_value,
		       ad.attr_def_id, ad.code, ad.name, ad.field_type, ad.is_required, ad.is_system, ad.sort_order
		FROM entity_attribute_values eav
		JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
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
			&av.OriginalLanguage, &av.OriginalValue,
			&av.AttributeDef.AttrDefID, &av.AttributeDef.Code, &av.AttributeDef.Name,
			&av.AttributeDef.FieldType, &av.AttributeDef.IsRequired, &av.AttributeDef.IsSystem, &av.AttributeDef.SortOrder,
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
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}

	var in struct {
		KindID string `json:"kind_id"`
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

	// Validate kind exists and is visible
	var kindExists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM entity_kinds WHERE kind_id=$1 AND is_hidden=false)`, kindID,
	).Scan(&kindExists); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "db error")
		return
	}
	if !kindExists {
		writeError(w, http.StatusNotFound, "GLOSS_KIND_NOT_FOUND", "kind not found")
		return
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

	// Load attribute definitions for this kind
	attrRows, err := tx.Query(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 ORDER BY sort_order`, kindID)
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
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}

	ctx := r.Context()
	q := r.URL.Query()

	// Build dynamic WHERE clause
	args := []any{bookID}
	n := 1
	where := []string{"e.book_id = $1", "e.deleted_at IS NULL"}

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

	// Filter: search (ILIKE on name/term attribute original_value)
	if searchVal := q.Get("search"); searchVal != "" {
		n++
		where = append(where, fmt.Sprintf(`EXISTS (
			SELECT 1 FROM entity_attribute_values eav
			JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
			WHERE eav.entity_id = e.entity_id
			  AND ad.code IN ('name','term')
			  AND eav.original_value ILIKE $%d)`, n))
		args = append(args, "%"+searchVal+"%")
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
		JOIN entity_kinds ek ON ek.kind_id = e.kind_id
		%s`, whereClause)
	var total int
	if err := s.pool.QueryRow(ctx, countSQL, args...).Scan(&total); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count query failed")
		return
	}

	// Sort
	sortClause := "ORDER BY e.updated_at DESC"
	if q.Get("sort") == "updated_at_asc" {
		sortClause = "ORDER BY e.updated_at ASC"
	}

	// Pagination
	limit := 50
	offset := 0
	if v, err := strconv.Atoi(q.Get("limit")); err == nil && v > 0 && v <= 200 {
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

	mainSQL := fmt.Sprintf(`
		SELECT
			e.entity_id, e.book_id, e.kind_id, e.status, e.tags, e.created_at, e.updated_at,
			ek.kind_id, ek.code, ek.name, ek.icon, ek.color,
			COALESCE((
				SELECT eav.original_value FROM entity_attribute_values eav
				JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
				WHERE eav.entity_id = e.entity_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			), '') AS display_name,
			e.short_description, e.is_pinned_for_context,
			(SELECT COUNT(*) FROM chapter_entity_links WHERE entity_id = e.entity_id) AS chapter_link_count,
			(SELECT COUNT(*) FROM attribute_translations tr
				JOIN entity_attribute_values eav2 ON eav2.attr_value_id = tr.attr_value_id
				WHERE eav2.entity_id = e.entity_id) AS translation_count,
			(SELECT COUNT(*) FROM evidences ev
				JOIN entity_attribute_values eav3 ON eav3.attr_value_id = ev.attr_value_id
				WHERE eav3.entity_id = e.entity_id) AS evidence_count
		FROM glossary_entities e
		JOIN entity_kinds ek ON ek.kind_id = e.kind_id
		%s
		%s
		LIMIT $%d OFFSET $%d`,
		whereClause, sortClause, limitArg, offsetArg)

	rows, err := s.pool.Query(ctx, mainSQL, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "list query failed")
		return
	}
	defer rows.Close()

	items := []entityListItem{}
	for rows.Next() {
		var item entityListItem
		if err := rows.Scan(
			&item.EntityID, &item.BookID, &item.KindID, &item.Status, &item.Tags,
			&item.CreatedAt, &item.UpdatedAt,
			&item.Kind.KindID, &item.Kind.Code, &item.Kind.Name, &item.Kind.Icon, &item.Kind.Color,
			&item.DisplayName,
			&item.ShortDescription, &item.IsPinnedForContext,
			&item.ChapterLinkCount, &item.TranslationCount, &item.EvidenceCount,
		); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		if item.Tags == nil {
			item.Tags = []string{}
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
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
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
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}

	var in map[string]json.RawMessage
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}

	setClauses := []string{}
	args := []any{}
	argN := 1

	if raw, ok := in["status"]; ok {
		var status string
		if err := json.Unmarshal(raw, &status); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid status")
			return
		}
		switch status {
		case "active", "inactive", "draft":
		default:
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_STATUS",
				"status must be active, inactive, or draft")
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
		updateSQL := fmt.Sprintf(
			"UPDATE glossary_entities SET %s WHERE entity_id = $%d AND book_id = $%d",
			strings.Join(setClauses, ", "), argN, argN+1)
		tag, err := s.pool.Exec(ctx, updateSQL, args...)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
			return
		}
		if tag.RowsAffected() == 0 {
			writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found")
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
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
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
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}

	ctx := r.Context()
	tag, err := s.pool.Exec(ctx,
		`UPDATE glossary_entities
	 SET deleted_at = now(), updated_at = now()
	 WHERE entity_id = $1 AND book_id = $2 AND deleted_at IS NULL`,
		entityID, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ── GET /v1/glossary/books/{book_id}/entity-names ───────────────────────────
// Lightweight endpoint for editor decoration scanning.
// Returns only entity_id, display_name, display_name_translation, kind metadata.

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
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}

	rows, err := s.pool.Query(r.Context(), `
		SELECT e.entity_id, eav.original_value AS display_name,
			ek.code AS kind_code, ek.color AS kind_color, ek.icon AS kind_icon, ek.name AS kind_name
		FROM glossary_entities e
		JOIN entity_kinds ek ON ek.kind_id = e.kind_id
		LEFT JOIN entity_attribute_values eav ON eav.entity_id = e.entity_id
			AND eav.attr_def_id = (SELECT attr_def_id FROM attribute_definitions WHERE kind_id = e.kind_id AND code = 'name' LIMIT 1)
		WHERE e.book_id = $1 AND e.deleted_at IS NULL AND e.status = 'active'
		ORDER BY eav.original_value
		LIMIT 500`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()

	items := make([]map[string]any, 0, 100)
	for rows.Next() {
		var entityID uuid.UUID
		var displayName, kindCode, kindColor, kindIcon, kindName *string
		if err := rows.Scan(&entityID, &displayName, &kindCode, &kindColor, &kindIcon, &kindName); err != nil {
			continue
		}
		dn := ""
		if displayName != nil {
			dn = *displayName
		}
		if dn == "" {
			continue // skip entities without a name
		}
		m := map[string]any{
			"entity_id":    entityID,
			"display_name": dn,
		}
		if kindCode != nil {
			m["kind_code"] = *kindCode
		}
		if kindColor != nil {
			m["kind_color"] = *kindColor
		}
		if kindIcon != nil {
			m["kind_icon"] = *kindIcon
		}
		if kindName != nil {
			m["kind_name"] = *kindName
		}
		items = append(items, m)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "row iteration failed")
		return
	}

	writeJSON(w, http.StatusOK, items)
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
