package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

// Generalized class-C confirm + preview endpoints (spec §13.5). One JWT-gated
// confirm path serves every high-impact glossary action via an action descriptor;
// a separate non-consuming preview path re-renders the human-facing card from
// CURRENT state at confirm-render time (§5.1 #5). Both are reachable only with the
// user's browser JWT — the MCP/mint path can never call them (the un-bypassability
// argument carried over from the schema-confirm design).

// bookDeleteParams is the captured intent for a book_delete action. Code-addressed
// (§6.8): genre/kind by their book-local code; attribute by (kind_code, genre_code,
// code) since attribute codes are unique only within (kind × genre).
type bookDeleteParams struct {
	Level     string `json:"level"`      // genre | kind | attribute
	Code      string `json:"code"`       // genre/kind code, or the attribute's own code
	KindCode  string `json:"kind_code"`  // attribute level only
	GenreCode string `json:"genre_code"` // attribute level only
}

const (
	deleteLevelGenre = "genre"
	deleteLevelKind  = "kind"
	deleteLevelAttr  = "attribute"
)

// adoptParams is the captured intent for an adopt action (copy-down from standards).
type adoptParams struct {
	Genres []string `json:"genres"`
	Kinds  []string `json:"kinds"`
}

// consumeToken records a jti in the consumed_tokens ledger, enforcing single-use
// (§13.4). Returns claimed=true the FIRST time a jti is seen; a replay hits the PK
// and ON CONFLICT DO NOTHING → 0 rows → claimed=false (reject as replay).
func (s *Server) consumeToken(ctx context.Context, jti, descriptor string, exp time.Time) (bool, error) {
	tag, err := s.pool.Exec(ctx,
		`INSERT INTO consumed_tokens (jti, descriptor, exp) VALUES ($1, $2, $3)
		 ON CONFLICT (jti) DO NOTHING`, jti, descriptor, exp)
	if err != nil {
		return false, err
	}
	return tag.RowsAffected() > 0, nil
}

// decodeConfirmToken reads {confirm_token} and verifies it; writes the 4xx itself
// on a missing/expired/invalid token and returns ok=false.
func (s *Server) decodeConfirmToken(w http.ResponseWriter, r *http.Request) (actionClaims, bool) {
	var body struct {
		ConfirmToken string `json:"confirm_token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || strings.TrimSpace(body.ConfirmToken) == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "confirm_token is required")
		return actionClaims{}, false
	}
	claims, err := verifyActionToken(s.cfg.JWTSecret, body.ConfirmToken, time.Now())
	if errors.Is(err, ErrActionTokenExpired) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "confirmation expired — propose again")
		return actionClaims{}, false
	}
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "invalid confirmation")
		return actionClaims{}, false
	}
	return claims, true
}

// authorizeAction re-checks authority at confirm/preview time (C3 + defense in
// depth). For grant actions: the redeemer must be the proposing user AND still hold
// the Manage grant. The admin branch is structured but not wired in Foundation
// (returns a clean 501 — T4 enables it). Writes the error itself; ok=false → stop.
func (s *Server) authorizeAction(w http.ResponseWriter, r *http.Request, userID uuid.UUID, claims actionClaims) bool {
	switch claims.Authority {
	case authorityGrant:
		// Bound to the proposer — a different signed-in user cannot redeem it even
		// with the string. Checked BEFORE consuming so a stranger can't burn it.
		if claims.UserID != userID {
			writeError(w, http.StatusForbidden, "GLOSS_FORBIDDEN", "confirmation not valid for this user")
			return false
		}
		return s.requireGrant(w, r.Context(), claims.BookID, userID, grantclient.GrantManage)
	case authorityAdmin:
		writeError(w, http.StatusNotImplemented, "GLOSS_ADMIN_DISABLED", "admin actions are not enabled yet")
		return false
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "unknown authority")
		return false
	}
}

// confirmAction handles POST /v1/glossary/actions/confirm — the token-gated,
// single-use class-C write path. Order: verify token → re-check authority → claim
// jti (single-use) → re-validate + run the effect. Authority is checked BEFORE the
// jti is consumed so a stranger submitting a victim's token can't burn it.
func (s *Server) confirmAction(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	claims, ok := s.decodeConfirmToken(w, r)
	if !ok {
		return
	}
	if !s.authorizeAction(w, r, userID, claims) {
		return
	}
	// Single-use: claim the jti now. Fail-closed — once claimed, a failed effect
	// does NOT release it; the human re-proposes (§13.4).
	claimed, err := s.consumeToken(r.Context(), claims.JTI, claims.Descriptor, time.Unix(claims.Exp, 0))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "confirmation failed")
		return
	}
	if !claimed {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "already confirmed — propose again")
		return
	}

	switch claims.Descriptor {
	case descBookDelete:
		s.effectBookDelete(w, r.Context(), claims)
	case descSchemaCreateKind:
		s.effectSchemaCreateKind(w, r.Context(), claims)
	case descSchemaCreateAttr:
		s.effectSchemaCreateAttr(w, r.Context(), claims)
	case descAdopt:
		s.effectAdopt(w, r.Context(), claims)
	case descSyncApply:
		s.effectSyncApply(w, r.Context(), claims)
	case descBookRevert:
		s.effectBookRevert(w, r.Context(), claims)
	case descStatusChange:
		s.effectStatusChange(w, r.Context(), claims)
	case descRestoreRevision:
		s.effectRestoreRevision(w, r.Context(), claims)
	case descReassignKind:
		s.effectReassignKind(w, r.Context(), claims)
	case descMerge:
		s.effectMerge(w, r.Context(), claims)
	case descDeepResearch:
		s.effectDeepResearch(w, r.Context(), claims)
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "unknown action")
	}
}

// syncApplyParams is the captured intent for a sync_apply action: the per-row choice
// set the LLM proposed and the human confirmed (§12.4). Each item is re-validated
// against current source state at confirm time inside applyBookSyncCore.
type syncApplyParams struct {
	Items []syncApplyItemReq `json:"items"`
}

func (s *Server) effectSyncApply(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p syncApplyParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	// userID = the proposer (== redeemer, enforced in authorizeAction). The user-tier
	// source scoping inside applySyncRow keys off it, so a grantee can only pull their
	// own private user-tier values (D-GKA-SYNC-USER-SOURCE-VISIBILITY).
	resp, err := s.applyBookSyncCore(ctx, claims.BookID, claims.UserID, p.Items)
	if errors.Is(err, errSyncInvalidItem) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the proposed items are no longer valid — propose again")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "sync apply failed")
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (s *Server) effectAdopt(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p adoptParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	// userID = the proposer (already confirmed == the redeemer in authorizeAction).
	if err := s.adoptBookOntologyCore(ctx, claims.BookID, claims.UserID, p.Genres, p.Kinds); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "adopt failed")
		return
	}
	ont, err := s.loadBookOntology(ctx, claims.BookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load ontology failed")
		return
	}
	writeJSON(w, http.StatusOK, ont)
}

// ── effects (each re-validates against CURRENT state, §13.5 #4) ───────────────

func (s *Server) effectBookDelete(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p bookDeleteParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	targetID, err := s.resolveDeleteTarget(ctx, claims.BookID, p)
	if isNoRows(err) {
		// The target was edited/deleted between propose and confirm — re-proposable.
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the target no longer exists — propose again")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	var found bool
	switch p.Level {
	case deleteLevelGenre:
		found, err = s.cascadeDeleteBookGenre(ctx, claims.BookID, targetID)
	case deleteLevelKind:
		found, err = s.cascadeDeleteBookKind(ctx, claims.BookID, targetID)
	case deleteLevelAttr:
		found, err = s.softDeleteBookAttribute(ctx, claims.BookID, targetID)
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "unknown delete level")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if !found {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the target no longer exists — propose again")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) effectSchemaCreateKind(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p kindCreateParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	k, err := s.createKindFromParams(ctx, claims.BookID, p)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "kind code already exists")
			return
		}
		if errors.Is(err, errNotAdopted) {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the book ontology must be adopted before adding kinds")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to create kind")
		return
	}
	writeJSON(w, http.StatusCreated, k)
}

func (s *Server) effectSchemaCreateAttr(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p attrCreateParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	a, err := s.createAttrDefFromParams(ctx, claims.BookID, p)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "attribute code already exists for this kind")
			return
		}
		if isForeignKeyViolation(err) || errors.Is(err, errNotAdopted) {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the target kind no longer exists — propose again")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to create attribute")
		return
	}
	writeJSON(w, http.StatusCreated, a)
}

// resolveDeleteTarget maps a book_delete's code-addressed params to the live row id.
func (s *Server) resolveDeleteTarget(ctx context.Context, bookID uuid.UUID, p bookDeleteParams) (uuid.UUID, error) {
	switch p.Level {
	case deleteLevelGenre:
		return s.resolveBookGenreID(ctx, bookID, p.Code)
	case deleteLevelKind:
		return s.resolveBookKindID(ctx, bookID, p.Code)
	case deleteLevelAttr:
		return s.resolveBookAttrID(ctx, bookID, p.KindCode, p.GenreCode, p.Code)
	default:
		return uuid.Nil, fmt.Errorf("unknown delete level %q", p.Level)
	}
}

// ── preview (non-consuming; current-state render of the confirm card) ─────────

type actionPreview struct {
	Descriptor  string       `json:"descriptor"`
	Title       string       `json:"title"`
	PreviewRows []previewRow `json:"preview_rows"`
	Destructive bool         `json:"destructive"`
}

// previewAction handles POST /v1/glossary/actions/preview — JWT-gated, read-only,
// NEVER consumes the token. Re-renders the confirm card's preview from CURRENT
// state so the human confirms against what is true now, not at mint time (§5.1 #5).
func (s *Server) previewAction(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	claims, ok := s.decodeConfirmToken(w, r)
	if !ok {
		return
	}
	if !s.authorizeAction(w, r, userID, claims) {
		return
	}
	switch claims.Descriptor {
	case descBookDelete:
		s.previewBookDelete(w, r.Context(), claims)
	case descSchemaCreateKind, descSchemaCreateAttr:
		s.previewSchemaCreate(w, claims)
	case descAdopt:
		s.previewAdopt(w, r.Context(), claims)
	case descSyncApply:
		s.previewSyncApply(w, r.Context(), claims)
	case descBookRevert:
		s.previewBookRevert(w, r.Context(), claims)
	case descStatusChange:
		s.previewStatusChange(w, r.Context(), claims)
	case descRestoreRevision:
		s.previewRestoreRevision(w, r.Context(), claims)
	case descReassignKind:
		s.previewReassignKind(w, r.Context(), claims)
	case descMerge:
		s.previewMerge(w, r.Context(), claims)
	case descDeepResearch:
		s.previewDeepResearch(w, r.Context(), claims)
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "unknown action")
	}
}

// previewSyncApply re-renders the sync confirm card from CURRENT state (§5.1 #5):
// it re-runs the live diff and reports, of the proposed rows, how many will still
// take_theirs / keep_mine and how many the source has retired since the proposal.
func (s *Server) previewSyncApply(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p syncApplyParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	// Bucket each proposed row by whether its source is CURRENTLY live — matching what
	// applySyncRow will actually do (a live row applies, take or keep; a row whose
	// source retired since the proposal is skipped as source_retired).
	live, err := s.bookSyncSourceLiveByID(ctx, claims.BookID, claims.UserID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "preview failed")
		return
	}
	var takeN, keepN, retiredN int
	for _, it := range p.Items {
		if !live[it.ID] {
			retiredN++ // source retired/removed (or no longer a sourced row of this book)
			continue
		}
		if it.Choice == "take_theirs" {
			takeN++
		} else {
			keepN++
		}
	}
	writeJSON(w, http.StatusOK, actionPreview{
		Descriptor: descSyncApply, Title: "Apply standard updates to this book", Destructive: true,
		PreviewRows: []previewRow{
			{Label: "rows updated from source", Value: fmt.Sprint(takeN), Note: "take_theirs"},
			{Label: "rows kept as-is", Value: fmt.Sprint(keepN), Note: "keep_mine (accept divergence)"},
			{Label: "no longer available", Value: fmt.Sprint(retiredN), Note: "source retired / already current since proposed"},
		},
	})
}

// previewAdopt enumerates, from CURRENT state, how many picked standards are new vs
// already present (adopt is idempotent copy-down, §12.7).
func (s *Server) previewAdopt(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p adoptParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	newGenres, newKinds, err := s.adoptCounts(ctx, claims.BookID, p.Genres, p.Kinds)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "preview failed")
		return
	}
	writeJSON(w, http.StatusOK, actionPreview{
		Descriptor: descAdopt, Title: "Adopt standards into this book", Destructive: false,
		PreviewRows: []previewRow{
			{Label: "genres newly adopted", Value: fmt.Sprint(newGenres), Note: "+ universal (always)"},
			{Label: "kinds newly adopted", Value: fmt.Sprint(newKinds), Note: "+ unknown (always)"},
		},
	})
}

func (s *Server) previewBookDelete(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p bookDeleteParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	out := actionPreview{Descriptor: descBookDelete, Destructive: true,
		Title: fmt.Sprintf("Delete %s %q", p.Level, p.Code)}
	targetID, err := s.resolveDeleteTarget(ctx, claims.BookID, p)
	if isNoRows(err) {
		out.PreviewRows = []previewRow{{Label: "status", Value: "already removed", Note: "nothing to delete — this target no longer exists"}}
		writeJSON(w, http.StatusOK, out)
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "preview failed")
		return
	}
	rows, err := s.bookDeleteCascadeRows(ctx, claims.BookID, p.Level, targetID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "preview failed")
		return
	}
	out.PreviewRows = rows
	writeJSON(w, http.StatusOK, out)
}

// effectBookRevert re-pulls a book row's parent values (G-U1). Re-resolves the target by
// code at confirm time; a vanished target or a now-retired/deprecated source is
// re-proposable (422). On success returns the refreshed row.
func (s *Server) effectBookRevert(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p bookDeleteParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	targetID, err := s.resolveDeleteTarget(ctx, claims.BookID, p)
	if isNoRows(err) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the target no longer exists — propose again")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "revert failed")
		return
	}
	reverted, err := s.revertBookRow(ctx, claims.BookID, claims.UserID, p.Level, targetID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "revert failed")
		return
	}
	if !reverted {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN",
			"the parent standard is no longer available — propose again")
		return
	}
	var detail any
	switch p.Level {
	case deleteLevelGenre:
		detail, err = s.loadBookGenreOne(ctx, claims.BookID, targetID)
	case deleteLevelKind:
		detail, err = s.loadBookKindOne(ctx, claims.BookID, targetID)
	case deleteLevelAttr:
		detail, err = s.loadBookAttrOne(ctx, claims.BookID, targetID)
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "unknown revert level")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

// previewBookRevert re-renders the revert confirm card from CURRENT state: the parent tier
// the row reverts to, or a "book-native / nothing to revert" note.
func (s *Server) previewBookRevert(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p bookDeleteParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	out := actionPreview{Descriptor: descBookRevert, Destructive: false,
		Title: fmt.Sprintf("Revert %s %q to default", p.Level, p.Code)}
	targetID, err := s.resolveDeleteTarget(ctx, claims.BookID, p)
	if isNoRows(err) {
		out.PreviewRows = []previewRow{{Label: "status", Value: "already removed", Note: "this target no longer exists"}}
		writeJSON(w, http.StatusOK, out)
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "preview failed")
		return
	}
	ref, err := s.bookRowSourceRef(ctx, claims.BookID, p.Level, targetID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "preview failed")
		return
	}
	if ref == "" {
		out.PreviewRows = []previewRow{{Label: "status", Value: "book-native", Note: "no parent standard to revert to"}}
		writeJSON(w, http.StatusOK, out)
		return
	}
	out.PreviewRows = []previewRow{
		{Label: "reverts to", Value: tierLabel(ref) + " default", Note: "discards this book's local edits to this row"},
	}
	writeJSON(w, http.StatusOK, out)
}

// bookDeleteCascadeRows enumerates the blast radius the soft-delete cascade will
// deprecate/remove, from current state (§11 #10).
func (s *Server) bookDeleteCascadeRows(ctx context.Context, bookID uuid.UUID, level string, targetID uuid.UUID) ([]previewRow, error) {
	count := func(q string, args ...any) (int, error) {
		var n int
		err := s.pool.QueryRow(ctx, q, args...).Scan(&n)
		return n, err
	}
	switch level {
	case deleteLevelGenre:
		attrs, err := count(`SELECT count(*) FROM book_attributes WHERE book_id=$1 AND genre_id=$2 AND deprecated_at IS NULL`, bookID, targetID)
		if err != nil {
			return nil, err
		}
		links, err := count(`SELECT count(*) FROM book_kind_genres WHERE book_id=$1 AND genre_id=$2`, bookID, targetID)
		if err != nil {
			return nil, err
		}
		active, err := count(`SELECT count(*) FROM book_active_genres WHERE book_id=$1 AND genre_id=$2`, bookID, targetID)
		if err != nil {
			return nil, err
		}
		eg, err := count(`SELECT count(*) FROM entity_genres WHERE genre_id=$1`, targetID)
		if err != nil {
			return nil, err
		}
		return []previewRow{
			{Label: "attributes deprecated", Value: fmt.Sprint(attrs)},
			{Label: "kind links removed", Value: fmt.Sprint(links)},
			{Label: "active-genre rows removed", Value: fmt.Sprint(active)},
			{Label: "entity genre overrides removed", Value: fmt.Sprint(eg)},
		}, nil
	case deleteLevelKind:
		attrs, err := count(`SELECT count(*) FROM book_attributes WHERE book_id=$1 AND kind_id=$2 AND deprecated_at IS NULL`, bookID, targetID)
		if err != nil {
			return nil, err
		}
		links, err := count(`SELECT count(*) FROM book_kind_genres WHERE book_id=$1 AND kind_id=$2`, bookID, targetID)
		if err != nil {
			return nil, err
		}
		return []previewRow{
			{Label: "attributes deprecated", Value: fmt.Sprint(attrs)},
			{Label: "genre links removed", Value: fmt.Sprint(links)},
		}, nil
	case deleteLevelAttr:
		return []previewRow{{Label: "attribute removed", Value: "1", Note: "no cascade"}}, nil
	default:
		return nil, fmt.Errorf("unknown delete level %q", level)
	}
}

func (s *Server) previewSchemaCreate(w http.ResponseWriter, claims actionClaims) {
	rows := []previewRow{}
	title := "Create schema"
	switch claims.Descriptor {
	case descSchemaCreateKind:
		var p kindCreateParams
		_ = json.Unmarshal(claims.Params, &p)
		title = fmt.Sprintf("Create kind %q", p.Name)
		rows = []previewRow{{Label: "code", Value: p.Code}, {Label: "name", Value: p.Name}}
	case descSchemaCreateAttr:
		var p attrCreateParams
		_ = json.Unmarshal(claims.Params, &p)
		title = fmt.Sprintf("Add attribute %q", p.Name)
		rows = []previewRow{{Label: "code", Value: p.Code}, {Label: "name", Value: p.Name}, {Label: "field type", Value: p.FieldType}}
	}
	writeJSON(w, http.StatusOK, actionPreview{Descriptor: claims.Descriptor, Title: title, PreviewRows: rows, Destructive: false})
}
