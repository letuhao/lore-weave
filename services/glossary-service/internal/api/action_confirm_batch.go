package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

// Coalesced confirm/preview (#27 / #29 / #30). A weak local model loops single-propose
// tools instead of one batch, minting N confirm_tokens — and the old N-card UX orphaned
// every card after the first (one resume deleted the shared run). The chat run-loop now
// bundles those N tokens into ONE human card; on Apply/Preview the FE posts every child
// token here. The batch path reuses the EXACT per-descriptor effects of /actions/confirm
// (via dispatchConfirmEffect over a per-child recorder) so no effect is rewritten and the
// human gate, single-use ledger, ownership, and re-validation all hold per child.

// maxBatchChildren bounds the work one coalesced card can trigger — far above any real
// turn (the run-loop caps writes well below this), so a legitimate batch never trips it;
// it only stops a pathological/abusive token list.
const maxBatchChildren = 50

type batchChildOutcome struct {
	Descriptor string `json:"descriptor"`
	Outcome    string `json:"outcome"` // applied | skipped | failed
	Status     int    `json:"status"`
	Detail     string `json:"detail,omitempty"`
}

type batchConfirmResult struct {
	Applied  int                 `json:"applied"`
	Skipped  int                 `json:"skipped"`
	Failed   int                 `json:"failed"`
	Children []batchChildOutcome `json:"children"`
}

// decodeBatchChildren reads {child_tokens, enabled_ops?}, then VERIFIES + AUTHORIZES every
// child BEFORE any token is consumed or any effect runs (fail-closed: a bad/foreign/expired
// child rejects the whole batch, so the human never half-applies a coherent bundle). Returns
// the verified claims in request order. All children must be grant-authority, proposed by the
// caller, and share ONE book (the suspended run is bound to one book); the Manage grant is
// checked once for that book. Writes the 4xx itself and returns ok=false on any violation.
func (s *Server) decodeBatchChildren(w http.ResponseWriter, r *http.Request, userID uuid.UUID) ([]actionClaims, []string, bool) {
	var body struct {
		ChildTokens []string `json:"child_tokens"`
		EnabledOps  []string `json:"enabled_ops"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || len(body.ChildTokens) == 0 {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "child_tokens is required")
		return nil, nil, false
	}
	if len(body.ChildTokens) > maxBatchChildren {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_VALIDATION", "too many actions in one batch — split them")
		return nil, nil, false
	}
	now := time.Now()
	claimsList := make([]actionClaims, 0, len(body.ChildTokens))
	var bookID uuid.UUID
	for i, tok := range body.ChildTokens {
		claims, err := verifyActionToken(s.cfg.JWTSecret, strings.TrimSpace(tok), now)
		if errors.Is(err, ErrActionTokenExpired) {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "a confirmation in this batch expired — propose again")
			return nil, nil, false
		}
		if err != nil {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "an invalid confirmation in this batch")
			return nil, nil, false
		}
		// Only grant-authority actions are coalesced here — admin (authorityAdmin) keeps its
		// own RS256 /actions/admin/confirm path and must never ride a user-JWT batch.
		if claims.Authority != authorityGrant {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "this batch contains a non-grant action")
			return nil, nil, false
		}
		// Proposer-bound: a different signed-in user cannot redeem any child even with the
		// string (checked before consuming so a stranger can't burn the tokens).
		if claims.UserID != userID {
			writeError(w, http.StatusForbidden, "GLOSS_FORBIDDEN", "a confirmation in this batch is not valid for this user")
			return nil, nil, false
		}
		if i == 0 {
			bookID = claims.BookID
		} else if claims.BookID != bookID {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "this batch mixes books — confirm them per book")
			return nil, nil, false
		}
		claimsList = append(claimsList, claims)
	}
	// One Manage-grant re-check for the shared book (C3 defense-in-depth) — every child is
	// already proposer-bound + book-scoped to this same book.
	if err := s.checkGrant(r.Context(), bookID, userID, grantclient.GrantManage); err != nil {
		writeError(w, http.StatusForbidden, "GLOSS_FORBIDDEN", "manage grant required for this book")
		return nil, nil, false
	}
	return claimsList, body.EnabledOps, true
}

// confirmActionBatch handles POST /v1/glossary/actions/confirm-batch — the coalesced,
// single-use, human-confirmed write path for a bundle of child tokens. Order mirrors the
// single confirm (verify → authorize → claim → effect) but per child, AFTER all children
// passed verify+authorize. A replayed child (jti already in the ledger) SKIPS — never
// double-applies (idempotent re-confirm); a child whose effect fails is reported `failed`
// (its single-use token is burned, re-proposable) without aborting the rest. The 200 body
// carries per-child outcomes so a partial batch is honest, never a silent all-or-nothing.
func (s *Server) confirmActionBatch(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	claimsList, enabledOps, ok := s.decodeBatchChildren(w, r, userID)
	if !ok {
		return
	}
	result := batchConfirmResult{Children: make([]batchChildOutcome, 0, len(claimsList))}
	for _, claims := range claimsList {
		oc := batchChildOutcome{Descriptor: claims.Descriptor}
		// Single-use: claim each child jti in the SAME consumed_tokens ledger. Fail-closed —
		// a failed effect below does NOT release it; the human re-proposes that child.
		claimed, err := s.consumeToken(r.Context(), claims.JTI, claims.Descriptor, time.Unix(claims.Exp, 0))
		if err != nil {
			oc.Outcome, oc.Status, oc.Detail = "failed", http.StatusInternalServerError, "claim failed"
			result.Failed++
			result.Children = append(result.Children, oc)
			continue
		}
		if !claimed {
			// Replay (already confirmed in a prior batch/single) → skip, never double-apply.
			oc.Outcome, oc.Status, oc.Detail = "skipped", http.StatusOK, "already confirmed"
			result.Skipped++
			result.Children = append(result.Children, oc)
			continue
		}
		// Run the SAME per-descriptor effect as /actions/confirm; capture its HTTP outcome.
		rec := httptest.NewRecorder()
		s.dispatchConfirmEffect(rec, r.Context(), claims, enabledOps)
		if rec.Code >= 200 && rec.Code < 300 {
			oc.Outcome, oc.Status = "applied", rec.Code
			result.Applied++
		} else {
			oc.Outcome, oc.Status, oc.Detail = "failed", rec.Code, batchErrDetail(rec.Body.Bytes())
			result.Failed++
		}
		result.Children = append(result.Children, oc)
	}
	writeJSON(w, http.StatusOK, result)
}

// batchPreviewResult aggregates each child's current-state preview into ONE card the human
// reviews before applying the whole bundle. preview_rows concatenates the children's rows in
// order (each effect already labels its own rows); `destructive` is true if ANY child is.
type batchPreviewResult struct {
	Descriptor  string       `json:"descriptor"`
	Title       string       `json:"title"`
	PreviewRows []previewRow `json:"preview_rows"`
	Destructive bool         `json:"destructive"`
	Children    int          `json:"children"`
}

// previewActionBatch handles POST /v1/glossary/actions/preview-batch — JWT-gated, read-only,
// NEVER consumes a token. Re-renders every child's preview from CURRENT state (§5.1 #5) and
// concatenates them, so the human confirms against what is true now for the whole bundle.
func (s *Server) previewActionBatch(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	claimsList, _, ok := s.decodeBatchChildren(w, r, userID)
	if !ok {
		return
	}
	out := batchPreviewResult{
		Descriptor: descBatch, PreviewRows: make([]previewRow, 0, len(claimsList)), Children: len(claimsList),
	}
	for _, claims := range claimsList {
		rec := httptest.NewRecorder()
		s.dispatchPreviewEffect(rec, r.Context(), claims)
		// A child whose preview failed (e.g. a vanished target) still gets a row, so the human
		// sees the gap rather than a silently-shorter card.
		if rec.Code < 200 || rec.Code >= 300 {
			out.PreviewRows = append(out.PreviewRows, previewRow{
				Label: claims.Descriptor, Value: "unavailable", Note: batchErrDetail(rec.Body.Bytes()),
			})
			continue
		}
		var p actionPreview
		if err := json.Unmarshal(rec.Body.Bytes(), &p); err != nil {
			continue
		}
		if p.Destructive {
			out.Destructive = true
		}
		// Lead each child's rows with its title so a multi-action card stays readable.
		out.PreviewRows = append(out.PreviewRows, previewRow{Label: "action", Value: p.Title, Note: p.Descriptor})
		out.PreviewRows = append(out.PreviewRows, p.PreviewRows...)
	}
	out.Title = batchTitle(len(claimsList), out.Destructive)
	writeJSON(w, http.StatusOK, out)
}

// batchErrDetail pulls a short, human-safe message out of a child effect's error body
// (the {error:{message}} envelope writeError emits); falls back to the raw trimmed body.
func batchErrDetail(body []byte) string {
	var env struct {
		Error struct {
			Message string `json:"message"`
		} `json:"error"`
	}
	if err := json.Unmarshal(body, &env); err == nil && env.Error.Message != "" {
		return env.Error.Message
	}
	return strings.TrimSpace(string(body))
}

func batchTitle(n int, destructive bool) string {
	noun := "action"
	if n != 1 {
		noun = "actions"
	}
	if destructive {
		return "Review " + strconv.Itoa(n) + " " + noun + " (some are destructive)"
	}
	return "Apply " + strconv.Itoa(n) + " " + noun + " in one step"
}
