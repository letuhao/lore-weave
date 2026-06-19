package api

// G5 — book Sync (on-demand, pull-based diff/apply of the book's adopted standards).
// Spec docs/specs/2026-06-19-genre-kind-attribute-tiering.md §5; build plan §5.
//
// At adopt (Moment A) each book row captured source_ref ('system:<id>' | 'user:<id>')
// + source_hash (the standard's content_hash at copy time). Sync compares that frozen
// hash against the source's CURRENT hash:
//   - update available  ⇔ source resolves live AND its hash ≠ book.source_hash
//   - source retired     ⇔ source_ref resolves to nothing (deleted/purged) — the book
//                          copy stays frozen, shown as a "retired source" card.
// All pull-based, per-row, never auto-pushed (D8). `take_theirs` overwrites the book
// row's SEMANTIC fields (exactly the hash surface) + refreshes source_hash; `keep_mine`
// just bumps source_hash to silence the prompt (accept divergence).
//
// Genre/attribute hashes are stored content_hash columns; the kind tiers carry no
// content_hash, so the kind hash is recomputed md5(code|name|description) — identical
// to the formula book_adopt_handler.go used to capture book_kinds.source_hash.

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/loreweave/grantclient"
)

// kindHashExpr is the upstream-kind content hash, recomputed from a source row alias.
// MUST match book_adopt_handler.go's md5(code|name|description) so a freshly-adopted
// kind reads as up-to-date.
func kindHashExpr(alias string) string {
	return fmt.Sprintf("md5(%s.code||'|'||%s.name||'|'||coalesce(%s.description,''))", alias, alias, alias)
}

// ── response types ─────────────────────────────────────────────────────────────

type syncVals struct {
	Name        string   `json:"name"`
	Description *string  `json:"description,omitempty"`
	FieldType   *string  `json:"field_type,omitempty"`
	IsRequired  *bool    `json:"is_required,omitempty"`
	Options     []string `json:"options,omitempty"`
}

type syncUpdateItem struct {
	Entity    string    `json:"entity"` // "genre" | "kind" | "attribute"
	ID        string    `json:"id"`     // the BOOK row PK (genre_id|book_kind_id|attr_id)
	Code      string    `json:"code"`
	Status    string    `json:"status"`           // "update_available" | "source_retired"
	SourceRef string    `json:"source_ref"`       // 'system:<id>' | 'user:<id>'
	Mine      syncVals  `json:"mine"`             // the book's current values
	Theirs    *syncVals `json:"theirs,omitempty"` // upstream values (nil when retired)
}

type syncAvailableResp struct {
	BookID  string           `json:"book_id"`
	Updates []syncUpdateItem `json:"updates"`
}

const (
	syncStatusUpdate  = "update_available"
	syncStatusRetired = "source_retired"
)

// ── GET /v1/glossary/books/{book_id}/sync/available ─────────────────────────────

func (s *Server) getBookSyncAvailable(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	// Read-only diff — View is enough (mirrors getBookOntology); apply needs Manage.
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
		return
	}

	ctx := r.Context()
	out := &syncAvailableResp{BookID: bookID.String(), Updates: []syncUpdateItem{}}

	g, err := s.syncGenresAvailable(ctx, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "genre diff failed")
		return
	}
	out.Updates = append(out.Updates, g...)
	k, err := s.syncKindsAvailable(ctx, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "kind diff failed")
		return
	}
	out.Updates = append(out.Updates, k...)
	a, err := s.syncAttributesAvailable(ctx, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "attribute diff failed")
		return
	}
	out.Updates = append(out.Updates, a...)

	writeJSON(w, http.StatusOK, out)
}

func (s *Server) syncGenresAvailable(ctx context.Context, bookID uuid.UUID) ([]syncUpdateItem, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT bg.genre_id::text, bg.code, bg.source_ref, bg.name,
		       COALESCE(sg.content_hash, ug.content_hash) AS up_hash,
		       COALESCE(sg.name, ug.name)                 AS up_name,
		       (sg.genre_id IS NOT NULL OR ug.genre_id IS NOT NULL) AS src_live
		FROM book_genres bg
		LEFT JOIN system_genres sg ON bg.source_ref = 'system:'||sg.genre_id::text
		LEFT JOIN user_genres   ug ON bg.source_ref = 'user:'||ug.genre_id::text
		                           AND ug.deleted_at IS NULL AND ug.permanently_deleted_at IS NULL
		WHERE bg.book_id=$1 AND bg.deprecated_at IS NULL AND bg.source_ref IS NOT NULL
		  AND ( (sg.genre_id IS NULL AND ug.genre_id IS NULL)
		     OR COALESCE(sg.content_hash, ug.content_hash) IS DISTINCT FROM bg.source_hash )
		ORDER BY bg.code`, bookID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []syncUpdateItem{}
	for rows.Next() {
		var it syncUpdateItem
		var upHash, upName *string
		var srcLive bool
		if err := rows.Scan(&it.ID, &it.Code, &it.SourceRef, &it.Mine.Name, &upHash, &upName, &srcLive); err != nil {
			return nil, err
		}
		it.Entity = "genre"
		if !srcLive {
			it.Status = syncStatusRetired
		} else {
			it.Status = syncStatusUpdate
			it.Theirs = &syncVals{Name: derefStr(upName)}
		}
		out = append(out, it)
	}
	return out, rows.Err()
}

func (s *Server) syncKindsAvailable(ctx context.Context, bookID uuid.UUID) ([]syncUpdateItem, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT bk.book_kind_id::text, bk.code, bk.source_ref, bk.name, bk.description,
		       COALESCE(`+kindHashExpr("sk")+`, `+kindHashExpr("uk")+`) AS up_hash,
		       COALESCE(sk.name, uk.name)               AS up_name,
		       COALESCE(sk.description, uk.description)  AS up_desc,
		       (sk.kind_id IS NOT NULL OR uk.user_kind_id IS NOT NULL) AS src_live
		FROM book_kinds bk
		LEFT JOIN system_kinds sk ON bk.source_ref = 'system:'||sk.kind_id::text
		LEFT JOIN user_kinds   uk ON bk.source_ref = 'user:'||uk.user_kind_id::text
		                          AND uk.deleted_at IS NULL AND uk.permanently_deleted_at IS NULL
		WHERE bk.book_id=$1 AND bk.deprecated_at IS NULL AND bk.source_ref IS NOT NULL
		  AND ( (sk.kind_id IS NULL AND uk.user_kind_id IS NULL)
		     OR COALESCE(`+kindHashExpr("sk")+`, `+kindHashExpr("uk")+`) IS DISTINCT FROM bk.source_hash )
		ORDER BY bk.code`, bookID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []syncUpdateItem{}
	for rows.Next() {
		var it syncUpdateItem
		var upHash, upName, upDesc *string
		var srcLive bool
		if err := rows.Scan(&it.ID, &it.Code, &it.SourceRef, &it.Mine.Name, &it.Mine.Description,
			&upHash, &upName, &upDesc, &srcLive); err != nil {
			return nil, err
		}
		it.Entity = "kind"
		if !srcLive {
			it.Status = syncStatusRetired
		} else {
			it.Status = syncStatusUpdate
			it.Theirs = &syncVals{Name: derefStr(upName), Description: upDesc}
		}
		out = append(out, it)
	}
	return out, rows.Err()
}

func (s *Server) syncAttributesAvailable(ctx context.Context, bookID uuid.UUID) ([]syncUpdateItem, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT ba.attr_id::text, ba.code, ba.source_ref,
		       ba.name, ba.description, ba.field_type, ba.is_required, ba.options,
		       COALESCE(sa.content_hash, ua.content_hash) AS up_hash,
		       COALESCE(sa.name, ua.name)                 AS up_name,
		       COALESCE(sa.description, ua.description)    AS up_desc,
		       COALESCE(sa.field_type, ua.field_type)     AS up_ftype,
		       COALESCE(sa.is_required, ua.is_required)   AS up_req,
		       COALESCE(sa.options, ua.options)           AS up_opts,
		       (sa.attr_id IS NOT NULL OR ua.attr_id IS NOT NULL) AS src_live
		FROM book_attributes ba
		LEFT JOIN system_attributes sa ON ba.source_ref = 'system:'||sa.attr_id::text
		LEFT JOIN user_attributes   ua ON ba.source_ref = 'user:'||ua.attr_id::text
		                               AND ua.deleted_at IS NULL
		WHERE ba.book_id=$1 AND ba.deprecated_at IS NULL AND ba.source_ref IS NOT NULL
		  AND ( (sa.attr_id IS NULL AND ua.attr_id IS NULL)
		     OR COALESCE(sa.content_hash, ua.content_hash) IS DISTINCT FROM ba.source_hash )
		ORDER BY ba.code`, bookID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []syncUpdateItem{}
	for rows.Next() {
		var it syncUpdateItem
		var upHash, upName, upDesc, upFtype *string
		var upReq *bool
		var upOpts []string
		var srcLive bool
		if err := rows.Scan(&it.ID, &it.Code, &it.SourceRef,
			&it.Mine.Name, &it.Mine.Description, &it.Mine.FieldType, &it.Mine.IsRequired, &it.Mine.Options,
			&upHash, &upName, &upDesc, &upFtype, &upReq, &upOpts, &srcLive); err != nil {
			return nil, err
		}
		it.Entity = "attribute"
		if it.Mine.Options == nil {
			it.Mine.Options = []string{}
		}
		if !srcLive {
			it.Status = syncStatusRetired
		} else {
			it.Status = syncStatusUpdate
			if upOpts == nil {
				upOpts = []string{}
			}
			it.Theirs = &syncVals{Name: derefStr(upName), Description: upDesc, FieldType: upFtype, IsRequired: upReq, Options: upOpts}
		}
		out = append(out, it)
	}
	return out, rows.Err()
}

// ── POST /v1/glossary/books/{book_id}/sync/apply ────────────────────────────────

type syncApplyItemReq struct {
	Entity string `json:"entity"`
	ID     string `json:"id"`
	Choice string `json:"choice"` // "keep_mine" | "take_theirs"
}

type syncApplyItemResult struct {
	Entity string `json:"entity"`
	ID     string `json:"id"`
	Result string `json:"result"` // "applied" | "source_retired" (source gone / not a sourced row of this book)
}

type syncApplyResp struct {
	Applied int                   `json:"applied"`
	Results []syncApplyItemResult `json:"results"`
}

func (s *Server) applyBookSync(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	// Reshapes the book's adopted ontology → Manage (same gate as adopt / book CRUD).
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantManage) {
		return
	}

	var in struct {
		Items []syncApplyItemReq `json:"items"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	if len(in.Items) == 0 {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "items is required")
		return
	}
	// Validate every item BEFORE mutating so a bad item rejects the whole batch (no
	// partial apply on malformed input).
	for _, it := range in.Items {
		if it.Entity != "genre" && it.Entity != "kind" && it.Entity != "attribute" {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid entity: "+it.Entity)
			return
		}
		if it.Choice != "keep_mine" && it.Choice != "take_theirs" {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid choice: "+it.Choice)
			return
		}
		if _, err := uuid.Parse(it.ID); err != nil {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid id: "+it.ID)
			return
		}
	}

	ctx := r.Context()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx failed")
		return
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	// Same per-book advisory lock as adopt: serialize apply against concurrent
	// adopt / +adopt-more so the multi-statement updates can't interleave.
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext('gloss-adopt:' || $1::text))`, bookID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "lock failed")
		return
	}

	resp := syncApplyResp{Results: []syncApplyItemResult{}}
	for _, it := range in.Items {
		id := uuid.MustParse(it.ID) // validated above
		take := it.Choice == "take_theirs"
		applied, err := s.applySyncRow(ctx, tx, bookID, it.Entity, id, take)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "apply failed")
			return
		}
		res := syncApplyItemResult{Entity: it.Entity, ID: it.ID, Result: syncStatusRetired}
		if applied {
			res.Result = "applied"
			resp.Applied++
		}
		resp.Results = append(resp.Results, res)
	}

	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

// applySyncRow refreshes one book row from its recorded source. It runs the system-
// and user-tier UPDATE variants; exactly one matches by source_ref prefix (the other
// affects 0 rows). Returns applied=false when neither matches — i.e. the source was
// retired (deleted/purged) or the id isn't a sourced book row of this book.
//
// take_theirs overwrites the SEMANTIC fields (the hash surface) + source_hash;
// keep_mine bumps source_hash only (accept divergence, silence the prompt). The table
// / column names are internal constants (no request data) — no SQL-injection surface.
func (s *Server) applySyncRow(ctx context.Context, tx pgx.Tx, bookID uuid.UUID, entity string, id uuid.UUID, take bool) (bool, error) {
	var sysSQL, usrSQL string
	switch entity {
	case "genre":
		setT := "name = src.name, "
		sysSQL = `UPDATE book_genres bg SET ` + ternarySet(take, setT) + `source_hash = src.content_hash, updated_at = now()
			FROM system_genres src
			WHERE bg.book_id=$1 AND bg.genre_id=$2 AND bg.source_ref = 'system:'||src.genre_id::text`
		usrSQL = `UPDATE book_genres bg SET ` + ternarySet(take, setT) + `source_hash = src.content_hash, updated_at = now()
			FROM user_genres src
			WHERE bg.book_id=$1 AND bg.genre_id=$2 AND bg.source_ref = 'user:'||src.genre_id::text
			  AND src.deleted_at IS NULL AND src.permanently_deleted_at IS NULL`
	case "kind":
		setT := "name = src.name, description = src.description, "
		hash := kindHashExpr("src")
		sysSQL = `UPDATE book_kinds bk SET ` + ternarySet(take, setT) + `source_hash = ` + hash + `, updated_at = now()
			FROM system_kinds src
			WHERE bk.book_id=$1 AND bk.book_kind_id=$2 AND bk.source_ref = 'system:'||src.kind_id::text`
		usrSQL = `UPDATE book_kinds bk SET ` + ternarySet(take, setT) + `source_hash = ` + hash + `, updated_at = now()
			FROM user_kinds src
			WHERE bk.book_id=$1 AND bk.book_kind_id=$2 AND bk.source_ref = 'user:'||src.user_kind_id::text
			  AND src.deleted_at IS NULL AND src.permanently_deleted_at IS NULL`
	case "attribute":
		setT := "name = src.name, description = src.description, field_type = src.field_type, " +
			"is_required = src.is_required, options = src.options, "
		sysSQL = `UPDATE book_attributes ba SET ` + ternarySet(take, setT) + `source_hash = src.content_hash, updated_at = now()
			FROM system_attributes src
			WHERE ba.book_id=$1 AND ba.attr_id=$2 AND ba.source_ref = 'system:'||src.attr_id::text`
		usrSQL = `UPDATE book_attributes ba SET ` + ternarySet(take, setT) + `source_hash = src.content_hash, updated_at = now()
			FROM user_attributes src
			WHERE ba.book_id=$1 AND ba.attr_id=$2 AND ba.source_ref = 'user:'||src.attr_id::text
			  AND src.deleted_at IS NULL`
	default:
		return false, fmt.Errorf("unknown sync entity %q", entity) // unreachable (validated)
	}

	tag, err := tx.Exec(ctx, sysSQL, bookID, id)
	if err != nil {
		return false, err
	}
	if tag.RowsAffected() > 0 {
		return true, nil
	}
	tag, err = tx.Exec(ctx, usrSQL, bookID, id)
	if err != nil {
		return false, err
	}
	return tag.RowsAffected() > 0, nil
}

// ternarySet returns the take_theirs semantic SET prefix, or "" for keep_mine.
func ternarySet(take bool, set string) string {
	if take {
		return set
	}
	return ""
}

func derefStr(p *string) string {
	if p == nil {
		return ""
	}
	return *p
}
