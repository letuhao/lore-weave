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
	lwmcp "github.com/loreweave/loreweave_mcp"
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

// resolveConfirmCaller returns the redeeming user's ID for a confirm/preview call,
// trusting EITHER:
//   - a valid Bearer JWT (the browser UI calling directly), or
//   - a trusted internal-service envelope: X-Internal-Token (constant-time compare
//     against the shared internal token) + X-User-Id (the owner uuid).
//
// The second path is how `auth-service`'s public-MCP confirm-replay (self-confirm
// AND human-approve, `mcp_approvals.go::replayConfirm`) calls this route — it is a
// trusted internal caller, never a browser, so it cannot present a user's Bearer JWT
// and instead carries the already-verified owner identity in a header. This mirrors
// the SAME dual-auth pattern composition/translation/knowledge-service's Python
// confirm routes already implement (`_resolve_envelope_user` / `_resolve_confirm_caller`
// / `_resolve_kg_confirm_caller`, decision tag D-PMCP-WORKER-CARRIER,
// docs/plans/2026-06-28-public-mcp-p4-wave-c.md §"domain confirm routes") — glossary
// (along with book-service and provider-registry-service's settings routes) was never
// retrofitted with it, so EVERY confirm-replay to this route 401'd unconditionally
// (found live 2026-07-08 via the MCP discoverability audit's confirm_action repro).
// The internal-token branch is checked FIRST and, if the token matches but X-User-Id
// is missing/malformed, this fails closed rather than falling through to the Bearer
// path (an internal caller that got the envelope wrong should not silently succeed
// via some unrelated Bearer header it happens to also be carrying).
func (s *Server) resolveConfirmCaller(r *http.Request) (uuid.UUID, bool) {
	return lwmcp.ResolveEnvelopeOrBearerCaller(r, s.cfg.InternalServiceToken, s.requireUserID)
}

// decodeConfirmToken reads the confirm token — from the `token` query param (the
// shape auth-service's internal confirm-replay sends, nil body) or the JSON body
// `{confirm_token, enabled_ops?}` (the shape the browser UI sends) — and verifies
// it; writes the 4xx itself on a missing/expired/invalid token and returns ok=false.
// enabled_ops is the per-op destructive opt-in for an execute_plan confirm (§4 G1);
// nil/absent for every other action (and ignored by the read-only preview path, and
// by definition absent on the query-param/replay path — a self-confirm/human-approve
// replay never carries execute_plan's per-op opt-ins today).
func (s *Server) decodeConfirmToken(w http.ResponseWriter, r *http.Request) (actionClaims, []string, bool) {
	token := strings.TrimSpace(r.URL.Query().Get("token"))
	var enabledOps []string
	if token == "" {
		var body struct {
			ConfirmToken string   `json:"confirm_token"`
			EnabledOps   []string `json:"enabled_ops"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil || strings.TrimSpace(body.ConfirmToken) == "" {
			writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "confirm_token is required")
			return actionClaims{}, nil, false
		}
		token = body.ConfirmToken
		enabledOps = body.EnabledOps
	}
	claims, err := verifyActionToken(s.cfg.JWTSecret, token, time.Now())
	if errors.Is(err, ErrActionTokenExpired) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "confirmation expired — propose again")
		return actionClaims{}, nil, false
	}
	if err != nil {
		// IN-6 (mcp-tool-io.md): a concrete, actionable reason instead of a bare
		// "invalid confirmation" — the specific cause (bad signature vs unknown
		// descriptor vs malformed payload) is intentionally NOT distinguished further
		// here (same anti-oracle posture as a forbidden-grant check: telling a caller
		// exactly WHICH structural check failed would help someone probing a forged
		// token). The fix pointer is always the same regardless of which sub-case hit.
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN",
			"invalid confirmation — the token is malformed, was tampered with, or was signed by a "+
				"different server/environment; propose the action again to get a fresh confirm_token")
		return actionClaims{}, nil, false
	}
	return claims, enabledOps, true
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
			writeError(w, http.StatusForbidden, "GLOSS_FORBIDDEN",
				"confirmation not valid for this user — this confirm_token was proposed by a "+
					"different account; only that account can redeem it. Propose the action again "+
					"from your own account to get your own confirm_token")
			return false
		}
		return s.requireGrant(w, r.Context(), claims.BookID, userID, grantclient.GrantManage)
	case authorityAdmin:
		writeError(w, http.StatusNotImplemented, "GLOSS_ADMIN_DISABLED",
			"system-tier admin actions are not enabled on the regular user confirm path — this token "+
				"requires a platform admin to apply it via the RS256-gated admin confirm route, not "+
				"this one")
		return false
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN",
			"unknown confirmation authority — this token looks corrupted or was minted by an "+
				"incompatible server version; propose the action again to get a fresh confirm_token")
		return false
	}
}

// confirmAction handles POST /v1/glossary/actions/confirm — the token-gated,
// single-use class-C write path. Order: verify token → re-check authority → claim
// jti (single-use) → re-validate + run the effect. Authority is checked BEFORE the
// jti is consumed so a stranger submitting a victim's token can't burn it.
func (s *Server) confirmAction(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.resolveConfirmCaller(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token or internal-service confirm envelope required")
		return
	}
	claims, enabledOps, ok := s.decodeConfirmToken(w, r)
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

	s.dispatchConfirmEffect(w, r.Context(), claims, enabledOps)
}

// dispatchConfirmEffect runs the effect for a verified, authorized, jti-claimed token,
// writing the effect's HTTP response to `w`. Extracted from confirmAction so the SAME
// per-descriptor effect handlers serve BOTH the single confirm (/actions/confirm) and
// the batch confirm (/actions/confirm-batch, #27/#29/#30): the batch path drives each
// child token through this dispatch via a per-child recorder — no effect is rewritten.
func (s *Server) dispatchConfirmEffect(w http.ResponseWriter, ctx context.Context, claims actionClaims, enabledOps []string) {
	switch claims.Descriptor {
	case descBookDelete:
		s.effectBookDelete(w, ctx, claims)
	case descBookDeleteBatch:
		s.effectBookDeleteBatch(w, ctx, claims)
	case descSchemaCreateKind:
		s.effectSchemaCreateKind(w, ctx, claims)
	case descSchemaCreateKinds:
		s.effectSchemaCreateKinds(w, ctx, claims)
	case descSchemaCreateAttr:
		s.effectSchemaCreateAttr(w, ctx, claims)
	case descAdopt:
		s.effectAdopt(w, ctx, claims)
	case descSyncApply:
		s.effectSyncApply(w, ctx, claims)
	case descBookRevert:
		s.effectBookRevert(w, ctx, claims)
	case descStatusChange:
		s.effectStatusChange(w, ctx, claims)
	case descRestoreRevision:
		s.effectRestoreRevision(w, ctx, claims)
	case descReassignKind:
		s.effectReassignKind(w, ctx, claims)
	case descMerge:
		s.effectMerge(w, ctx, claims)
	case descEntityDelete:
		s.effectEntityDelete(w, ctx, claims)
	case descDeepResearch:
		s.effectDeepResearch(w, ctx, claims)
	case descExecutePlan:
		s.effectExecutePlan(w, ctx, claims, enabledOps)
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "unknown action")
	}
}

// dispatchPreviewEffect renders the (non-consuming) current-state preview for a verified,
// authorized token. Extracted from previewAction for the same single+batch reuse reason.
func (s *Server) dispatchPreviewEffect(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	switch claims.Descriptor {
	case descBookDelete:
		s.previewBookDelete(w, ctx, claims)
	case descBookDeleteBatch:
		s.previewBookDeleteBatch(w, ctx, claims)
	case descSchemaCreateKind, descSchemaCreateAttr:
		s.previewSchemaCreate(w, claims)
	case descSchemaCreateKinds:
		s.previewSchemaCreateKinds(w, claims)
	case descAdopt:
		s.previewAdopt(w, ctx, claims)
	case descSyncApply:
		s.previewSyncApply(w, ctx, claims)
	case descBookRevert:
		s.previewBookRevert(w, ctx, claims)
	case descStatusChange:
		s.previewStatusChange(w, ctx, claims)
	case descRestoreRevision:
		s.previewRestoreRevision(w, ctx, claims)
	case descReassignKind:
		s.previewReassignKind(w, ctx, claims)
	case descMerge:
		s.previewMerge(w, ctx, claims)
	case descEntityDelete:
		s.previewEntityDelete(w, ctx, claims)
	case descDeepResearch:
		s.previewDeepResearch(w, ctx, claims)
	case descExecutePlan:
		s.previewExecutePlan(w, ctx, claims)
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

// ensureBookScaffolded guarantees the book has the baseline `universal` genre (and
// `unknown` kind) that custom kinds anchor to. Idempotent — a no-op once the book is
// scaffolded. This lets glossary_propose_new_kind "just work" without a MANDATORY
// prior glossary_adopt_standards: the universal genre is infrastructure, not a content
// choice (adopt ALWAYS seeds it regardless of picked genres), so a user/agent never
// has to know the adopt→kind ordering. Genre-specific standards (fantasy, …) can still
// be adopted later to import their seeded kinds.
func (s *Server) ensureBookScaffolded(ctx context.Context, bookID, userID uuid.UUID) error {
	var exists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM book_genres WHERE book_id=$1 AND code='universal' AND deprecated_at IS NULL)`,
		bookID).Scan(&exists); err != nil {
		return err
	}
	if exists {
		return nil
	}
	// nil genres/kinds → adoptBookOntologyCore still seeds the baseline `universal`
	// genre + `unknown` kind (it dedup-appends them), and is itself idempotent
	// (advisory lock + ON CONFLICT DO NOTHING).
	return s.adoptBookOntologyCore(ctx, bookID, userID, nil, nil)
}

func (s *Server) effectSchemaCreateKind(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p kindCreateParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	// Auto-scaffold the baseline ontology if the book hasn't been adopted yet, so
	// creating the first custom kind succeeds instead of 422'ing "not adopted" AFTER
	// the human already confirmed (and the single-use token burned). The agent no
	// longer has to sequence adopt→kind by hand.
	if err := s.ensureBookScaffolded(ctx, claims.BookID, claims.UserID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scaffold book ontology")
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

// kindsBatchParams is the captured intent of a glossary_propose_kinds proposal: the
// full list of kinds (each with its attributes) the user confirms in one click.
type kindsBatchParams struct {
	Kinds []kindCreateParams `json:"kinds"`
}

// effectSchemaCreateKinds creates every kind (+ its attributes) in the batch on one
// confirm. Idempotent: a kind whose code already exists is SKIPPED (unique-violation),
// so a re-confirm after a partial batch fills only the missing kinds instead of
// failing the whole package. Auto-scaffolds the baseline ontology once up front.
func (s *Server) effectSchemaCreateKinds(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p kindsBatchParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	if len(p.Kinds) == 0 {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "no kinds in this proposal — propose again")
		return
	}
	if err := s.ensureBookScaffolded(ctx, claims.BookID, claims.UserID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scaffold book ontology")
		return
	}
	created := make([]string, 0, len(p.Kinds))
	skipped := make([]string, 0)
	for _, kp := range p.Kinds {
		switch _, err := s.createKindFromParams(ctx, claims.BookID, kp); {
		case err == nil:
			created = append(created, kp.Code)
		case isUniqueViolation(err):
			skipped = append(skipped, kp.Code) // already exists — idempotent re-confirm
		default:
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to create kind "+kp.Code)
			return
		}
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"created":       created,
		"skipped":       skipped,
		"created_count": len(created),
		"skipped_count": len(skipped),
	})
}

func (s *Server) previewSchemaCreateKinds(w http.ResponseWriter, claims actionClaims) {
	var p kindsBatchParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	rows := make([]previewRow, 0, len(p.Kinds))
	for _, kp := range p.Kinds {
		rows = append(rows, previewRow{Label: "kind", Value: kp.Code, Note: fmt.Sprintf("%s · %d attribute(s)", kp.Name, len(kp.Attributes))})
	}
	writeJSON(w, http.StatusOK, actionPreview{
		Descriptor: descSchemaCreateKinds, Destructive: false,
		Title:       fmt.Sprintf("Create %d kind(s) with their attributes", len(p.Kinds)),
		PreviewRows: rows,
	})
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
	claims, _, ok := s.decodeConfirmToken(w, r)
	if !ok {
		return
	}
	if !s.authorizeAction(w, r, userID, claims) {
		return
	}
	s.dispatchPreviewEffect(w, r.Context(), claims)
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
		Descriptor: descAdopt, Title: "Set up your book's world", Destructive: false,
		PreviewRows: []previewRow{
			{Label: "Story genres to add", Value: fmt.Sprint(newGenres), Note: "plus the always-on baseline"},
			{Label: "Lore categories to add", Value: fmt.Sprint(newKinds), Note: "plus the always-on baseline"},
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
		// F3b — list the defining attributes created atomically with the kind.
		if len(p.Attributes) > 0 {
			title = fmt.Sprintf("Create kind %q + %d attribute(s)", p.Name, len(p.Attributes))
			for _, a := range p.Attributes {
				ft := a.FieldType
				if ft == "" {
					ft = "text"
				}
				rows = append(rows, previewRow{Label: "+ attribute", Value: a.Code, Note: ft})
			}
		}
	case descSchemaCreateAttr:
		var p attrCreateParams
		_ = json.Unmarshal(claims.Params, &p)
		title = fmt.Sprintf("Add attribute %q", p.Name)
		rows = []previewRow{{Label: "code", Value: p.Code}, {Label: "name", Value: p.Name}, {Label: "field type", Value: p.FieldType}}
	}
	writeJSON(w, http.StatusOK, actionPreview{Descriptor: claims.Descriptor, Title: title, PreviewRows: rows, Destructive: false})
}
